"""Adds an 'Accuracy' tab to src/components/teacher_tools.py. Exact-text edits only; refuses if the file differs.
Usage (project root):  python tools/wire_accuracy_tab.py [--dry-run]"""
import pathlib
import shutil
import sys

P = pathlib.Path("src/components/teacher_tools.py")
EDITS = [
    ("from src.components.leave_ui import teacher_leave_tab\n",
     "from src.components.leave_ui import teacher_leave_tab\nfrom src.features.accuracy.ui import show_accuracy_page\n"),
    ('    t1, t2, t3, t4 = st.tabs(["Leave Requests", "Corrections & Audit", "Eligibility", "Schedule & Location"])\n',
     '    t1, t2, t3, t4, t5 = st.tabs(["Leave Requests", "Corrections & Audit", "Eligibility", "Schedule & Location", "Accuracy"])\n'),
    ("    with t4:\n        _schedule(subjects, teacher_id)\n",
     "    with t4:\n        _schedule(subjects, teacher_id)\n    with t5:\n        show_accuracy_page()\n"),
]

if not P.exists():
    sys.exit(f"{P} not found. Run from the project root.")
s = P.read_text(encoding="utf-8")
if "show_accuracy_page" in s:
    sys.exit("Already wired. Nothing changed.")
for old, _ in EDITS:
    if s.count(old) != 1:
        sys.exit("FAIL: expected text not found exactly once:\n" + old + "Nothing changed. Send me src/components/teacher_tools.py.")
for old, new in EDITS:
    s = s.replace(old, new, 1)
if "--dry-run" in sys.argv:
    sys.exit("Dry run OK: all 3 edits would apply.")
shutil.copy(P, str(P) + ".bak")
P.write_text(s, encoding="utf-8")
compile(s, str(P), "exec")
print(f"Wired. Backup at {P}.bak")
