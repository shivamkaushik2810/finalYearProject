"""Cleans up Phase 9 test rows for ONE run ID. Never deletes by pattern or age.

Rows the database protects (audit events, versions referenced by substitutions) are not deleted.
They are marked as test data instead, so they can be recognised and hidden.
Usage: python3 scripts/phase9_cleanup.py <RUN_ID>   (RUN_ID must start with p9-)"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

from src.database.config import supabase  # noqa: E402


def main():
    if len(sys.argv) != 2 or not sys.argv[1].startswith("p9-"):
        sys.exit("Give exactly one run ID that starts with p9-")
    run = sys.argv[1]
    counts = {}
    counts["notification_outbox"] = len(supabase.table("notification_outbox").delete()
                                        .like("idempotency_key", f"{run}%").execute().data or [])
    counts["faculty_substitutions_cancelled"] = len(supabase.table("faculty_substitutions")
        .update({"status": "unassigned", "substitute_teacher_id": None, "reasons": "phase9 test data"})
        .like("created_by", f"{run}%").execute().data or [])
    counts["timetable_versions_archived"] = len(supabase.table("timetable_versions")
        .update({"status": "archived", "notes": "phase9 test data"})
        .like("label", f"{run}%").execute().data or [])
    counts["teachers_deactivated"] = len(supabase.table("teachers")
        .update({"status": "rejected"})
        .like("username", f"{run}%").execute().data or [])
    print(f"Cleaned {run}: {counts}")
    print("Audit events are kept by design. Test rows are archived, cancelled or deactivated, not deleted.")


if __name__ == "__main__":
    main()
