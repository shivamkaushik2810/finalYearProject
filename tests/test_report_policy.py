from src.services.report_policy import normalise_frequency, should_send


def test_unknown_or_missing_value_defaults_to_weekly():
    assert normalise_frequency(None) == "weekly"
    assert normalise_frequency("hourly") == "weekly"


def test_off_never_sends():
    assert should_send("off", 10, 75) is False


def test_only_below_sends_only_under_target():
    assert should_send("only_below", 74.9, 75) is True
    assert should_send("only_below", 75, 75) is False
    assert should_send("only_below", None, 75) is False


def test_weekly_always_sends():
    assert should_send("weekly", 99, 75) is True
    assert should_send(None, None, 75) is True
