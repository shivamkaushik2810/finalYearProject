"""Baseline unit tests for SnapClass. No network, no real DB, no real emails."""
import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

# Stub the Supabase client BEFORE any src.* import (config.py reads st.secrets).
_fake_config = types.ModuleType("src.database.config")
_fake_config.supabase = MagicMock()
sys.modules["src.database.config"] = _fake_config

from src.pipelines.attendance_prediction import predict_absent_risk, get_subject_health
from src.pipelines.nlp_analytics import parse_query, answer_query
from src.services import weekly_report_service as wrs


def _log(sid, present):
    return {"student_id": sid, "is_present": present}


class TestAttendancePrediction(unittest.TestCase):
    def test_risk_levels(self):
        students = [{"student_id": "a", "name": "A"},
                    {"student_id": "b", "name": "B"},
                    {"student_id": "c", "name": "C"}]
        logs = ([_log("a", True)] * 4                      # 100% low
                + [_log("b", True), _log("b", False)]      # 50% medium
                + [_log("c", False)] * 3)                  # 0% high
        res = {r["student_id"]: r for r in predict_absent_risk(logs, students)}
        self.assertEqual(res["a"]["risk_level"], "low")
        self.assertEqual(res["b"]["risk_level"], "medium")
        self.assertEqual(res["c"]["risk_level"], "high")

    def test_no_data_and_empty_inputs(self):
        res = predict_absent_risk([], [{"student_id": "x", "name": "X"}])
        self.assertEqual(res[0]["risk_level"], "unknown")
        self.assertEqual(predict_absent_risk([], []), [])

    def test_ignores_logs_without_student_id(self):
        res = predict_absent_risk([{"is_present": True}], [{"student_id": "x", "name": "X"}])
        self.assertEqual(res[0]["total_classes"], 0)

    def test_subject_health(self):
        self.assertEqual(get_subject_health([], 5)["status"], "No Data")
        self.assertEqual(get_subject_health([_log("a", True)], 0)["status"], "No Data")
        self.assertEqual(get_subject_health([_log("a", True)] * 9 + [_log("a", False)], 1)["status"], "Excellent")
        self.assertEqual(get_subject_health([_log("a", False)] * 3, 1)["status"], "Poor")


class TestNlp(unittest.TestCase):
    def test_intents(self):
        self.assertEqual(parse_query("Who was absent?"), "absent_students")
        self.assertEqual(parse_query("which students are at risk"), "at_risk")
        self.assertEqual(parse_query("zzz"), "general_summary")

    def test_answer_with_no_logs_does_not_crash(self):
        students = [{"student_id": "a", "name": "A"}]
        text, _ = answer_query("attendance rate", [], students, "Math")
        self.assertIsInstance(text, str)

    def test_answer_with_no_students_does_not_crash(self):
        text, _ = answer_query("what is the summary", [], [], "Math")
        self.assertIsInstance(text, str)


class TestWeeklyReportEmail(unittest.TestCase):
    def _reports(self, attended, total):
        pct = round(attended / total * 100, 1) if total else 0
        return [{"subject_name": "Math", "subject_code": "M1", "total": total,
                 "attended": attended, "absent": total - attended, "attendance_pct": pct}]

    @patch.object(wrs, "_send")
    def test_email_content_and_warning(self, mock_send):
        wrs.send_weekly_parent_email("Parent", "p@example.com", "Stu", "1", "A",
                                     self._reports(1, 4), date(2026, 10, 12), date(2026, 10, 18))
        to, subject, html, plain = mock_send.call_args[0]
        self.assertEqual(to, "p@example.com")
        self.assertIn("Stu", subject)
        self.assertIn("Action Required", html)   # 25% < 75%
        self.assertIn("1/4", plain)

    @patch.object(wrs, "_send")
    def test_no_classes_no_division_error(self, mock_send):
        wrs.send_weekly_parent_email("P", "p@example.com", "S", None, None,
                                     [], "2026-10-12", "2026-10-18")
        self.assertTrue(mock_send.called)

    @patch.object(wrs, "_send")
    def test_good_attendance_has_no_warning(self, mock_send):
        wrs.send_weekly_parent_email("P", "p@example.com", "S", "1", "A",
                                     self._reports(4, 4), date(2026, 10, 12), date(2026, 10, 18))
        self.assertNotIn("Action Required", mock_send.call_args[0][2])


class TestWeeklyBatchIsolation(unittest.TestCase):
    STUDENTS = [
        {"student_id": "1", "name": "A", "parent_email": "a@x.com"},
        {"student_id": "2", "name": "B", "parent_email": "b@x.com"},
    ]
    SUBJECTS = [{"subjects": {"subject_id": "s", "name": "M", "subject_code": "M1"}}]

    @patch.object(wrs, "save_weekly_report")
    @patch.object(wrs, "send_weekly_parent_email")
    @patch.object(wrs, "get_weekly_attendance", return_value=[{"is_present": True}])
    @patch.object(wrs, "get_subjects_for_student")
    @patch.object(wrs, "get_all_enrolled_students_with_parents")
    @patch.object(wrs, "_already_reported", return_value=False)
    def test_one_failure_does_not_stop_others(self, _rep, m_students, m_subjects, _logs, m_send, _save):
        m_students.return_value = self.STUDENTS
        m_subjects.return_value = self.SUBJECTS
        m_send.side_effect = [Exception("smtp down"), None]
        self.assertEqual(wrs.send_weekly_reports_to_all_parents(), (1, 1))

    @patch.object(wrs, "send_weekly_parent_email")
    @patch.object(wrs, "get_all_enrolled_students_with_parents")
    @patch.object(wrs, "_already_reported", return_value=True)
    def test_already_reported_students_are_skipped_not_failed(self, _rep, m_students, m_send):
        m_students.return_value = self.STUDENTS
        self.assertEqual(wrs.send_weekly_reports_to_all_parents(), (0, 0))
        m_send.assert_not_called()

    @patch.object(wrs, "send_weekly_parent_email")
    @patch.object(wrs, "get_all_enrolled_students_with_parents")
    @patch.object(wrs, "_already_reported", side_effect=Exception("db down"))
    def test_dedupe_check_failure_fails_closed(self, _rep, m_students, m_send):
        m_students.return_value = self.STUDENTS
        self.assertEqual(wrs.send_weekly_reports_to_all_parents(), (0, 2))
        m_send.assert_not_called()

    @patch.object(wrs, "get_all_enrolled_students_with_parents")
    def test_students_without_parent_email_skipped(self, m_students):
        m_students.return_value = [{"student_id": "1", "name": "A", "parent_email": None}]
        self.assertEqual(wrs.send_weekly_reports_to_all_parents(), (0, 0))


if __name__ == "__main__":
    unittest.main()
