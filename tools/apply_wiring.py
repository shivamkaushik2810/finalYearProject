"""Wires features into your real files with exact-text edits. Each file is all-or-nothing: if any expected text
is not found exactly once, that file is left untouched. A .bak copy is written before any change.
Usage (project root):  python tools/apply_wiring.py --dry-run   then   python tools/apply_wiring.py"""
import pathlib
import shutil
import sys

DRY = "--dry-run" in sys.argv

STUDENTS_QUERY_OLD = '''def get_students_with_faces():
    """All students that have a face embedding (paginated, stable order, no 1000-row cap)."""
    rows, start = [], 0
    while True:
        res = supabase.table('students') \\
            .select('student_id, name, face_embedding') \\
            .not_.is_('face_embedding', 'null') \\
            .order('student_id') \\
            .range(start, start + PAGE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows
'''
STUDENTS_QUERY_NEW = '''def get_students_with_faces():
    """All students that have a face embedding (paginated, stable order, no 1000-row cap).
    Includes the extra face angles (face_embeddings) when that column exists."""
    cols = 'student_id, name, face_embedding, face_embeddings'
    rows, start = [], 0
    while True:
        try:
            res = supabase.table('students') \\
                .select(cols) \\
                .not_.is_('face_embedding', 'null') \\
                .order('student_id') \\
                .range(start, start + PAGE - 1).execute()
        except Exception:
            if cols == 'student_id, name, face_embedding':
                raise
            cols = 'student_id, name, face_embedding'      # extra-angles column not migrated yet
            continue
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows
'''

FACE_OLD = '''    for s in get_students_with_faces():
        e = s.get('face_embedding')
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except Exception:
                continue
        if e and len(e) == 128:
            ids.append(s['student_id'])
            embs.append(e)
    return ids, np.array(embs, dtype=float)
'''
FACE_NEW = '''    for s in get_students_with_faces():
        # registration face plus extra angles: each is its own row for the same student,
        # so the nearest angle decides the match
        for e in [s.get('face_embedding')] + list(s.get('face_embeddings') or []):
            if isinstance(e, str):
                try:
                    e = json.loads(e)
                except Exception:
                    continue
            if e and len(e) == 128:
                ids.append(s['student_id'])
                embs.append(e)
    return ids, np.array(embs, dtype=float)
'''

PLAN = {
 "src/database/students_query.py": ("face_embeddings", [(STUDENTS_QUERY_OLD, STUDENTS_QUERY_NEW)]),
 "src/pipelines/face_pipeline.py": ("extra angles", [(FACE_OLD, FACE_NEW)]),
 "src/screens/student_screen.py": ("student_leave_tab", [
  ("from src.components.timetable import render_timetable\n",
   "from src.components.timetable import render_timetable\n"
   "from src.components.leave_ui import student_leave_tab\n"
   "from src.components.dialog_add_angles import add_angles_dialog\n"
   "from src.services.face_embeddings import all_embeddings\n"),
  ("    show_parent_email_update(student_data)\n",
   "    show_parent_email_update(student_data)\n\n"
   "    if len(all_embeddings(student_data)) < 3:\n"
   "        st.warning(\"📸 Add at least 3 face angles (front, left, right) so you are recognised reliably.\")\n"
   "        if st.button('Add face angles now', type='primary', key='add_angles_banner'):\n"
   "            add_angles_dialog(student_id)\n"),
  ("    tab_over, tab1, tab2, tab3 = st.tabs(['🏠 Overview', '📚 My Subjects', '📋 My Attendance', '📝 My Marks'])\n",
   "    tab_over, tab1, tab2, tab3, tab_leave = st.tabs(['🏠 Overview', '📚 My Subjects', '📋 My Attendance', '📝 My Marks', '📝 Leave'])\n"),
  ("    with tab3:\n        show_student_marks(student_id)\n",
   "    with tab3:\n        show_student_marks(student_id)\n\n"
   "    with tab_leave:\n        try:\n            student_leave_tab(student_id)\n"
   "        except Exception as e:\n            print(f\"Leave tab error: {type(e).__name__}\")\n"
   "            st.info(\"Leave requests are not available yet (database setup missing).\")\n"),
 ]),
 "src/screens/teacher_screen.py": ("teacher_more_tools", [
  ('    "analytics": ":material/monitoring: Analytics",\n}\n',
   '    "analytics": ":material/monitoring: Analytics",\n    "more_tools": ":material/build: Tools",\n}\n'),
  ("    elif current == \"analytics\":\n        teacher_analytics_tab(subjects, teacher_id)\n",
   "    elif current == \"analytics\":\n        teacher_analytics_tab(subjects, teacher_id)\n"
   "    elif current == \"more_tools\":\n"
   "        try:\n            from src.components.teacher_tools import teacher_more_tools\n"
   "            teacher_more_tools(subjects, teacher_id)\n"
   "        except Exception:\n            _log.exception(\"Tools tab failed\")\n"
   "            st.error(\"Tools could not load. Check the database setup (sql/migrations) and the terminal log.\")\n"),
 ]),
 "src/components/qr_session.py": ("check_session_allowed", [
  ("def _start_session(subject_id, teacher_id, minutes):\n    now = _now()\n",
   "def _start_session(subject_id, teacher_id, minutes):\n"
   "    try:                                    # timetable rule; no slots set = always allowed\n"
   "        from src.services.schedule_service import check_session_allowed\n"
   "        allowed, why = check_session_allowed(subject_id)\n"
   "    except Exception as e:                  # a setup problem must not block taking attendance\n"
   "        print(f\"Schedule check skipped: {type(e).__name__}\")\n"
   "        allowed, why = True, \"\"\n"
   "    if not allowed:\n        raise ValueError(why)\n    now = _now()\n"),
  ("    ok, _ = record_scan(_sid(session), student_id, subject_id, 'qr')\n    if not ok:\n"
   "        return False, \"You have already marked attendance for this session.\"\n",
   "    try:                                    # location / classroom-network rule; off unless the teacher enabled it\n"
   "        from src.components.session_guards import guard_scan\n"
   "        allowed, why = guard_scan(subject_id)\n"
   "    except Exception as e:\n        print(f\"Location check skipped: {type(e).__name__}\")\n"
   "        allowed, why = True, \"\"\n"
   "    if not allowed:\n        return False, why\n\n"
   "    ok, _ = record_scan(_sid(session), student_id, subject_id, 'qr')\n    if not ok:\n"
   "        return False, \"You have already marked attendance for this session.\"\n"),
 ]),
}

problems, ready = [], {}
for path, (marker, edits) in PLAN.items():
    p = pathlib.Path(path)
    if not p.exists():
        print(f"SKIP   {path}: file not found"); continue
    s = p.read_text(encoding="utf-8")
    if marker in s:
        print(f"DONE   {path}: already wired"); continue
    bad = [old.splitlines()[0][:70] for old, _ in edits if s.count(old) != 1]
    if bad:
        problems.append(path); print(f"FAIL   {path}: text not found exactly once -> {bad[0]!r}  (file left untouched)"); continue
    for old, new in edits:
        s = s.replace(old, new, 1)
    try:
        compile(s, path, "exec")
    except SyntaxError as e:
        problems.append(path); print(f"FAIL   {path}: result would not compile ({e.msg}); file left untouched"); continue
    ready[path] = s
    print(f"{'WOULD ' if DRY else ''}PATCH {path}: {len(edits)} edit(s)")
if not DRY:
    for path, s in ready.items():
        shutil.copy(path, path + ".bak")
        pathlib.Path(path).write_text(s, encoding="utf-8")
print("\nDry run only, nothing written." if DRY else f"\nWrote {len(ready)} file(s); .bak copies saved.")
sys.exit(1 if problems else 0)
