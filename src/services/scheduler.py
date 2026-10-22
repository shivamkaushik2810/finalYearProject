def check_and_send_weekly_reports():
    """Intentionally a no-op: the scheduled GitHub Action sends the weekly reports now."""
    return


def manual_send_weekly_reports():
    """Teacher dashboard button: sends to every parent who hasn't received this week's report yet."""
    from src.services.weekly_report_runner import send_weekly_reports_to_all_parents
    return send_weekly_reports_to_all_parents(force=False)
