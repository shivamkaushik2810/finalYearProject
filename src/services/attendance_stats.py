"""Pure helpers for attendance maths. No Streamlit or database imports, so they are easy to test."""
import math

GOOD_PCT = 75
AVG_PCT = 50


def _is_present(v):
    return v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1)


def pct(present, total):
    return round(present / total * 100, 1) if total else 0.0


def status_for(percent, total=1):
    """Return (kind, label, icon). Text and icon are both used so colour is never the only signal."""
    if not total:
        return "none", "No data", "-"
    if percent >= GOOD_PCT:
        return "good", "Good", "\u2713"
    if percent >= AVG_PCT:
        return "avg", "Average", "~"
    return "risk", "At risk", "!"


def classes_needed(present, total, target=GOOD_PCT):
    """Classes to attend in a row to reach `target` percent. 0 if already there."""
    if total == 0 or target >= 100:
        return 0
    need = math.ceil((target * total - 100 * present) / (100 - target))
    return max(0, need)


def per_student(logs):
    """logs -> {student_id: {'present': n, 'total': n}}"""
    out = {}
    for log in logs or []:
        sid = log.get("student_id")
        if not sid:
            continue
        row = out.setdefault(sid, {"present": 0, "total": 0})
        row["total"] += 1
        if _is_present(log.get("is_present")):
            row["present"] += 1
    return out


def per_subject(logs):
    """logs -> {subject_id: {'present': n, 'total': n}}"""
    out = {}
    for log in logs or []:
        sid = log.get("subject_id")
        if not sid:
            continue
        row = out.setdefault(sid, {"present": 0, "total": 0})
        row["total"] += 1
        if _is_present(log.get("is_present")):
            row["present"] += 1
    return out


def overall(logs):
    total = len(logs or [])
    present = sum(1 for l in logs or [] if _is_present(l.get("is_present")))
    return {"present": present, "total": total, "pct": pct(present, total)}


def at_risk_students(logs, threshold=GOOD_PCT):
    """Distinct students whose attendance in any subject is below the threshold."""
    pairs = {}
    for log in logs or []:
        key = (log.get("subject_id"), log.get("student_id"))
        if not key[1]:
            continue
        row = pairs.setdefault(key, {"present": 0, "total": 0})
        row["total"] += 1
        if _is_present(log.get("is_present")):
            row["present"] += 1
    return {k[1] for k, v in pairs.items() if v["total"] and pct(v["present"], v["total"]) < threshold}


def last_session(logs):
    stamps = [l.get("timestamp") for l in logs or [] if l.get("timestamp")]
    return max(stamps) if stamps else None


def csv_safe(value):
    """Stop spreadsheet formula injection when exporting text that users typed."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def valid_email(value):
    v = (value or "").strip()
    if " " in v or v.count("@") != 1:
        return False
    local, _, domain = v.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")
