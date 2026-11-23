"""Which weekly parent reports to send. Pure: no database, no Streamlit."""

FREQUENCIES = ("weekly", "only_below", "off")
FREQ_LABELS = {
    "weekly": "Every week",
    "only_below": "Only if attendance is below the target",
    "off": "Never send",
}


def normalise_frequency(value):
    return value if value in FREQUENCIES else "weekly"


def should_send(frequency, overall_pct, target):
    """overall_pct None means no classes, so nothing is sent for 'only_below'."""
    f = normalise_frequency(frequency)
    if f == "off":
        return False
    if f == "only_below":
        return overall_pct is not None and overall_pct < target
    return True
