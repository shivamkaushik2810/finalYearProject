#!/usr/bin/env bash
# snapclass_lib.sh: shared helpers. Source it from every other script.
set -euo pipefail

find_project() {
  # Accepts the project root (contains app.py and src/), or searches from $PWD upward.
  if [ -n "${SNAPCLASS_ROOT:-}" ] && [ -f "$SNAPCLASS_ROOT/app.py" ]; then
    echo "$SNAPCLASS_ROOT"; return
  fi
  local d="$PWD"
  while [ "$d" != "/" ]; do
    if [ -f "$d/app.py" ] && [ -d "$d/src" ]; then echo "$d"; return; fi
    d="$(dirname "$d")"
  done
  echo "ERROR: no app.py + src/ found. Run from inside your project or set SNAPCLASS_ROOT." >&2
  exit 1
}

require_files() {
  local missing=0
  for f in "$@"; do
    [ -f "$f" ] || { echo "MISSING  $f"; missing=1; }
  done
  [ "$missing" -eq 0 ] || { echo "Stopped. Nothing was changed."; exit 1; }
}

backup() { cp "$1" "$1.bak.$(date +%Y%m%d%H%M%S)"; }

# Replace a file only if the new content compiles; otherwise restore the backup.
safe_write() {
  local target="$1" tmp="$2"
  backup "$target"
  mv "$tmp" "$target"
  if ! python3 -m py_compile "$target" 2>/dev/null; then
    echo "COMPILE FAILED for $target, restoring backup"
    cp "$(ls -t "$target".bak.* | head -1)" "$target"
    exit 1
  fi
  echo "OK  $target"
}
