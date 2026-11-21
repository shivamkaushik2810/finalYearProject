#!/usr/bin/env bash
# restructure.sh - tidy the project folder WITHOUT touching any Python package paths.
# Default = dry run (prints the plan). Add --apply to move files. Uses git mv when tracked.
# Never overwrites. Safe to run twice. Run from the project root (where app.py is).
set -uo pipefail
[ -f app.py ] && [ -d src ] || { echo "Run from the project root (app.py and src/ must be here)."; exit 2; }
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
moved=0; skipped=0
mv_safe() {  # src dst
  local s="$1" d="$2"
  [ -e "$s" ] || return 0
  if [ -e "$d" ]; then echo "skip (target exists)  $s -> $d"; skipped=$((skipped+1)); return 0; fi
  echo "$([ $APPLY = 1 ] && echo move || echo plan)  $s -> $d"
  if [ $APPLY = 1 ]; then
    mkdir -p "$(dirname "$d")"
    if git ls-files --error-unmatch "$s" >/dev/null 2>&1; then git mv "$s" "$d"; else mv "$s" "$d"; fi
  fi
  moved=$((moved+1))
}
for f in 00_preflight.sh 50_patch_face_confidence.sh 91_restore_overwritten.sh 94_collect_files.sh \
         95_relocate.sh 96_inspect_real_project.sh 97_find_project.sh 98_diagnose.sh 99_verify.sh \
         fix_script_paths.sh merge_1_base_layout.sh merge_2_header_card.sh merge_4_teacher_screen.sh \
         merge_5_student_screens.sh merge_7_review_table.sh snapclass_lib.sh snapclass_root.sh \
         snapclass_where.sh patch_teacher.py patch_dns_diag.py fix_attendance_corrections.py verify.sh; do
  mv_safe "$f" "tools/archive/$f"
done
mv_safe scripts/apply_batch2_patches.py tools/archive/apply_batch2_patches.py
mv_safe monitor_snapclass.py tools/monitor_snapclass.py
for f in reserve_email_quota optimize_queries feedback_daily_limit 01_security_rls 02_face_angles \
         03_leave_requests 04_batch2 05_fixes multi_section_subjects; do mv_safe "sql/$f.sql" "sql/migrations/$f.sql"; done
mv_safe sql/status_views.sql tools/archive/status_views.sql.NOT_SQL
if [ -f python-version.txt ] && [ ! -e .python-version ]; then
  echo "$([ $APPLY = 1 ] && echo write || echo plan)  .python-version (3.11.15)"
  [ $APPLY = 1 ] && sed 's/^Python *//' python-version.txt > .python-version
  mv_safe python-version.txt tools/archive/python-version.txt
fi
echo; echo "$([ $APPLY = 1 ] && echo moved || echo would move): $moved   skipped: $skipped"
[ $APPLY = 1 ] || echo "Dry run only. Re-run with --apply to do it."
[ $APPLY = 1 ] && python3 -m compileall -q src >/dev/null && echo "src/ still compiles (no Python package paths were changed)."
