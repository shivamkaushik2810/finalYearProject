"""Deletes ALL test data (marker: e-mails ending @snapclass-test.invalid, subject codes TST*)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snap_testdata as td

if __name__ == "__main__":
    c = td.count_test_rows()
    print(f"About to delete: {c['teachers']} teacher(s), {c['students']} students, "
          f"{c['subjects']} subjects, {c['attendance_rows']} attendance rows (plus their marks, enrollments, reports).")
    if c["students"] == c["teachers"] == c["subjects"] == 0:
        print("No test data found. Nothing to delete.")
        sys.exit(0)
    if "--yes" not in sys.argv and input("Type DELETE TEST DATA to continue: ").strip() != "DELETE TEST DATA":
        raise SystemExit("Cancelled.")
    td.cleanup_test_data(print)
