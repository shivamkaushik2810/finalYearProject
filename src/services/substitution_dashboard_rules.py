"""KPI arithmetic for the substitution dashboard. Pure: no database or Streamlit imports."""


def day_kpis(rows, absent_teachers):
    total = len(rows)
    assigned = sum(1 for r in rows if r["status"] == "assigned")
    pending = sum(1 for r in rows if r["status"] == "proposed")
    unassigned = sum(1 for r in rows if r["status"] == "unassigned")
    completion = round(assigned / total * 100, 1) if total else 0.0
    return {"absent_teachers": absent_teachers, "requiring": total, "assigned": assigned,
            "pending": pending, "unassigned": unassigned, "completion": completion}
