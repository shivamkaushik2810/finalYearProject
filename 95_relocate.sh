#!/usr/bin/env bash
set -euo pipefail
top="$HOME/FinalYearProject"; real="$top/ai-attendance-project-app"
cd "$top"
[ -d "$real/src" ] || { echo "Real project not found at $real"; exit 1; }

echo "== 1. add building blocks to the real project (never overwrites)"
for f in src/ui/tokens.py src/ui/widgets.py src/services/attendance_stats.py \
         src/components/charts.py src/services/email_templates.py tests/test_snapclass_ui.py; do
  if [ -f "$top/$f" ]; then
    mkdir -p "$real/$(dirname "$f")"
    if [ -e "$real/$f" ]; then echo "skip (already exists)  $f"
    else cp "$top/$f" "$real/$f"; echo "added                  $f"; fi
  else echo "missing source         $f"; fi
done

echo "== 2. move my misplaced top-level copies aside (reversible)"
q="$top/_misplaced_ui_scripts"; mkdir -p "$q"
for f in src/ui/tokens.py src/ui/base_layout.py src/ui/widgets.py \
  src/components/header.py src/components/charts.py src/components/subject_card.py \
  src/components/dialog_attendance_results.py src/components/dialog_voice_attendance.py \
  src/components/student_attendance_list.py \
  src/services/attendance_stats.py src/services/email_templates.py \
  src/services/email_service.py src/services/weekly_report_service.py \
  src/database/ui_queries.py src/database/ui_queries.py.bak.* \
  src/screens/teacher_screen.py src/screens/teacher_screen.py.bak.* src/screens/student_screen.py \
  tests/test_snapclass_ui.py 00_preflight.sh 50_patch_face_confidence.sh \
  95_relocate.sh 96_inspect_real_project.sh 97_find_project.sh 98_diagnose.sh 99_verify.sh; do
  if [ -e "$top/$f" ] && [ "$f" != "95_relocate.sh" ]; then
    mkdir -p "$q/$(dirname "$f")"; mv "$top/$f" "$q/$f"; echo "moved  $f"
  fi
done

echo "== 3. run the helper tests inside the real project"
cd "$real"
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_snapclass_ui.py" 2>&1 | tail -4
echo "== git status (real project)"
git status --short | head -20
