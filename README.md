# foundation

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
| 5 | Updates | tool update, license, dependencies |
| 6 | Discord | server info and invite lookup |
| 7 | Roblox | public API lookups |
| 8 | Advanced | load testing, reputation checks, vulnerability research |
| 9 | Settings | theme, fonts, borders, animation, palette, api keys, updates |

Advanced includes the research suite: version to CVE correlation, parameter
discovery, fuzzing, injection and misconfiguration probes, JWT analysis,
sensitive file discovery.

## API keys

Optional. Without keys the tool uses its free, keyless endpoints. Adding keys
turns on enrichment that those endpoints cannot provide (reputation scores,
breach data, host banners, passive DNS).

```bash
cp .env.example .env      # then fill in the services you use
```

Keys are read from `.env` in the project root, which is git-ignored. Exported
environment variables override the file. Manage them without editing the file:
**Settings → 9**. That menu shows each service as `set` or `not set`, lets you
enter values, and clears the response cache.

Supported services: VirusTotal, urlscan.io, Censys, IPinfo, AbuseIPDB,
AlienVault OTX, GreyNoise, Shodan, Have I Been Pwned, EmailRep, Hunter.io,
SecurityTrails.

Requests are rate-limited per service and cached under `reports/.cache/` so
repeated lookups return instantly. A missing key never errors — the affected
lookup is simply skipped and the free path is used instead.

## Relay (shared keys)

To give users enrichment without distributing your own keys, run the relay
host side and point clients at it.

On the relay host:

```bash
cp relay-keys.example.env relay-keys.env     # fill in upstream keys here
cp relay-users.example.json relay-users.json
python3 relay.py --new-token alice           # prints the token once
# paste its token_sha256 into relay-users.json
python3 relay.py --host 0.0.0.0 --port 8080
```

On the client, set both values (or use **Settings → 9 → r**):

```bash
NF_RELAY_URL=https://relay.example.com
NF_RELAY_TOKEN=alice-token-from-relay
```

When the relay is configured it takes precedence over local keys; upstream
credentials never reach the client. The relay validates every request against
an allowlist built from the service registry, so it cannot be used to reach an
arbitrary host. Per-user rate limits and daily quotas apply before any upstream
call is made. Run it behind TLS — put it behind nginx/Caddy, not bare HTTP.

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

25 built-in palettes, plus a full custom-colour mode.

`lightblue` (default), `bloody_red`, `pitchblack`, `matrix`, `cyber`, `nord`,
`dracula`, `tokyo`, `synthwave`, `gruvbox`, `catppuccin`, `monokai`,
`rose_pine`, `neon`, `blood_moon`, `violet`, `grayscale`, `solarized`, `ice`,
`amber`, `mocha`, `ocean`, `forest`, `ember`, `sunset`.

Set under **Settings > 4** (browsable gallery with live swatches). Stored in
`settings.json`.

## Customization

Everything about the interface is configurable, and a first-run wizard walks
a new install through it. Re-run it any time with `python3 main.py --setup`,
or skip it with `--no-setup`.

**Settings > 9** opens the customization center:

| Option | What it does |
|---|---|
| 1 | Animations on/off |
| 2 | Animation style: `typewriter`, `sweep`, `glitch`, `fade`, `instant` |
| 3 | Animation speed multiplier (0.25 - 4) |
| 4 | Theme gallery (25 palettes + custom) |
| 5 | Custom palette: per-slot hex, colour picker, seed from theme |
| 6 | Font: default, bold, dim, italic, underline, bold_italic, reverse |
| 7 | Border: double, single, rounded, heavy, ascii, none |
| 8 | Glyphs: unicode, ascii, dots, minimal |
| 9 | Density: compact, normal, roomy |
| a | Logo: block, slim, none |
| c | Colour mode: truecolor, 256, 16 (for terminals without 24-bit) |
| d | Clock on/off |
| e | Accent colour (overrides the primary slot only) |
| f | HTTP timeout |
| r | Save reports |
| s | Preview every element at once |
| k | API keys and relay |
| u | Check for updates |
| z | Reset all defaults |

Custom palettes have six independent slots: primary, secondary, muted,
success, warning and error. The colour picker tunes one channel (r/g/b) at a
time with live preview; deltas are clamped to 0-255, so the value can never
leave the valid range.

Unknown or malformed settings are discarded at load. A hand-edited
`settings.json` containing an invalid theme, font, border, glyph set, density,
logo style, colour mode, animation style or non-hex colour falls back to its
default instead of breaking the interface.

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
install_pack.py     upgrade pack installer
build_protected.py  compiles the project to a bytecode copy in dist/
```

## Updates

Type `5` at the main menu. The menu updates the tool, shows the license,
installs dependencies and optional packages, and opens the upgrade contact.

The footer shows the current build:

```
build: free  •  upgrade: t.me/zerostate00
build: paid
```

Tool update is also available as `u` at the prompt, Settings > 7, or
`python3 main.py --update`. The tool compares its version against the published
`version.json`, copies replaced files into `backups/`, and restores any file
that fails to compile.

## Upgrade

The free build covers OSINT, network, web, utilities and the research suite.
Additional modules are available as a paid upgrade.

Message [t.me/zerostate00](https://t.me/zerostate00).

## Intended use

Published for education, research and authorized security testing. Running it
against systems you do not own, or do not have written permission to test, may
be unlawful and breaches the terms of most hosting providers.

You are responsible for your use of this software and for the laws that apply
to you. Full statement: [DISCLAIMER.md](DISCLAIMER.md).

## License

MIT. See [LICENSE](LICENSE).
