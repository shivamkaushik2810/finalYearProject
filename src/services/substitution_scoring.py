"""Substitution scoring and daily planning. Pure: no database or Streamlit imports.

Hard rules come from faculty_availability_rules.eligibility_reasons. This module ranks only the
teachers who pass every hard rule, then assigns a day's classes one at a time in a fixed order."""
from collections import Counter

from src.services.faculty_availability_rules import eligibility_reasons, teaching_load
from src.services.timetable_validator import TEACHING, Entry
from src.services.substitution_manual_rules import run_ok

CRITERIA = ("expertise", "workload", "department", "previous_section", "preference")
DEFAULT_WEIGHTS = {"expertise": 40, "workload": 20, "department": 15,
                   "previous_section": 15, "preference": 10}
EXPERTISE_FACTOR = {"primary": 1.0, "secondary": 0.6, "trained": 0.3}
NEUTRAL_PREFERENCE = 0.5
MAX_ALTERNATIVES = 3


def validate_weights(weights):
    if set(weights) != set(CRITERIA):
        raise ValueError(f"weights must contain exactly: {', '.join(CRITERIA)}")
    out = {}
    for key in CRITERIA:
        value = weights[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"the weight for {key} must be a number of 0 or more")
        out[key] = float(value)
    total = sum(out.values())
    if round(total, 6) != 100:
        raise ValueError(f"weights must total 100, got {total:g}")
    return out


def score_candidate(profile, slot, weights, work):
    """Returns (total, factors). Every factor is between 0 and 1; the total is out of 100."""
    code = profile["code"]
    level = (profile["quals"].get(slot["subject_code"]) or {}).get("level")
    expertise = EXPERTISE_FACTOR.get(level, 0.0)

    max_weekly = (profile.get("limits") or {}).get("max_weekly") or 0
    load = teaching_load(work, code)
    workload = max(0.0, 1 - load / max_weekly) if max_weekly else 0.0

    dept = profile.get("department")
    department = 1.0 if dept and dept == slot.get("department") else 0.0

    previous = 1.0 if slot["section_code"] in profile.get("previous_sections", ()) else 0.0

    pref = profile.get("preference")
    preference = NEUTRAL_PREFERENCE if pref is None else float(pref)

    factors = {"expertise": expertise, "workload": workload, "department": department,
               "previous_section": previous, "preference": preference}
    total = sum(weights[k] * factors[k] for k in CRITERIA)
    return round(total, 2), {k: round(v, 4) for k, v in factors.items()}


def _candidates(slot, pool, work, weights, on_date):
    eligible, refusals = [], {}
    for code in sorted(pool):
        if code == slot["absent_code"] or code in slot.get("absent_codes", ()):
            continue
        if code in slot.get("excluded", ()):
            refusals[code] = ["declined or overridden earlier for this class"]
            continue
        prof = pool[code]
        reasons = eligibility_reasons(
            code=code, subject_code=slot["subject_code"], weekday=slot["weekday"],
            period=slot["period"], on_date=on_date, entries=work, quals=prof["quals"],
            rules=prof["rules"], absences=prof["absences"], limits=prof["limits"],
            teacher_status=prof["status"])
        if reasons:
            refusals[code] = reasons
            continue
        periods = {p for e in work if e.weekday == slot["weekday"] and e.faculty_code == code
                   and e.kind in TEACHING for p in e.periods()}
        periods.add(slot["period"])
        if not run_ok(periods):
            refusals[code] = ["would teach more than 3 periods in a row"]
            continue
        total, factors = score_candidate(prof, slot, weights, work)
        eligible.append((total, code, factors))
    return eligible, refusals


def _summarise(refusals):
    if not refusals:
        return "no other teacher could be checked"
    counts = Counter(reason for reasons in refusals.values() for reason in reasons)
    parts = [f"{n} x {reason}" for reason, n in counts.most_common()]
    return "no eligible teacher: " + "; ".join(parts)


def plan_day(slots, pool, entries, weights, on_date):
    """Assigns each slot to the best eligible teacher, one slot at a time.

    slots: dicts with section_code, subject_code, weekday, period, room, absent_code, department.
    pool: {code: profile}. Each profile has code, status, department, quals, rules, absences,
          limits, previous_sections (set) and preference (None means neutral).
    entries: the timetable as Entry objects, plus any substitutions already assigned for the day.
    Returns one decision dict per slot, in the order they were decided."""
    weights = validate_weights(weights)
    work = list(entries)

    def open_count(slot):
        return len(_candidates(slot, pool, entries, weights, on_date)[0])

    ordered = sorted(slots, key=lambda s: (open_count(s), s["weekday"], s["period"], s["section_code"]))
    decisions = []
    for slot in ordered:
        eligible, refusals = _candidates(slot, pool, work, weights, on_date)
        base = {"section_code": slot["section_code"], "subject_code": slot["subject_code"],
                "weekday": slot["weekday"], "period": slot["period"],
                "room": slot.get("room"), "absent_code": slot["absent_code"]}
        if not eligible:
            decisions.append({**base, "status": "unassigned", "substitute_code": None,
                              "score": None, "factors": None, "alternatives": [],
                              "reasons": _summarise(refusals)})
            continue
        eligible.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_code, best_factors = eligible[0]
        work.append(Entry(id=None, section_id=0, section_code=slot["section_code"],
                          weekday=slot["weekday"], period_no=slot["period"], block_len=1,
                          kind=slot.get("kind", "theory"), subject_code=slot["subject_code"],
                          subject_name=None, faculty_code=best_code, room=slot.get("room")))
        decisions.append({
            **base, "status": "assigned", "substitute_code": best_code,
            "score": best_score, "factors": best_factors,
            "alternatives": [{"code": c, "score": s} for s, c, _ in eligible[1:1 + MAX_ALTERNATIVES]],
            "reasons": None})
    return decisions
