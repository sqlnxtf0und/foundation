"""Keyed API integrations: key store, rate limiting, response cache, and a
relay transport so a hosted server can hold the keys instead of the client.

Two transport modes:

  direct  the machine has its own keys in .env (or the shell environment)
  relay   the machine has a relay URL + user token; upstream keys stay on the
          relay host and never reach this process

Mode is chosen per call: relay is used when NF_RELAY_URL and NF_RELAY_TOKEN
are set, otherwise the direct path runs. A missing key or relay never raises;
the lookup is simply skipped and the caller falls back to its free endpoint.
"""

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, ".env")
CACHE_ROOT = os.path.join(BASE, "reports", ".cache")


# --------------------------------------------------------------------------
# service registry — single source of truth for client and relay
# --------------------------------------------------------------------------

SPECS = {
    "virustotal": {
        "label": "VirusTotal",
        "base": "www.virustotal.com",
        "prefix": "/api/v3/",
        "env": ("VT_API_KEY",),
        "ttl": 3600,
        "interval": 15.0,
        "limit": (4, 4 / 60),
        "hint": "free tier allows 4 requests/min",
        "auth": lambda k: {"x-apikey": k.get("VT_API_KEY", "")},
    },
    "urlscan": {
        "label": "urlscan.io",
        "base": "urlscan.io",
        "prefix": "/api/v1/",
        "env": ("URLSCAN_API_KEY",),
        "ttl": 900,
        "interval": 2.0,
        "limit": (60, 1.0),
        "hint": "free tier is rate limited",
        "auth": lambda k: {"api-key": k.get("URLSCAN_API_KEY", "")},
    },
    "censys": {
        "label": "Censys",
        "base": "search.censys.io",
        "prefix": "/api/v2/",
        "env": ("CENSYS_API_ID", "CENSYS_API_SECRET"),
        "ttl": 3600,
        "interval": 1.2,
        "limit": (8, 8 / 60),
        "hint": "free tier allows 250 queries/month",
        "auth": lambda k: {"Authorization": "Basic " + base64.b64encode(
            f"{k.get('CENSYS_API_ID', '')}:{k.get('CENSYS_API_SECRET', '')}"
            .encode()).decode()},
    },
    "ipinfo": {
        "label": "IPinfo",
        "base": "ipinfo.io",
        "prefix": "/",
        "env": ("IPINFO_TOKEN",),
        "ttl": 86400,
        "interval": 0.05,
        "limit": (60, 1.0),
        "hint": "50k lookups/month",
        "auth": lambda k: {"Authorization": f"Bearer {k.get('IPINFO_TOKEN', '')}"},
    },
    "abuseipdb": {
        "label": "AbuseIPDB",
        "base": "api.abuseipdb.com",
        "prefix": "/api/v2/",
        "env": ("ABUSEIPDB_API_KEY",),
        "ttl": 3600,
        "interval": 0.9,
        "limit": (60, 1.0),
        "hint": "1000 checks/day",
        "auth": lambda k: {"Key": k.get("ABUSEIPDB_API_KEY", ""),
                           "Accept": "application/json"},
    },
    "otx": {
        "label": "AlienVault OTX",
        "base": "otx.alienvault.com",
        "prefix": "/api/v1/",
        "env": ("OTX_API_KEY",),
        "ttl": 3600,
        "interval": 0.5,
        "limit": (60, 1.0),
        "hint": "free",
        "auth": lambda k: {"X-OTX-API-KEY": k.get("OTX_API_KEY", "")},
    },
    "greynoise": {
        "label": "GreyNoise",
        "base": "api.greynoise.io",
        "prefix": "/v3/",
        "env": ("GREYNOISE_API_KEY",),
        "ttl": 3600,
        "interval": 1.0,
        "limit": (60, 1.0),
        "hint": "community API",
        "auth": lambda k: {"key": k.get("GREYNOISE_API_KEY", "")},
    },
    "shodan": {
        "label": "Shodan",
        "base": "api.shodan.io",
        "prefix": "/shodan/",
        "env": ("SHODAN_API_KEY",),
        "ttl": 3600,
        "interval": 1.0,
        "limit": (60, 1.0),
        "hint": "paid plan — key goes in the query string",
        "auth": lambda k: {},
        "qauth": lambda k: {"key": k.get("SHODAN_API_KEY", "")},
    },
    "hibp": {
        "label": "Have I Been Pwned",
        "base": "haveibeenpwned.com",
        "prefix": "/api/v3/",
        "env": ("HIBP_API_KEY",),
        "ttl": 3600,
        "interval": 1.6,
        "limit": (60, 1.0),
        "hint": "breach search needs a paid subscription",
        "auth": lambda k: {"hibp-api-key": k.get("HIBP_API_KEY", ""),
                           "user-agent": "foundation"},
    },
    "emailrep": {
        "label": "EmailRep",
        "base": "emailrep.io",
        "prefix": "/",
        "env": ("EMAILREP_API_KEY",),
        "ttl": 3600,
        "interval": 1.0,
        "limit": (60, 1.0),
        "hint": "optional — higher quota with a key",
        "auth": lambda k: {"Key": k.get("EMAILREP_API_KEY", "")},
    },
    "hunter": {
        "label": "Hunter.io",
        "base": "api.hunter.io",
        "prefix": "/v2/",
        "env": ("HUNTER_API_KEY",),
        "ttl": 3600,
        "interval": 1.0,
        "limit": (30, 0.5),
        "hint": "25 searches/month on the free plan",
        "auth": lambda k: {},
        "qauth": lambda k: {"api_key": k.get("HUNTER_API_KEY", "")},
    },
    "securitytrails": {
        "label": "SecurityTrails",
        "base": "api.securitytrails.com",
        "prefix": "/v1/",
        "env": ("SECURITYTRAILS_API_KEY",),
        "ttl": 3600,
        "interval": 1.0,
        "limit": (30, 0.5),
        "hint": "free tier is limited",
        "auth": lambda k: {"APIKEY": k.get("SECURITYTRAILS_API_KEY", "")},
    },
}

ORDER = ("virustotal", "urlscan", "censys", "ipinfo", "abuseipdb", "otx",
         "greynoise", "shodan", "hibp", "emailrep", "hunter", "securitytrails")


def service_keys(spec):
    """Current key values for a spec, read from the environment."""
    return {var: os.environ.get(var, "").strip() for var in spec["env"]}


def has_keys(spec):
    return all(service_keys(spec).values())


# --------------------------------------------------------------------------
# .env handling
# --------------------------------------------------------------------------

def load_env(path=ENV_PATH):
    """Populate os.environ from .env without overriding real environment vars."""
    loaded = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                loaded[key] = value
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    for key, value in loaded.items():
        if value:
            os.environ.setdefault(key, value)
    return loaded


def write_env(updates, path=ENV_PATH):
    """Merge key=value pairs into .env, preserving comments and other lines."""
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        pass
    index = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            index[stripped.partition("=")[0].strip()] = i
    for key, value in updates.items():
        if key in index:
            lines[index[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    for key, value in updates.items():
        if value:
            os.environ[key] = value


# --------------------------------------------------------------------------
# relay configuration
# --------------------------------------------------------------------------

RELAY_URL_VAR = "NF_RELAY_URL"
RELAY_TOKEN_VAR = "NF_RELAY_TOKEN"


def relay_config():
    return {
        "url": os.environ.get(RELAY_URL_VAR, "").strip().rstrip("/"),
        "token": os.environ.get(RELAY_TOKEN_VAR, "").strip(),
    }


def relay_enabled():
    cfg = relay_config()
    return bool(cfg["url"] and cfg["token"])


def relay_available():
    """True when this machine can reach every service through the relay."""
    return relay_enabled()


class Keyring:
    """Presence check and header builder for every registered service."""

    def __init__(self, path=ENV_PATH):
        self.path = path
        load_env(path)
        self.reload()

    def reload(self):
        self.relay = relay_enabled()
        self.local = {name: has_keys(spec) for name, spec in SPECS.items()}

    def available(self, service):
        if self.relay:
            return service in SPECS
        return self.local.get(service, False)

    def headers(self, service):
        spec = SPECS.get(service)
        if not spec or not self.available(service):
            return None
        keys = service_keys(spec)
        return spec["auth"](keys) if has_keys(spec) else None

    def status(self):
        return [(name, SPECS[name]["label"], self.available(name))
                for name in ORDER]

    def mode(self):
        return "relay" if self.relay else "direct"


# --------------------------------------------------------------------------
# rate limiting and cache
# --------------------------------------------------------------------------

_locks = {}
_last = {}
_guard = threading.Lock()


def _wait(service):
    """Block until the service's minimum interval since the last call elapses."""
    spec = SPECS.get(service)
    if not spec or spec.get("interval", 0) <= 0:
        return
    with _guard:
        lock = _locks.setdefault(service, threading.Lock())
    with lock:
        delay = spec["interval"] - (time.monotonic() - _last.get(service, 0.0))
        if delay > 0:
            time.sleep(delay)
        _last[service] = time.monotonic()


def _cache_path(service, key):
    digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:32]
    return os.path.join(CACHE_ROOT, service, digest + ".json")


def cache_get(service, key):
    try:
        with open(_cache_path(service, key), "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        if time.time() - float(blob.get("at", 0)) > float(blob.get("ttl", 0)):
            return None
        return blob.get("data")
    except Exception:
        return None


def cache_put(service, key, data, ttl):
    if ttl <= 0:
        return
    try:
        path = _cache_path(service, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"at": time.time(), "ttl": ttl, "data": data}, fh)
    except Exception:
        pass


def clear_cache():
    """Delete every cached response. Returns the number of files removed."""
    removed = 0
    for root, _dirs, files in os.walk(CACHE_ROOT):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
                removed += 1
            except OSError:
                pass
    return removed


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

def _direct_call(nf, service, path, query, body_limit, extra_headers, timeout):
    """Call the upstream API from this machine using locally held keys."""
    spec = SPECS[service]
    url = "https://" + spec["base"] + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
    keys = service_keys(spec)
    headers = dict(spec["auth"](keys))
    if extra_headers:
        headers.update(extra_headers)
    r = nf.http(url, nf.CFG, extra_headers=headers, body_limit=body_limit,
                timeout=timeout if timeout is not None else max(12, nf.CFG["timeout"]))
    if r.error:
        return None, 0, "transport"
    if r.status == 429:
        return None, r.status, "throttled"
    if r.status == 404:
        return None, r.status, "not_found"
    if r.status == 401 or r.status == 403:
        return None, r.status, "forbidden"
    if r.status != 200:
        return None, r.status, "upstream"
    try:
        return json.loads(r.text or "null"), r.status, ""
    except Exception:
        return None, r.status, "decode"


def _relay_call(nf, service, path, query, body_limit, timeout):
    """Call the same endpoint through the relay, which supplies the keys."""
    cfg = relay_config()
    payload = json.dumps({"service": service, "path": path,
                          "query": query or {}})
    r = nf.http(cfg["url"] + "/v1/q", nf.CFG, method="POST",
                extra_headers={"X-Relay-Token": cfg["token"],
                               "Content-Type": "application/json"},
                body=payload, body_limit=body_limit,
                timeout=timeout if timeout is not None else max(20, nf.CFG["timeout"]))
    if r.error:
        return None, 0, "transport"
    try:
        envelope = json.loads(r.text or "null")
    except Exception:
        return None, r.status, "decode"
    if not isinstance(envelope, dict):
        return None, r.status, "decode"
    if envelope.get("ok"):
        return envelope.get("data"), r.status, ""
    return None, r.status, str((envelope.get("error") or {}).get("code") or "relay")


def get_json(nf, service, path, *, cache_key=None, ttl=None, body_limit=2_000_000,
             extra_headers=None, timeout=None, not_found_ok=False, query=None):
    """Rate-limited, cached JSON GET against a keyed service.

    Returns parsed JSON on success, an empty list when not_found_ok and the
    upstream answered 404, and None when no transport is configured or the
    call failed for any other reason.
    """
    spec = SPECS.get(service)
    ring = getattr(nf, "KEYS", None)
    if spec is None or ring is None or not ring.available(service):
        return None
    ttl = spec["ttl"] if ttl is None else ttl
    cache_key = cache_key or f"{service}:{path}:{sorted((query or {}).items())}"
    cached = cache_get(service, cache_key)
    if cached is not None:
        return cached

    # Client-side smoothing in both modes: protects a relay from a runaway loop
    # and keeps direct calls inside free-tier limits.
    _wait(service)

    if relay_enabled():
        data, status, err = _relay_call(nf, service, path, query, body_limit, timeout)
    else:
        if not has_keys(spec):
            return None
        data, status, err = _direct_call(nf, service, path, query, body_limit,
                                         extra_headers, timeout)

    if err == "not_found" and not_found_ok:
        cache_put(service, cache_key, [], ttl)
        return []
    if err == "throttled" or status == 429:
        nf.note(f"{spec['label']}: throttled — try again later")
        return None
    if err == "forbidden":
        nf.note(f"{spec['label']}: key rejected ({status})")
        return None
    if err:
        return None
    cache_put(service, cache_key, data, ttl)
    return data


# --------------------------------------------------------------------------
# per-service helpers
# --------------------------------------------------------------------------

def _q(value):
    return urllib.parse.quote(str(value), safe="")


def vt_domain(nf, domain):
    return get_json(nf, "virustotal", "/api/v3/domains/" + _q(domain),
                    cache_key=f"vt:domain:{domain.lower()}")


def vt_ip(nf, ip):
    return get_json(nf, "virustotal", "/api/v3/ip_addresses/" + _q(ip),
                    cache_key=f"vt:ip:{ip}")


def ipinfo(nf, ip):
    return get_json(nf, "ipinfo", "/" + _q(ip) + "/json",
                    cache_key=f"ipinfo:{ip}")


def abuseipdb(nf, ip, days=90):
    return get_json(nf, "abuseipdb", "/api/v2/check",
                    query={"ipAddress": ip, "maxAgeInDays": days},
                    cache_key=f"abuseipdb:{ip}:{days}")


def greynoise(nf, ip):
    return get_json(nf, "greynoise", "/v3/community/" + _q(ip),
                    cache_key=f"greynoise:{ip}")


def otx_ip(nf, ip):
    return get_json(nf, "otx", "/api/v1/indicators/IPv4/" + _q(ip) + "/general",
                    cache_key=f"otx:ip:{ip}")


def censys_host(nf, ip):
    return get_json(nf, "censys", "/api/v2/hosts/" + _q(ip),
                    cache_key=f"censys:host:{ip}")


def shodan_host(nf, ip):
    # In direct mode the key belongs in the query string; the relay adds its own.
    if relay_enabled():
        query = None
    else:
        key = os.environ.get("SHODAN_API_KEY", "").strip()
        if not key:
            return None
        query = {"key": key}
    return get_json(nf, "shodan", "/shodan/host/" + _q(ip), query=query,
                    cache_key=f"shodan:host:{ip}")


def urlscan_domain(nf, domain):
    return get_json(nf, "urlscan", "/api/v1/search/",
                    query={"q": f"domain:{domain}", "size": 20},
                    cache_key=f"urlscan:{domain.lower()}")


def hibp_account(nf, email):
    return get_json(nf, "hibp", "/api/v3/breachedaccount/" + _q(email),
                    query={"truncateResponse": "false"},
                    cache_key=f"hibp:{email.lower()}", not_found_ok=True)


def emailrep(nf, email):
    return get_json(nf, "emailrep", "/" + _q(email),
                    cache_key=f"emailrep:{email.lower()}")


# --------------------------------------------------------------------------
# aggregation and rendering
# --------------------------------------------------------------------------

def ip_context(nf, ip):
    """Everything the configured transport can return for a single IP."""
    ring = getattr(nf, "KEYS", None)
    if ring is None:
        return {}
    probes = (
        ("ipinfo", ipinfo), ("abuseipdb", abuseipdb), ("greynoise", greynoise),
        ("otx", otx_ip), ("shodan", shodan_host), ("censys", censys_host),
        ("virustotal", vt_ip),
    )
    out = {}
    for name, fetch in probes:
        if ring.available(name):
            value = fetch(nf, ip)
            if value is not None:
                out[name] = value
    return out


def render_vt_data(nf, blob, label="virustotal"):
    attrs = ((blob or {}).get("data") or {}).get("attributes") or {}
    stats = attrs.get("last_analysis_stats") or {}
    if not stats and not attrs.get("reputation"):
        return
    nf.section(f"{label} — verdict")
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    nf.kv("malicious", malicious, nf.P.bad if malicious else nf.P.ok)
    nf.kv("suspicious", suspicious, nf.P.warn if suspicious else nf.P.ok)
    nf.kv("harmless", stats.get("harmless", 0))
    nf.kv("reputation", attrs.get("reputation", 0))
    categories = sorted(set((attrs.get("categories") or {}).values()))
    if categories:
        nf.kv("categories", ", ".join(categories[:8]))
    if attrs.get("as_owner"):
        nf.kv("as owner", attrs["as_owner"])
    if attrs.get("country"):
        nf.kv("country", attrs["country"])


def domain_reputation(nf, domain):
    blob = vt_domain(nf, domain)
    if blob is None:
        return None
    render_vt_data(nf, blob)
    return blob


def render_ip_context(nf, ctx):
    if not ctx:
        nf.note("no keyed source available — set keys or a relay under Settings -> 9")
        return

    d = ctx.get("ipinfo") or {}
    if d and not d.get("bogon"):
        nf.section("ipinfo")
        for key in ("org", "asn", "hostname", "country", "region", "city"):
            if d.get(key):
                nf.kv(key, d[key])
        privacy = d.get("privacy") or {}
        flagged = [name for name, on in privacy.items() if on]
        if flagged:
            nf.kv("privacy", ", ".join(flagged), nf.P.warn)

    d = (ctx.get("abuseipdb") or {}).get("data") or {}
    if d:
        nf.section("abuseipdb")
        score = d.get("abuseConfidenceScore", 0)
        nf.kv("confidence", f"{score}%", nf.P.bad if score >= 25 else nf.P.ok)
        nf.kv("reports", d.get("totalReports", 0))
        if d.get("lastReportedAt"):
            nf.kv("last report", d["lastReportedAt"][:10])
        if d.get("isTor"):
            nf.kv("tor exit", "yes", nf.P.warn)

    d = ctx.get("greynoise") or {}
    if d and not d.get("message"):
        nf.section("greynoise")
        classification = d.get("classification") or "unknown"
        nf.kv("classification", classification,
              nf.P.bad if classification == "malicious" else nf.P.ok)
        nf.kv("noise", "yes" if d.get("noise") else "no")
        nf.kv("riot", "yes" if d.get("riot") else "no")
        if d.get("name"):
            nf.kv("actor", d["name"])

    d = ctx.get("otx") or {}
    if d:
        pulses = (d.get("pulse_info") or {}).get("count", 0)
        nf.section("alienvault otx")
        nf.kv("pulses", pulses, nf.P.warn if pulses else nf.P.ok)
        if d.get("reputation") is not None:
            nf.kv("reputation", d["reputation"])

    d = ctx.get("shodan") or {}
    if d and not d.get("error"):
        nf.section("shodan")
        nf.kv("org", d.get("org") or "-")
        nf.kv("os", d.get("os") or "-")
        ports = d.get("ports") or []
        if ports:
            nf.kv("ports", ", ".join(str(p) for p in ports[:25]))
        for cve in list(d.get("vulns") or [])[:20]:
            nf.finding("HIGH", "known vuln", cve)

    d = ctx.get("censys") or {}
    services = ((d.get("result") or {}).get("services")) or []
    if services:
        nf.section("censys")
        nf.kv("services", ", ".join(str(s.get("port")) for s in services[:25]))

    render_vt_data(nf, ctx.get("virustotal") or {})
