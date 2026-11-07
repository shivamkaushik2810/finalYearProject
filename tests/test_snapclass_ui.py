"""Unit tests for the pure helpers behind the UI refresh. Run from the project root:
    python -m unittest discover -s tests -v
They need no database, no Gmail and no camera."""
import sys
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock

sys.path.insert(0, ".")
try:
    import streamlit  # noqa: F401
except ImportError:  # lets the tests run on a machine without Streamlit
    sys.modules["streamlit"] = MagicMock()

from src.components import charts
from src.services import attendance_stats as S
from src.services import email_templates as T
from src.ui import tokens, widgets


class StatsTests(unittest.TestCase):
    def test_status_boundaries(self):
        self.assertEqual(S.status_for(75, 4)[0], "good")
        self.assertEqual(S.status_for(74.9, 4)[0], "avg")
        self.assertEqual(S.status_for(50, 4)[0], "avg")
        self.assertEqual(S.status_for(49.9, 4)[0], "risk")
        self.assertEqual(S.status_for(0, 0)[0], "none")  # no classes is not 0 percent

    def test_pct_never_divides_by_zero(self):
        self.assertEqual(S.pct(0, 0), 0.0)
        self.assertEqual(S.pct(3, 4), 75.0)

    def test_classes_needed(self):
        need = S.classes_needed(6, 10)
        self.assertEqual(need, 6)
        self.assertGreaterEqual((6 + need) / (10 + need), 0.75)
        self.assertLess((6 + need - 1) / (10 + need - 1), 0.75)
        self.assertEqual(S.classes_needed(9, 10), 0)
        self.assertEqual(S.classes_needed(0, 0), 0)

    def test_per_student_handles_missing_values(self):
        logs = [{"student_id": "a", "is_present": True}, {"student_id": "a", "is_present": None},
                {"student_id": "a", "is_present": False}, {"student_id": None, "is_present": True},
                {"is_present": True}]
        self.assertEqual(S.per_student(logs), {"a": {"present": 1, "total": 3}})

    def test_at_risk_counts_distinct_students(self):
        logs = ([{"student_id": "a", "subject_id": 1, "is_present": False}] * 3
                + [{"student_id": "a", "subject_id": 2, "is_present": False}] * 3
                + [{"student_id": "b", "subject_id": 1, "is_present": True}] * 3)
        self.assertEqual(S.at_risk_students(logs), {"a"})

    def test_overall_and_last_session(self):
        logs = [{"is_present": True, "timestamp": "2026-10-01T10:00:00"},
                {"is_present": False, "timestamp": "2026-10-02T10:00:00"}]
        self.assertEqual(S.overall(logs)["pct"], 50.0)
        self.assertEqual(S.last_session(logs), "2026-10-02T10:00:00")
        self.assertIsNone(S.last_session([]))

    def test_csv_safe_blocks_formulas(self):
        self.assertEqual(S.csv_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(S.csv_safe("+1"), "'+1")
        self.assertEqual(S.csv_safe("Ananya"), "Ananya")
        self.assertEqual(S.csv_safe(5), 5)

    def test_valid_email(self):
        for ok in ("a@b.co", "first.last@college.edu.in"):
            self.assertTrue(S.valid_email(ok), ok)
        for bad in ("", None, "a@b", "a b@c.com", "@c.com", "a@@c.com", "a@c."):
            self.assertFalse(S.valid_email(bad), bad)


class WidgetTests(unittest.TestCase):
    def test_password_requirements(self):
        _, score, label = widgets.password_requirements("abc")
        self.assertEqual((score, label), (1, "Weak"))
        _, score, label = widgets.password_requirements("Abcdef12")
        self.assertEqual((score, label), (4, "Fair"))
        _, score, label = widgets.password_requirements("Abcdef12!")
        self.assertEqual((score, label), (5, "Strong"))
        self.assertEqual(widgets.password_requirements(None)[1], 0)

    def test_html_is_escaped(self):
        self.assertNotIn("<script>", widgets.chip("<script>alert(1)</script>"))
        self.assertEqual(widgets.esc(None), "")

    def test_progress_is_clamped(self):
        self.assertIn("width:100.0%", widgets.progress_html(250))
        self.assertIn("width:0.0%", widgets.progress_html(-5))
        self.assertIn("width:0.0%", widgets.progress_html(None))

    def test_tokens_render_css_variables(self):
        css = tokens.css_variables()
        self.assertTrue(css.startswith(":root{") and "--sc-primary:#5865F2" in css)


class ChartTests(unittest.TestCase):
    LOGS = [
        {"timestamp": "2026-10-12T10:00:00", "is_present": True},
        {"timestamp": "2026-10-12T11:00:00", "is_present": False},
        {"timestamp": "2026-10-13T10:00:00+00:00", "is_present": True},
        {"timestamp": "2026-10-14T10:00:00.123456", "is_present": False},
        {"timestamp": "not a date", "is_present": True},
        {"timestamp": None, "is_present": True},
    ]

    def test_bad_timestamps_are_dropped(self):
        df = charts.logs_to_df(self.LOGS)
        self.assertEqual(len(df), 4)

    def test_empty_inputs(self):
        self.assertTrue(charts.logs_to_df([]).empty)
        self.assertTrue(charts.logs_to_df([{"x": 1}]).empty)
        self.assertTrue(charts.weekly_trend(charts.logs_to_df([])).empty)

    def test_weekly_trend_is_percent(self):
        tr = charts.weekly_trend(charts.logs_to_df(self.LOGS))
        self.assertEqual(float(tr["Attendance %"].iloc[0]), 50.0)

    def test_heatmap_cells(self):
        df = charts.logs_to_df(self.LOGS)
        rows = charts.heatmap_rows(df, weeks=1, today=date(2026, 10, 16))
        label, cells = rows[0]
        self.assertEqual(label, "12 Oct")
        self.assertEqual(cells[0][1], "avg")    # Mon: one present, one absent
        self.assertEqual(cells[1][1], "good")   # Tue
        self.assertEqual(cells[2][1], "risk")   # Wed
        self.assertEqual(cells[3][1], "none")   # Thu: no class
        self.assertEqual(cells[5][1], "none")   # Sat is after "today"


class EmailTests(unittest.TestCase):
    def test_student_email_escapes_user_text(self):
        html, plain = T.student_attendance_email("<b>Eve</b>", "Maths<script>", "M1", "T & Co", "today")
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>Eve</b>", html)
        self.assertIn("&lt;b&gt;Eve&lt;/b&gt;", html)
        self.assertIn("Present", plain)

    def test_teacher_email_counts(self):
        html, plain = T.teacher_summary_email("Ms Roy", "ML", "CS101", "now", ["A", "B"], 5)
        self.assertIn("Present : 2 / 5", plain)
        self.assertIn("Absent  : 3", plain)
        html_empty, _ = T.teacher_summary_email("Ms Roy", "ML", "CS101", "now", [], 5)
        self.assertIn("No students were present", html_empty)

    def test_weekly_email_with_and_without_classes(self):
        reports = [{"subject_name": "ML", "attended": 1, "total": 4, "attendance_pct": 25.0}]
        html, plain = T.weekly_parent_email("Mr K", "Kid", "12", "A", "a", "b", reports)
        self.assertIn("below 75%", html)
        self.assertIn("Overall: 1/4 (25.0%)", plain)
        html0, plain0 = T.weekly_parent_email("Mr K", "Kid", None, None, "a", "b", [])
        self.assertIn("No classes this week", html0)
        self.assertNotIn("below 75%", html0)

    def test_every_template_shares_the_brand_shell(self):
        a, _ = T.student_attendance_email("a", "b", "c", "d", "e")
        b, _ = T.teacher_summary_email("a", "b", "c", "d", [], 0)
        c, _ = T.weekly_parent_email("a", "b", "c", "d", "e", "f", [])
        for page in (a, b, c):
            self.assertIn(T.BRAND, page)
            self.assertIn("Making attendance smarter with AI", page)


if __name__ == "__main__":
    unittest.main()
