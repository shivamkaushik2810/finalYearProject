"""Read-only: checks which database pieces the new wiring needs. Changes nothing.  python tools/check_db_setup.py"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
from src.database.config import supabase

CHECKS = [
 ("students", "face_embeddings", "extra face angles", "sql/migrations/02_face_angles.sql"),
 ("leave_requests", "id", "student leave requests", "sql/migrations/03_leave_requests.sql then 05_fixes.sql"),
 ("subject_slots", "id", "class timetable rule", "sql/migrations/04_batch2.sql"),
 ("subject_geofence", "subject_id", "classroom location rule", "sql/migrations/04_batch2.sql"),
 ("attendance_audit_log", "id", "corrections audit log", "sql/migrations/04_batch2.sql"),
 ("eligibility_settings", "subject_id", "exam eligibility", "sql/migrations/04_batch2.sql"),
 ("alert_log", "id", "alert de-duplication", "sql/migrations/04_batch2.sql"),
 ("students", "phone", "phone numbers for alerts", "sql/migrations/04_batch2.sql"),
]
missing = 0
for table, col, what, fix in CHECKS:
    try:
        supabase.table(table).select(col).limit(1).execute()
        print(f"ok       {table}.{col}  ({what})")
    except Exception as e:
        missing += 1
        print(f"MISSING  {table}.{col}  ({what})  -> run {fix}")
print("\nAll present." if not missing else f"\n{missing} item(s) missing. The app still works; those features stay unavailable until the SQL is run.")
