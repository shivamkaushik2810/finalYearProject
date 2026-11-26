from src.services.substitution_dashboard_rules import day_kpis


def test_counts_and_completion():
    rows = [{"status": "assigned"}, {"status": "assigned"}, {"status": "proposed"}, {"status": "unassigned"}]
    k = day_kpis(rows, absent_teachers=2)
    assert k == {"absent_teachers": 2, "requiring": 4, "assigned": 2,
                 "pending": 1, "unassigned": 1, "completion": 50.0}


def test_empty_day_has_zero_completion_not_a_division_error():
    k = day_kpis([], absent_teachers=0)
    assert k["requiring"] == 0 and k["completion"] == 0.0
