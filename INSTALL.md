# Installing and running foundation

Windows, Linux and macOS. Python 3.9 or newer; 3.12 is tested. No key, licence
or account.

Use only on systems you own or have written permission to test. See
[DISCLAIMER.md](DISCLAIMER.md).

---

## Windows

### 1. Install Python

Download the installer from [python.org/downloads](https://www.python.org/downloads/).
Do not use the Microsoft Store build.

Tick `Add python.exe to PATH` on the first installer screen. Without it, the
`python` command is not available in a new shell.

Verify in PowerShell:

```powershell
python --version
pip --version
```

Both must print a version. If `python` opens the Microsoft Store, disable the
alias under Settings > Apps > Advanced app settings > App execution aliases,
then reinstall Python.

### 2. Get the files

Download the repository ZIP and extract it, or clone it:

```powershell
git clone https://github.com/sqlnxtf0und/foundation.git
cd foundation
```

The current directory must contain `main.py`.

### 3. Install the dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `pip` is not on PATH, use `python -m pip`.

### 4. Run it

```powershell
python main.py
```

Numbers open a section, `b` goes back, `0` exits.

### Windows notes

- The interface uses Unicode borders. Use Windows Terminal, or run
  `chcp 65001` in `cmd.exe`. `PYTHONUTF8=1` also works.
- PowerShell execution policy does not apply to `python main.py`.
- The firewall prompt on the first network scan is normal. Allow private
  networks.
- Packet capture requires Npcap and Administrator. Other modules run as a
  normal user.
- Nmap and Masscan are optional. Without them the tool reports the missing
  binary and uses its internal scanner.

---

## Linux

### 1. Install Python and pip

Debian, Ubuntu, Kali:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

Fedora:

```bash
sudo dnf install -y python3 python3-pip git
```

Arch, Manjaro:

```bash
sudo pacman -S --needed python python-pip git
```

### 2. Get the files

```bash
git clone https://github.com/sqlnxtf0und/foundation.git
cd foundation
```

### 3. Install the dependencies

Current distributions (Ubuntu 23.04+, Debian 12+, recent Kali, Fedora 38+)
reject system-wide installs with `externally-managed-environment`. Use a
virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Older distributions can use:

```bash
python3 -m pip install --user -r requirements.txt
```

### 4. Run it

```bash
python3 main.py
```

Inside the environment `python main.py` also works. `deactivate` leaves it.

### Linux notes

- Use a terminal with full Unicode support. GNOME Terminal, Konsole,
  Alacritty, kitty and Terminator are suitable.
- `traceroute` is not installed by default on Debian: `sudo apt install traceroute`.
- Packet capture requires root and `libpcap`: `sudo python3 main.py`.
- Nmap and Metasploit are optional: `sudo apt install nmap`,
  `sudo apt install metasploit-framework`. Kali includes both.
- `searchsploit` comes from `exploitdb`: `sudo apt install exploitdb`.

---

## macOS

```bash
brew install python git
git clone https://github.com/sqlnxtf0und/foundation.git
cd foundation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## First run

The first time you start the tool it opens a setup screen: theme, animation
style, animations on/off, logo, border, density, glyphs and colour mode. Each
choice previews live. When it finishes, a preview page renders every element at
once.

Re-run it any time:

```bash
python3 main.py --setup      # walk through setup again
python3 main.py --no-setup   # start without the wizard
```

Everything the wizard sets is also under **Settings > 9**, along with custom
palettes, fonts, accent colour and animation speed.

```
1 OSINT          usernames, email, phone, domains, IPs, certificates
2 Network        host and port scanning, DNS, TLS, headers, capture
3 Web            content discovery, endpoint mapping, site mirroring
4 Utilities      hashing, encoding, metadata, local record search
5 Updates        tool update, license, dependencies
6 Discord        server and webhook lookups
7 Roblox         public API lookups
8 Advanced       load testing, reputation, vulnerability research
9 Settings       theme, fonts, borders, animation, palette, api keys, updates
0 Exit
```

`b` returns one level, at the menu, in a submenu and at every prompt. `0`
exits.

Nothing is written without confirmation. Reports prompt
`save this report? (y/n)` and default to no. Output goes to `reports/`,
`builds/` or `loot/`. If a folder is not writable the tool writes to
the temp directory and reports the change.

---

## Optional extras

| package | purpose | install |
|---|---|---|
| `requests` | HTTP client, TLS handling | `pip install requests` (in requirements) |
| `phonenumbers` | phone number parsing | `pip install phonenumbers` |
| `pysocks` | SOCKS proxy support | `pip install pysocks` |
| `nmap` | nmap scan module | OS package manager |
| `metasploit` | MSF console and payloads | OS package manager |
| `exploitdb` | vulnerability reference lookup | OS package manager |
| `traceroute` | network path tool | OS package manager |
| `npcap` | packet capture on Windows | npcap.com |

A missing extra does not break the tool. The module reports it and falls back
where possible.

---

## Updates

`5` at the main menu opens the update menu. It installs a newer tool build,
shows the license, installs `requirements.txt` and optional packages, and opens
the upgrade contact.

The footer shows `build: free` or `build: paid`.

Tool update is also available as `u`, `9` then `7`, or
`python3 main.py --update`. It copies every replaced file into
`backups/update-<stamp>/`, downloads the changed modules, compiles each one,
and restores the backup if a file fails.

The free build covers OSINT, network, web, utilities and the research suite.
Additional modules are available as a paid upgrade: [t.me/zerostate00](https://t.me/zerostate00).

---

## Bytecode build

To produce a copy without readable `.py` files:

```bash
python3 build_protected.py
python3 dist/foundation/foundation.py
```

Windows: `python build_protected.py`, then `python dist\foundation\foundation.py`.

The build writes `.pyc` modules and a launcher into `dist/foundation/`. This is
obfuscation, not encryption; bytecode can be decompiled. `.pyc` files only run
on the Python version that produced them, so build on the machine that will
run the result.

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `python: command not found` | Python missing or not on PATH | reinstall with **Add to PATH** ticked |
| `pip: command not found` | pip not on PATH | use `python -m pip` |
| `externally-managed-environment` | system pip blocked | use a virtual environment |
| `ModuleNotFoundError: requests` | dependencies missing | `pip install -r requirements.txt` |
| `ModuleNotFoundError: phonenumbers` | optional extra missing | `pip install phonenumbers` |
| borders show `????` or boxes | terminal encoding | Windows Terminal, `chcp 65001`, `PYTHONUTF8=1` |
| menu exits immediately | exception on boot | run `python3 main.py` and read the traceback |
| `Permission denied` on `loot/` | folder owned by root | tool falls back to `/tmp/foundation`; or `sudo chown -R $USER .` |
| nmap module reports not installed | binary missing | install nmap or use the internal scanner |
| packet capture returns nothing | no root or no libpcap | `sudo python3 main.py`, install libpcap |

---

## Install check

```bash
python3 main.py
```

The menu appears. Open `1`, run any tool, press `b`, then `0`.
