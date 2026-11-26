"""Build the SAMPLE draft CSV for section 3C (semester 5). Writes a file only.

Usage:  python3 scripts/make_sample_timetable.py [--force]
Then:   python3 scripts/import_timetable_csv.py data/sample_sem5_3C.csv --label sample-sem5-3C --dry-run
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.sample_timetable import CATALOGUE, build, to_csv_rows  # noqa: E402

REAL_CODES = frozenset({"HU", "PS", "RM", "RO", "SH", "SN", "VK", "VU"})
OUT = ROOT / "data" / "sample_sem5_3C.csv"
COLUMNS = ["section_code", "weekday", "period_no", "kind", "subject_code",
           "subject_name", "faculty_code", "room", "block_len"]
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


def main():
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT} already exists. Re-run with --force to replace it.")

    result = build(real_codes=REAL_CODES)
    if result["unplaced"]:
        print("NOT WRITTEN. These classes could not be placed cleanly:")
        for u in result["unplaced"]:
            print(f"  {u['subject_code']} block {u['n'] + 1} ({u['faculty_name']})")
        sys.exit(1)

    rows = to_csv_rows(result)
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} periods to {OUT}")
    print("Sample faculty codes (not real accounts):")
    for name, code in sorted(result["faculty_codes"].items(), key=lambda x: x[1]):
        print(f"  {code}  {name}")
    print()
    for r in rows:
        span = f"P{r['period_no']}" + (f"-{r['period_no'] + r['block_len'] - 1}" if r["block_len"] > 1 else "")
        print(f"{DAY_NAMES[r['weekday']]} {span:<6} {r['subject_code']:<8} {r['kind']:<7} {r['faculty_code']}")


if __name__ == "__main__":
    main()
