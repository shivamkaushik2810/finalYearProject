"""Phase A importer: loads a timetable CSV into a NEW draft version.
Writes only to the new tables. Never reads or writes timetables or subject_slots.
Idempotent per --label. Refuses invalid rows and same-period clashes. Never publishes.
Usage (project root):
  python scripts/import_timetable_csv.py data/timetable_3d_from_photo.csv --label import-3D-VI --dry-run
  python scripts/import_timetable_csv.py data/timetable_3d_from_photo.csv --label import-3D-VI
"""
import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

COLUMNS = ["section_code", "weekday", "period_no", "kind", "subject_code",
           "subject_name", "faculty_code", "room", "block_len"]
KINDS = {"theory", "lab", "training", "activity"}
DAYS = range(1, 7)
PERIODS = range(1, 9)


def fail(msg):
    sys.exit(f"ERROR: {msg}")


def year_for(code):
    if code[:1] in ("P", "C") and code[1:] in ("1", "2", "3", "4"):
        return 1
    if len(code) == 2 and code[0] in "234" and code[1].isalpha():
        return int(code[0])
    return None


def read_rows(path):
    rows, errors = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            fail(f"CSV is missing columns: {', '.join(missing)}")
        for line_no, raw in enumerate(reader, start=2):
            r = {c: (raw.get(c) or "").strip() for c in COLUMNS}
            try:
                weekday = int(r["weekday"])
                period = int(r["period_no"])
                block = int(r["block_len"] or 1)
            except ValueError:
                errors.append(f"line {line_no}: weekday, period_no and block_len must be whole numbers")
                continue
            code = r["section_code"].upper()
            if year_for(code) is None:
                errors.append(f"line {line_no}: unknown section code '{code}'")
            if weekday not in DAYS:
                errors.append(f"line {line_no}: weekday must be 1 (Mon) to 6 (Sat)")
            if period not in PERIODS:
                errors.append(f"line {line_no}: period_no must be 1 to 8")
            if r["kind"] not in KINDS:
                errors.append(f"line {line_no}: kind must be one of {sorted(KINDS)}")
            if not 1 <= block <= 4 or period + block - 1 > max(PERIODS):
                errors.append(f"line {line_no}: block_len {block} from period {period} runs past period 8")
            if r["kind"] in ("theory", "lab"):
                if not r["subject_code"]:
                    errors.append(f"line {line_no}: {r['kind']} rows need a subject_code")
                if not r["faculty_code"]:
                    errors.append(f"line {line_no}: {r['kind']} rows need a faculty_code")
            rows.append({
                "line": line_no, "section_code": code, "weekday": weekday, "period_no": period,
                "kind": r["kind"], "subject_code": r["subject_code"] or None,
                "subject_name": r["subject_name"] or None,
                "faculty_code": r["faculty_code"].upper() or None,
                "room": r["room"] or None, "block_len": block,
            })
    return rows, errors


def clashes(rows):
    errors, used = [], {}
    for r in rows:
        for p in range(r["period_no"], min(r["period_no"] + r["block_len"], max(PERIODS) + 1)):
            for kind, value in (("section", r["section_code"]),
                                ("faculty", r["faculty_code"]),
                                ("room", r["room"])):
                if not value:
                    continue
                key = (kind, value, r["weekday"], p)
                if key in used:
                    errors.append(f"line {r['line']}: {kind} {value} already booked on day "
                                  f"{r['weekday']} period {p} (line {used[key]})")
                else:
                    used[key] = r["line"]
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.csv_path.is_file():
        fail(f"file not found: {args.csv_path}")

    rows, errors = read_rows(args.csv_path)
    errors += clashes(rows)
    if errors:
        print("Import refused. Fix these lines in the CSV:")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    sections = sorted({r["section_code"] for r in rows})
    print(f"{len(rows)} rows valid. Sections: {', '.join(sections)}")
    if args.dry_run:
        print("Dry run: nothing written.")
        return

    from src.database.config import supabase

    existing = (supabase.table("timetable_versions").select("id,status")
                .eq("label", args.label).limit(1).execute().data or [])
    if existing:
        if existing[0]["status"] != "draft":
            fail(f"version '{args.label}' is '{existing[0]['status']}'; only drafts can be imported into")
        version_id, created = existing[0]["id"], False
    else:
        row = (supabase.table("timetable_versions")
               .insert({"label": args.label, "status": "draft", "created_by": "import",
                        "notes": "Imported from CSV (Phase A)"}).execute().data)
        version_id, created = row[0]["id"], True

    have = {s["code"]: s["id"] for s in supabase.table("sections").select("id,code").execute().data or []}
    missing = [{"year_code": year_for(c), "code": c} for c in sections if c not in have]
    if missing:
        supabase.table("sections").insert(missing).execute()
        have = {s["code"]: s["id"] for s in supabase.table("sections").select("id,code").execute().data or []}

    present = {(e["section_id"], e["weekday"], e["period_no"]) for e in
               (supabase.table("timetable_entries").select("section_id,weekday,period_no")
                .eq("version_id", version_id).execute().data or [])}
    payload = [{
        "version_id": version_id, "section_id": have[r["section_code"]],
        "weekday": r["weekday"], "period_no": r["period_no"], "block_len": r["block_len"],
        "kind": r["kind"], "subject_code": r["subject_code"], "subject_name": r["subject_name"],
        "faculty_code": r["faculty_code"], "room": r["room"],
    } for r in rows]
    new = [p for p in payload if (p["section_id"], p["weekday"], p["period_no"]) not in present]

    inserted = 0
    for i in range(0, len(new), 200):
        res = supabase.table("timetable_entries").insert(new[i:i + 200]).execute().data or []
        inserted += len(res)
        if res:
            supabase.table("timetable_changes").insert([{
                "version_id": version_id, "entry_id": e["id"], "action": "import",
                "before_json": None, "after_json": e, "changed_by": "import"} for e in res]).execute()

    print(f"Version '{args.label}' (id {version_id}, {'created' if created else 'reused'}): "
          f"inserted {inserted}, already present {len(payload) - len(new)}.")
    print("Nothing was published. Review the draft before approval.")


if __name__ == "__main__":
    main()
