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


def _print_status(nf, code, body):
    ok = 200 <= code < 300
    nf.finding("OK" if ok else "MED", f"http {code}",
               "" if ok else str(body)[:160])
    return ok


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

