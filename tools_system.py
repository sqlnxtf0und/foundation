"""System info and anonymity utilities."""

import base64
import json
import os
import random
import shutil
import socket
import string
import sys
import time
import urllib.request
import zlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def cmd_info(nf):
    nf.section("about nxtf0und")
    nf.kv("name", "nxtf0und")
    nf.kv("engine", f"python {sys.version.split()[0]}")
    nf.kv("display", f"theme: {nf.CFG.get('theme', 'lightblue')}")
    nf.kv("root", BASE_DIR)
    nf.kv("themes", ", ".join(nf.THEMES.keys()))
    nf.kv("modules", "osint, network, web, utilities, builders, discord, roblox, advanced")
    nf.kv("reports", os.path.join(BASE_DIR, "reports"))
    nf.kv("builds", os.path.join(BASE_DIR, "builds"))
    nf.kv("dox", os.path.join(BASE_DIR, "dox"))
    nf.kv("loot", os.path.join(BASE_DIR, "loot"))
    nf.note("network work needs outbound http; sniffer and some modules need root")

def cmd_site(nf):
    nf.section("site / local files")
    entries = ["main.py", "tools_osint.py", "tools_scan.py", "tools_extra.py",
               "tools_hunt.py", "tools_utils.py", "tools_discord.py",
               "tools_roblox.py", "tools_advanced.py", "tools_system.py",
               "install_pack.py", "requirements.txt", "settings.json"]
    for name in entries:
        path = os.path.join(BASE_DIR, name)
        state = "present" if os.path.exists(path) else "missing"
        nf.kv(name, state, nf.P.ok if state == "present" else nf.P.bad)
    nf.section("quick commands")
    nf.kv("run", "python3 main.py")
    nf.kv("fast", "python3 main.py --no-anim")
    nf.kv("install deps", "pip install -r requirements.txt")
    nf.kv("open reports", f"xdg-open {os.path.join(BASE_DIR, 'reports')}")
    nf.kv("open builds", f"xdg-open {os.path.join(BASE_DIR, 'builds')}")

def _socks_available(host="127.0.0.1", port=9050, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def cmd_anonymization(nf):
    nf.section("anonymization software")
    tor = _socks_available()
    nf.kv("tor socks 127.0.0.1:9050", "open" if tor else "closed",
          nf.P.ok if tor else nf.P.warn)
    if tor:
        try:
            import socks
            import requests
            session = requests.Session()
            session.proxies = {"http": "socks5h://127.0.0.1:9050",
                               "https": "socks5h://127.0.0.1:9050"}
            r = session.get("https://check.torproject.org/api/ip", timeout=20)
            data = r.json()
            nf.kv("tor exit ip", data.get("IP", "-"))
            nf.kv("is tor", data.get("IsTor"), nf.P.ok if data.get("IsTor") else nf.P.bad)
        except ImportError:
            nf.note("pip install pysocks to route through tor from python")
        except Exception as exc:
            nf.finding("MED", "tor check failed", str(exc))
    else:
        nf.note("start tor: sudo systemctl start tor  (or tor &)")
    section_ip = nf.http("https://api.ipify.org?format=json", nf.CFG)
    if not section_ip.error:
        try:
            nf.kv("direct ip", json.loads(section_ip.text).get("ip", "-"))
        except Exception:
            pass
    nf.section("quick hygiene")
    nf.kv("browser fingerprint", "use tor browser for anything sensitive")
    nf.kv("dns leak", "check dnsleaktest.com through the tunnel")
    nf.kv("mac", ":".join(f"{random.randrange(256):02x}" for _ in range(6))
          + "  (random example, not applied)")
    nf.note("route tools manually: export ALL_PROXY=socks5h://127.0.0.1:9050")
