#!/usr/bin/env bash
# Stage everything not ignored, commit, and push. Run from anywhere:
#   ./push.sh              -> commit message "sync"
#   ./push.sh "message"    -> custom commit message
set -euo pipefail

cd "$(dirname "$0")"

msg="${1:-sync}"

git add -A
if git diff --cached --quiet; then
    echo "nothing to commit — already in sync"
else
    git commit -m "$msg"
fi
git push origin main