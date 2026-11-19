# nxtf0und

Terminal multitool for security research, OSINT and network inspection. One
Python entry point, modular tool files, no account and no telemetry.

Use it only on systems you own or are authorized to test. See
[DISCLAIMER.md](DISCLAIMER.md).

## Requirements

- Python 3.9 or newer (3.12 tested)
- Windows, Linux or macOS
- `pip install -r requirements.txt`

## Install

Full walkthrough: [INSTALL.md](INSTALL.md)

```bash
git clone https://github.com/sqlnxtf0und/foundation.git
cd foundation
python3 -m pip install -r requirements.txt
python3 main.py
```

Windows uses `python main.py`.

## Running

```
nxtf0und@doxxed.com:~$
```

| input | effect |
|---|---|
| `1`-`9` | open a section |
| `b` | back one level |
| `0` | exit |
| `u` | check for a newer build |

## Sections

| # | section | contents |
|---|---|---|
| 1 | OSINT | username, email, phone, domain, IP and certificate lookups |
| 2 | Network | host discovery, port scanning, DNS, TLS, HTTP headers, packet capture |
| 3 | Web | content discovery, endpoint mapping, TLS inspection, site mirroring |
| 4 | Utilities | hashing, encoding, metadata, local record search |
| 5 | Extensions | optional module pack, install and status |
| 6 | Discord | server info and invite lookup |
| 7 | Roblox | public API lookups |
| 8 | Advanced | load testing, reputation checks, vulnerability research |
| 9 | Settings | theme, timeout, user agent, save prompts, updates |

Advanced includes the research suite: version to CVE correlation, parameter
discovery, fuzzing, injection and misconfiguration probes, JWT analysis,
sensitive file discovery.

## Reports

Reports are written only after confirmation. Every report prompts
`save this report? (y/n)` and defaults to no.

```
reports/    scan results, JSON and text
builds/     generated scripts
loot/       captured data from local test pages
```

If a folder is not writable the tool writes to the temp directory and reports
the change.

## Themes

`lightblue` (default), `bloody_red`, `pitchblack`, `matrix`, `cyber`, `amber`.
Set under Settings > 5. Stored in `settings.json`.

## Layout

```
main.py             entry point, menus, theme, HTTP client, reports
tools_osint.py      OSINT lookups
tools_scan.py       network and web scanners
tools_extra.py      headers, TLS, banners, robots, WAF, wayback
tools_hunt.py       vulnerability research suite
tools_utils.py      hashing, encoding, mirroring, local records
tools_discord.py    Discord lookups
tools_roblox.py     Roblox API lookups
tools_advanced.py   reputation, CVE and research integration
tools_system.py     system and anonymity utilities
install_pack.py     installs or removes an extension pack
build_protected.py  compiles the project to a bytecode copy in dist/
```

## Extensions

Sections marked optional are supplied as a separate pack. The pack is a single
zip and installs into this folder without moving files elsewhere:

```bash
python3 install_pack.py nxtf0und-pack-1.2.zip
```

Alternative, from the tool: `5` > `2`, or `python3 main.py --install-pack`.

Installed modules are copied next to `main.py`. Replaced files are backed up
under `backups/pack-<stamp>/`. Remove the pack with:

```bash
python3 install_pack.py --remove
```

Restart the tool after install or removal. The pack is versioned against the
installed release; `install_pack.py` refuses a mismatch unless `--force` is
passed. Reinstall the pack after updating the tool.

## Updating

Press `u`, or Settings > 7. The tool compares its version against the published
`version.json`, copies replaced files into `backups/`, and restores them if a
download fails to compile.

## Intended use

Published for education, research and authorized security testing. Running it
against systems you do not own, or do not have written permission to test, may
be unlawful and breaches the terms of most hosting providers.

You are responsible for your use of this software and for the laws that apply
to you. Full statement: [DISCLAIMER.md](DISCLAIMER.md).

## License

MIT. See [LICENSE](LICENSE).
