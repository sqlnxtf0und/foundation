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

import apikeys


def _json(nf, url, headers=None, body_limit=2_000_000):
    r = nf.http(url, nf.CFG, extra_headers=headers, body_limit=body_limit,
                timeout=max(12, nf.CFG["timeout"]))
    if r.error:
        return None
    try:
        return json.loads(r.text)
    except Exception:
        return None


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
    apikeys.render_ip_context(nf, apikeys.ip_context(nf, ip))

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
    hits = apikeys.hibp_account(nf, email)
    if hits:
        nf.section(f"haveibeenpwned — {len(hits)} breach(es)")
        for row in hits[:40]:
            name = row.get("Name") or "?"
            date = (row.get("BreachDate") or "")[:10]
            classes = ", ".join(row.get("DataClasses") or [])[:80]
            nf.finding("HIGH", name, f"{date}  {classes}")
        nf.save_report(f"breach_{email.split('@')[0]}", hits)
    elif hits == []:
        nf.finding("OK", "no breach records for this address")
    elif nf.KEYS.available("hibp"):
        nf.finding("MED", "hibp query failed — check the subscription or key")
    else:
        nf.note("set HIBP_API_KEY under Settings -> 9 for breach search")
    data = _json(nf, f"https://api.xposedornot.com/v1/check-email/{urllib.parse.quote(email)}")
    if data:
        breaches = data.get("breaches") or data.get("Breaches") or []
        if isinstance(breaches, list) and breaches:
            nf.section("xposedornot")
            flat = []
            for entry in breaches:
                if isinstance(entry, list):
                    flat += entry
                else:
                    flat.append(entry)
            for name in flat[:30]:
                nf.finding("HIGH", str(name))
    profile = apikeys.emailrep(nf, email)
    if isinstance(profile, dict) and profile.get("reputation"):
        nf.section("emailrep")
        nf.kv("reputation", profile.get("reputation"))
        nf.kv("suspicious", "yes" if profile.get("suspicious") else "no",
              nf.P.warn if profile.get("suspicious") else nf.P.ok)
        details = profile.get("details") or {}
        exposed = [k for k, v in details.items() if v is True]
        if exposed:
            nf.kv("exposed", ", ".join(exposed[:10]))
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
