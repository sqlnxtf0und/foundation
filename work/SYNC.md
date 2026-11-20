# work/ — the project

Everything here is tracked and pushed. This is the project root: run the tool
from inside this folder.

```bash
cd work
python3 main.py
```

## Pushing

```bash
./work/push.sh                 # stages work/, commits, pushes
./work/push.sh "work: reason"  # custom commit message
```

Or manually, from the repository root:

```bash
git add -A work && git commit -m "work: sync" && git push origin main
```

## What is NOT here

Private files live in the repository root and are git-ignored, so they are
never pushed:

| File | Purpose | Linked from |
|---|---|---|
| `../.env` | API keys | `work/.env` |
| `../settings.json` | your configuration | `work/settings.json` |
| `../pack.json` | installed pack manifest | `work/pack.json` |

The symlinks in `work/` exist so the tool resolves them from its new root.
They are ignored, so they are not pushed either.