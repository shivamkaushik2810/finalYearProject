import numpy as np
from collections import defaultdict


def predict_absent_risk(attendance_logs, enrolled_students):
    """
    Predict which students are at risk of being absent.
    attendance_logs: list of logs from DB
    enrolled_students: list of student dicts
    Returns list of {"student_id", "name", "risk_level", "attendance_pct", "message"}
    """
    # Build attendance stats per student
    stats = defaultdict(lambda: {"total": 0, "present": 0})

    for log in attendance_logs:
        sid = log.get('student_id')
        if not sid:
            continue
        stats[sid]['total'] += 1
        if log.get('is_present'):
            stats[sid]['present'] += 1

    results = []
    for student in enrolled_students:
        sid  = student.get('student_id')
        name = student.get('name', 'Unknown')
        s    = stats.get(sid, {"total": 0, "present": 0})

        total   = s['total']
        present = s['present']

        if total == 0:
            pct        = 100
            risk_level = "unknown"
            message    = "No attendance data yet"
        else:
            pct = round((present / total) * 100, 1)

            if pct >= 75:
                risk_level = "low"
                message    = f"Good attendance ({pct}%) — Keep it up!"
            elif pct >= 50:
                risk_level = "medium"
                message    = f"Attendance dropping ({pct}%) — Needs attention"
            else:
                risk_level = "high"
                message    = f"Very low attendance ({pct}%) — At risk of failing!"

        results.append({
            "student_id":     sid,
            "name":           name,
            "total_classes":  total,
            "present":        present,
            "absent":         total - present,
            "attendance_pct": pct,
            "risk_level":     risk_level,
            "message":        message
        })

    # Sort by attendance percentage ascending (worst first)
    results.sort(key=lambda x: x['attendance_pct'])
    return results


def get_risk_emoji(risk_level):
    return {
        "low":     "🟢",
        "medium":  "🟡",
        "high":    "🔴",
        "unknown": "⚪"
    }.get(risk_level, "⚪")


def get_subject_health(attendance_logs, total_enrolled):
    """
    Overall subject attendance health score.
    Returns dict with health_score, status, recommendation
    """
    if not attendance_logs or total_enrolled == 0:
        return {
            "health_score":    0,
            "status":          "No Data",
            "recommendation":  "Take at least one attendance session first."
        }

    present_count = sum(1 for log in attendance_logs if log.get('is_present'))
    total_logs    = len(attendance_logs)
    avg_pct       = round((present_count / total_logs) * 100, 1) if total_logs > 0 else 0

    if avg_pct >= 80:
        status         = "Excellent"
        recommendation = "Great class engagement! Keep up the good work."
    elif avg_pct >= 60:
        status         = "Average"
        recommendation = "Some students need motivation. Consider follow-up."
    else:
        status         = "Poor"
        recommendation = "Low attendance detected. Immediate action recommended."

    return {
        "health_score":    avg_pct,
        "status":          status,
        "recommendation":  recommendation
    }
