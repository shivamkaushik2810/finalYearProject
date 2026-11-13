#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
echo "app.py:          $([ -f "$SNAPCLASS_ROOT/app.py" ] && echo yes || echo NO)"
echo "teacher_screen:  $(grep -c -E 'attendance_hub|show_feedback_section|teacher_analytics_tab' "$SNAPCLASS_ROOT/src/screens/teacher_screen.py") (QR/feedback/analytics markers; 0 means not your full version)"
echo "uncommitted:     $(git -C "$SNAPCLASS_ROOT" status --short 2>/dev/null | grep -vc '^??') tracked file(s) differ from the last commit"
