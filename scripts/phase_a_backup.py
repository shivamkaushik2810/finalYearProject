"""Read-only backup of existing timetable tables to CSV under backups/. Changes nothing in the database."""
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

from src.database.config import supabase

TABLES = {"timetables": "id", "subject_slots": "id", "subjects": "subject_id"}
PAGE = 1000


def fetch_all(table, order_col):
    rows, start = [], 0
    while True:
        chunk = (supabase.table(table).select("*").order(order_col)
                 .range(start, start + PAGE - 1).execute().data or [])
        rows.extend(chunk)
        if len(chunk) < PAGE:
            return rows
        start += PAGE


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "backups" / f"phase_a_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = []
    for table, order_col in TABLES.items():
        rows = fetch_all(table, order_col)
        path = out_dir / f"{table}.csv"
        cols = sorted({k for r in rows for k in r.keys()}) or ["empty"]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        manifest.append(f"{table}: {len(rows)} rows -> {path.name}")
        print(f"backed up {table}: {len(rows)} rows")
    (out_dir / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"Backup folder: {out_dir}")


if __name__ == "__main__":
    main()
