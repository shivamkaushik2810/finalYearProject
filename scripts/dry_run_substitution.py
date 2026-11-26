"""Dry run of the substitution planner for one date. Read-only: saves nothing.

Treats RM as absent on the chosen date, runs the planner against the live timetable and
the faculty data, and prints each slot with the assigned substitute or the reasons.
Usage (project root):  python scripts/dry_run_substitution.py [YYYY-MM-DD] [TEACHER_CODE]
"""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

from src.database.config import supabase
from src.services import substitution_service as svc
from src.services.substitution_scoring import DEFAULT_WEIGHTS, plan_day
from src.services.timetable_service import load_entries

PERIOD_NAMES = {1: "P1", 2: "P2", 3: "P3", 4: "P4", 5: "P5", 6: "P6", 7: "P7", 8: "P8"}


def main():
    on_date = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 11, 25)
    absent_code = sys.argv[2] if len(sys.argv) > 2 else "RM"

    version = (supabase.table("timetable_versions").select("id,label,status")
               .eq("label", "import-3D-VI").limit(1).execute().data or [])
    if not version:
        sys.exit("No draft 'import-3D-VI' found.")
    vid = version[0]["id"]
    entries = load_entries(vid)

    code_rows = supabase.table("teacher_codes").select("code,teacher_id").execute().data or []
    tid_by_code = {r["code"]: str(r["teacher_id"]) for r in code_rows}
    if absent_code not in tid_by_code:
        sys.exit(f"{absent_code} has no teacher code. Link it first.")

    weekday = on_date.isoweekday()
    slots = []
    for e in entries:
        if e.weekday != weekday or e.faculty_code != absent_code or e.kind not in ("theory", "lab", "training"):
            continue
        for p in e.periods():
            slots.append({"section_code": e.section_code, "subject_code": e.subject_code,
                          "kind": e.kind, "weekday": weekday, "period": p, "room": e.room,
                          "absent_code": absent_code, "department": None})

    pool = svc._pool(tid_by_code, entries)
    decisions = plan_day(slots, pool, entries, dict(DEFAULT_WEIGHTS), on_date)

    print(f"Dry run for {on_date.isoformat()} ({absent_code} absent). Saves nothing.")
    print(f"Classes needing cover: {len(decisions)}")
    print()
    for d in sorted(decisions, key=lambda x: (x["period"], x["section_code"])):
        head = f"{PERIOD_NAMES[d['period']]}  {d['section_code']:<4} {d['subject_code']:<10}"
        if d["status"] == "assigned":
            print(f"{head} -> {d['substitute_code']}  score {d['score']}  {d['factors']}")
        else:
            print(f"{head} -> UNASSIGNED: {d['reasons']}")

    print()
    print("Pool used by the planner:")
    for code, prof in sorted(pool.items()):
        quals = ", ".join(f"{s} ({q['level']})" for s, q in sorted(prof["quals"].items())) or "none"
        limits = prof["limits"]
        lim = f"{limits['max_daily']}/day, {limits['max_weekly']}/week" if limits else "not set"
        print(f"  {code}: status {prof['status']}; qualifications {quals}; limits {lim}")


if __name__ == "__main__":
    main()
