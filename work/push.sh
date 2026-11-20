#!/usr/bin/env bash
# Commit and push only the work/ folder. Nothing else in the repo is staged.
set -euo pipefail

cd "$(dirname "$0")/.."

msg="${1:-work: sync}"

git add -A work
if git diff --cached --quiet; then
    echo "work/: nothing to push"
else
    git commit -m "$msg"
fi
git push origin main