#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[ -d src/components ] || { echo "Run this inside your project."; exit 1; }
git switch -c ui-ux-restore 2>/dev/null || git switch ui-ux-restore
printf '_my_full_replacements/\n*.bak.*\n' >> .git/info/exclude   # local-only, nothing is committed

files="src/ui/base_layout.py src/components/header.py src/components/subject_card.py
src/components/dialog_attendance_results.py src/components/dialog_voice_attendance.py
src/components/student_attendance_list.py src/screens/teacher_screen.py src/screens/student_screen.py
src/services/email_service.py src/services/weekly_report_service.py"

for f in $files; do
  bak=$(ls "$f".bak.2026* 2>/dev/null | sort | head -1 || true)
  if [ -z "$bak" ]; then echo "no backup, left alone: $f"; continue; fi
  mkdir -p "_my_full_replacements/$(dirname "$f")"
  cp "$f" "_my_full_replacements/$f"
  cp "$bak" "$f"
  printf "restored %-48s %4s lines  <- %s\n" "$f" "$(wc -l < "$f" | tr -d ' ')" "$(basename "$bak")"
done

echo; echo "== your features should be back (each count should be 1 or more)"
printf "teacher_screen  attendance_hub/feedback/analytics: %s\n" "$(grep -c -E 'attendance_hub|show_feedback_section|teacher_analytics_tab' src/screens/teacher_screen.py)"
printf "student_screen  add_angles/leave/liveness:         %s\n" "$(grep -c -E 'add_angles_dialog|student_leave_tab|liveness_camera_input' src/screens/student_screen.py)"
printf "email_service   pool/queue/smtp helpers:           %s\n" "$(grep -c -E 'smtp_open|smtp_close|_local' src/services/email_service.py)"

echo; echo "== tracked files that still differ from the last commit"
git status --short | grep -v '^??' || echo "(none)"

echo; echo "== tests"
[ -f tests/run_all.py ] && python3 tests/run_all.py 2>&1 | tail -3 || echo "tests/run_all.py not found"
