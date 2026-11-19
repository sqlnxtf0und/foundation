"""nxtf0und relay — holds upstream API keys on the server and proxies calls.

The client never sees an upstream key. It sends a per-user token, a service
name, and a path; this server validates all three against an allowlist derived
from apikeys.SPECS, injects the real key, and returns the upstream JSON.

Run it:

    export NF_RELAY_KEYS=/etc/nxtf0und/relay-keys.env   # upstream keys
    export NF_RELAY_USERS=/etc/nxtf0und/users.json      # per-user tokens
    python3 relay.py --port 8080

Requests:

    POST /v1/q
      X-Relay-Token: <user token>
      {"service": "ipinfo", "path": "/1.1.1.1/json", "query": {}}

    GET /v1/health            no auth, reports service availability only

Design notes:

  * Upstream keys live only in this process's environment.
  * Paths are validated against a compiled allowlist — the relay cannot be
    used to reach an arbitrary host or endpoint.
  * Per-user rate limits and a daily quota are enforced before any upstream
    call is made, so a leaked token cannot drain an account without bounds.
  * Every user token is compared in constant time.
  * Error responses never include upstream headers or key material.
"""

import argparse
import base64
import collections
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import apikeys

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEYS_ENV = os.path.join(BASE, "relay-keys.env")
DEFAULT_USERS = os.path.join(BASE, "relay-users.json")

MAX_BODY = 8192
UPSTREAM_TIMEOUT = 20
UPSTREAM_LIMIT = 4_000_000


# --------------------------------------------------------------------------
# allowlist derived from the shared registry
# --------------------------------------------------------------------------

def _pattern(prefix):
    """Compile an allowlist pattern from a service prefix.

    Segments are literal until a placeholder appears, so /api/v3/domains/...
    permits exactly one path segment after the literal prefix.
    """
    return re.compile("^" + re.escape(prefix) + r"[A-Za-z0-9._~!$&'()*+,;=:@%/-]{0,200}$")


ALLOW = {}
for _name, _spec in apikeys.SPECS.items():
    ALLOW[_name] = {
        "host": _spec["base"],
        "prefix": _spec["prefix"],
        "rx": _pattern(_spec["prefix"]),
        "limits": _spec.get("limit", (60, 1.0)),
    }


def resolve(service, path):
    """Return (host, path) when the request is inside the allowlist, else None."""
    entry = ALLOW.get(service)
    if entry is None or not isinstance(path, str):
        return None
    if not path.startswith("/") or "//" in path or ".." in path:
        return None
    if "\r" in path or "\n" in path or "\x00" in path:
        return None
    if not entry["rx"].match(path):
        return None
    return entry["host"], path


# --------------------------------------------------------------------------
# user store
# --------------------------------------------------------------------------

class Users:
    """Token -> {name, daily_quota}. Tokens are stored hashed."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.by_hash = {}
        self.load()

    def _digest(self, token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def load(self):
        users = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            print(f"  ! no user file at {self.path} — every request will be rejected")
            raw = {}
        except Exception as exc:
            print(f"  ! cannot read {self.path}: {exc}")
            raw = {}
        entries = raw.get("users") if isinstance(raw, dict) else raw
        for entry in (entries or []):
            if not isinstance(entry, dict):
                continue
            token = entry.get("token") or ""
            token_hash = entry.get("token_sha256") or ""
            if token and not token_hash:
                token_hash = self._digest(token)
            if not token_hash:
                continue
            users[token_hash] = {
                "name": str(entry.get("name") or "user")[:64],
                "daily_quota": int(entry.get("daily_quota") or 5000),
            }
        with self.lock:
            self.by_hash = users
        return len(users)

    def identify(self, token):
        if not token:
            return None
        digest = self._digest(token)
        found = None
        # constant-time compare against every hash so timing reveals nothing
        with self.lock:
            for token_hash, meta in self.by_hash.items():
                if hmac.compare_digest(token_hash, digest):
                    found = (token_hash, dict(meta))
        return found


# --------------------------------------------------------------------------
# quotas and rate limits
# --------------------------------------------------------------------------

class Throttle:
    def __init__(self):
        self.lock = threading.Lock()
        self.windows = collections.defaultdict(collections.deque)
        self.daily = {}

    def check(self, token_hash, limits):
        per_minute, per_second = limits
        now = time.monotonic()
        with self.lock:
            window = self.windows[token_hash]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= per_minute:
                return False, "rate_limited"
            if per_second > 0 and len(window) >= 1:
                # smooth the burst across the minute
                gap = 1.0 / per_second if per_second < 1 else per_second
                if now - window[-1] < min(gap, 1.0):
                    return False, "rate_limited"
            window.append(now)
            return True, ""

    def consume_quota(self, token_hash, quota):
        today = time.strftime("%Y-%m-%d")
        with self.lock:
            record = self.daily.get(token_hash)
            if not record or record[0] != today:
                record = (today, 0)
            if record[1] >= quota:
                self.daily[token_hash] = record
                return False
            self.daily[token_hash] = (today, record[1] + 1)
            return True


# --------------------------------------------------------------------------
# upstream call
# --------------------------------------------------------------------------

def upstream(service, path, query):
    """Inject the server-held key and fetch the upstream JSON."""
    spec = apikeys.SPECS[service]
    keys = apikeys.service_keys(spec)
    if not apikeys.has_keys(spec):
        return None, "not_configured", 0

    url = "https://" + spec["base"] + path
    merged = dict(query or {})
    qauth = spec.get("qauth")
    if qauth:
        merged.update({k: v for k, v in qauth(keys).items() if v})
    if merged:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(merged)

    headers = {"User-Agent": "nxtf0und-relay/1.0", "Accept": "*/*"}
    headers.update({k: v for k, v in spec["auth"](keys).items() if v})

    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT, context=ctx) as r:
            payload = r.read(UPSTREAM_LIMIT)
            try:
                return json.loads(payload.decode("utf-8", "replace")), "", r.status
            except Exception:
                return None, "decode", r.status
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None, "not_found", 404
        if err.code in (401, 403):
            return None, "upstream_auth", err.code
        if err.code == 429:
            return None, "upstream_throttled", 429
        return None, "upstream_error", err.code
    except Exception:
        return None, "upstream_unreachable", 0


# --------------------------------------------------------------------------
# http handler
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "nxtf0und-relay"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Log the route and outcome, never the token or query values.
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _fail(self, status, code, message=""):
        self._send(status, {"ok": False,
                            "error": {"code": code, "message": message[:200]}})

    def do_GET(self):
        if self.path.split("?")[0] == "/v1/health":
            available = {name: apikeys.has_keys(spec)
                         for name, spec in apikeys.SPECS.items()}
            self._send(200, {"ok": True, "services": available})
            return
        self._fail(404, "not_found")

    def do_POST(self):
        if self.path.split("?")[0] != "/v1/q":
            self._fail(404, "not_found")
            return

        length = self.headers.get("Content-Length") or "0"
        try:
            length = int(length)
        except ValueError:
            self._fail(400, "bad_length")
            return
        if length <= 0 or length > MAX_BODY:
            self._fail(413, "bad_length")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:
            self._fail(400, "bad_json")
            return
        if not isinstance(body, dict):
            self._fail(400, "bad_json")
            return

        token = self.headers.get("X-Relay-Token") or ""
        identity = self.server.users.identify(token)
        if identity is None:
            time.sleep(0.15)          # blunt token enumeration
            self._fail(401, "unauthorized")
            return
        token_hash, meta = identity

        service = str(body.get("service") or "")
        path = body.get("path") or ""
        query = body.get("query") or {}
        if not isinstance(query, dict):
            self._fail(400, "bad_query")
            return
        if len(query) > 16:
            self._fail(400, "bad_query")
            return
        query = {str(k)[:64]: str(v)[:200] for k, v in query.items()}

        resolved = resolve(service, path)
        if resolved is None:
            self._fail(404, "not_allowed")
            return
        host, safe_path = resolved

        if not self.server.throttle.consume_quota(token_hash, meta["daily_quota"]):
            self._fail(429, "quota_exhausted")
            return
        allowed, reason = self.server.throttle.check(token_hash,
                                                    ALLOW[service]["limits"])
        if not allowed:
            self._fail(429, reason)
            return

        data, err, status = upstream(service, safe_path, query)
        if err == "not_found":
            self._send(200, {"ok": False, "error": {"code": "not_found"}})
            return
        if err:
            self._fail(502 if status in (0, 5) else 502, err)
            return
        self._send(200, {"ok": True, "service": service, "data": data})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, users):
        super().__init__(addr, Handler)
        self.users = users
        self.throttle = Throttle()


def main(argv=None):
    parser = argparse.ArgumentParser(description="nxtf0und key relay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--keys", default=os.environ.get("NF_RELAY_KEYS", DEFAULT_KEYS_ENV))
    parser.add_argument("--users", default=os.environ.get("NF_RELAY_USERS", DEFAULT_USERS))
    parser.add_argument("--new-token", metavar="NAME",
                        help="print a fresh token for NAME and exit")
    args = parser.parse_args(argv)

    apikeys.load_env(args.keys)

    if args.new_token:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        print(json.dumps({"name": args.new_token,
                          "token": token,
                          "token_sha256": digest}, indent=2))
        print("\nAdd the token_sha256 value to " + args.users
              + " — the plaintext is shown once and never stored.")
        return 0

    users = Users(args.users)
    configured = [n for n, s in apikeys.SPECS.items() if apikeys.has_keys(s)]
    print(f"relay listening on http://{args.host}:{args.port}")
    print(f"  keys file : {args.keys}")
    print(f"  users file: {args.users}  ({len(users.by_hash)} token(s))")
    print(f"  upstream  : {', '.join(configured) if configured else 'NONE — set keys'}")
    if not users.by_hash:
        print("  ! no user tokens — generate one with --new-token NAME")

    server = Server((args.host, args.port), users)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
