"""Build the dist/ bytecode copy."""

import importlib.util
import marshal
import os
import shutil
import struct
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(BASE, "dist", "nxtf0und")

MODULES = [
    "main.py",
    "tools_osint.py",
    "tools_scan.py",
    "tools_extra.py",
    "tools_hunt.py",
    "tools_utils.py",
    "tools_discord.py",
    "tools_roblox.py",
    "tools_advanced.py",
    "tools_system.py",
]

PACK_MODULE = "tools_builder.py"
if os.path.isfile(os.path.join(BASE, PACK_MODULE)):
    MODULES.append(PACK_MODULE)

LAUNCHER = '''#!/usr/bin/env python3
"""nxtf0und launcher — bytecode build."""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import main

if __name__ == "__main__":
    try:
        main.main()
    except KeyboardInterrupt:
        print("\\n  interrupted")
'''

def pyc_header():
    magic = importlib.util.MAGIC_NUMBER
    return magic + struct.pack("<I", 0) + struct.pack("<I", 0) + struct.pack("<I", 0)

def build_module(src_path, out_dir):
    with open(src_path, "r", encoding="utf-8") as fh:
        source = fh.read()
    name = os.path.splitext(os.path.basename(src_path))[0]
    code = compile(source, name + ".py", "exec", dont_inherit=True)
    target = os.path.join(out_dir, name + ".pyc")
    with open(target, "wb") as fh:
        fh.write(pyc_header())
        marshal.dump(code, fh)
    return target, len(source)

def main():
    if not os.path.isdir(BASE):
        print("run this from the project directory")
        return 1
    missing = [m for m in MODULES if not os.path.isfile(os.path.join(BASE, m))]
    if missing:
        print("missing modules: " + ", ".join(missing))
        return 1
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST, exist_ok=True)

    total_src = 0
    total_pyc = 0
    print(f"building bytecode dist → {DIST}")
    for module in MODULES:
        target, size = build_module(os.path.join(BASE, module), DIST)
        built = os.path.getsize(target)
        total_src += size
        total_pyc += built
        print(f"  {os.path.basename(target):<22} {size:>7,} B source -> {built:>7,} B pyc")

    for extra in ("requirements.txt", "README.md"):
        src = os.path.join(BASE, extra)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DIST, extra))

    launcher = os.path.join(DIST, "nxtf0und.py")
    with open(launcher, "w", encoding="utf-8") as fh:
        fh.write(LAUNCHER)
    os.chmod(launcher, 0o755)

    for folder in ("reports", "builds", "loot", "dox", "templates"):
        os.makedirs(os.path.join(DIST, folder), exist_ok=True)

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(DIST, "BUILD.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"nxtf0und bytecode build\nbuilt: {stamp}\n"
                 f"python: {sys.version.split()[0]}\n"
                 f"source bytes: {total_src:,}\n"
                 f"pyc bytes: {total_pyc:,}\n")

    print(f"\ndone — {total_pyc:,} B of bytecode, no .py beside it")
    print(f"run: python3 {os.path.join(DIST, 'nxtf0und.py')}")
    print(f"python target: {sys.version.split()[0]} (pyc is version locked)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
