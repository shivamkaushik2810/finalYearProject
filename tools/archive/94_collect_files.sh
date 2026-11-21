#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
cd "$SNAPCLASS_ROOT" || exit 1
out=~/FinalYearProject/files_for_claude.txt
: > "$out"
for f in src/ui/base_layout.py src/components/header.py \
         src/components/subject_card.py src/screens/teacher_screen.py; do
  echo "=================== $f ===================" >> "$out"
  cat "$f" >> "$out"
  echo >> "$out"
done
wc -l "$out"
pbcopy < "$out" && echo "Copied to clipboard. Paste it in the chat, or attach $out."
