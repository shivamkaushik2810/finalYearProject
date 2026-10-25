import sys, types, unittest
from unittest.mock import MagicMock, patch

cfg = types.ModuleType("src.database.config"); cfg.supabase = MagicMock()
db  = types.ModuleType("src.database.db")
for n in ("get_all_enrolled_students_with_parents","get_subjects_for_student",
          "get_weekly_attendance","save_weekly_report"):
    setattr(db, n, MagicMock())
em  = types.ModuleType("src.services.email_service"); em._send = MagicMock()
sys.modules.update({"src.database.config": cfg, "src.database.db": db,
                    "src.services.email_service": em})
from src.services import weekly_report_service as w


def student(i=1, **kw):
    d = dict(student_id=i, name=f"S{i}", parent_email=f"p{i}@x.com",
             parent_name="Par", roll_no="1", section="A")
    d.update(kw); return d

def node(sid=10):
    return {"subjects": {"subject_id": sid, "name": "Math", "subject_code": "M1"}}

class T(unittest.TestCase):
    def setUp(self):
        for m in (w.get_all_enrolled_students_with_parents, w.get_subjects_for_student,
                  w.get_weekly_attendance, w.save_weekly_report, w._send):
            m.reset_mock(side_effect=True, return_value=True)
        w.get_subjects_for_student.return_value = [node()]
        w.get_weekly_attendance.return_value = [{"is_present": True}, {"is_present": False}]
        self.rep = patch.object(w, "_already_reported", return_value=False); self.rep.start()
    def tearDown(self): self.rep.stop()

    def test_happy_path_sends_then_saves(self):
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 0))
        w._send.assert_called_once(); w.save_weekly_report.assert_called_once()
        self.assertEqual(w.save_weekly_report.call_args[0][4:], (2, 1, 1, 50.0))

    def test_window_includes_sunday(self):
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        w.send_weekly_reports_to_all_parents()
        start, end = w.get_weekly_attendance.call_args[0][2:4]
        self.assertTrue(start.endswith("T00:00:00")); self.assertTrue(end.endswith("T23:59:59"))

    def test_no_save_if_send_fails(self):
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        w._send.side_effect = RuntimeError("smtp down")
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 1))
        w.save_weekly_report.assert_not_called()

    def test_already_reported_skips(self):
        self.rep.stop(); self.rep = patch.object(w, "_already_reported", return_value=True); self.rep.start()
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 0))
        w._send.assert_not_called()

    def test_dedupe_check_error_fails_closed(self):
        self.rep.stop(); self.rep = patch.object(w, "_already_reported", side_effect=RuntimeError("db")); self.rep.start()
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 1))
        w._send.assert_not_called()

    def test_zero_classes_not_emailed(self):
        w.get_weekly_attendance.return_value = []
        w.get_all_enrolled_students_with_parents.return_value = [student()]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 0))
        w._send.assert_not_called(); w.save_weekly_report.assert_not_called()

    def test_failure_isolated_between_students(self):
        w.get_all_enrolled_students_with_parents.return_value = [student(1), student(2)]
        w._send.side_effect = [RuntimeError("x"), None]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 1))

    def test_missing_parent_email_and_none_parent_name(self):
        w.get_all_enrolled_students_with_parents.return_value = [
            student(1, parent_email=None), student(2, parent_name=None)]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 0))
        self.assertEqual(w._send.call_args[0][0], "p2@x.com")
        self.assertIn("Dear <strong>Parent</strong>", w._send.call_args[0][2])

    def test_html_escaped_but_subject_raw(self):
        evil = '<script>alert(1)</script>'
        w.get_all_enrolled_students_with_parents.return_value = [student(name=evil, section=evil)]
        w.get_subjects_for_student.return_value = [
            {"subjects": {"subject_id": 1, "name": evil, "subject_code": "X"}}]
        w.send_weekly_reports_to_all_parents()
        subject, body = w._send.call_args[0][1], w._send.call_args[0][2]
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertIn(evil, subject)

    def test_none_values_in_email_builder(self):
        w.send_weekly_parent_email("P","p@x.com","S",None,None,
            [{"subject_name":"M","attended":0,"total":2,"attendance_pct":0.0}],
            "2026-10-12","2026-10-18")
        self.assertIn("N/A", w._send.call_args[0][2])

if __name__ == "__main__":
    unittest.main(verbosity=2)
