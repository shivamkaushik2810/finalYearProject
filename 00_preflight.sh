#!/usr/bin/env bash
set -euo pipefail
[ -f app.py ] || { echo "Run this from the project root (where app.py is)."; exit 1; }
git status --short
if [ -n "$(git status --porcelain)" ]; then echo "Commit or stash your changes first."; exit 1; fi
git checkout -b ui-ux-refresh
grep -qxF '*.bak.*' .gitignore || echo '*.bak.*' >> .gitignore
echo "Branch ui-ux-refresh created."
