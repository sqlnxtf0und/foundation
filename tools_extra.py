"""Extra recon, web and metadata tools."""

import concurrent.futures
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import time
import urllib.parse

import apikeys

def cmd_headers(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    r = nf.http(url, nf.CFG, body_limit=200_000)
    if r.error:
        nf.finding("HIGH", "request failed", r.error)
        return
    nf.section(f"response — {url}")
    nf.kv("status", r.status)
    nf.kv("final url", r.url)
    for hop in r.history:
        nf.kv("hop", hop, nf.P.dim)
    for key, value in r.headers.items():
        nf.kv(key, str(value)[:120])
    interesting = [k for k in r.headers
                   if k.lower() in ("server", "x-powered-by", "x-aspnet-version",
                                    "x-generator", "x-drupal-cache", "cf-ray",
                                    "x-vercel-id", "via", "x-cache")]
    if interesting:
        nf.section("fingerprint")
        for key in interesting:
            nf.finding("LOW", key, str(r.headers.get(key))[:80])
    nf.save_report(f"headers_{urllib.parse.urlparse(r.url).hostname}", dict(r.headers))

def cmd_ssl_cert(nf):
    host = nf.ask("host (no scheme)")
    if not host:
        return
    host = host.replace("https://", "").split("/")[0]
    port = nf.ask("port", "443")
    try:
        port = int(port)
    except ValueError:
        port = 443
    nf.loading("handshaking")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                cipher = tls.cipher()
                version = tls.version()
    except Exception as exc:
        nf.finding("HIGH", "tls failed", str(exc)[:120])
        return
    nf.section(f"certificate — {host}:{port}")
    nf.kv("tls", version)
    nf.kv("cipher", f"{cipher[0]}  {cipher[1]} bit" if cipher else "-")
    if not cert:
        nf.note("self-signed / no parsed certificate")
        return
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            nf.kv(f"subject {key}", value)
    for rdn in cert.get("issuer", ()):
        for key, value in rdn:
            nf.kv(f"issuer {key}", value)
    nf.kv("valid from", cert.get("notBefore"))
    nf.kv("valid until", cert.get("notAfter"))
    alt = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"]
    nf.kv("san", ", ".join(alt[:12]) or "-")
    try:
        expiry = ssl.cert_time_to_seconds(cert["notAfter"])
        days = int((expiry - time.time()) / 86400)
        nf.kv("expires in", f"{days} days",
              nf.P.ok if days > 14 else nf.P.bad)
    except Exception:
        pass

def cmd_traceroute(nf):
    target = nf.ask("target host / ip")
    if not target:
        return
    hops = nf.ask("max hops", "20")
    try:
        hops = max(1, min(40, int(hops)))
    except ValueError:
        hops = 20
    binary = None
    for name in ("traceroute", "tracepath", "tracert"):
        if shutil.which(name):
            binary = name
            break
    if not binary:
        nf.finding("MED", "traceroute not installed", "apt install traceroute")
        return
    nf.section(f"path — {target}")
    try:
        if binary == "traceroute":
            subprocess.call([binary, "-m", str(hops), "-w", "2", "-n", target])
        elif binary == "tracepath":
            subprocess.call([binary, "-m", str(hops), target])
        else:
            subprocess.call([binary, "-h", str(hops), "-w", "2000", target])
    except Exception as exc:
        nf.finding("HIGH", "traceroute failed", str(exc))

def cmd_banner(nf):
    target = nf.ask("target host / ip")
    if not target:
        return
    spec = nf.ask("ports", "21,22,25,80,110,143,3306,5432,6379,8080,8443")
    ports = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ports.append(int(chunk))
    if not ports:
        nf.finding("MED", "no ports parsed")
        return
    nf.section(f"banners — {target}")
    timeout = min(6, max(2, nf.CFG["timeout"]))
    for port in ports[:30]:
        try:
            with socket.create_connection((target, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                try:
                    sock.sendall(b"\r\n")
                except Exception:
                    pass
                try:
                    blob = sock.recv(1024)
                except socket.timeout:
                    blob = b""
                text = blob.decode("utf-8", "replace").strip().replace("\r", " ")
                nf.kv(f"{port}/tcp", text[:120] or "(no banner)", nf.P.ok)
        except Exception as exc:
            nf.kv(f"{port}/tcp", f"closed ({type(exc).__name__})", nf.P.dim)

def cmd_robots(nf):
    raw = nf.ask("domain / url")
    if not raw:
        return
    base = nf.normalize_url(raw).rstrip("/")
    nf.section("robots / sitemap")
    robots = nf.http(f"{base}/robots.txt", nf.CFG, body_limit=200_000)
    if robots.error or robots.status >= 400:
        nf.finding("INFO", "robots.txt not served",
                   "" if robots.error else str(robots.status))
    else:
        lines = [ln.strip() for ln in robots.text.splitlines() if ln.strip()]
        nf.kv("lines", len(lines))
        for line in lines[:40]:
            nf.kv("", line[:110])
        sitemaps = [ln.split(":", 1)[1].strip() for ln in lines
                    if ln.lower().startswith("sitemap:")]
        for url in sitemaps[:5]:
            nf.finding("LOW", "sitemap", url)
        for line in lines:
            if line.lower().startswith("disallow:") and len(line) > 10:
                nf.finding("LOW", "disallowed path", line.split(":", 1)[1].strip())
    for candidate in ("sitemap.xml", "sitemap_index.xml", "sitemap-index.xml"):
        r = nf.http(f"{base}/{candidate}", nf.CFG, body_limit=400_000)
        if r.error or r.status >= 400:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
        nf.kv(candidate, f"{len(locs)} urls")
        for loc in locs[:10]:
            nf.note(f"    {loc[:110]}")
        break

DIR_WORDLIST = [
    "admin", "administrator", "login", "logout", "register", "signup", "dashboard",
    "panel", "cpanel", "wp-admin", "wp-login.php", "wp-content", "wp-json", "api",
    "api/v1", "api/v2", "graphql", "swagger", "swagger.json", "openapi.json",
    "docs", "documentation", "backup", "backups", "old", "test", "dev", "staging",
    "config", "config.php", "config.json", ".env", ".git/config", ".git/HEAD",
    ".svn/entries", "server-status", "phpinfo.php", "info.php", "debug", "console",
    "uploads", "files", "download", "downloads", "assets", "static", "media",
    "images", "img", "css", "js", "private", "secret", "internal", "db", "sql",
    "database", "dump.sql", "backup.zip", "backup.tar.gz", "robots.txt", "sitemap.xml",
    "health", "status", "metrics", "actuator", "actuator/health", "trace", "env",
]

def _probe_path(nf, base, path):
    url = f"{base}/{path.lstrip('/')}"
    r = nf.http(url, nf.CFG, body_limit=4000, timeout=min(6, nf.CFG["timeout"]))
    if r.error:
        return None
    if r.status in (200, 201, 204, 301, 302, 401, 403):
        return (r.status, len(r.text), url)
    return None

def cmd_dir_brute(nf):
    raw = nf.ask("base url")
    if not raw:
        return
    base = nf.normalize_url(raw).rstrip("/")
    nf.section(f"directory sweep — {base}")
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=18) as pool:
        futures = {pool.submit(_probe_path, nf, base, path): path for path in DIR_WORDLIST}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except Exception:
                res = None
            if not res:
                continue
            status, size, url = res
            hits.append(res)
            sev = "HIGH" if status in (200, 204) else "LOW"
            nf.finding(sev, f"{status}", f"{url}  ({size} B)")
    nf.finding("OK" if hits else "INFO", f"{len(hits)} path(s) responding")
    if hits:
        nf.save_report(f"dirbrute_{urllib.parse.urlparse(base).hostname}",
                       [{"status": s, "size": n, "url": u} for s, n, u in hits])

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "'\"><svg/onload=alert(1)>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "\"><iframe src=javascript:alert(1)>",
]

def _params(url):
    parsed = urllib.parse.urlparse(url)
    return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

def _with_param(url, name, value):
    parsed = urllib.parse.urlparse(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    q[name] = value
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q)))

def cmd_xss(nf):
    raw = nf.ask("url with parameters")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url has no query parameters")
        return
    nf.section(f"reflection sweep — {len(params)} param(s)")
    found = 0
    for param in params:
        for payload in XSS_PAYLOADS:
            test = _with_param(url, param, payload)
            r = nf.http(test, nf.CFG, body_limit=400_000)
            if r.error:
                continue
            if payload in r.text:
                found += 1
                nf.finding("HIGH", "unescaped reflection", f"{param} = {payload}")
                break
            encoded = urllib.parse.quote(payload)
            if encoded in r.text:
                nf.finding("LOW", "encoded reflection only", f"{param}")
    if not found:
        nf.finding("OK", "no raw reflection found")
    nf.save_report("xss_scan", {"url": url, "reflections": found})

LFI_PAYLOADS = [
    "../../../../etc/passwd",
    "../../../../etc/passwd%00",
    "....//....//....//etc/passwd",
    "..%2f..%2f..%2f..%2fetc%2fpasswd",
    "/etc/passwd",
    "php://filter/convert.base64-encode/resource=index.php",
    "../../../../windows/win.ini",
]

def cmd_lfi(nf):
    raw = nf.ask("url with a file parameter")
    if not raw:
        return
    url = nf.normalize_url(raw)
    params = _params(url)
    if not params:
        nf.finding("MED", "url has no query parameters")
        return
    nf.section("path traversal sweep")
    for param in params:
        for payload in LFI_PAYLOADS:
            r = nf.http(_with_param(url, param, payload), nf.CFG, body_limit=200_000)
            if r.error:
                continue
            if re.search(r"root:[x*]?:0:0:", r.text):
                nf.finding("HIGH", "local file read (/etc/passwd)", f"{param} = {payload}")
                break
            if "[extensions]" in r.text and "[fonts]" in r.text:
                nf.finding("HIGH", "local file read (win.ini)", f"{param} = {payload}")
                break
            if "PD9waHA" in r.text:
                nf.finding("HIGH", "php filter base64 dump", f"{param}")
                break
    nf.note("blank result means no readable traversal; try wrapper variants manually")

REDIRECT_PARAMS = ("url", "redirect", "next", "return", "returnUrl", "dest",
                   "destination", "continue", "target", "r", "u", "goto", "out")

def cmd_open_redirect(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    marker = "https://example.com/nf-redirect"
    nf.section("open redirect sweep")
    hits = 0
    for param in REDIRECT_PARAMS:
        test = _with_param(url, param, marker) if _params(url) else \
            f"{url}{'&' if '?' in url else '?'}{param}={urllib.parse.quote(marker)}"
        r = nf.http(test, nf.CFG, allow_redirects=False, body_limit=20_000)
        if r.error:
            continue
        location = ""
        for key, value in (r.headers or {}).items():
            if key.lower() == "location":
                location = str(value)
        if r.status in (301, 302, 303, 307, 308) and "example.com" in location:
            hits += 1
            nf.finding("HIGH", f"redirect via {param}", f"{url} -> {location[:90]}")
        elif marker in r.text and r.status == 200:
            nf.finding("LOW", "marker reflected in body", param)
    if not hits:
        nf.finding("OK", "no direct redirect accepted")

WAF_MARKERS = {
    "cloudflare": ("cf-ray", "cloudflare"),
    "akamai": ("akamai", "x-akamai"),
    "aws waf": ("awselb", "x-amzn"),
    "sucuri": ("x-sucuri", "sucuri"),
    "incapsula": ("incap_ses", "visid_incap"),
    "f5 bigip": ("bigip", "ts01"),
    "barracuda": ("barra", "barracuda"),
    "modsecurity": ("mod_security", "modsecurity"),
    "fastly": ("x-fastly", "fastly"),
    "wordfence": ("wordfence",),
}

def cmd_waf(nf):
    raw = nf.ask("url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    nf.section("waf fingerprint")
    hits = []
    for label, path in (("clean", url),
                        ("traversal", f"{url.rstrip('/')}/?id=../../etc/passwd"),
                        ("xss", f"{url.rstrip('/')}/?q=<script>alert(1)</script>"),
                        ("sqli", f"{url.rstrip('/')}/?id=1%27%20OR%201=1--")):
        r = nf.http(path, nf.CFG, body_limit=30_000)
        if r.error:
            nf.kv(label, f"error: {r.error[:60]}")
            continue
        blob = " ".join(f"{k}:{v}" for k, v in (r.headers or {}).items()).lower()
        blob += " " + (r.text or "")[:2000].lower()
        nf.kv(label, f"status {r.status}")
        for name, needles in WAF_MARKERS.items():
            if any(needle in blob for needle in needles):
                if name not in hits:
                    hits.append(name)
                    nf.finding("MED", f"waf hint: {name}", label)
        if r.status in (403, 406, 419, 429, 503):
            nf.finding("MED", "blocked response", f"{label} -> {r.status}")
    nf.finding("INFO" if hits else "OK",
               f"{len(hits)} waf signature(s)" if hits else "no waf signature")

def cmd_wayback(nf):
    raw = nf.ask("domain")
    if not raw:
        return
    domain = raw.replace("https://", "").replace("http://", "").split("/")[0]
    nf.loading("querying wayback cdx")
    url = ("http://web.archive.org/cdx/search/cdx?url="
           + urllib.parse.quote(f"{domain}/*")
           + "&output=json&collapse=urlkey&limit=400&fl=original,timestamp,statuscode")
    r = nf.http(url, nf.CFG, body_limit=4_000_000, timeout=max(15, nf.CFG["timeout"]))
    if r.error:
        nf.finding("HIGH", "cdx failed", r.error[:120])
        return
    try:
        rows = json.loads(r.text)
    except Exception:
        nf.finding("MED", "cdx returned non-json")
        return
    rows = rows[1:] if rows and rows[0][0] == "original" else rows
    nf.section(f"archived urls — {len(rows)}")
    interesting = ("admin", "login", "backup", ".env", "config", "upload",
                   "api", "debug", ".sql", ".zip", ".git")
    for row in rows[:60]:
        original = row[0]
        stamp = row[1] if len(row) > 1 else ""
        flag = any(word in original.lower() for word in interesting)
        nf.kv(original[:90], stamp, nf.P.warn if flag else None)
    flagged = [r[0] for r in rows if any(w in r[0].lower() for w in interesting)]
    if flagged:
        nf.section("flagged")
        for item in flagged[:25]:
            nf.finding("LOW", "worth a look", item[:100])
    nf.save_report(f"wayback_{domain}", rows[:400])

def cmd_shodan(nf):
    raw = nf.ask("ip address")
    if not raw:
        return
    try:
        ip = socket.gethostbyname(raw)
    except Exception:
        nf.finding("HIGH", "did not resolve")
        return
    nf.loading("querying internetdb")
    r = nf.http(f"https://internetdb.shodan.io/{ip}", nf.CFG, body_limit=400_000)
    if r.error or r.status != 200:
        nf.finding("MED", "no internetdb record",
                   r.error or str(r.status))
        return
    try:
        data = json.loads(r.text)
    except Exception:
        nf.finding("MED", "unreadable response")
        return
    nf.section(f"internetdb — {ip}")
    for key in ("hostnames", "ports", "cpes", "tags"):
        if data.get(key):
            nf.kv(key, ", ".join(str(v) for v in data[key][:15]))
    vulns = data.get("vulns") or []
    if vulns:
        for cve in vulns[:20]:
            nf.finding("HIGH", "known vuln", cve)
    else:
        nf.finding("OK", "no listed cves")
    apikeys.render_ip_context(nf, apikeys.ip_context(nf, ip))
    nf.save_report(f"shodan_{ip}", data)

def cmd_exif(nf):
    path = nf.ask("image / file path")
    if not path or not os.path.isfile(path):
        nf.finding("HIGH", "file not found", path or "-")
        return
    nf.section(f"metadata — {os.path.basename(path)}")
    nf.kv("size", f"{os.path.getsize(path):,} B")
    found = False
    try:
        from PIL import Image, ExifTags
        with Image.open(path) as img:
            nf.kv("format", img.format)
            nf.kv("dimensions", f"{img.width}x{img.height}")
            exif = img.getexif()
            for tag, value in exif.items():
                name = ExifTags.TAGS.get(tag, str(tag))
                nf.kv(name, str(value)[:100])
                found = True
    except ImportError:
        nf.note("pip install pillow for parsed exif")
    except Exception as exc:
        nf.note(f"pillow: {exc}")
    if not found:
        try:
            import struct
            with open(path, "rb") as fh:
                head = fh.read(4096)
            if head[:2] == b"\xff\xd8" or head[:4] in (b"II*\x00", b"MM\x00*"):
                nf.note("exif block present — install pillow to parse it")
            gps = re.findall(rb"(GPS[A-Za-z]+)", head)
            if gps:
                nf.kv("gps tags", ", ".join(sorted({g.decode() for g in gps})[:10]))
        except Exception:
            pass
    nf.save_report(f"meta_{os.path.basename(path)}", {"path": path})

def cmd_discord_id(nf):
    nf.section("discord id decoder")
    value = nf.ask("discord id (or user snowflake)")
    if not value.isdigit():
        nf.finding("MED", "numeric snowflake required")
        return
    snowflake = int(value)
    stamp = ((snowflake >> 22) + 1420070400000) / 1000
    created = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(stamp))
    nf.kv("id", value)
    nf.kv("created", created)
    nf.kv("age (days)", int((time.time() - stamp) / 86400))
    nf.kv("worker", (snowflake >> 17) & 0x1F)
    nf.kv("process", (snowflake >> 12) & 0x1F)
    nf.kv("increment", snowflake & 0xFFF)
    r = nf.http(f"https://discord.com/api/v10/users/{value}", nf.CFG, body_limit=100_000)
    if not r.error and r.status == 200:
        try:
            user = json.loads(r.text)
            nf.kv("username", user.get("username"))
            nf.kv("display", user.get("global_name"))
            nf.kv("bot", user.get("bot", False))
            if user.get("avatar"):
                nf.kv("avatar", f"https://cdn.discordapp.com/avatars/{value}/{user['avatar']}.png")
        except Exception:
            pass

def cmd_username_variants(nf):
    nf.section("username variant generator")
    base = nf.ask("base username")
    if not base:
        return
    suffixes = ("", "1", "01", "123", "_", ".", "-", "x", "xd", "real", "official",
                "tv", "gg", "hq", "yt", "ttv")
    years = ("", "99", "00", "01", "07", "09", "11", "13", "21", "22", "23", "24", "25", "26")
    out = []
    for suffix in suffixes:
        for year in years[:6] if suffix else years:
            name = f"{base}{suffix}{year}"
            if name not in out:
                out.append(name)
    for name in out[:70]:
        nf.kv(name, "")
    nf.finding("OK", f"{len(out)} variants")
    if nf.ask("save variants? (y/n)", "n").lower().startswith("y"):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, f"variants_{re.sub(r'[^A-Za-z0-9]', '_', base)}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
        nf.finding("OK", "saved", path)
    else:
        nf.note("not saved")

SUBDOMAIN_WORDS = [
    "www", "mail", "webmail", "smtp", "pop", "imap", "mx", "remote", "vpn", "ftp",
    "dev", "staging", "stage", "test", "beta", "demo", "sandbox", "preview",
    "api", "api-v1", "api2", "internal", "intranet", "portal", "admin", "panel",
    "cpanel", "dashboard", "manage", "support", "help", "status", "monitor",
    "cdn", "static", "assets", "img", "images", "media", "files", "upload",
    "git", "gitlab", "jenkins", "ci", "build", "deploy", "docker", "registry",
    "db", "mysql", "postgres", "redis", "mongo", "sql", "backup", "old", "new",
    "shop", "store", "pay", "billing", "invoice", "auth", "login", "sso",
    "docs", "wiki", "blog", "news", "forum", "chat", "meet", "video", "stream",
]

def _resolves(host):
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None

def cmd_subdomains(nf):
    domain = nf.ask("domain")
    if not domain:
        return
    domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    nf.section(f"subdomain sweep — {domain}")
    hits = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        futures = {pool.submit(_resolves, f"{word}.{domain}"): word
                   for word in SUBDOMAIN_WORDS}
        for fut in concurrent.futures.as_completed(futures):
            try:
                host = fut.result()
            except Exception:
                host = None
            if host:
                hits[host] = ""
                print("  " + nf.P.ok("◆") + " " + nf.P.sec(host))
    nf.loading("checking certificate transparency")
    r = nf.http(f"https://crt.sh/?q=%25.{domain}&output=json", nf.CFG,
                body_limit=6_000_000, timeout=max(15, nf.CFG["timeout"]))
    if not r.error and r.status == 200:
        try:
            for entry in json.loads(r.text):
                for name in (entry.get("name_value") or "").splitlines():
                    name = name.strip().lstrip("*.")
                    if name.endswith(domain) and name not in hits:
                        hits[name] = "crt.sh"
        except Exception:
            pass
    nf.finding("OK", f"{len(hits)} hostname(s)")
    nf.save_report(f"subdomains_{domain}", sorted(hits))

def cmd_hash_file(nf):
    import hashlib
    path = nf.ask("file path")
    if not path or not os.path.isfile(path):
        nf.finding("HIGH", "file not found", path or "-")
        return
    nf.section(f"hashes — {os.path.basename(path)}")
    nf.kv("size", f"{os.path.getsize(path):,} B")
    digests = {}
    for name in ("md5", "sha1", "sha256", "sha512"):
        h = hashlib.new(name)
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        digests[name] = h.hexdigest()
        nf.kv(name, h.hexdigest())
    nf.save_report(f"hashes_{os.path.basename(path)}", digests)
