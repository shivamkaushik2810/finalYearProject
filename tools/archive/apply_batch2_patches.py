import pathlib
import shutil


def patch(path, old, new, marker):
    p = pathlib.Path(path)
    if not p.exists():
        print(f"SKIP  {path}: file not found"); return False
    s = p.read_text(encoding="utf-8")
    if marker in s:
        print(f"DONE  {path}: already patched ({marker!r})"); return True
    if s.count(old) != 1:
        print(f"FAIL  {path}: anchor found {s.count(old)}x (need 1) -> apply by hand ({marker!r})"); return False
    bak = pathlib.Path(str(p) + ".bak")
    if not bak.exists():
        shutil.copy(p, bak)
    p.write_text(s.replace(old, new), encoding="utf-8")
    print(f"OK    {path}: {marker!r}"); return True


FP = "src/pipelines/face_pipeline.py"
patch(FP,
'''from src.database.db import get_all_students
''',
'''from src.database.db import get_all_students
from src.services.face_embeddings import all_embeddings
''', "from src.services.face_embeddings import all_embeddings")

patch(FP,
'''            emb = student.get('face_embedding')
            sid = student.get('student_id')
            if emb and sid:
                # Add each embedding multiple times for better training
                for _ in range(5):
                    X.append(emb)
                    y.append(sid)
''',
'''            sid = student.get('student_id')
            embs = all_embeddings(student)
            if embs and sid:
                # One sample: repeat it (as before). Several angles: use each once.
                reps = 5 if len(embs) == 1 else 1
                for emb in embs:
                    for _ in range(reps):
                        X.append(emb)
                        y.append(sid)
''', "reps = 5 if len(embs) == 1 else 1")

patch(FP,
'''                final_dist = np.linalg.norm(
                    np.array(list(unique_students[final_match])[0]) - encoding_np
                ) if final_match in unique_students else 1.0
''',
'''                final_dist = min(
                    np.linalg.norm(np.array(e) - encoding_np)
                    for e in unique_students[final_match]
                ) if final_match in unique_students else 1.0
''', "for e in unique_students[final_match]")

SS = "src/screens/student_screen.py"
patch(SS,
'''from src.components.marks_management import show_student_marks
''',
'''from src.components.marks_management import show_student_marks
from src.components.dialog_add_angles import add_angles_dialog
from src.components.leave_ui import student_leave_tab
from src.components.contact_prefs import contact_prefs_ui
from src.services.face_embeddings import all_embeddings
''', "from src.components.dialog_add_angles import")

patch(SS,
'''    st.space()

    tab1, tab2, tab3 = st.tabs(['📚 My Subjects', '📋 My Attendance', '📝 My Marks'])
''',
'''    st.space()

    if len(all_embeddings(student_data)) < 3:
        st.warning("📸 Add at least 3 face angles (front, left, right) so you are recognised reliably.")
        if st.button('Add face angles now', type='primary', key='add_angles_banner'):
            add_angles_dialog(student_id)

    with st.expander("🔔 Alert contact settings"):
        contact_prefs_ui(student_id)

    tab1, tab2, tab3, tab4 = st.tabs(['📚 My Subjects', '📋 My Attendance', '📝 My Marks', '📝 Leave'])
''', "'📝 Leave'")

patch(SS,
'''    with tab3:
        show_student_marks(student_id)

    footer_dashboard()
''',
'''    with tab3:
        show_student_marks(student_id)

    with tab4:
        student_leave_tab(student_id)

    footer_dashboard()
''', "with tab4:")

TS = "src/screens/teacher_screen.py"
patch(TS,
'''from src.components.dialog_voice_attendance import voice_attendance_dialog
''',
'''from src.components.dialog_voice_attendance import voice_attendance_dialog
from src.components.teacher_tools import teacher_more_tools
''', "from src.components.teacher_tools import teacher_more_tools")

patch(TS,
'''    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Take Attendance",
        "Manage Subjects",
        "Enrolled Students",
        "Attendance Records",
        "Marks",
        "AI Insights"
    ])
''',
'''    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Take Attendance",
        "Manage Subjects",
        "Enrolled Students",
        "Attendance Records",
        "Marks",
        "AI Insights",
        "More Tools"
    ])
''', '"More Tools"')

patch(TS,
'''    with tab6:
        if st.button("AI Insights", type="tertiary", width="stretch", icon=":material/smart_toy:"):
            st.session_state.current_teacher_tab = "ai_insights"
            st.rerun()
''',
'''    with tab6:
        if st.button("AI Insights", type="tertiary", width="stretch", icon=":material/smart_toy:"):
            st.session_state.current_teacher_tab = "ai_insights"
            st.rerun()

    with tab7:
        type7 = "primary" if st.session_state.current_teacher_tab == "more_tools" else "tertiary"
        if st.button("More Tools", type=type7, width="stretch", icon=":material/build:"):
            st.session_state.current_teacher_tab = "more_tools"
            st.rerun()
''', "with tab7:")

patch(TS,
'''    if st.session_state.current_teacher_tab == "ai_insights":
        teacher_tab_ai_insights(subjects, teacher_id)
''',
'''    if st.session_state.current_teacher_tab == "ai_insights":
        teacher_tab_ai_insights(subjects, teacher_id)
    if st.session_state.current_teacher_tab == "more_tools":
        teacher_more_tools(subjects, teacher_id)
''', "teacher_more_tools(subjects, teacher_id)")

# excused absences must not count against the student
SA = "src/components/student_attendance_list.py"
patch(SA,
'''        subject_stats[sid]['total'] += 1
        if log.get('is_present'):
            subject_stats[sid]['present'] += 1
        else:
            subject_stats[sid]['absent'] += 1
        subject_stats[sid]['logs'].append(log)
''',
'''        if log.get('is_excused') and not log.get('is_present'):
            subject_stats[sid]['excused'] = subject_stats[sid].get('excused', 0) + 1
        else:
            subject_stats[sid]['total'] += 1
            if log.get('is_present'):
                subject_stats[sid]['present'] += 1
            else:
                subject_stats[sid]['absent'] += 1
        subject_stats[sid]['logs'].append(log)
''', "'excused'")

patch(SA,
'''                status     = "✅ Present" if is_present else "❌ Absent"
''',
'''                if is_present:
                    status = "✅ Present"
                elif log.get('is_excused'):
                    status = "🟦 Excused"
                else:
                    status = "❌ Absent"
''', "🟦 Excused")

patch("src/pipelines/attendance_prediction.py",
'''        sid = log.get('student_id')
        if not sid:
            continue
        stats[sid]['total'] += 1
''',
'''        sid = log.get('student_id')
        if not sid:
            continue
        if log.get('is_excused') and not log.get('is_present'):
            continue
        stats[sid]['total'] += 1
''', "is_excused")

patch("src/pipelines/nlp_analytics.py",
'''        if sid not in stats:
            continue
        stats[sid]['total'] += 1
''',
'''        if sid not in stats:
            continue
        if log.get('is_excused') and not log.get('is_present'):
            continue
        stats[sid]['total'] += 1
''', "is_excused")

patch("src/services/weekly_report_service.py",
'''                total   = len(logs)
                attended = sum(1 for l in logs if l.get('is_present'))
''',
'''                logs = [l for l in logs if l.get('is_present') or not l.get('is_excused')]
                total   = len(logs)
                attended = sum(1 for l in logs if l.get('is_present'))
''', "is_excused")

# weekly report now runs from GitHub Actions, not on page load
SC = "src/services/scheduler.py"
patch(SC, "import threading\n", "import os\nimport threading\n", "import os\nimport threading")
patch(SC,
'''        if not _should_send_weekly_report():
            return
''',
'''        if os.environ.get("SNAPCLASS_PAGELOAD_JOBS", "0") != "1":
            return  # weekly report now runs from GitHub Actions
        if not _should_send_weekly_report():
            return
''', "SNAPCLASS_PAGELOAD_JOBS")

# requirements + gitignore
for path, lines in (("requirements.txt", ["requests", "streamlit-js-eval"]),
                    (".gitignore", ["*.bak"])):
    p = pathlib.Path(path)
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        missing = [l for l in lines if l not in txt.split()]
        if missing:
            p.write_text(txt.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
            print(f"OK    {path}: added {missing}")
        else:
            print(f"DONE  {path}")
