from src.services import substitution_analytics as A

ROWS = [
    {"id": 1, "substitution_date": "2026-11-23", "status": "assigned", "substitute_name": "Nikhil Tomar",
     "original_teacher_code": "RM", "subject_code": "BCS 603", "reasons": None,
     "created_at": "2026-11-23T10:00:00+00:00"},
    {"id": 2, "substitution_date": "2026-11-24", "status": "unassigned", "substitute_name": "",
     "original_teacher_code": "RM", "subject_code": "BCS 603",
     "reasons": "no eligible teacher: 2 x not qualified", "created_at": "2026-11-24T09:00:00+00:00"},
    {"id": 3, "substitution_date": "2026-11-30", "status": "assigned", "substitute_name": "afsha ishtiyaq",
     "original_teacher_code": "VU", "subject_code": "BCS 601", "reasons": None,
     "created_at": "2026-11-30T08:00:00+00:00"},
]
EVENTS = [
    {"substitution_id": 1, "action": "confirm", "at": "2026-11-23T10:30:00+00:00"},
    {"substitution_id": 2, "action": "override", "at": "2026-11-24T09:45:00+00:00"},
    {"substitution_id": 1, "action": "accept", "at": "2026-11-23T11:00:00+00:00"},
    {"substitution_id": 3, "action": "accept", "at": "2026-11-30T09:00:00+00:00"},
    {"substitution_id": 3, "action": "decline", "at": "2026-11-30T09:30:00+00:00"},
    {"substitution_id": 2, "action": "reject", "at": "2026-11-24T08:00:00+00:00"},
]


def test_summary_percentages():
    s = A.summary(ROWS)
    assert (s["total"], s["assigned"], s["unassigned"]) == (3, 2, 1)
    assert s["assigned_pct"] == 66.7 and s["unassigned_pct"] == 33.3


def test_weekly_buckets_start_on_monday():
    weeks = A.by_week(ROWS)
    assert [w["period"] for w in weeks] == ["2026-11-23", "2026-11-30"]
    assert weeks[0]["total"] == 2 and weeks[0]["unassigned"] == 1


def test_monthly_bucket():
    assert A.by_month(ROWS) == [{"period": "2026-11", "total": 3, "assigned": 2, "unassigned": 1}]


def test_most_absent_and_substitutes():
    assert A.most_absent(ROWS)[0] == {"name": "RM", "count": 2}
    names = {x["name"] for x in A.most_used_substitutes(ROWS)}
    assert names == {"Nikhil Tomar", "afsha ishtiyaq"}


def test_unassigned_rows_do_not_count_as_substitutes():
    assert all(x["name"] for x in A.substitute_workload(ROWS))


def test_department_grouping_uses_unknown_until_entered():
    assert A.by_department(ROWS, {"RM": "CSE"}) == [{"name": "Unknown", "count": 1}, {"name": "CSE", "count": 2}] \
        or A.by_department(ROWS, {"RM": "CSE"}) == [{"name": "CSE", "count": 2}, {"name": "Unknown", "count": 1}]
    assert A.by_department(ROWS, {}) == [{"name": "Unknown", "count": 3}]


def test_unassigned_reasons_are_counted():
    assert A.unassigned_reasons(ROWS) == [{"name": "no eligible teacher: 2 x not qualified", "count": 1}]


def test_decision_rates():
    r = A.decision_rates(EVENTS)
    assert (r["accepted"], r["declined"]) == (2, 1)
    assert r["acceptance_rate"] == 66.7
    assert r["rejected"] == 1 and r["rejection_rate"] == 33.3


def test_assignment_speed_measures_only_events_that_exist():
    s = A.assignment_speed(ROWS, EVENTS)
    assert s["measured"] == 2 and s["of"] == 3
    assert s["coverage_pct"] == 66.7
    assert s["avg_minutes"] == 37.5


def test_empty_inputs_never_divide_by_zero():
    assert A.summary([])["assigned_pct"] == 0.0
    assert A.decision_rates([])["acceptance_rate"] == 0.0
    assert A.assignment_speed([], [])["avg_minutes"] is None
    assert A.pct(0, 0) == 0.0
    assert A.by_week([]) == []
