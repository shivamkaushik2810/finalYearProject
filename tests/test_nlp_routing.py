import pytest
from src.pipelines.nlp_analytics import parse_query, answer_query

@pytest.mark.parametrize("q,intent", [
    ("Who was absent the most?", "most_absent"),
    ("How many students were present today?", "count_present"),
    ("Which students are at risk?", "at_risk"),
    ("What is the attendance rate?", "attendance_rate"),
    ("Who has the best attendance?", "best_attendance"),
    ("Who has the worst attendance?", "worst_attendance"),
    ("Who attended the most?", "most_present"),
])
def test_example_questions_route_correctly(q, intent):
    assert parse_query(q) == intent


def test_rate_ignores_students_with_no_logs():
    students = [{"student_id": "a", "name": "A"}, {"student_id": "b", "name": "B"}]
    logs = [{"student_id": "a", "is_present": True, "timestamp": "2026-11-01T10:00:00"}]
    text, _ = answer_query("what is the attendance rate", logs, students, "X")
    assert "100.0%" in text
