"""Install or remove an extension pack."""

import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile

MARKER = "pack.json"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _base_version(base_dir):
    path = os.path.join(base_dir, "main.py")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            match = re.search(r'^VERSION = "([^"]+)"', fh.read(), re.M)
        return match.group(1) if match else ""
    except OSError:
        return ""


def _find_prefix(zf):
    """Locate pack.json at the archive root or inside a single folder.

    Zip tools differ: `zip -r p.zip files/` nests everything under a
    directory, while `zip -r p.zip .` keeps it flat. Accept both, but only
    when the marker is unambiguous.
    """
    names = zf.namelist()
    if MARKER in names:
        return ""
    nested = [n for n in names
              if n.endswith("/" + MARKER) and not n.startswith("/")
              and ".." not in n.split("/")]
    if not nested:
        raise ValueError(
            "pack.json missing from archive - zip the files themselves, "
            "not the folder")
    if len(nested) > 1:
        raise ValueError("archive contains more than one pack.json")
    return nested[0][: -len(MARKER)]


def _read_manifest(zf):
    prefix = _find_prefix(zf)
    raw = zf.read(prefix + MARKER)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"pack.json is not valid json: {exc}")
    if not isinstance(manifest, dict):
        raise ValueError("pack.json is not an object")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("pack.json lists no files")
    for name, digest in files.items():
        if os.path.basename(name) != name or not name.endswith(".py"):
            raise ValueError(f"invalid module name: {name}")
        member = prefix + name
        if member not in zf.namelist():
            raise ValueError(f"missing module: {name}")
        if _sha256(zf.read(member)) != digest:
            raise ValueError(f"checksum mismatch: {name}")
    manifest["_prefix"] = prefix
    return manifest


def install(zip_path, base_dir=None, force=False):
    base_dir = os.path.abspath(base_dir or os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isfile(zip_path):
        raise ValueError(f"not a file: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        manifest = _read_manifest(zf)
        prefix = manifest.pop("_prefix", "")
        files = manifest["files"]
        base = str(manifest.get("base") or "")
        current = _base_version(base_dir)
        if base and current and base != current and not force:
            raise ValueError(
                f"pack targets {base}, installed tool is {current}; "
                f"update the tool or pass --force")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(base_dir, "backups", f"pack-{stamp}")
        os.makedirs(backup, exist_ok=True)
        replaced = []
        for name in files:
            target = os.path.join(base_dir, name)
            if os.path.isfile(target):
                shutil.copy2(target, os.path.join(backup, name))
                replaced.append(name)
            with open(target, "wb") as fh:
                fh.write(zf.read(prefix + name))
        manifest["installed"] = stamp
        manifest["previous"] = replaced
        with open(os.path.join(base_dir, MARKER), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
    return [
        f"pack: {manifest.get('name', '-')} {manifest.get('version', '')}".strip(),
        f"modules: {len(files)}",
        f"replaced: {len(replaced)}",
        f"backup: {backup}",
        "restart the tool",
    ]


def remove(base_dir=None):
    base_dir = os.path.abspath(base_dir or os.path.dirname(os.path.abspath(__file__)))
    marker = os.path.join(base_dir, MARKER)
    if not os.path.isfile(marker):
        raise ValueError("no pack installed")
    with open(marker, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    stamp = manifest.get("installed")
    backup = os.path.join(base_dir, "backups", f"pack-{stamp}") if stamp else ""
    previous = set(manifest.get("previous") or [])
    if previous:
        if not backup or not os.path.isdir(backup):
            raise ValueError("backup folder missing, nothing removed")
        missing = [n for n in previous
                   if not os.path.isfile(os.path.join(backup, n))]
        if missing:
            raise ValueError("backup incomplete: " + ", ".join(sorted(missing)))
    restored = []
    removed = []
    for name in manifest.get("files", {}):
        saved = os.path.join(backup, name) if backup else ""
        if name in previous and saved and os.path.isfile(saved):
            shutil.copy2(saved, os.path.join(base_dir, name))
            restored.append(name)
        else:
            target = os.path.join(base_dir, name)
            if os.path.isfile(target):
                os.remove(target)
                removed.append(name)
    os.remove(marker)
    return [
        f"restored: {len(restored)}",
        f"removed: {len(removed)}",
        f"backup: {backup or '-'}",
        "restart the tool",
    ]


def _pick(base_dir):
    """Choose a pack archive: prefer names containing 'pack'.

    The folder also holds the distributable tool zip, which has no
    pack.json, so a plain alphabetical pick would break upgrades.
    """
    zips = sorted(n for n in os.listdir(base_dir) if n.lower().endswith(".zip"))
    if not zips:
        raise ValueError("no .zip in this folder")
    packs = [n for n in zips if "pack" in n.lower()]
    return os.path.join(base_dir, (packs or zips)[0])


def main(argv):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]
    try:
        if "--remove" in argv:
            messages = remove(base_dir)
        else:
            target = args[0] if args else _pick(base_dir)
            messages = install(target, base_dir, force=force)
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    for line in messages:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
