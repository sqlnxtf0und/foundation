"""Utilities for nxtf0und."""

import base64
import hashlib
import http.server
import ipaddress
import os
import random
import re
import secrets
import shutil
import socketserver
import string
import struct
import time
import urllib.parse


def _md4(data: bytes) -> bytes:
    def left_rotate(x, n):
        x &= 0xFFFFFFFF
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    msg = bytearray(data)
    ml = len(data) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", ml)
    a, b, c, d = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    for off in range(0, len(msg), 64):
        x = list(struct.unpack("<16I", msg[off:off + 64]))
        aa, bb, cc, dd = a, b, c, d
        for i in range(16):
            k = i
            s = [3, 7, 11, 19][i % 4]
            f = (b & c) | (~b & d)
            a = left_rotate(a + f + x[k], s)
            a, b, c, d = d, a, b, c
        for i in range(16):
            k = (i % 4) * 4 + (i // 4)
            s = [3, 5, 9, 13][i % 4]
            g = (b & c) | (b & d) | (c & d)
            a = left_rotate(a + g + x[k] + 0x5A827999, s)
            a, b, c, d = d, a, b, c
        for i in range(16):
            k = [0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15][i]
            s = [3, 9, 11, 15][i % 4]
            h = b ^ c ^ d
            a = left_rotate(a + h + x[k] + 0x6ED9EBA1, s)
            a, b, c, d = d, a, b, c
        a = (a + aa) & 0xFFFFFFFF
        b = (b + bb) & 0xFFFFFFFF
        c = (c + cc) & 0xFFFFFFFF
        d = (d + dd) & 0xFFFFFFFF
    return struct.pack("<4I", a, b, c, d)

def _ntlm(password: str) -> str:
    return _md4(password.encode("utf-16-le")).hex()

BUILTIN_WORDS = """
password 123456 12345678 qwerty 123456789 12345 1234 111111 1234567 dragon
123123 baseball abc123 football monkey letmein shadow master 666666 qwertyuiop
123321 mustang 1234567890 michael 654321 pussy superman 1qaz2wsx 7777777
fuckyou 121212 000000 qazwsx 123qwe killer trustno1 jordan jennifer zxcvbnm
asdfgh hunter buster soccer harley batman andrew tigger sunshine iloveyou
fuckme 2000 charlie robert thomas hockey ranger daniel starwars klaster 112233
george asshole computer michelle jessica pepper 1111 zxcvbn 555555 11111111
131313 freedom 777777 pass fuckmylife maggie 159753 aaaaaa ginger princess
joshua cheese amanda summer love ashley 6969 nicole chelsea biteme matthew
access yankees 987654321 dallas austin thunder taylor matrix william corvette
hello martin heather secret fucker merlin diamond 1234qwer gfhjkm hammer
silver 222222 88888888 anthony justin test bailey q1w2e3r4 patrick internet
scooter orange 11111 golfer cookie richard samantha bigdog guitar jackson
whatever mickey chicken sparky snoopy maverick phoenix camaro sexy peanut
morgan welcome falcon cowboy ferrari samsung andrea smokey steelers joseph
mercedes dakota arsenal eagles melissa boomer booboo spider nascar monster
tigers yellow xxxxxx 123123123 gateway marina diablo bulldog qwer1234 compaq
purple hardcore banana junior hannah 123654 porsche lakers iceman money
cowboys 987654 london tennis999 ncc1701 coffee scooby 0000 miller boston
q1w2e3r4t5 viking skipper pitcher montana knicks tomcat eleven nintendo
""".split()

def _variants(word):
    yield word
    yield word.lower()
    yield word.upper()
    yield word.capitalize()
    yield word + "1"
    yield word + "123"
    yield word + "!"
    yield word + "2024"
    yield word + "2025"
    yield word + "2026"
    leet = word.replace("a", "@").replace("e", "3").replace("i", "1").replace("o", "0").replace("s", "$")
    if leet != word:
        yield leet

def cmd_hash_crack(nf):
    nf.section("password decrypted attack")
    target = nf.ask("hash")
    if not target:
        return
    algo = nf.ask("algorithm (auto/md5/sha1/sha256/sha512/ntlm)", "auto")
    wordlist = nf.ask("wordlist path (blank = rockyou/builtin)", "")
    algo = algo.lower().strip()
    hashers = {}
    if algo == "auto":
        if re.fullmatch(r"[a-fA-F0-9]{32}", target):
            hashers = {"md5": lambda s: hashlib.md5(s.encode()).hexdigest(),
                       "ntlm": _ntlm}
        elif re.fullmatch(r"[a-fA-F0-9]{40}", target):
            hashers = {"sha1": lambda s: hashlib.sha1(s.encode()).hexdigest()}
        elif re.fullmatch(r"[a-fA-F0-9]{64}", target):
            hashers = {"sha256": lambda s: hashlib.sha256(s.encode()).hexdigest()}
        elif re.fullmatch(r"[a-fA-F0-9]{128}", target):
            hashers = {"sha512": lambda s: hashlib.sha512(s.encode()).hexdigest()}
        else:
            nf.finding("MED", "unknown hash shape")
            return
    else:
        map_ = {"md5": hashlib.md5, "sha1": hashlib.sha1,
                "sha256": hashlib.sha256, "sha512": hashlib.sha512}
        if algo == "ntlm":
            hashers = {"ntlm": _ntlm}
        elif algo in map_:
            fn = map_[algo]
            hashers = {algo: lambda s, fn=fn: fn(s.encode()).hexdigest()}
        else:
            nf.finding("MED", "unsupported algorithm")
            return
    words = []
    if wordlist and os.path.isfile(wordlist):
        try:
            with open(wordlist, "r", encoding="utf-8", errors="ignore") as fh:
                words = [ln.strip() for ln in fh if ln.strip()]
        except Exception as exc:
            nf.finding("MED", "wordlist unreadable", str(exc))
    if not words:
        default_wl = "/usr/share/wordlists/rockyou.txt"
        rockyou = "/usr/share/wordlists/rockyou.txt.gz"
        if os.path.isfile(default_wl):
            with open(default_wl, "r", encoding="utf-8", errors="ignore") as fh:
                words = [ln.strip() for ln in fh if ln.strip()]
        elif os.path.isfile(rockyou):
            import gzip
            with gzip.open(rockyou, "rt", encoding="utf-8", errors="ignore") as fh:
                words = [ln.strip() for ln in fh if ln.strip()]
        else:
            words = BUILTIN_WORDS[:]
            nf.note("rockyou not found — using builtin list")
    nf.section("cracking")
    nf.kv("hash", target)
    nf.kv("algorithms", ", ".join(hashers))
    nf.kv("candidates", len(words))
    lower = target.lower()
    start = time.time()
    attempts = 0
    found = None
    try:
        for word in words:
            for cand in _variants(word):
                attempts += 1
                for name, fn in hashers.items():
                    if fn(cand) == lower:
                        found = (cand, name)
                        break
                if found:
                    break
            if found:
                break
            if attempts % 20000 == 0:
                rate = attempts / max(0.001, time.time() - start)
                print("  " + nf.P.dim(f"{attempts} tries  {rate:,.0f}/s"))
    except KeyboardInterrupt:
        nf.note("stopped early")
    elapsed = time.time() - start
    nf.section("result")
    nf.kv("attempts", attempts)
    nf.kv("time", f"{elapsed:.2f}s")
    nf.kv("rate", f"{attempts / max(0.001, elapsed):,.0f}/s")
    if found:
        nf.finding("OK", f"password: {found[0]}", found[1])
    else:
        nf.finding("MED", "not in wordlist")

def _entropy(pw):
    pool = 0
    if re.search(r"[a-z]", pw):
        pool += 26
    if re.search(r"[A-Z]", pw):
        pool += 26
    if re.search(r"\d", pw):
        pool += 10
    if re.search(r"[^A-Za-z0-9]", pw):
        pool += 32
    if pool == 0:
        return 0
    import math
    return round(len(pw) * math.log2(pool), 1)

def cmd_password_encrypt(nf):
    nf.section("password encrypted")
    nf.kv("1", "generate password")
    nf.kv("2", "hash password (pbkdf2)")
    nf.kv("3", "verify password")
    pick = nf.ask("choice", "1")
    if pick == "1":
        length = nf.ask("length", "20")
        try:
            length = max(6, min(128, int(length)))
        except ValueError:
            length = 20
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.?"
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        nf.section("generated")
        nf.kv("password", pw, nf.P.ok)
        nf.kv("entropy", f"{_entropy(pw)} bits")
        nf.kv("sha256", hashlib.sha256(pw.encode()).hexdigest())
    elif pick == "2":
        pw = nf.ask("password")
        if not pw:
            return
        iterations = nf.ask("iterations", "260000")
        try:
            iterations = max(10000, int(iterations))
        except ValueError:
            iterations = 260000
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)
        blob = base64.b64encode(salt + digest).decode()
        nf.section("hashed")
        nf.kv("iterations", iterations)
        nf.kv("salt", base64.b64encode(salt).decode())
        nf.kv("pbkdf2", blob, nf.P.ok)
        nf.kv("entropy", f"{_entropy(pw)} bits")
    else:
        pw = nf.ask("password")
        blob = nf.ask("stored blob")
        iterations = nf.ask("iterations", "260000")
        try:
            raw = base64.b64decode(blob)
            salt, digest = raw[:16], raw[16:]
            test = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, int(iterations))
            nf.finding("OK" if test == digest else "HIGH",
                       "match" if test == digest else "does not match")
        except Exception as exc:
            nf.finding("MED", "verification failed", str(exc))

DB_EXTS = {".txt", ".csv", ".json", ".sql", ".log", ".md", ".dat", ".lst"}

def cmd_db_search(nf):
    nf.section("search in database")
    query = nf.ask("query")
    if not query:
        return
    root = nf.ask("directory", os.path.join(os.path.dirname(os.path.abspath(__file__)), "db"))
    if not os.path.isdir(root):
        nf.finding("HIGH", "directory not found", root)
        return
    q = query.lower()
    hits = 0
    files = 0
    nf.section("matches")
    for base, _dirs, names in os.walk(root):
        for name in names:
            if os.path.splitext(name)[1].lower() not in DB_EXTS:
                continue
            path = os.path.join(base, name)
            files += 1
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if q in line.lower():
                            hits += 1
                            if hits <= 60:
                                nf.kv(f"{os.path.relpath(path, root)}:{lineno}",
                                      line.strip()[:160])
                            if hits >= 500:
                                break
            except Exception:
                continue
            if hits >= 500:
                break
        if hits >= 500:
            break
    nf.finding("OK" if hits else "INFO", f"{hits} hit(s) across {files} file(s)")

DARKWEB = {
    "search": [
        ("Ahmia", "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion", "clearnet index of onion services"),
        ("Torch", "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion", "long-running onion index"),
        ("DuckDuckGo", "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion", "search with onion results"),
    ],
    "news": [
        ("BBC News", "https://www.bbcnewsd73hkzno2ini43t4gblxvycyac5aw4gnv7t2rccijh7745uqd.onion", "tor mirror"),
        ("ProPublica", "https://p53lf57qovyuvwsc6xnrppyply3vtqm7l6pcobkmyqsiofyeznfu5uqd.onion", "tor mirror"),
        ("The New York Times", "https://ej3kv4ebuugcmuwxctx5ic7zxh73rnxt42soi3tdneu2c2em55thufqd.onion", "tor mirror"),
    ],
    "security": [
        ("Tor Project", "http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion", "official project onion"),
        ("SecureDrop", "http://sdolvtfhatvsysc6l34d65ymdwxcujausv7k5jk4cy5ttzh365rztid.onion", "whistleblower drop index"),
        ("Riseup", "http://vww6ybal4bd7szmgncyruucpgfkqahzddi37ktceo3ah7ngmcopnpyyd.onion", "mail + vpn collective"),
        ("Mullvad", "http://o54hon2e2vj6c7m3aqqu6uyece65by3vgoxxhlqlsvkmacw6a7m7kiad.onion", "vpn provider mirror"),
        ("ProtonMail", "https://protonmailrmez3lotccipshtkleegetolb73fuirgj7r4vpqe2kp4qwmad.onion", "mail mirror"),
    ],
    "markets (verify current mirrors)": [
        ("Dread", "http://dreadytofatroptsdj6io7l3xptbet6onoyno2yv7jicoxknyazubrad.onion", "reddit-style darknet forum"),
        ("Bohemia", "http://bohemiaobr2jcm3mkwqrzoqxjhvc3qlt4lnsnjne5mxuwvrb2egqpxqd.onion", "marketplace"),
        ("ASAP", "http://asap4u7p2eypzj2j2ewuwbjx2drwm5xrch4lwo5n5c4ybxpxjgw3eid.onion", "marketplace"),
        ("Incognito", "http://incognitj5w3r7x6i5p2fomxq5jq3mno5ccrbvtkjqf6zqgw5rq7evad.onion", "marketplace"),
    ],
    "infrastructure": [
        ("Hidden Wiki", "http://zqktlwiuavvvqqt4ybvgvi7tyo4hjl5xgfuvpdf6otjiycgwqbym2qad.onion", "directory"),
        ("OnionMail", "http://onionmailvrgq5pnrjwmnpoxddbxr4jxd23nbyx2jmj55k3zcjdfwvyid.onion", "mail provider"),
        ("Keybase", "http://keybase5wmilwokqirssclfnsqrjdsi7jdir5wy7y7iu3tanwmtp6oid.onion", "identity mirror"),
    ],
}

def cmd_darkweb(nf):
    nf.section("dark web links")
    labels = list(DARKWEB)
    for i, name in enumerate(labels, 1):
        nf.kv(str(i), name)
    pick = nf.ask("category (blank = all)", "")
    wanted = [labels[int(pick) - 1]] if pick.isdigit() and 1 <= int(pick) <= len(labels) else labels
    for cat in wanted:
        nf.section(cat)
        for name, url, desc in DARKWEB[cat]:
            nf.kv(name, url, nf.P.sec)
            nf.note(f"    {desc}")
    nf.note("open in tor browser: tor-browser <url>")

def _public_ip(rng):
    while True:
        value = struct.unpack(">I", bytes(rng.getrandbits(8) for _ in range(4)))[0]
        try:
            ip = ipaddress.IPv4Address(value)
        except Exception:
            continue
        if ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_reserved \
                or ip.is_link_local or ip.is_unspecified:
            continue
        return str(ip)

def cmd_ip_generator(nf):
    nf.section("ip generator")
    count = nf.ask("count", "10")
    kind = nf.ask("ip / mac / both", "both")
    try:
        count = max(1, min(1000, int(count)))
    except ValueError:
        count = 10
    rng = random.SystemRandom()
    out = []
    nf.section("generated")
    for _ in range(count):
        row = {}
        if kind in ("ip", "both"):
            row["ip"] = _public_ip(rng)
        if kind in ("mac", "both"):
            row["mac"] = ":".join(f"{rng.randrange(256):02x}" for _ in range(6))
        out.append(row)
        nf.kv(f"{len(out):>4}", "  ".join(row.values()))
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(path, exist_ok=True)
    fname = os.path.join(path, f"ipgen_{time.strftime('%Y%m%d-%H%M%S')}.csv")
    if nf.ask("save list? (y/n)", "n").lower().startswith("y"):
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write(",".join(out[0].keys()) + "\n")
            for row in out:
                fh.write(",".join(row.values()) + "\n")
        nf.finding("OK", "saved", fname)
    else:
        nf.note("list not saved")

CLONE_REF_RE = re.compile(
    r"""(?P<attr>src|href)\s*=\s*(?P<q>["'])(?P<attr_url>[^"']+)(?P=q)"""
    r"""|url\(\s*(?P<q2>["']?)(?P<css_url>[^"')]+)(?P=q2)\s*\)""",
    re.I,
)

CLONE_SKIP_PREFIX = ("data:", "javascript:", "mailto:", "tel:", "#", "blob:", "about:")

CLONE_EXT = (
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm",
)

CLONE_MAX_ASSETS = 60
CLONE_MAX_BYTES = 2 * 1024 * 1024

def _clone_name(url, index):
    path = urllib.parse.urlparse(url).path
    base = os.path.basename(path) or f"asset{index}"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:64] or f"asset{index}"
    if not os.path.splitext(base)[1]:
        base += ".bin"
    return f"{index:03d}_{base}"

def _clone_refs(html, base_url):
    """Yield (absolute_url, kind) for every asset reference in the document."""
    seen = set()
    for match in CLONE_REF_RE.finditer(html):
        raw = match.group("attr_url") or match.group("css_url") or ""
        raw = raw.strip().strip("'\"")
        if not raw or raw.lower().startswith(CLONE_SKIP_PREFIX):
            continue
        absolute = urllib.parse.urljoin(base_url, raw)
        absolute, _frag = urllib.parse.urldefrag(absolute)
        if absolute in seen:
            continue
        seen.add(absolute)
        yield absolute

def clone_site(nf, url, max_assets=CLONE_MAX_ASSETS):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "site"
    page = nf.http(url, nf.CFG, body_limit=3_000_000)
    if page.error:
        return None, page.error
    html = page.text
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", host)[:40]
    root = os.path.join(nf.writable_dir("builds"), f"clone_{slug}")
    assets_dir = os.path.join(root, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    mapping = {}
    saved = 0
    skipped = 0
    for absolute in _clone_refs(html, page.url):
        if saved >= max_assets:
            skipped += 1
            continue
        path = urllib.parse.urlparse(absolute).path.lower()
        ext = os.path.splitext(path)[1]
        if ext and ext not in CLONE_EXT:
            skipped += 1
            continue
        if ext == "" and not absolute.rstrip("/").endswith((".js", ".css")):
            skipped += 1
            continue
        res = nf.http(absolute, nf.CFG, body_limit=CLONE_MAX_BYTES,
                      timeout=max(8, nf.CFG["timeout"]))
        if res.error or res.status >= 400 or not res.raw:
            skipped += 1
            continue
        name = _clone_name(absolute, saved + 1)
        try:
            with open(os.path.join(assets_dir, name), "wb") as fh:
                fh.write(res.raw)
        except Exception:
            skipped += 1
            continue
        mapping[absolute] = f"assets/{name}"
        saved += 1
        print("  " + nf.P.ok("◆") + " " + nf.P.sec(f"{name:<38}") + nf.P.dim(f"{len(res.raw):,} B"))

    def rewrite(match):
        raw = match.group("attr_url") or match.group("css_url") or ""
        token = raw.strip().strip("'\"")
        if not token or token.lower().startswith(CLONE_SKIP_PREFIX):
            return match.group(0)
        absolute, _ = urllib.parse.urldefrag(urllib.parse.urljoin(page.url, token))
        local = mapping.get(absolute)
        if not local:
            return match.group(0)
        if match.group("attr_url") is not None:
            return f'{match.group("attr")}={match.group("q")}{local}{match.group("q")}'
        return f'url({match.group("q2")}{local}{match.group("q2")})'

    output = CLONE_REF_RE.sub(rewrite, html)
    banner = (f"<!-- cloned from {url} — {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n")
    index_path = os.path.join(root, "index.html")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(banner + output)
    return {"root": root, "index": index_path, "host": host, "saved": saved,
            "skipped": skipped, "assets": mapping}, None

def cmd_site_clone(nf):
    nf.section("website cloner")
    raw = nf.ask("target url")
    if not raw:
        return
    url = nf.normalize_url(raw)
    cap = nf.ask("max assets", str(CLONE_MAX_ASSETS))
    try:
        cap = max(1, min(300, int(cap)))
    except ValueError:
        cap = CLONE_MAX_ASSETS
    nf.loading("pulling page")
    result, error = clone_site(nf, url, cap)
    if error:
        nf.finding("HIGH", "clone failed", str(error)[:160])
        return
    nf.section("clone summary")
    nf.kv("host", result["host"])
    nf.kv("assets saved", result["saved"], nf.P.ok if result["saved"] else nf.P.warn)
    nf.kv("references skipped", result["skipped"])
    nf.kv("index", result["index"])
    nf.kv("assets dir", os.path.join(result["root"], "assets"))
    nf.note(f"serve it: python3 -m http.server 8080 --directory {result['root']}")
    nf.note("static mirror only — server-side logic, auth and dynamic calls stay on the origin")


