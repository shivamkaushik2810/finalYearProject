#!/usr/bin/env bash
# Rewrites the folder paths inside the scripts you already have, so they find the project
# with snapclass_root.sh instead of a fixed folder. Safe to run twice. Keeps a .pathbak copy.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ -f "$here/snapclass_root.sh" ] || { echo "snapclass_root.sh must be in the same folder as this script."; exit 1; }
fixed=0; same=0; bad=0
for f in "$here"/merge_*.sh "$here"/9[0-4]_*.sh; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  if grep -q 'snapclass_root.sh' "$f"; then echo "already fixed   $name"; same=$((same + 1)); continue; fi
  cp "$f" "$f.pathbak"
  python3 - "$f" << 'PY'
import re, sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
SRC = 'source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1'
out, inserted = [], False
for i, line in enumerate(lines):
    s = line.strip()
    if re.match(r"^cd\s+.*(FinalYearProject|git rev-parse --show-toplevel).*$", s):
        line = 'cd "$SNAPCLASS_ROOT" || exit 1'
    elif s.startswith('real="$HOME/FinalYearProject'):
        line = 'real="$SNAPCLASS_ROOT"'
    elif s.startswith('q="$HOME/FinalYearProject'):
        line = 'q="$SNAPCLASS_ROOT/_misplaced_ui_scripts"'
    out.append(line)
    if not inserted and re.match(r"^set -[a-z]+.*pipefail", s):
        out.append(SRC); inserted = True
if not inserted:                      # scripts with no 'set -e' line: put it right after the shebang
    out.insert(1 if out and out[0].startswith("#!") else 0, SRC)
open(path, "w", encoding="utf-8").write("\n".join(out))
PY
  if bash -n "$f" && grep -q 'SNAPCLASS_ROOT' "$f"; then
    echo "fixed           $name"; fixed=$((fixed + 1))
  else
    echo "FAILED, restored $name"; cp "$f.pathbak" "$f"; bad=$((bad + 1))
  fi
done
echo; echo "fixed: $fixed   already fixed: $same   failed: $bad"
