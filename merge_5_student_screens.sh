#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
cd "$SNAPCLASS_ROOT" || exit 1
for need in src/ui/widgets.py src/services/attendance_stats.py src/components/charts.py src/components/subject_card.py; do
  [ -f "$need" ] || { echo "Missing $need. Run merge_1 and merge_2 first."; exit 1; }
done
grep -q "pct=None, total=None" src/components/subject_card.py || { echo "Run merge_2_header_card.sh first."; exit 1; }

ts=$(date +%Y%m%d%H%M%S)
cp src/screens/student_screen.py src/screens/student_screen.py.bak.$ts
cp src/components/student_attendance_list.py src/components/student_attendance_list.py.bak.$ts

python3 - << 'PYEOF'
import os, re, sys

SS = os.environ.get("STUDENT_PATH", "src/screens/student_screen.py")
SA = os.environ.get("ATT_LIST_PATH", "src/components/student_attendance_list.py")


def must_sub(pattern, repl, text, what, flags=re.S):
    new, n = re.subn(pattern, lambda m: repl, text, count=1, flags=flags)
    if n != 1:
        sys.exit(f"Anchor not found for: {what}. Nothing was changed.")
    return new


def patch_student_screen():
    src = open(SS, encoding="utf-8").read()
    if "_student_summary_header" in src:
        return None, "student_screen.py already merged"

    src = must_sub(r"from src\.components\.subject_card import subject_card\n",
                   "from src.components.subject_card import subject_card\n"
                   "import logging\n"
                   "from src.services import attendance_stats as S\n"
                   "from src.ui.widgets import stat_cards, confirm_dialog\n\n"
                   "_log = logging.getLogger(__name__)\n",
                   src, "subject_card import")

    src = must_sub(r"""st\.button\("Logout", type=(['"])secondary\1, key=(['"])loginbackbtn\2""",
                   """st.button("Log out", type='secondary', key='danger_student_logout'""",
                   src, "logout button")

    header_fn = '''def _student_summary_header(student_id):
    """Four summary cards above the tabs. Excused absences are left out, as in My Attendance."""
    try:
        rows = get_student_attendance(student_id) or []
    except Exception:
        _log.exception("Could not load attendance summary")
        return
    counted = [r for r in rows if r.get("is_present") or not r.get("is_excused")]
    total = S.overall(counted)
    by_subject = S.per_subject(counted)
    at_risk = sum(1 for v in by_subject.values() if v["total"] and S.pct(v["present"], v["total"]) < 75)
    tone = {"good": "good", "avg": "avg", "risk": "bad"}.get(S.status_for(total["pct"], total["total"])[0], "")
    stat_cards([
        ("Overall attendance", f"{total['pct']:.0f}%" if total["total"] else "No data", tone),
        ("Classes attended", f"{total['present']} / {total['total']}", ""),
        ("Subjects at risk", at_risk, "bad" if at_risk else "good"),
        ("Subjects tracked", len(by_subject), ""),
    ])


'''
    src = must_sub(r"def student_dashboard\(\):", header_fn + "def student_dashboard():", src, "dashboard def")

    start = src.index("def student_dashboard():")
    marker = "\n    st.space()\n"
    i = src.find(marker, start)
    if i < 0:
        sys.exit("Anchor not found for: st.space() in student_dashboard. Nothing was changed.")
    i += len(marker)
    src = src[:i] + "\n    _student_summary_header(student_id)\n" + src[i:]

    old_loop = "        for log in logs:\n            sid = log['subject_id']\n"
    if src.count(old_loop) == 1:
        src = src.replace(old_loop, old_loop + "            if log.get('is_excused') and not log.get('is_present'):\n                continue\n", 1)
    else:
        print("NOTE  student_screen.py: card statistics loop differs, excused absences are still counted on the cards")

    if "stats_map.get(sid" in src and src.count("footer_callback=unenroll_button") == 1:
        src = src.replace("footer_callback=unenroll_button",
                          "footer_callback=unenroll_button,\n"
                          "                        pct=S.pct(stats['attended'], stats['total']), total=stats['total']", 1)
    else:
        print("NOTE  student_screen.py: subject card call differs, skipped the chip/progress bar")

    m = re.search(r"(?P<i>[ ]+)unenroll_student_to_subject\(student_id, sid\)\s*\n\s*st\.toast\(f\"Unenrolled from \{sub\['name'\]\} successfully!\"\)\s*\n\s*st\.rerun\(\)", src)
    if not m:
        print("NOTE  student_screen.py: unenroll block differs, left the unenroll button as it was")
    else:
        ind = m.group("i")
        block = (f"{ind}def _do_unenroll(sid=sid, name=sub['name']):\n"
                 f"{ind}    unenroll_student_to_subject(student_id, sid)\n"
                 f"{ind}    st.toast(f\"Unenrolled from {{name}}\")\n"
                 f"{ind}confirm_dialog(f\"Unenroll from {{sub['name']}}? Your past attendance stays on record.\",\n"
                 f"{ind}               \"Unenroll\", _do_unenroll, key=f\"unenroll_{{sid}}\")")
        src = src[:m.start()] + block + src[m.end():]
    return src, "student_screen.py merged"


def patch_attendance_list():
    src = open(SA, encoding="utf-8").read()
    if "attendance_trend(" in src:
        return None, "student_attendance_list.py already merged"
    anchor = "    # Subject wise breakdown\n"
    if src.count(anchor) != 1:
        sys.exit("Anchor not found for: '# Subject wise breakdown'. Nothing was changed.")
    charts = '''    # charts (excused absences are left out, as in the numbers above)
    from src.components.charts import attendance_trend, subject_bars, weekly_heatmap
    counted_logs = [l for l in logs if l.get('is_present') or not l.get('is_excused')]
    ch1, ch2 = st.columns(2)
    with ch1:
        attendance_trend(counted_logs)
    with ch2:
        subject_bars([(s['name'], round(s['present'] / s['total'] * 100, 1) if s['total'] else 0.0)
                      for s in subject_stats.values()])
    weekly_heatmap(counted_logs)
    st.divider()

'''
    src = src.replace(anchor, charts + anchor, 1)
    old = 'st.warning(f"⚠️ Your attendance is below 75%! You need to attend more classes.")'
    if src.count(old) == 1:
        from_stats = ("from src.services.attendance_stats import classes_needed\n"
                      "                need = classes_needed(stats['present'], stats['total'])\n"
                      "                ")
        src = src.replace(old, from_stats + 'st.warning(f"⚠️ Your attendance is below 75%. Attend the next {need} class(es) in a row to reach it.")', 1)
    else:
        print("NOTE  student_attendance_list.py: warning line differs, left it as it was")
    return src, "student_attendance_list.py merged"


new_ss, msg1 = patch_student_screen()
new_sa, msg2 = patch_attendance_list()
if new_ss is not None:
    open(SS, "w", encoding="utf-8").write(new_ss)
if new_sa is not None:
    open(SA, "w", encoding="utf-8").write(new_sa)
print(msg1); print(msg2)
PYEOF

if python3 -m py_compile src/screens/student_screen.py src/components/student_attendance_list.py; then
  echo "compiled both files"
else
  echo "COMPILE FAILED, restoring both files from backup"
  cp src/screens/student_screen.py.bak.$ts src/screens/student_screen.py
  cp src/components/student_attendance_list.py.bak.$ts src/components/student_attendance_list.py
  exit 1
fi
git diff --stat -- src/screens/student_screen.py src/components/student_attendance_list.py
