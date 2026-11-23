#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
cd "$SNAPCLASS_ROOT" || exit 1
for need in src/ui/widgets.py src/services/attendance_stats.py src/components/charts.py \
            src/components/subject_card.py src/ui/base_layout.py; do
  [ -f "$need" ] || { echo "Missing $need. Run merge_1 and merge_2 first."; exit 1; }
done
grep -q "pct=None, total=None" src/components/subject_card.py || { echo "Run merge_2_header_card.sh first."; exit 1; }

f="src/screens/teacher_screen.py"
cp "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"

python3 - << 'PYEOF'
import os, re, sys

path = os.environ.get("TEACHER_PATH", "src/screens/teacher_screen.py")
src = open(path, encoding="utf-8").read()
if "TEACHER_NAV" in src:
    sys.exit("Already merged: TEACHER_NAV found. Nothing changed.")


def must_sub(pattern, repl, text, what, flags=re.S):
    new, n = re.subn(pattern, lambda m: repl, text, count=1, flags=flags)
    if n != 1:
        sys.exit(f"Anchor not found for: {what}. Nothing was changed.")
    return new


# 1. imports (added after the last existing import of this file)
anchor = "from src.components.attendance_corrections import teacher_attendance_corrections\n"
if anchor not in src:
    sys.exit("Anchor not found for: imports. Nothing was changed.")
src = src.replace(anchor, anchor + """
import logging
from src.services import attendance_stats as S
from src.components.charts import attendance_trend, subject_bars
from src.ui.widgets import empty_state, stat_cards

_log = logging.getLogger(__name__)

TEACHER_NAV = {
    "overview": ":material/dashboard: Overview",
    "take_attendance": ":material/photo_camera: Attendance",
    "manage_subjects": ":material/menu_book: Subjects",
    "enrolled_students": ":material/group: Students",
    "attendance_records": ":material/cards_stack: Records",
    "marks": ":material/grade: Marks",
    "ai_insights": ":material/smart_toy: Insights",
    "analytics": ":material/monitoring: Analytics",
}
""", 1)

# 2. logout button: red outline style via the 'danger' key prefix
src = must_sub(r'if st\.button\("Logout", type="secondary", key="loginbackbtn", shortcut="control\+backspace"\):',
               'if st.button("Log out", type="secondary", key="danger_logout", shortcut="control+backspace"):',
               src, "logout button")

# 3. replace the 7 tabs-with-buttons block by one navigation row
m = re.search(r'    if "current_teacher_tab" not in st\.session_state:.*?\n    st\.divider\(\)\s*\n\s*current = st\.session_state\.current_teacher_tab\n',
               src, flags=re.S)
if not m or "st.tabs(" not in m.group(0) or "tabbtn_" not in m.group(0):
    sys.exit("Anchor not found for: tabs block. Nothing was changed.")
nav_block = '''    # one navigation row. The state key is the same one other code already uses.
    if st.session_state.get("current_teacher_tab") not in TEACHER_NAV:
        st.session_state.current_teacher_tab = st.session_state.get("_last_teacher_tab") or "overview"
    picked = st.segmented_control(
        "Section", list(TEACHER_NAV), format_func=TEACHER_NAV.get,
        key="current_teacher_tab", label_visibility="collapsed",
    )
    if picked:
        st.session_state["_last_teacher_tab"] = picked

    st.divider()

    current = picked or st.session_state.get("_last_teacher_tab") or "overview"
'''
src = src[:m.start()] + nav_block + src[m.end():]

# 4. overview branch
src = must_sub(r'    if current == "take_attendance":\n        teacher_tab_take_attendance\(\)',
               '    if current == "overview":\n        teacher_tab_overview(subjects)\n    elif current == "take_attendance":\n        teacher_tab_take_attendance()',
               src, "dispatch")

# 5. new functions, placed before teacher_tab_ai_insights
new_funcs = '''def _goto_tab(tab):
    st.session_state.current_teacher_tab = tab


def _load_subject_logs(subjects):
    """{subject_id: eligible logs}. Same helpers as AI Insights, so the numbers match."""
    out, failed = {}, []
    for s in subjects:
        sid = s["subject_id"]
        try:
            out[sid] = eligible(get_subject_logs_full(sid)) or []
        except Exception:
            _log.exception("Could not load attendance logs for subject_id=%s", sid)
            failed.append(s["name"])
    return out, failed


def _subject_pct_map(subjects):
    logs_by_sid, _ = _load_subject_logs(subjects)
    result = {}
    for sid, rows in logs_by_sid.items():
        t = S.overall(rows)
        result[sid] = (t["pct"], t["total"])
    return result


def teacher_tab_overview(subjects):
    st.header("Overview")
    if not subjects:
        empty_state("Create your first subject", "Subjects hold your students, attendance and marks.")
        st.button("Create subject", type="primary", on_click=_goto_tab, args=("manage_subjects",))
        return

    st.button("Take attendance now", type="primary", icon=":material/photo_camera:",
              on_click=_goto_tab, args=("take_attendance",))

    with st.spinner("Loading attendance..."):
        logs_by_sid, failed = _load_subject_logs(subjects)
    if failed:
        st.warning("Couldn't load attendance for: " + ", ".join(failed) + ". The numbers below leave them out.")

    all_logs = [dict(row, subject_id=sid) for sid, rows in logs_by_sid.items() for row in rows]
    total = S.overall(all_logs)
    at_risk = len(S.at_risk_students(all_logs))
    last = pd.to_datetime(S.last_session(all_logs), errors="coerce")
    last_txt = "None yet" if pd.isna(last) else f"{last:%d %b, %I:%M %p}"
    tone = ("" if not total["total"] else "good" if total["pct"] >= 75
            else "avg" if total["pct"] >= 50 else "bad")
    stat_cards([
        ("Subjects", len(subjects), ""),
        ("Average attendance", f"{total['pct']:.0f}%" if total["total"] else "No data", tone),
        ("At-risk students", at_risk, "bad" if at_risk else "good"),
        ("Last session", last_txt, ""),
    ])

    cols = st.columns(2)
    chart_rows = []
    for i, sub in enumerate(subjects):
        loaded = sub["subject_id"] in logs_by_sid  # a subject that failed to load shows no numbers
        t = S.overall(logs_by_sid.get(sub["subject_id"], []))
        if loaded:
            chart_rows.append((sub["name"], t["pct"]))
        with cols[i % 2]:
            subject_card(
                name=sub["name"], code=sub["subject_code"], section=sub["section"],
                course=sub.get("course"), year=sub.get("year"),
                stats=[("\\U0001FAC2", "Students", sub["total_students"]),
                       ("\\U0001F570\\uFE0F", "Classes", sub["total_classes"])],
                pct=t["pct"] if loaded else None, total=t["total"] if loaded else None,
            )

    c1, c2 = st.columns(2)
    with c1:
        subject_bars(chart_rows)
    with c2:
        attendance_trend(all_logs)


def _password_checks(pw, username="", name=""):
    """Checklist that mirrors validate_password below, so the hints never disagree with the rules."""
    pw = pw or ""
    low = pw.lower()
    personal = [p for p in [(username or "").lower()] + [w.lower() for w in (name or "").split() if len(w) >= 3] if p]
    _, msg = validate_password(pw)
    predictable = msg.startswith(("Password is too common", "Password must not repeat",
                                  "Password must not contain predictable"))
    return [
        (8 <= len(pw) <= 64, "8 to 64 characters"),
        (bool(re.search(r"[A-Z]", pw)), "An uppercase letter"),
        (bool(re.search(r"[a-z]", pw)), "A lowercase letter"),
        (bool(re.search(r"[0-9]", pw)), "A number"),
        (bool(re.search(r'[!@#$%^&*(),.?":{}|<>_\\-]', pw)), "A special character"),
        (bool(pw) and not predictable, "No common words, repeats or sequences like 1234"),
        (bool(pw) and not any(p in low for p in personal), "Doesn't contain your username or name"),
    ]


def _render_password_checklist(pw, username="", name=""):
    if not pw:
        return
    checks = _password_checks(pw, username, name)
    score = sum(1 for ok, _ in checks if ok)
    label = "Strong" if score == len(checks) else "Fair" if score >= 5 else "Weak"
    color = {"Strong": "#3B6D11", "Fair": "#BA7517", "Weak": "#A32D2D"}[label]
    segs = "".join(f'<i style="background:{color if n < score else "#cbd5e1"}"></i>' for n in range(len(checks)))
    tick, cross = "\\u2713", "\\u2717"
    lines = "<br>".join(f"{tick if ok else cross} {text}" for ok, text in checks)
    st.markdown(f'<div class="sc-pw" role="img" aria-label="Password strength: {label}">{segs}</div>'
                f'<div style="font-size:.85rem"><b>{label}</b><br>{lines}</div>', unsafe_allow_html=True)


'''
src = must_sub(r'def teacher_tab_ai_insights\(subjects, teacher_id\):',
               new_funcs + 'def teacher_tab_ai_insights(subjects, teacher_id):', src, "ai_insights def")

# 6. manage subjects: show status chip and progress bar on each card
src = must_sub(r"    subjects = get_teacher_subjects\(teacher_id\)\n    if subjects:\n        for sub in subjects:\n",
               "    subjects = get_teacher_subjects(teacher_id)\n    pct_map = _subject_pct_map(subjects) if subjects else {}\n    if subjects:\n        for sub in subjects:\n",
               src, "manage subjects loop")
src = must_sub(r"                stats=stats,\n                footer_callback=share_btn\n",
               "                stats=stats,\n                footer_callback=share_btn,\n                pct=pct_map.get(sub['subject_id'], (None, None))[0],\n                total=pct_map.get(sub['subject_id'], (None, None))[1]\n",
               src, "manage subjects card")

# 7. register screen: live password checklist
src = must_sub(r"    teacher_pass_confirm = st\.text_input\(\"Confirm your password\"",
               "    _render_password_checklist(teacher_pass, teacher_username, teacher_name)\n    teacher_pass_confirm = st.text_input(\"Confirm your password\"",
               src, "register password")

open(path, "w", encoding="utf-8").write(src)
print("merged", path)
PYEOF

python3 -m py_compile "$f" && echo "compiled $f"
git diff --stat -- "$f"
echo "Run: streamlit run app.py"
