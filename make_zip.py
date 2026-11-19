"""Build a clean distributable zip of the tool.

    python3 make_zip.py                  # foundation-<version>.zip
    python3 make_zip.py --pack ./folder  # pack zip with pack.json at the root
    python3 make_zip.py --check FILE.zip # inspect an existing archive

The default build contains only the free tool: no .env, no settings.json,
no pack.json, no paid modules, no backups, no reports.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))

TOOL_FILES = (
    "main.py",
    "apikeys.py",
    "relay.py",
    "install_pack.py",
    "build_protected.py",
    "tools_osint.py",
    "tools_scan.py",
    "tools_extra.py",
    "tools_hunt.py",
    "tools_utils.py",
    "tools_discord.py",
    "tools_roblox.py",
    "tools_advanced.py",
    "tools_system.py",
    "requirements.txt",
    "README.md",
    "INSTALL.md",
    "DISCLAIMER.md",
    "LICENSE",
    "version.json",
    "settings.example.json",
    ".env.example",
    "relay-keys.example.env",
    "relay-users.example.json",
)

# Never ship these, whatever else changes.
FORBIDDEN_NAMES = {
    ".env", "settings.json", "pack.json", "relay-keys.env", "relay-users.json",
    "AGENTS.md",
}

# Content that must never appear inside a shipped file.
SECRET_PATTERNS = (
    (re.compile(r"[0-9a-fA-F]{64}"), "64-char hex (api key)"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
     "uuid-shaped key"),
    (re.compile(r"(sk|pk)_(live|test)?_?[A-Za-z0-9]{16,}"), "stripe-style key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "slack token"),
    (re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"), "private key block"),
)

# Words that mark a line as documentation rather than a real credential.
# Kept to unambiguous markers: a broad filter like "here" would skip almost
# every source line and leave the scan useless.
PLACEHOLDER = re.compile(
    r"(your[_-]|<[a-z_ -]*key|xxx+|placeholder|example|changeme|dummy|"
    r"redacted|\bnone\b|\bnull\b|\bfalse\b|\btrue\b)", re.I)


def version():
    try:
        with open(os.path.join(BASE, "version.json"), "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "0")
    except (OSError, ValueError):
        return "0"


def _scan(path, data):
    """Return a list of (pattern label, line number) hits in a file."""
    hits = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if PLACEHOLDER.search(line):
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(line):
                hits.append((label, lineno))
    return hits


def _add(zf, path, arcname):
    with open(path, "rb") as fh:
        data = fh.read()
    hits = _scan(path, data)
    if hits:
        detail = ", ".join(f"{label} line {line}" for label, line in hits[:3])
        raise SystemExit(f"refusing to ship {arcname}: possible secret ({detail})")
    zf.writestr(arcname, data)
    return len(data)


def build_tool(out_path):
    missing = [n for n in TOOL_FILES if not os.path.isfile(os.path.join(BASE, n))]
    if missing:
        raise SystemExit("missing files: " + ", ".join(missing))
    total = 0
    added = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in TOOL_FILES:
            if os.path.basename(name) in FORBIDDEN_NAMES:
                raise SystemExit(f"refusing to ship {name}")
            size = _add(zf, os.path.join(BASE, name), name)
            total += size
            added.append(name)
    return added, total


def build_pack(src_dir, out_path):
    """Zip a pack folder with pack.json at the archive root."""
    src_dir = os.path.abspath(src_dir)
    marker = os.path.join(src_dir, "pack.json")
    if not os.path.isfile(marker):
        raise SystemExit(f"no pack.json in {src_dir}")
    with open(marker, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    modules = manifest.get("files")
    if not isinstance(modules, dict) or not modules:
        raise SystemExit("pack.json lists no files")

    total = 0
    added = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        raw = open(marker, "rb").read()
        zf.writestr("pack.json", raw)
        total += len(raw)
        added.append("pack.json")
        for name, digest in modules.items():
            if os.path.basename(name) != name:
                raise SystemExit(f"invalid module name: {name}")
            path = os.path.join(src_dir, name)
            if not os.path.isfile(path):
                raise SystemExit(f"missing module: {name}")
            data = open(path, "rb").read()
            actual = hashlib.sha256(data).hexdigest()
            if actual != digest:
                print(f"  warning: {name} hash differs from pack.json, updating manifest")
                manifest["files"][name] = actual
            zf.writestr(name, data)
            total += len(data)
            added.append(name)
        zf.writestr("pack.json", json.dumps(manifest, indent=2))
    return added, total


def check(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        print(f"archive: {os.path.basename(zip_path)}")
        print(f"entries: {len(names)}")
        secrets = [n for n in names if os.path.basename(n) in FORBIDDEN_NAMES]
        print(f"secret files: {secrets or 'none'}")
        problems = []
        for name in names:
            if name.endswith("/"):
                continue
            for label, line in _scan(name, zf.read(name)):
                problems.append(f"{name}:{line} {label}")
        print(f"secret-like content: {problems or 'none'}")
        has_marker = "pack.json" in names or any(
            n.endswith("/pack.json") for n in names)
        print(f"pack.json present: {has_marker}")
        return 1 if secrets or problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="build a distributable zip")
    parser.add_argument("--pack", metavar="DIR", help="zip a pack folder instead")
    parser.add_argument("--check", metavar="ZIP", help="inspect an archive")
    parser.add_argument("-o", "--out", help="output path")
    args = parser.parse_args(argv)

    if args.check:
        return check(args.check)

    if args.pack:
        src = args.pack
        name = os.path.basename(os.path.abspath(src)) or "pack"
        out = args.out or os.path.join(BASE, f"{name}.zip")
        added, total = build_pack(src, out)
    else:
        out = args.out or os.path.join(BASE, f"foundation-{version()}.zip")
        added, total = build_tool(out)

    print(f"wrote {out}")
    print(f"files: {len(added)}  raw: {total / 1024:.1f} KiB  "
          f"zip: {os.path.getsize(out) / 1024:.1f} KiB")
    for name in added:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
