# work/

Permanent sync folder. Everything in here is tracked and pushed every time.

- Not matched by any ignore rule — this folder always ships.
- Subfolders are fine; keep flat files small, big artifacts go elsewhere.
- Run `./work/push.sh` (or the one-liner in SETUP below) to commit and push this folder alone.

## SETUP

First push handled at creation. From now on:

```bash
git add -A work && git commit -m "work: sync" && git push origin main
```

Nothing else in the repo is touched by that command.