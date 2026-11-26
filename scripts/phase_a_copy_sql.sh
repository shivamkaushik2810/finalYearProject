#!/usr/bin/env bash
# Copies sql/06_timetable_core.sql to the clipboard for pasting into the Supabase SQL editor.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

f="sql/06_timetable_core.sql"
[ -f "$f" ] || { echo "MISSING $f"; exit 1; }

first=$(head -n 1 "$f")
if [ "$first" != "-- 06_timetable_core.sql (Phase A)" ]; then
  echo "Unexpected first line in $f:"
  echo "  $first"
  echo "Stopped. The file was not copied."
  exit 1
fi

pbcopy < "$f"
echo "Copied $(wc -l < "$f" | tr -d ' ') lines of SQL to the clipboard."
echo
echo "Next, in your browser:"
echo "  1. Open the Supabase SQL Editor and click inside it."
echo "  2. Press Cmd+A, then Delete (the editor must be empty)."
echo "  3. Press Cmd+V, check that the first line is the comment above, then click Run."
