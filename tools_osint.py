"""OSINT modules."""

import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time

DOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dox")

PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"']+")

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "tempmail.com",
    "temp-mail.org", "10minutemail.com", "yopmail.com", "throwawaymail.com",
    "sharklasers.com", "trashmail.com", "getnada.com", "dispostable.com",
    "maildrop.cc", "mytemp.email", "fakeinbox.com", "spam4.me", "mailnesia.com",
}

SITES = [
    ("GitHub", "https://github.com/{}"),
    ("GitLab", "https://gitlab.com/{}"),
    ("Bitbucket", "https://bitbucket.org/{}"),
    ("Codeberg", "https://codeberg.org/{}"),
    ("Reddit", "https://www.reddit.com/user/{}"),
    ("Twitter/X", "https://x.com/{}"),
    ("Instagram", "https://www.instagram.com/{}/"),
    ("TikTok", "https://www.tiktok.com/@{}"),
    ("YouTube", "https://www.youtube.com/@{}"),
    ("Twitch", "https://www.twitch.tv/{}"),
    ("Steam", "https://steamcommunity.com/id/{}"),
    ("Roblox", "https://www.roblox.com/user.aspx?username={}"),
    ("Pinterest", "https://www.pinterest.com/{}/"),
    ("Tumblr", "https://{}.tumblr.com"),
    ("Medium", "https://medium.com/@{}"),
    ("DeviantArt", "https://www.deviantart.com/{}"),
    ("SoundCloud", "https://soundcloud.com/{}"),
    ("Spotify", "https://open.spotify.com/user/{}"),
    ("Telegram", "https://t.me/{}"),
    ("Patreon", "https://www.patreon.com/{}"),
    ("Keybase", "https://keybase.io/{}"),
    ("HackerNews", "https://news.ycombinator.com/user?id={}"),
    ("StackOverflow", "https://stackoverflow.com/users/{}"),
    ("Behance", "https://www.behance.net/{}"),
    ("Dribbble", "https://dribbble.com/{}"),
    ("Vimeo", "https://vimeo.com/{}"),
    ("Flickr", "https://www.flickr.com/people/{}"),
    ("VSCO", "https://vsco.co/{}"),
    ("Snapchat", "https://www.snapchat.com/add/{}"),
    ("Rumble", "https://rumble.com/user/{}"),
    ("Odysee", "https://odysee.com/@{}"),
    ("NPM", "https://www.npmjs.com/~{}"),
    ("DockerHub", "https://hub.docker.com/u/{}"),
    ("Kaggle", "https://www.kaggle.com/{}"),
    ("Replit", "https://replit.com/@{}"),
    ("CodePen", "https://codepen.io/{}"),
    ("TryHackMe", "https://tryhackme.com/p/{}"),
    ("HackTheBox", "https://app.hackthebox.com/profile/{}"),
    ("Chess.com", "https://www.chess.com/member/{}"),
    ("Lichess", "https://lichess.org/@/{}"),
    ("Duolingo", "https://www.duolingo.com/profile/{}"),
    ("Letterboxd", "https://letterboxd.com/{}/"),
    ("Last.fm", "https://www.last.fm/user/{}"),
    ("Goodreads", "https://www.goodreads.com/{}"),
    ("Wattpad", "https://www.wattpad.com/user/{}"),
    ("Archive of Our Own", "https://archiveofourown.org/users/{}/profile"),
]

MISS_MARKERS = (
    "page not found", "user not found", "not found", "doesn't exist",
    "does not exist", "no user", "couldn't find", "could not find",
    "account not found", "profile not found", "404",
)

def _host_domain(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname or ""
    except Exception:
        return ""

def _og(html, prop):
    pats = (
        r'<meta[^>]+property="og:%s"[^>]+content="([^"]*)"' % prop,
        r'<meta[^>]+content="([^"]*)"[^>]+property="og:%s"' % prop,
    )
    for pat in pats:
        m = re.search(pat, html, re.I | re.S)
        if m:
            return m.group(1).strip()
    return ""

def telegram_profile(nf, username):
    handle = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,64}", handle or ""):
        return {"error": "invalid telegram username"}
    r = nf.http(f"https://t.me/{handle}", nf.CFG, body_limit=800_000)
    if r.error:
        return {"error": r.error}
    if r.status != 200:
        return {"error": f"status {r.status}"}
    html = r.text
    embed = nf.http(f"https://t.me/{handle}?embed=1&mode=tme", nf.CFG,
                    body_limit=800_000)
    blob = html + "\n" + embed.text
    title = _og(html, "title")
    desc = _og(html, "description")
    image = _og(html, "image")
    extra = ""
    m = re.search(r'tgme_page_extra">([^<]+)<', blob)
    if m:
        extra = m.group(1).strip()
    data = {
        "username": handle,
        "title": title,
        "description": desc,
        "extra": extra,
        "photo": image,
        "phones_in_bio": [],
        "emails_in_bio": [],
        "links_in_bio": [],
        "user_id": None,
    }
    scope = " ".join([title, desc, extra])
    data["emails_in_bio"] = sorted(set(EMAIL_RE.findall(scope)))
    data["links_in_bio"] = sorted(set(URL_RE.findall(scope)))
    phones = []
    for cand in PHONE_RE.findall(scope):
        digits = re.sub(r"\D", "", cand)
        if 8 <= len(digits) <= 15 and cand not in phones:
            phones.append(cand.strip())
    data["phones_in_bio"] = phones
    idm = re.search(r"tg://user\?id=(\d+)", blob)
    if idm:
        data["user_id"] = idm.group(1)
    elif title.startswith("Telegram: Contact @"):
        data["user_id"] = "hidden"
    return data

def _print_telegram(nf, data):
    nf.section(f"telegram — @{data['username']}")
    nf.kv("display name", data.get("title") or "-")
    nf.kv("bio", data.get("description") or "-")
    nf.kv("extra", data.get("extra") or "-")
    nf.kv("user id", data.get("user_id") or "not exposed publicly")
    nf.kv("photo", data.get("photo") or "-")
    if data["phones_in_bio"]:
        for ph in data["phones_in_bio"]:
            nf.finding("OK", f"phone in bio: {ph}")
            profile = phone_profile(ph)
            if profile.get("valid"):
                nf.kv("  region", profile.get("region", "-"))
                nf.kv("  carrier", profile.get("carrier", "-"))
    else:
        nf.finding("INFO", "no phone number in the public bio")
        nf.note("telegram does not expose numbers via @handle; bios and linked accounts only")
    for em in data["emails_in_bio"]:
        nf.finding("LOW", f"email in bio: {em}")
    for link in data["links_in_bio"]:
        nf.finding("LOW", f"link in bio: {link}")

def cmd_telegram(nf):
    raw = nf.ask("telegram @username")
    if not raw:
        return
    nf.loading("resolving telegram profile")
    data = telegram_profile(nf, raw)
    if data.get("error"):
        nf.finding("HIGH", "lookup failed", data["error"])
        return
    _print_telegram(nf, data)
    nf.save_report(f"telegram_{data['username']}", data)
    if data["phones_in_bio"]:
        follow = nf.ask("run phone lookup on first number? (y/n)", "n")
        if follow.lower().startswith("y"):
            _print_phone(nf, phone_profile(data["phones_in_bio"][0]),
                         data["phones_in_bio"][0])

def _site_check(nf, site):
    name, url = site
    r = nf.http(url, nf.CFG, timeout=min(7, nf.CFG["timeout"]))
    if r.error or r.status != 200:
        return None
    low = r.text[:6000].lower()
    for marker in MISS_MARKERS:
        if marker in low:
            return None
    return (name, url)

def collect_username(nf, username):
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(_site_check, nf, (name, tpl.format(username))): name
                   for name, tpl in SITES}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            done += 1
            try:
                res = fut.result()
            except Exception:
                res = None
            if res:
                hits.append(res)
                print("  " + nf.P.ok("◆") + " " + nf.P.sec(f"{res[0]:<18}") + nf.P.dim(res[1]))
            if done % 8 == 0:
                print("  " + nf.P.dim(f"... {done}/{len(SITES)} checked"))
    hits.sort()
    return hits

def cmd_username(nf):
    user = nf.ask("username")
    if not user:
        return
    nf.section(f"username sweep — {user}")
    hits = collect_username(nf, user)
    nf.finding("OK" if hits else "INFO", f"{len(hits)} profiles found")
    nf.save_report(f"username_{user}", {"username": user, "hits": hits})

def _mx_records(domain):
    if shutil.which("dig"):
        try:
            out = subprocess.check_output(["dig", "+short", "MX", domain],
                                          stderr=subprocess.DEVNULL, timeout=8)
            recs = [ln.split()[-1].rstrip(".") for ln in out.decode().splitlines() if ln.strip()]
            if recs:
                return recs
        except Exception:
            pass
    if shutil.which("nslookup"):
        try:
            out = subprocess.check_output(["nslookup", "-type=MX", domain],
                                          stderr=subprocess.DEVNULL, timeout=8).decode()
            recs = re.findall(r"mail exchanger = ([^\s]+)", out)
            return [r.rstrip(".") for r in recs]
        except Exception:
            pass
    try:
        import dns.resolver
        return [str(r.exchange).rstrip(".") for r in dns.resolver.resolve(domain, "MX")]
    except Exception:
        return []

def collect_email(nf, email):
    email = email.strip()
    data = {"email": email, "valid_syntax": bool(re.fullmatch(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email)),
        "domain": email.split("@")[-1].lower() if "@" in email else "",
        "mx": [], "disposable": False, "gravatar": None, "gravatar_profile": None,
        "emailrep": None}
    if not data["valid_syntax"]:
        return data
    data["disposable"] = data["domain"] in DISPOSABLE
    data["mx"] = _mx_records(data["domain"])
    md5 = hashlib.md5(email.lower().encode()).hexdigest()
    gr = nf.http(f"https://gravatar.com/avatar/{md5}?d=404", nf.CFG, body_limit=1000)
    if not gr.error and gr.status == 200:
        data["gravatar"] = f"https://gravatar.com/avatar/{md5}"
        prof = nf.http(f"https://gravatar.com/{md5}.json", nf.CFG, body_limit=200_000)
        if not prof.error and prof.status == 200:
            try:
                data["gravatar_profile"] = json.loads(prof.text)
            except Exception:
                pass
    rep = nf.http(f"https://emailrep.io/{email}", nf.CFG,
                  extra_headers={"User-Agent": "nxtf0und-osint"})
    if not rep.error and rep.status == 200:
        try:
            data["emailrep"] = json.loads(rep.text)
        except Exception:
            pass
    return data

def _print_email(nf, data):
    nf.section(f"email — {data['email']}")
    nf.kv("syntax", "ok" if data["valid_syntax"] else "invalid",
          nf.P.ok if data["valid_syntax"] else nf.P.bad)
    if not data["valid_syntax"]:
        return
    nf.kv("domain", data["domain"])
    nf.kv("disposable", "yes" if data["disposable"] else "no",
          nf.P.bad if data["disposable"] else nf.P.ok)
    if data["mx"]:
        nf.kv("mx", ", ".join(data["mx"][:5]), nf.P.ok)
    else:
        nf.finding("MED", "no mx records found")
    if data["gravatar"]:
        nf.finding("LOW", "gravatar exists", data["gravatar"])
        prof = data.get("gravatar_profile") or {}
        for entry in (prof.get("entry") or [])[:1]:
            if entry.get("displayName"):
                nf.kv("gravatar name", entry["displayName"])
            if entry.get("preferredUsername"):
                nf.kv("gravatar user", entry["preferredUsername"])
    if data.get("emailrep"):
        rep = data["emailrep"]
        for key in ("reputation", "suspicious", "references", "details"):
            if key in rep:
                nf.kv(f"emailrep {key}", str(rep[key])[:100])
    else:
        nf.note("emailrep returned nothing usable")

def cmd_email(nf):
    email = nf.ask("email address")
    if not email:
        return
    nf.loading("checking email footprint")
    data = collect_email(nf, email)
    _print_email(nf, data)
    nf.save_report(f"email_{email.split('@')[0]}", data)

DIAL_CODES = {
    "1": ("US/CA", "North America"), "7": ("RU/KZ", "Russia/Kazakhstan"),
    "20": ("EG", "Egypt"), "27": ("ZA", "South Africa"), "30": ("GR", "Greece"),
    "31": ("NL", "Netherlands"), "32": ("BE", "Belgium"), "33": ("FR", "France"),
    "34": ("ES", "Spain"), "36": ("HU", "Hungary"), "39": ("IT", "Italy"),
    "40": ("RO", "Romania"), "41": ("CH", "Switzerland"), "43": ("AT", "Austria"),
    "44": ("GB", "United Kingdom"), "45": ("DK", "Denmark"), "46": ("SE", "Sweden"),
    "47": ("NO", "Norway"), "48": ("PL", "Poland"), "49": ("DE", "Germany"),
    "51": ("PE", "Peru"), "52": ("MX", "Mexico"), "54": ("AR", "Argentina"),
    "55": ("BR", "Brazil"), "56": ("CL", "Chile"), "57": ("CO", "Colombia"),
    "60": ("MY", "Malaysia"), "61": ("AU", "Australia"), "62": ("ID", "Indonesia"),
    "63": ("PH", "Philippines"), "64": ("NZ", "New Zealand"), "65": ("SG", "Singapore"),
    "66": ("TH", "Thailand"), "81": ("JP", "Japan"), "82": ("KR", "South Korea"),
    "84": ("VN", "Vietnam"), "86": ("CN", "China"), "90": ("TR", "Turkey"),
    "91": ("IN", "India"), "92": ("PK", "Pakistan"), "94": ("LK", "Sri Lanka"),
    "98": ("IR", "Iran"), "212": ("MA", "Morocco"), "213": ("DZ", "Algeria"),
    "216": ("TN", "Tunisia"), "218": ("LY", "Libya"), "234": ("NG", "Nigeria"),
    "254": ("KE", "Kenya"), "351": ("PT", "Portugal"), "353": ("IE", "Ireland"),
    "358": ("FI", "Finland"), "380": ("UA", "Ukraine"), "420": ("CZ", "Czechia"),
    "966": ("SA", "Saudi Arabia"), "971": ("AE", "UAE"), "972": ("IL", "Israel"),
    "994": ("AZ", "Azerbaijan"), "995": ("GE", "Georgia"),
}

def phone_profile(number):
    raw = number.strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    data = {"input": raw, "e164": digits, "valid": False, "region": None,
            "carrier": None, "timezone": None, "line_type": None, "source": None}
    try:
        import phonenumbers
        parsed = phonenumbers.parse(digits, None)
        if phonenumbers.is_valid_number(parsed):
            data.update({
                "valid": True,
                "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "region": phonenumbers.region_code_for_number(parsed),
                "carrier": phonenumbers.carrier.name_for_number(parsed, "en") or "unknown",
                "timezone": ", ".join(phonenumbers.timezone.time_zones_for_number(parsed)),
                "line_type": str(phonenumbers.number_type(parsed)),
                "source": "phonenumbers",
            })
            return data
    except Exception:
        pass
    if digits.startswith("+") and len(digits) >= 8:
        cc = None
        for size in (3, 2, 1):
            cand = digits[1:1 + size]
            if cand in DIAL_CODES:
                cc = cand
                break
        if cc:
            region, name = DIAL_CODES[cc]
            data.update({"valid": True, "region": f"{region} ({name})",
                         "source": "dial code table"})
    return data

def _print_phone(nf, data, number):
    nf.section(f"phone — {number}")
    nf.kv("e164", data.get("e164") or "-")
    nf.kv("valid", "yes" if data.get("valid") else "unverified",
          nf.P.ok if data.get("valid") else nf.P.warn)
    if data.get("region"):
        nf.kv("region", data["region"])
    if data.get("carrier"):
        nf.kv("carrier", data["carrier"])
    if data.get("timezone"):
        nf.kv("timezone", data["timezone"])
    if data.get("line_type"):
        nf.kv("line type", data["line_type"])
    nf.kv("source", data.get("source") or "-")
    nf.note("carrier data needs phonenumbers: pip install phonenumbers")

def cmd_phone(nf):
    number = nf.ask("phone number (+country code)")
    if not number:
        return
    nf.loading("parsing number")
    data = phone_profile(number)
    _print_phone(nf, data, number)
    reps = {
        "truecaller": f"https://www.truecaller.com/search/global/{data['e164'].lstrip('+')}",
        "sync.me": f"https://sync.me/search/?number={data['e164']}",
        "numlookup": f"https://www.numlookup.com/?number={data['e164']}",
    }
    nf.section("manual lookup endpoints")
    for name, url in reps.items():
        nf.kv(name, url)
    nf.save_report(f"phone_{re.sub(r'[^0-9]', '', number)}", data)

def _username_hits_quiet(nf, user):
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(_site_check, nf, (name, tpl.format(user)))
                   for name, tpl in SITES]
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except Exception:
                res = None
            if res:
                hits.append(res)
    return sorted(hits)

def cmd_dox_create(nf):
    nf.section("dox create")
    alias = nf.ask("alias / username")
    email = nf.ask("email")
    phone = nf.ask("phone")
    ip = nf.ask("ip / hostname")
    name = nf.ask("real name (optional)")
    if not any((alias, email, phone, ip, name)):
        return
    profile = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alias": alias, "name": name, "email": email, "phone": phone, "ip": ip,
        "usernames": [], "email_data": {}, "phone_data": {}, "ip_data": {},
        "accounts": [],
    }
    if alias:
        nf.loading("sweeping usernames")
        for uname in {alias, alias.replace(" ", ""), alias.lower()}:
            profile["usernames"].append(uname)
            profile["accounts"] += [{"site": s, "url": u, "username": uname}
                                    for s, u in _username_hits_quiet(nf, uname)]
    if email:
        profile["email_data"] = collect_email(nf, email)
    if phone:
        profile["phone_data"] = phone_profile(phone)
    if ip:
        host = ip
        try:
            host = socket.gethostbyname(ip)
        except Exception:
            pass
        r = nf.http(f"http://ip-api.com/json/{host}?fields=status,country,regionName,city,isp,org,as,proxy,hosting,query", nf.CFG)
        if not r.error:
            try:
                profile["ip_data"] = json.loads(r.text)
            except Exception:
                pass
    DOX_DIR = nf.writable_dir("dox")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (alias or email or ip or name))[:40]
    path = os.path.join(DOX_DIR, f"{slug or 'target'}.json")
    if nf.ask("save dox profile? (y/n)", "n").lower().startswith("y"):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2)
        nf.kv("saved", path)
    else:
        nf.note("dox profile not saved")
    nf.section("dox summary")
    nf.kv("accounts", len(profile["accounts"]))
    for acc in profile["accounts"][:20]:
        nf.finding("LOW", acc["site"], acc["url"])

def cmd_dox_tracker(nf):
    nf.section("dox tracker")
    DOX_DIR = nf.writable_dir("dox")
    files = sorted(f for f in os.listdir(DOX_DIR) if f.endswith(".json"))
    if not files:
        nf.finding("INFO", "no saved dox profiles")
        return
    for i, f in enumerate(files, 1):
        nf.kv(str(i), f)
    pick = nf.ask("profile number", "1")
    try:
        path = os.path.join(DOX_DIR, files[int(pick) - 1])
    except Exception:
        nf.finding("MED", "invalid selection")
        return
    with open(path, "r", encoding="utf-8") as fh:
        profile = json.load(fh)
    old = {(a["site"], a["username"]) for a in profile.get("accounts", [])}
    usernames = profile.get("usernames") or ([profile["alias"]] if profile.get("alias") else [])
    if not usernames:
        nf.finding("INFO", "profile has no username to track")
        return
    nf.loading("re-sweeping footprint")
    new = set()
    for uname in usernames:
        for site, _url in _username_hits_quiet(nf, uname):
            new.add((site, uname))
    added = sorted(new - old)
    lost = sorted(old - new)
    nf.section("diff")
    if not added and not lost:
        nf.finding("OK", "no changes since last run")
    for site, uname in added:
        nf.finding("OK", f"new account: {site}", uname)
    for site, uname in lost:
        nf.finding("MED", f"lost/removed: {site}", uname)
    for uname in usernames:
        for site in [s for s, u in added if u == uname]:
            profile["accounts"].append({"site": site, "username": uname, "url": ""})
    profile["accounts"] = [a for a in profile["accounts"]
                           if (a["site"], a["username"]) not in set(lost)]
    profile["checked"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if nf.ask("update saved dox profile? (y/n)", "n").lower().startswith("y"):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2)
        nf.finding("OK", "profile updated", path)
    else:
        nf.note("profile left unchanged")

MENU = {"osint": [
    ("Dox Create", cmd_dox_create),
    ("Dox Tracker", cmd_dox_tracker),
]}
