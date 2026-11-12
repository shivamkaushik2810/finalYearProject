import argparse
import logging
import sys
 
from src.services.low_attendance_job import run
 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count recipients, send nothing")
    ap.add_argument("--threshold", type=float, default=75.0)
    ap.add_argument("--min-classes", type=int, default=3)
    ap.add_argument("--max-emails", type=int, default=400, help="per run; 0 = unlimited")
    a = ap.parse_args()
    stats = run(threshold=a.threshold, min_classes=a.min_classes, dry_run=a.dry_run,
                max_emails=a.max_emails or None)
    print("low-attendance:", stats)
    sys.exit(1 if stats.get("failed") and not stats.get("sent") else 0)
