"""Delivers queued substitution notices. Run by the scheduled workflow, or by hand.
Safe to run repeatedly: each notice is claimed once and marked sent or failed."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

from src.services.notification_service import deliver_due  # noqa: E402

MAX_ROUNDS = 20


def main():
    total = {"claimed": 0, "sent": 0, "failed": 0}
    for _ in range(MAX_ROUNDS):
        out = deliver_due()
        for key in total:
            total[key] += out[key]
        if out["claimed"] == 0:
            break
    print(f"Done: {total}")
    return 1 if total["failed"] and not total["sent"] else 0


if __name__ == "__main__":
    sys.exit(main())
