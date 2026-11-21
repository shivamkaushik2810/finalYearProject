"""Entry point for GitHub Actions / cron:  python -m src.features.alerts.run [--dry-run]"""
import argparse
import contextlib
import os
import sys

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count who would be warned; send nothing")
    ap.add_argument("--max-emails", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--min-classes", type=int, default=None)
    a = ap.parse_args(argv)
    from src.features.alerts import low_attendance as la
    try:
        from src.services.mail_pool import pooled_smtp      # one reused SMTP connection for the batch
        ctx = pooled_smtp()
    except ImportError:
        ctx = contextlib.nullcontext()
    with ctx:
        res = la.run(dry_run=a.dry_run,
                     max_emails=a.max_emails or la.DEFAULT_MAX_EMAILS,
                     threshold=a.threshold or la.THRESHOLD,
                     min_classes=a.min_classes or la.MIN_CLASSES)
    print(res)
    return 1 if res["failed"] and not (res["emails_sent"] or res["messages_sent"]) else 0


if __name__ == "__main__":
    sys.exit(main())
