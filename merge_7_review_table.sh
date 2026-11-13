#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
cd "$SNAPCLASS_ROOT" || exit 1
[ -f src/ui/widgets.py ] || { echo "Missing src/ui/widgets.py. Run merge_1 first."; exit 1; }
f="src/components/dialog_attendance_results.py"
ts=$(date +%Y%m%d%H%M%S)
cp "$f" "$f.bak.$ts"

python3 - << 'PYEOF'
import os, re, sys

path = os.environ.get("RESULTS_PATH", "src/components/dialog_attendance_results.py")
src = open(path, encoding="utf-8").read()
if "_editable_review" in src:
    sys.exit("Already merged. Nothing changed.")

fn = re.search(r"^def show_attendance_result\(df, logs[^)]*\):\s*$", src, re.M)
if not fn:
    sys.exit("Anchor not found for: def show_attendance_result(df, logs). Nothing was changed.")
table_line = list(re.finditer(r"^(?P<i>[ ]+)st\.dataframe\(df, hide_index=True, width=(['\"])stretch\2\)[ ]*$", src, re.M))
save_line = list(re.finditer(r"^(?P<i>[ ]+)create_attendance\(logs\)[ ]*$", src, re.M))
if len(table_line) != 1 or len(save_line) != 1:
    sys.exit(f"Anchors not unique (table lines: {len(table_line)}, save lines: {len(save_line)}). Nothing was changed.")
t, s = table_line[0], save_line[0]
if not (fn.start() < t.start() < s.start()):
    sys.exit("Anchors are not in the expected order inside show_attendance_result. Nothing was changed.")

helpers = '''def _editable_review(df, logs):
    """A Present checkbox per student, so the teacher can fix mistakes before saving.
    Returns {student_id: bool}. Falls back to the old read-only table if the columns are not there."""
    import pandas as _pd
    if "ID" not in df.columns or "Name" not in df.columns or not logs:
        st.dataframe(df, hide_index=True, width='stretch')
        return None
    auto = {l['student_id']: bool(l.get('is_present')) for l in logs}
    table = _pd.DataFrame({"ID": list(df["ID"]), "Student": list(df["Name"]),
                           "Present": [auto.get(i, False) for i in df["ID"]]})
    if "Source" in df.columns:
        table["Source"] = list(df["Source"])
    stamp = str(logs[0].get('timestamp', ''))
    edited = st.data_editor(
        table, hide_index=True, width='stretch', key=f"review_{stamp}_{len(logs)}",
        disabled=[c for c in table.columns if c != "Present"],
        column_config={"ID": None, "Present": st.column_config.CheckboxColumn("Present")},
    )
    now = {i: bool(p) for i, p in zip(edited["ID"], edited["Present"])}
    changed = sum(1 for i, p in now.items() if p != auto.get(i, False))
    from src.ui.widgets import stat_cards
    stat_cards([("Present", sum(now.values()), "good"),
                ("Absent", len(now) - sum(now.values()), ""),
                ("Edited by you", changed, "")])
    return now


def _apply_review(logs, review):
    """Copy of logs with the teacher's edits applied. Unchanged when there was no editable table."""
    if not review:
        return logs
    return [dict(l, is_present=review.get(l['student_id'], bool(l.get('is_present')))) for l in logs]


'''
out = src[:fn.start()] + helpers + src[fn.start():t.start()]
out += f"{t.group('i')}_review = _editable_review(df, logs)" + src[t.end():s.start()]
out += f"{s.group('i')}logs = _apply_review(logs, _review)\n{s.group('i')}create_attendance(logs)" + src[s.end():]
open(path, "w", encoding="utf-8").write(out)
print("merged", path)
PYEOF

if python3 -m py_compile "$f"; then
  echo "compiled $f"
else
  echo "COMPILE FAILED, restoring from backup"; cp "$f.bak.$ts" "$f"; exit 1
fi
git diff --stat -- "$f"
