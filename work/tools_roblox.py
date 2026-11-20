"""Roblox tooling for nxtf0und."""

import json
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) nxtf0und/2.0"

def _cookie(value):
    value = value.strip()
    if value.startswith(".ROBLOSECURITY="):
        value = value.split("=", 1)[1]
    return value

def _rb(nf, cookie, method, url, payload=None, headers=None, retry_csrf=True):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if cookie:
        hdrs["Cookie"] = ".ROBLOSECURITY=" + cookie
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(400_000)
            try:
                parsed = json.loads(body) if body else None
            except Exception:
                parsed = body.decode("utf-8", "replace")[:400]
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as err:
        body = err.read(300_000)
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body.decode("utf-8", "replace")[:400]
        token = err.headers.get("x-csrf-token") if err.headers else None
        if retry_csrf and err.code == 403 and token:
            hdrs2 = dict(hdrs)
            hdrs2["X-CSRF-Token"] = token
            return _rb(nf, cookie, method, url, payload, hdrs2, retry_csrf=False)
        return err.code, parsed, dict(err.headers) if err.headers else {}
    except Exception as exc:
        return 0, {"error": str(exc)}, {}

def _print(nf, code, body):
    ok = 200 <= code < 300
    nf.finding("OK" if ok else "MED", f"http {code}",
               "" if ok else str(body)[:200])
    return ok

def _account(nf, cookie):
    code, body, _ = _rb(nf, cookie, "GET",
                        "https://users.roblox.com/v1/users/authenticated")
    if code != 200:
        _print(nf, code, body)
        return None
    nf.section("account")
    for key in ("id", "name", "displayName", "created", "description"):
        if key in body:
            nf.kv(key, body[key])
    uid = body.get("id")
    code, cur, _ = _rb(nf, cookie, "GET",
                       f"https://economy.roblox.com/v1/users/{uid}/currency")
    if code == 200 and isinstance(cur, dict):
        nf.kv("robux", cur.get("robux"))
    code, prem, _ = _rb(nf, cookie, "GET",
                        f"https://premiumfeatures.roblox.com/v1/users/{uid}/validate-membership")
    if code == 200:
        nf.kv("premium", prem)
    code, ticket, hdrs = _rb(nf, cookie, "POST",
                             "https://auth.roblox.com/v1/authentication-ticket",
                             payload={})
    if code in (200, 403):
        nf.kv("auth ticket", hdrs.get("RBX-Authentication-Ticket", "-")[:64])
    code, birthday, _ = _rb(nf, cookie, "GET",
                            "https://accountsettings.roblox.com/v1/birthdate")
    if code == 200 and isinstance(birthday, dict):
        nf.kv("birthdate", f"{birthday.get('birthMonth')}/{birthday.get('birthDay')}/{birthday.get('birthYear')}")
    return body

def cmd_cookie_login(nf):
    cookie = _cookie(nf.ask("roblox cookie (.ROBLOSECURITY)"))
    if not cookie:
        return
    nf.loading("authenticating")
    _account(nf, cookie)

def cmd_cookie_info(nf):
    cookie = _cookie(nf.ask("roblox cookie (.ROBLOSECURITY)"))
    if not cookie:
        return
    user = _account(nf, cookie)
    if user:
        nf.save_report(f"roblox_{user.get('id')}", user)

def _lookup_user(nf, query):
    query = query.strip().lstrip("@")
    if query.isdigit():
        code, body, _ = _rb(nf, "", "GET",
                            f"https://users.roblox.com/v1/users/{query}")
        if code == 200:
            return body
        _print(nf, code, body)
        return None
    code, body, _ = _rb(nf, "", "POST",
                        "https://users.roblox.com/v1/usernames/users",
                        payload={"usernames": [query], "excludeBannedUsers": False})
    if code != 200 or not body.get("data"):
        nf.finding("MED", "user not found", query)
        return None
    uid = body["data"][0]["id"]
    code, body, _ = _rb(nf, "", "GET", f"https://users.roblox.com/v1/users/{uid}")
    return body if code == 200 else None

def cmd_user_info(nf):
    query = nf.ask("roblox username or id")
    if not query:
        return
    nf.loading("resolving user")
    user = _lookup_user(nf, query)
    if not user:
        return
    uid = user["id"]
    nf.section("user")
    for key in ("id", "name", "displayName", "created", "description"):
        if key in user:
            nf.kv(key, user[key])
    code, followers, _ = _rb(nf, "", "GET",
                             f"https://friends.roblox.com/v1/users/{uid}/followers/count")
    if code == 200:
        nf.kv("followers", followers.get("count"))
    code, following, _ = _rb(nf, "", "GET",
                             f"https://friends.roblox.com/v1/users/{uid}/followings/count")
    if code == 200:
        nf.kv("following", following.get("count"))
    code, friends, _ = _rb(nf, "", "GET",
                           f"https://friends.roblox.com/v1/users/{uid}/friends/count")
    if code == 200:
        nf.kv("friends", friends.get("count"))
    nf.kv("avatar", f"https://www.roblox.com/users/{uid}/profile")
    nf.save_report(f"roblox_user_{uid}", user)

def cmd_id_info(nf):
    nf.section("what is this id?")
    nf.kv("1", "game / place id")
    nf.kv("2", "asset id")
    pick = nf.ask("choice", "1")
    value = nf.ask("id")
    if not value.isdigit():
        nf.finding("MED", "numeric id required")
        return
    if pick == "2":
        code, body, _ = _rb(nf, "", "GET",
                            f"https://economy.roblox.com/v2/assets/{value}/details")
        if code != 200:
            _print(nf, code, body)
            return
        nf.section("asset")
        for key in ("Name", "AssetTypeId", "Creator", "Created", "Updated", "IsLimited", "PriceInRobux"):
            if key in body:
                nf.kv(key, body[key])
        return
    code, body, _ = _rb(nf, "", "GET",
                        f"https://apis.roblox.com/universes/v1/places/{value}/universe")
    if code != 200:
        _print(nf, code, body)
        return
    universe = body.get("universeId")
    if not universe:
        nf.finding("MED", "no universe for that place")
        return
    nf.kv("universe id", universe)
    code, body, _ = _rb(nf, "", "GET",
                        f"https://games.roblox.com/v1/games?universeIds={universe}")
    if code == 200 and body.get("data"):
        game = body["data"][0]
        nf.section("game")
        for key in ("name", "creator", "playing", "visits", "favoritedCount",
                    "created", "updated", "maxPlayers", "genre", "price"):
            if key in game:
                nf.kv(key, game[key])
    code, votes, _ = _rb(nf, "", "GET",
                         f"https://games.roblox.com/v1/games/votes?universeIds={universe}")
    if code == 200 and votes.get("data"):
        nf.kv("votes", str(votes["data"][0]))

MENU = {"roblox": [
    ("Cookie Login", cmd_cookie_login),
    ("Cookie Info", cmd_cookie_info),
]}
