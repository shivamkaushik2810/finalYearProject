import re
from datetime import datetime, timedelta
from collections import defaultdict


def parse_query(query: str):
    """
    Parse natural language query and return intent + parameters.
    """
    query = query.lower().strip()

    # Intent patterns
    intents = [
        # Absent queries
        (r'who.*(absent|miss|skip|not attend)', 'absent_students'),
        (r'(absent|miss|skip).*(most|maximum|highest|often)', 'most_absent'),
        (r'(absent|miss).*(today|this week|this month|yesterday)', 'absent_time'),

        # Present queries
        (r'who.*(present|attend|came)', 'present_students'),
        (r'(present|attend).*(most|maximum|highest|often)', 'most_present'),
        (r'(present|attend).*(today|this week|this month)', 'present_time'),

        # Count queries
        (r'how many.*(present|attend|came)', 'count_present'),
        (r'how many.*(absent|miss|skip)', 'count_absent'),
        (r'total.*(student|attend)', 'total_students'),

        # Percentage queries
        (r'(percent|percentage|rate).*(attend)', 'attendance_rate'),
        (r'(attend).*(percent|percentage|rate)', 'attendance_rate'),

        # Risk queries
        (r'(at risk|risk|danger|low attend|fail)', 'at_risk'),
        (r'(warning|alert|concern)', 'at_risk'),

        # Best/worst queries
        (r'(best|top|highest).*(attend)', 'best_attendance'),
        (r'(worst|lowest|poor).*(attend)', 'worst_attendance'),

        # Specific student

        # Subject queries
        (r'(which subject|what subject).*(low|poor|bad)', 'worst_subject'),
        (r'(which subject|what subject).*(high|best|good)', 'best_subject'),
    ]

    for pattern, intent in intents:
        if re.search(pattern, query):
            return intent

    return 'general_summary'


def answer_query(query: str, attendance_logs: list,
                 enrolled_students: list, subject_name: str = ""):
    """
    Answer natural language attendance query.
    Returns (answer_text, data_dict)
    """
    intent = parse_query(query)

    # Build stats
    stats = _build_stats(attendance_logs, enrolled_students)

    # Student-specific question: match any enrolled student's name in the query
    q_low = query.lower()
    for s in stats.values():
        full = (s.get('name') or '').strip().lower()
        if full and (full in q_low or full.split()[0] in q_low.split()):
            return (f"👤 **{s['name']}**: {s['present']} present, {s['absent']} absent "
                    f"out of {s['total']} classes ({s['pct']}% attendance).", {"student": s})

    if intent == 'absent_students':
        return _get_absent_students(stats, enrolled_students)

    elif intent == 'most_absent':
        return _get_most_absent(stats)

    elif intent == 'present_students':
        return _get_present_students(stats, enrolled_students)

    elif intent == 'most_present':
        return _get_most_present(stats)

    elif intent == 'count_present':
        return _count_present(stats, attendance_logs)

    elif intent == 'count_absent':
        return _count_absent(stats, enrolled_students)

    elif intent == 'attendance_rate':
        return _get_attendance_rate(stats)

    elif intent == 'at_risk':
        return _get_at_risk_students(stats)

    elif intent == 'best_attendance':
        return _get_best_students(stats)

    elif intent == 'worst_attendance':
        return _get_worst_students(stats)

    elif intent == 'total_students':
        total = len(enrolled_students)
        return (f"📊 Total {total} students are enrolled in {subject_name}.",
                {"total": total})

    else:
        return _general_summary(stats, enrolled_students, subject_name)


def _build_stats(logs, students):
    stats = {}
    student_map = {s['student_id']: s['name'] for s in students}

    for s in students:
        sid = s['student_id']
        stats[sid] = {
            "name":    s['name'],
            "total":   0,
            "present": 0,
            "absent":  0,
            "pct":     0
        }

    for log in logs:
        sid = log.get('student_id')
        if sid not in stats:
            continue
        stats[sid]['total'] += 1
        if log.get('is_present'):
            stats[sid]['present'] += 1
        else:
            stats[sid]['absent'] += 1

    for sid in stats:
        total = stats[sid]['total']
        if total > 0:
            stats[sid]['pct'] = round((stats[sid]['present'] / total) * 100, 1)

    return stats


def _get_absent_students(stats, students):
    absent = [s for s in stats.values() if s['absent'] > 0]
    if not absent:
        return ("✅ Great news! No students have been absent yet.", {})
    absent.sort(key=lambda x: x['absent'], reverse=True)
    lines = "\n".join(f"  • {s['name']}: {s['absent']} absent, {s['pct']}% attendance"
                      for s in absent)
    return (f"📋 Students with absences ({len(absent)} students):\n{lines}", {"absent": absent})


def _get_most_absent(stats):
    if not stats:
        return ("No attendance data available.", {})
    worst = max(stats.values(), key=lambda x: x['absent'])
    if worst['absent'] == 0:
        return ("✅ No student has been absent yet!", {})
    return (f"🔴 Most absent student: **{worst['name']}** "
            f"with {worst['absent']} absences ({worst['pct']}% attendance).", {"student": worst})


def _get_present_students(stats, students):
    present = [s for s in stats.values() if s['present'] > 0]
    if not present:
        return ("No attendance data yet.", {})
    present.sort(key=lambda x: x['present'], reverse=True)
    lines = "\n".join(f"  • {s['name']}: {s['present']} present ({s['pct']}%)"
                      for s in present)
    return (f"✅ Students with attendance:\n{lines}", {"present": present})


def _get_most_present(stats):
    if not stats:
        return ("No data available.", {})
    best = max(stats.values(), key=lambda x: x['pct'])
    return (f"🏆 Best attendance: **{best['name']}** "
            f"with {best['pct']}% attendance ({best['present']} classes).", {"student": best})


def _count_present(stats, logs):
    last_session = {}
    for log in sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True):
        sid = log.get('student_id')
        if sid not in last_session:
            last_session[sid] = log.get('is_present', False)
    count = sum(1 for v in last_session.values() if v)
    return (f"👥 In the last session, **{count} students** were present.", {"count": count})


def _count_absent(stats, students):
    absent = sum(1 for s in stats.values() if s['absent'] > 0)
    return (f"❌ **{absent} students** have at least one absence.", {"count": absent})


def _get_attendance_rate(stats):
    if not stats:
        return ("No data available.", {})
    avg = round(sum(s['pct'] for s in stats.values()) / len(stats), 1)
    return (f"📊 Overall class attendance rate: **{avg}%**", {"rate": avg})


def _get_at_risk_students(stats):
    at_risk = [s for s in stats.values() if s['pct'] < 75 and s['total'] > 0]
    if not at_risk:
        return ("✅ No students are at risk. All have attendance above 75%.", {})
    at_risk.sort(key=lambda x: x['pct'])
    lines = "\n".join(f"  🔴 {s['name']}: {s['pct']}% attendance" for s in at_risk)
    return (f"⚠️ {len(at_risk)} students at risk (below 75%):\n{lines}", {"at_risk": at_risk})


def _get_best_students(stats):
    if not stats:
        return ("No data available.", {})
    sorted_s = sorted(stats.values(), key=lambda x: x['pct'], reverse=True)[:3]
    lines = "\n".join(f"  🏆 {s['name']}: {s['pct']}%" for s in sorted_s)
    return (f"🌟 Top students by attendance:\n{lines}", {"top": sorted_s})


def _get_worst_students(stats):
    if not stats:
        return ("No data available.", {})
    sorted_s = sorted([s for s in stats.values() if s['total'] > 0],
                      key=lambda x: x['pct'])[:3]
    if not sorted_s:
        return ("No attendance data yet.", {})
    lines = "\n".join(f"  🔴 {s['name']}: {s['pct']}%" for s in sorted_s)
    return (f"⚠️ Students with lowest attendance:\n{lines}", {"worst": sorted_s})


def _general_summary(stats, students, subject_name):
    total    = len(students)
    at_risk  = sum(1 for s in stats.values() if s['pct'] < 75 and s['total'] > 0)
    avg_pct  = round(sum(s['pct'] for s in stats.values()) / len(stats), 1) if stats else 0
    summary  = (
        f"📊 **{subject_name} Attendance Summary**\n"
        f"  • Total Students: {total}\n"
        f"  • Average Attendance: {avg_pct}%\n"
        f"  • Students at Risk: {at_risk}\n"
    )
    return (summary, {"total": total, "avg_pct": avg_pct, "at_risk": at_risk})
