"""Network scanner modules for nxtf0und."""

import concurrent.futures
import ipaddress
import json
import re
import socket
import subprocess
import time
import urllib.parse

SQL_ERROR_RE = re.compile(
    r"(SQL syntax|mysql_?fetch|ORA-\d{5}|PostgreSQL.{0,20}ERROR|"
    r"SQLite/JDBCDriver|Unclosed quotation mark|syntax error at or near|"
    r"SqlException|MySqlException|valid MySQL result|pg_query\(\)|"
    r"Warning.{0,20}mysql_|ODBC SQL Server Driver|Division by zero)", re.I)

SQLI_PAYLOADS = [
    ("'", "error"),
    ('"', "error"),
    ("')", "error"),
    ("';", "error"),
    ("1' ORDER BY 100-- -", "error"),
    ("' UNION SELECT NULL-- -", "error"),
    ("' AND '1'='1", "bool"),
    ("' AND '1'='2", "bool"),
    ("1 AND 1=1", "bool"),
    ("1 AND 1=2", "bool"),
    ("'; WAITFOR DELAY '0:0:5'-- -", "time"),
    ("1'; WAITFOR DELAY '0:0:5'-- -", "time"),
    ("' OR SLEEP(5)-- -", "time"),
    ("1' AND SLEEP(5)-- -", "time"),
    ("'||pg_sleep(5)-- -", "time"),
    ("1 AND SLEEP(5)", "time"),
]

SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly",
    "adf.ly", "bit.do", "cutt.ly", "rb.gy", "shorturl.at", "rebrand.ly",
    "tiny.cc", "lnkd.in", "s.id", "v.gd", "clck.ru", "shorte.st",
}

SUSPICIOUS_TLDS = {
    "xyz", "top", "cf", "gq", "tk", "ml", "ga", "work", "click", "link",
    "zip", "mov", "rest", "buzz", "monster", "quest", "loan", "support",
    "live", "shop", "icu", "cam", "surf", "bar", "beauty", "makeup",
}

PHISH_WORDS = (
    "login", "signin", "verify", "secure", "update", "wallet", "seed",
    "account", "billing", "recovery", "unlock", "confirm", "support",
    "giveaway", "nitro", "free", "bonus", "airdrop", "claim",
)

def _params_of(url):
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return {k: v[0] for k, v in q.items()}
    except Exception:
        return {}

def _set_param(url, name, value):
    parsed = urllib.parse.urlparse(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    q[name] = value
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q)))

def _crawl(nf, url, limit=25):
    base = urllib.parse.urlparse(url)
    found = {url}
    r = nf.http(url, nf.CFG, body_limit=400_000)
    if r.error:
        return list(found)
    for href in re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I):
        if len(found) >= limit:
            break
        if href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        full = urllib.parse.urljoin(url, href)
        p = urllib.parse.urlparse(full)
        if p.netloc == base.netloc and p.query:
            found.add(urllib.parse.urlunparse(p._replace(fragment="")))
    return list(found)

def cmd_sqli(nf):
    target = nf.ask("target url")
    if not target:
        return
    url = nf.normalize_url(target)
    nf.loading("crawling target")
    urls = _crawl(nf, url)
    targets = [u for u in urls if _params_of(u)]
    if not targets:
        targets = [url]
        nf.note("no parameterised links found; testing the given url")
    nf.section(f"sqli scan — {len(targets)} url(s)")
    findings = []
    for u in targets[:25]:
        params = _params_of(u)
        if not params:
            nf.note(f"skip (no params): {u}")
            continue
        base = nf.http(u, nf.CFG, body_limit=300_000)
        if base.error:
            continue
        base_len = len(base.text)
        for param in list(params)[:12]:
            for payload, kind in SQLI_PAYLOADS:
                test = nf.http(_set_param(u, param, payload), nf.CFG,
                               body_limit=300_000,
                               timeout=max(9, nf.CFG["timeout"]))
                if test.error:
                    continue
                if kind == "error" and SQL_ERROR_RE.search(test.text):
                    findings.append((u, param, payload, "error-based"))
                    nf.finding("HIGH", "sql injection (error)", f"{param} @ {u}")
                    break
                if kind == "bool":
                    delta = abs(len(test.text) - base_len)
                    if delta > 60:
                        findings.append((u, param, payload, "boolean"))
                        nf.finding("MED", "boolean injection candidate",
                                   f"{param} delta {delta}")
                        break
                if kind == "time" and test.status:
                    pass
            for payload in ("' UNION SELECT SLEEP(5)-- -", "1' AND SLEEP(5)-- -"):
                start = time.time()
                nf.http(_set_param(u, param, payload), nf.CFG,
                        body_limit=5000, timeout=12)
                elapsed = time.time() - start
                if elapsed >= 4.5:
                    findings.append((u, param, payload, "time-based"))
                    nf.finding("HIGH", "time-based sql injection",
                               f"{param} delayed {elapsed:.1f}s")
                    break
    if not findings:
        nf.finding("OK", "no injectable parameters confirmed")
    nf.save_report("sqli", {"target": url, "findings": findings})

def cmd_website_scanner(nf):
    nf.cmd_url_scan(nf.CFG)

def _rdap_domain(domain):
    for base in (f"https://rdap.org/domain/{domain}",
                 f"https://rdap.verisign.com/com/v1/domain/{domain}"):
        try:
            import urllib.request
            req = urllib.request.Request(base, headers={"Accept": "application/rdap+json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read(400_000))
        except Exception:
            continue
    return None

def cmd_url_scanner(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not host:
        nf.finding("HIGH", "invalid url")
        return
    findings = []

    def add(sev, title, detail=""):
        findings.append({"severity": sev, "title": title, "detail": detail})
        nf.finding(sev, title, detail)

    nf.section("structure")
    nf.kv("scheme", parsed.scheme)
    nf.kv("host", host)
    nf.kv("port", parsed.port or ("443" if parsed.scheme == "https" else "80"))
    nf.kv("path", parsed.path or "/")

    if "@" in parsed.netloc:
        add("HIGH", "credentials embedded in url")
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        add("MED", "raw ip as host")
    if host.startswith("xn--") or ".xn--" in host:
        add("HIGH", "punycode host (homograph risk)", host)
    labels = host.split(".")
    if len(labels) > 4:
        add("MED", "deep subdomain chain", str(len(labels)))
    tld = labels[-1].lower() if labels else ""
    if tld in SUSPICIOUS_TLDS:
        add("MED", f"high-risk tld .{tld}")
    if host in SHORTENERS:
        add("LOW", "link shortener in use", host)
    if len(url) > 120:
        add("LOW", "long url", f"{len(url)} chars")
    low = urllib.parse.urlunparse(parsed).lower()
    hits = [w for w in PHISH_WORDS if w in low]
    if len(hits) >= 3:
        add("MED", "phishy keywords", ", ".join(hits[:6]))
    if parsed.scheme != "https":
        add("MED", "no https")

    nf.section("resolution")
    try:
        addrs = sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
        for a in addrs[:6]:
            nf.kv("ip", a, nf.P.ok)
    except Exception as exc:
        add("HIGH", "dns resolution failed", str(exc))
        return

    nf.section("redirect chain")
    nf.loading("following redirects")
    r = nf.http(url, nf.CFG, body_limit=200_000)
    if r.error:
        add("HIGH", "fetch failed", r.error)
    else:
        nf.kv("status", r.status)
        nf.kv("final url", r.url)
        for hop in r.history:
            nf.kv("hop", hop, nf.P.dim)
        if urllib.parse.urlparse(r.url).hostname != host:
            add("LOW", "cross-domain redirect", urllib.parse.urlparse(r.url).hostname or "")
        if r.status >= 400:
            add("LOW", f"http status {r.status}")

    nf.section("domain registration")
    domain = ".".join(labels[-2:]) if len(labels) >= 2 else host
    rdap = _rdap_domain(domain)
    if rdap:
        nf.kv("registrar", next((e.get("vcardArray", [None, []])[1][1][3]
                                 for e in (rdap.get("entities") or [])
                                 if "registrar" in (e.get("roles") or [])), "unknown"))
        for event in rdap.get("events") or []:
            if event.get("eventAction") in ("registration", "expiration", "last changed"):
                nf.kv(event["eventAction"], event.get("eventDate", "-"))
                if event.get("eventAction") == "registration":
                    try:
                        age = (time.time() - time.mktime(time.strptime(
                            event["eventDate"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
                        nf.kv("age (days)", int(age))
                        if age < 30:
                            add("MED", "domain registered recently", f"{int(age)} days")
                    except Exception:
                        pass
    else:
        nf.note("rdap data unavailable")

    nf.section("summary")
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    if not any(f["severity"] in ("HIGH", "MED") for f in findings):
        nf.finding("OK", "no structural red flags on this pass")
    nf.save_report(f"urlscan_{host}", {"url": url, "findings": findings})

def _alive(host, ports, timeout):
    for port in ports:
        try:
            with socket.create_connection((str(host), port), timeout=timeout):
                return host
        except Exception:
            continue
    return None

def cmd_ip_scanner(nf):
    spec = nf.ask("range (cidr e.g. 192.168.1.0/24)")
    if not spec:
        return
    try:
        net = ipaddress.ip_network(spec, strict=False)
    except ValueError as exc:
        nf.finding("HIGH", "bad network", str(exc))
        return
    hosts = list(net.hosts())
    cap = 1024
    if len(hosts) > cap:
        nf.finding("MED", f"range too large, capped at {cap} hosts")
        hosts = hosts[:cap]
    ports = [80, 443, 22, 445, 3389, 8080]
    nf.section(f"host sweep — {net} ({len(hosts)} addresses)")
    alive = []
    timeout = min(0.8, max(0.2, nf.CFG["timeout"] / 10))
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = {pool.submit(_alive, h, ports, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except Exception:
                res = None
            if res:
                alive.append(str(res))
                print("  " + nf.P.ok("◆") + " " + nf.P.sec(str(res)))
    nf.finding("OK" if alive else "INFO", f"{len(alive)} hosts responsive")
    nf.save_report("ipscan", {"network": str(net), "alive": sorted(alive)})

def _parse_ports(spec):
    spec = (spec or "").strip()
    if not spec or spec.lower() in ("top", "default"):
        return None
    ports = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            try:
                ports.update(range(int(a), int(b) + 1))
            except ValueError:
                continue
        elif chunk.isdigit():
            ports.add(int(chunk))
    return sorted(p for p in ports if 1 <= p <= 65535) or None

def cmd_ip_port_scanner(nf):
    target = nf.ask("target ip / host")
    if not target:
        return
    spec = nf.ask("ports (top / 1-1000 / 22,80,443)", "top")
    ports = _parse_ports(spec)
    nf.loading("probing ports")
    try:
        results = nf.py_port_scan(target, ports or None)
    except socket.gaierror:
        nf.finding("HIGH", "target did not resolve")
        return
    nf.section(f"open ports — {target}")
    if not results:
        nf.finding("INFO", "no open ports")
        return
    for port, ms, banner in results:
        nf.kv(f"{port}/tcp", f"{nf.SERVICE_HINTS.get(port, 'unknown')}  {ms}ms  {banner}",
              nf.P.ok)

def cmd_ip_pinger(nf):
    target = nf.ask("target ip / host")
    if not target:
        return
    count = nf.ask("count", "4")
    try:
        count = max(1, min(20, int(count)))
    except ValueError:
        count = 4
    nf.section(f"ping — {target}")
    ping = "ping" if nf.os.name != "nt" else "ping"
    flag = "-n" if nf.os.name == "nt" else "-c"
    if nf.shutil.which(ping):
        try:
            subprocess.call([ping, flag, str(count), target])
            return
        except Exception:
            pass
    rtts = []
    for i in range(count):
        start = time.time()
        try:
            with socket.create_connection((target, 443), timeout=3):
                pass
            rtt = (time.time() - start) * 1000
            rtts.append(rtt)
            print("  " + nf.P.ok(f"reply {i + 1}") + nf.P.dim(f"  {rtt:.1f} ms"))
        except Exception:
            print("  " + nf.P.bad(f"timeout {i + 1}"))
        time.sleep(0.2)
    if rtts:
        nf.section("stats")
        nf.kv("sent", count)
        nf.kv("received", len(rtts))
        nf.kv("min/avg/max", f"{min(rtts):.1f} / {sum(rtts)/len(rtts):.1f} / {max(rtts):.1f} ms")
    else:
        nf.finding("HIGH", "host not responding on tcp/443")
