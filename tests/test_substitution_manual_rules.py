from src.services.substitution_manual_rules import run_ok, validate_reason


def test_three_in_a_row_is_allowed_four_is_not():
    assert run_ok([1, 2, 3])
    assert not run_ok([1, 2, 3, 4])


def test_lunch_break_ends_a_run():
    assert run_ok([3, 4, 5, 6, 7])
    assert not run_ok([2, 3, 4, 5, 6])


def test_gaps_reset_the_run():
    assert run_ok([1, 2, 3, 5, 6, 7])


def test_empty_is_fine():
    assert run_ok([])


def test_reason_length_rules():
    assert validate_reason("Medical") is None
    assert validate_reason("no") is not None
    assert validate_reason("x" * 301) is not None
    assert validate_reason(None) is not None
