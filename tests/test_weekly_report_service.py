import unittest
from unittest.mock import MagicMock, patch

from src.services import weekly_report_service as w


def student(i=1, **kw):
    d = dict(student_id=i, name=f"S{i}", parent_email=f"p{i}@x.com",
             parent_name="Par", roll_no="1", section="A")
    d.update(kw)
    return d


def node(sid=10):
    return {"subjects": {"subject_id": sid, "name": "Math", "subject_code": "M1"}}


class T(unittest.TestCase):
    def setUp(self):
        self.mocks = {
            "get_all_enrolled_students_with_parents": patch.object(w, "get_all_enrolled_students_with_parents"),
            "get_subjects_for_student": patch.object(w, "get_subjects_for_student"),
            "get_weekly_attendance": patch.object(w, "get_weekly_attendance"),
            "save_weekly_report": patch.object(w, "save_weekly_report"),
            "_send": patch.object(w, "_send"),
            "_already_reported": patch.object(w, "_already_reported", return_value=False),
        }
        self.m = {k: p.start() for k, p in self.mocks.items()}
        self.addCleanup(patch.stopall)
        self.m["get_subjects_for_student"].return_value = [node()]
        self.m["get_weekly_attendance"].return_value = [{"is_present": True}, {"is_present": False}]

    def _students(self, *s):
        self.m["get_all_enrolled_students_with_parents"].return_value = list(s)

    def test_happy_path_sends_then_saves(self):
        self._students(student())
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 0))
        self.m["_send"].assert_called_once()
        self.m["save_weekly_report"].assert_called_once()
        self.assertEqual(self.m["save_weekly_report"].call_args[0][4:], (2, 1, 1, 50.0))

    def test_window_includes_sunday(self):
        self._students(student())
        w.send_weekly_reports_to_all_parents()
        start, end = self.m["get_weekly_attendance"].call_args[0][2:4]
        self.assertTrue(start.endswith("T00:00:00"))
        self.assertTrue(end.endswith("T23:59:59"))

    def test_no_save_if_send_fails(self):
        self._students(student())
        self.m["_send"].side_effect = RuntimeError("smtp down")
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 1))
        self.m["save_weekly_report"].assert_not_called()

    def test_already_reported_skips(self):
        self.m["_already_reported"].return_value = True
        self._students(student())
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 0))
        self.m["_send"].assert_not_called()

    def test_dedupe_check_error_fails_closed(self):
        self.m["_already_reported"].side_effect = RuntimeError("db")
        self._students(student())
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 1))
        self.m["_send"].assert_not_called()

    def test_zero_classes_not_emailed(self):
        self.m["get_weekly_attendance"].return_value = []
        self._students(student())
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (0, 0))
        self.m["_send"].assert_not_called()
        self.m["save_weekly_report"].assert_not_called()

    def test_failure_isolated_between_students(self):
        self._students(student(1), student(2))
        self.m["_send"].side_effect = [RuntimeError("x"), None]
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 1))

    def test_missing_parent_email_and_none_parent_name(self):
        self._students(student(1, parent_email=None), student(2, parent_name=None))
        self.assertEqual(w.send_weekly_reports_to_all_parents(), (1, 0))
        self.assertEqual(self.m["_send"].call_args[0][0], "p2@x.com")
        self.assertIn("Dear <strong>Parent</strong>", self.m["_send"].call_args[0][2])

    def test_html_escaped_but_subject_raw(self):
        evil = "<script>alert(1)</script>"
        self._students(student(name=evil, section=evil))
        self.m["get_subjects_for_student"].return_value = [
            {"subjects": {"subject_id": 1, "name": evil, "subject_code": "X"}}]
        w.send_weekly_reports_to_all_parents()
        subject, body = self.m["_send"].call_args[0][1], self.m["_send"].call_args[0][2]
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertIn(evil, subject)

    def test_none_values_in_email_builder(self):
        w.send_weekly_parent_email(
            "P", "p@x.com", "S", None, None,
            [{"subject_name": "M", "attended": 0, "total": 2, "attendance_pct": 0.0}],
            "2026-10-12", "2026-10-18")
        self.assertIn("N/A", self.m["_send"].call_args[0][2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
