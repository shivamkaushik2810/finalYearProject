"""Substitution planning and confirmation (Phase 4).
Reads timetable and faculty data, runs the pure planner, and saves the result through
faculty_substitution_save_plan. Auto-planned rows are saved as 'proposed'. They become
'assigned' only when an administrator confirms them. The permanent timetable is never written."""
from datetime import date

from src.database.config import supabase
from src.services.faculty_availability_rules import PERIODS
from src.services.substitution_scoring import DEFAULT_WEIGHTS, plan_day, validate_weights
from src.services.timetable_service import load_entries, require_admin
from src.services.timetable_validator import TEACHING, Entry

PAGE = 1000


class SubstitutionError(ValueError):
    """A rule was broken. The message is safe to show to the user."""


def _rows(table, cols):
    out, start = [], 0
    while True:
        chunk = supabase.table(table).select(cols).range(start, start + PAGE - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < PAGE:
            return out
        start += PAGE


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _load_weights():
    rows = _rows("substitution_weights", "criterion,weight")
    if not rows:
        return dict(DEFAULT_WEIGHTS)
    return validate_weights({r["criterion"]: r["weight"] for r in rows})


def _code_maps():
    by_code = {str(r["code"]): str(r["teacher_id"]) for r in _rows("teacher_codes", "code,teacher_id")}
    by_tid = {tid: code for code, tid in by_code.items()}
    return by_code, by_tid


def _pool(by_code, entries):
    teachers = {str(r["teacher_id"]): r for r in _rows("teachers", "teacher_id,status")}
    quals, rules, absences, limits = {}, {}, {}, {}
    for r in _rows("faculty_subject_qualifications", "teacher_id,subject_code,level,is_active"):
        quals.setdefault(str(r["teacher_id"]), {})[r["subject_code"]] = r
    for r in _rows("faculty_unavailability", "teacher_id,weekday,period_no,effective_from,effective_until"):
        rules.setdefault(str(r["teacher_id"]), []).append({
            **r,
            "effective_from": _d(r["effective_from"]),
            "effective_until": _d(r["effective_until"]) if r.get("effective_until") else None})
    for r in _rows("faculty_absences", "teacher_id,status,start_date,end_date,periods"):
        absences.setdefault(str(r["teacher_id"]), []).append({
            "status": r["status"], "start_date": _d(r["start_date"]),
            "end_date": _d(r["end_date"]), "periods": r.get("periods")})
    for r in _rows("faculty_limits", "teacher_id,max_daily_periods,max_weekly_periods"):
        limits[str(r["teacher_id"])] = {"max_daily": r["max_daily_periods"],
                                        "max_weekly": r["max_weekly_periods"]}
    previous = {}
    for e in entries:
        if e.kind in TEACHING and e.faculty_code:
            previous.setdefault(e.faculty_code, set()).add(e.section_code)

    pool = {}
    for code, tid in by_code.items():
        teacher = teachers.get(tid)
        if not teacher:
            continue
        pool[code] = {
            "code": code, "teacher_id": tid, "status": teacher["status"], "department": None,
            "quals": quals.get(tid, {}), "rules": rules.get(tid, []),
            "absences": absences.get(tid, []), "limits": limits.get(tid),
            "previous_sections": previous.get(code, set()), "preference": None}
    return pool


def _summary(on_date, version_id, decisions, saved, warnings, note=None):
    assigned = sum(1 for d in decisions if d["status"] == "assigned")
    return {"date": on_date.isoformat(), "version_id": version_id, "slots": len(decisions),
            "assigned": assigned, "unassigned": len(decisions) - assigned, "saved": saved,
            "warnings": warnings, "note": note, "decisions": decisions}


def plan_substitutions(admin_id, version_id, on_date):
    require_admin(admin_id)
    if not isinstance(on_date, date):
        raise SubstitutionError("a date is required")
    weekday = on_date.isoweekday()
    if weekday > 6:
        return _summary(on_date, version_id, [], 0, [], note="no classes on Sunday")

    by_code, by_tid = _code_maps()
    warnings = []

    absent = {}
    for r in _rows("faculty_absences", "teacher_id,status,start_date,end_date,periods"):
        if r["status"] != "approved" or not _d(r["start_date"]) <= on_date <= _d(r["end_date"]):
            continue
        code = by_tid.get(str(r["teacher_id"]))
        if code is None:
            warnings.append("an absent teacher has no timetable code, so their classes cannot be covered")
            continue
        periods = set(r["periods"]) if r.get("periods") else set(PERIODS)
        absent.setdefault(code, set()).update(periods)

    entries = load_entries(version_id)

    slots, seen = [], set()
    for e in entries:
        if e.weekday != weekday or e.kind not in TEACHING or e.faculty_code not in absent:
            continue
        for p in e.periods():
            if p not in absent[e.faculty_code] or (e.section_code, p) in seen:
                continue
            seen.add((e.section_code, p))
            slots.append({"section_code": e.section_code, "subject_code": e.subject_code,
                          "kind": e.kind, "weekday": weekday, "period": p, "room": e.room,
                          "absent_code": e.faculty_code, "department": None})

    existing = [r for r in _rows("faculty_substitutions",
                                 "version_id,substitution_date,weekday,period_no,section_code,"
                                 "subject_code,room,substitute_teacher_id,status")
                if str(r["version_id"]) == str(version_id)
                and _d(r["substitution_date"]) == on_date and r["status"] == "assigned"]
    done, extra = set(), []
    for r in existing:
        done.add((r["section_code"], r["period_no"]))
        code = by_tid.get(str(r["substitute_teacher_id"]))
        if code is None:
            continue
        extra.append(Entry(id=None, section_id=0, section_code=r["section_code"],
                           weekday=r["weekday"], period_no=r["period_no"], block_len=1,
                           kind="theory", subject_code=r["subject_code"], subject_name=None,
                           faculty_code=code, room=r.get("room")))
    slots = [s for s in slots if (s["section_code"], s["period"]) not in done]

    excluded = {}
    for r in _rows("substitution_exclusions", "version_id,substitution_date,section_code,period_no,teacher_id"):
        if str(r["version_id"]) != str(version_id) or _d(r["substitution_date"]) != on_date:
            continue
        code = by_tid.get(str(r["teacher_id"]))
        if code:
            excluded.setdefault((r["section_code"], r["period_no"]), set()).add(code)
    for s in slots:
        s["excluded"] = excluded.get((s["section_code"], s["period"]), set())
        s["absent_codes"] = set(absent)
    pool = _pool(by_code, entries)
    decisions = plan_day(slots, pool, entries + extra, _load_weights(), on_date)

    rows = [{
        "weekday": d["weekday"], "period": d["period"], "section_code": d["section_code"],
        "subject_code": d["subject_code"], "room": d["room"], "absent_code": d["absent_code"],
        "substitute_teacher_id": by_code.get(d["substitute_code"], "") if d["substitute_code"] else "",
        "status": "proposed" if d["status"] == "assigned" else "unassigned",
        "score": d["score"], "factors": d["factors"], "alternatives": d["alternatives"],
        "reasons": d["reasons"],
    } for d in decisions]

    saved = _rpc("faculty_substitution_save_plan", {
        "p_version_id": int(version_id), "p_date": on_date.isoformat(),
        "p_rows": rows, "p_actor": str(admin_id)})
    return _summary(on_date, version_id, decisions, saved or 0, warnings)


def confirm_substitution(admin_id, substitution_id):
    require_admin(admin_id)
    try:
        supabase.rpc("faculty_substitution_confirm", {
            "p_id": int(substitution_id), "p_actor": str(admin_id)}).execute()
    except Exception as exc:
        msg = str(exc)
        if "no_double_booking" in msg:
            raise SubstitutionError("This teacher already covers another class in that period.") from exc
        if "cannot confirm" in msg:
            raise SubstitutionError("Only a proposed substitution can be confirmed.") from exc
        raise SubstitutionError("The database refused the change. Nothing was saved.") from exc
    return True


def _rpc(name, params):
    try:
        return supabase.rpc(name, params).execute().data
    except Exception as exc:
        raise SubstitutionError("The database refused the change. Nothing was saved.") from exc


def absent_teacher_count(on_date):
    rows = _rows("faculty_absences", "teacher_id,status,start_date,end_date")
    return len({r["teacher_id"] for r in rows if r["status"] == "approved"
                and _d(r["start_date"]) <= on_date <= _d(r["end_date"])})


def list_day(admin_id, version_id, on_date):
    require_admin(admin_id)
    rows = (supabase.table("faculty_substitutions")
            .select("id,period_no,section_code,subject_code,room,original_teacher_code,"
                    "substitute_teacher_id,status,score,factors,alternatives,reasons")
            .eq("version_id", int(version_id))
            .eq("substitution_date", on_date.isoformat())
            .order("period_no").order("section_code").execute().data or [])
    names = {str(r["teacher_id"]): r["name"] for r in _rows("teachers", "teacher_id,name")}
    for r in rows:
        tid = r.get("substitute_teacher_id")
        r["substitute_name"] = names.get(str(tid), "") if tid else ""
    return rows


def reject_substitution(admin_id, substitution_id):
    require_admin(admin_id)
    try:
        supabase.rpc("faculty_substitution_reject", {
            "p_id": int(substitution_id), "p_actor": str(admin_id)}).execute()
    except Exception as exc:
        if "cannot reject" in str(exc):
            raise SubstitutionError("Only a proposed substitution can be rejected.") from exc
        raise SubstitutionError("The database refused the change. Nothing was saved.") from exc
    return True


def save_weights(admin_id, weights):
    require_admin(admin_id)
    clean = validate_weights(weights)
    try:
        supabase.rpc("substitution_weights_set", {
            "p_weights": {k: int(v) for k, v in clean.items()},
            "p_actor": str(admin_id)}).execute()
    except Exception as exc:
        raise SubstitutionError("The database refused the weights. Nothing was saved.") from exc
    return True
