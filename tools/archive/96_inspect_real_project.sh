#!/usr/bin/env bash
cd ~/FinalYearProject/ai-attendance-project-app || exit 1
echo "--- repo, branch, changes"
git rev-parse --show-toplevel; git branch --show-current; git status --short | head -20
echo "--- python files in the real src"
find src -type f -name "*.py" | sort
echo "--- size of each file my scripts would replace (absent = new)"
for f in src/ui/base_layout.py src/components/header.py src/components/subject_card.py \
  src/components/dialog_attendance_results.py src/components/dialog_voice_attendance.py \
  src/components/student_attendance_list.py src/screens/teacher_screen.py \
  src/screens/student_screen.py src/services/email_service.py src/services/weekly_report_service.py; do
  if [ -f "$f" ]; then echo "$(wc -l < "$f") lines  $f"; else echo "absent       $f"; fi
done
echo "--- features already in the real screens"
grep -n -i -E "qr|nfc|leave|admin|defaulter|authz|audit" src/screens/*.py | head -30
echo "--- the two backups created at the wrong level"
cd ~/FinalYearProject
wc -l src/screens/teacher_screen.py.bak.* src/database/ui_queries.py.bak.* 2>/dev/null
for f in src/screens/teacher_screen.py.bak.* src/database/ui_queries.py.bak.*; do echo "== $f"; head -8 "$f"; done
