import html
import logging
from collections import defaultdict
 
from src.database.config import supabase
from src.services import alert_service as alerts
from src.services.db_utils import fetch_all
from src.services.email_service import _send
from src.services.pure_logic import iso_week_key
 
log = logging.getLogger(__name__)
KIND = 'low_attendance'
 
 
def _low_rows(threshold, min_classes):
    rows = fetch_all(lambda: supabase.table('student_subject_attendance')
                     .select('pair_key, student_id, subject_id, total_classes, present_classes')
                     .order('pair_key'))
    low = defaultdict(list)
    for r in rows:
        total = int(r['total_classes'] or 0)
        if total < min_classes:
            continue
        pct = round(int(r['present_classes'] or 0) / total * 100, 1)
        if pct < threshold:
            low[str(r['student_id'])].append((str(r['subject_id']), pct, int(r['present_classes'] or 0), total))
    return low
 
 
def _fetch_students(ids):
    ids, out = list(ids), {}
    for i in range(0, len(ids), 100):
        res = supabase.table('students').select(
            'student_id,name,roll_no,email,parent_email,parent_name,phone,parent_phone,alert_opt_in'
        ).in_('student_id', ids[i:i + 100]).execute()
        for s in res.data or []:
            out[str(s['student_id'])] = s
    return out
 
 
def _bodies(name, roll, items, threshold, parent_name=None):
    greet = f"Dear {parent_name or 'Parent/Student'},"
    lines_plain = "\n".join(f"  - {n}: {p}% ({a}/{t})" for n, p, a, t in items)
    rows_html = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>{html.escape(n)}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center'>{a}/{t}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;color:#e74c3c;"
        f"font-weight:bold'>{p}%</td></tr>" for n, p, a, t in items)
    plain = (f"{greet}\n\nAttendance of {name} (Roll {roll or 'N/A'}) is below {threshold:g}% "
             f"in these subjects:\n{lines_plain}\n\nPlease ensure regular attendance.\n\nSnapClass")
    page = (f"<html><body style='font-family:Arial,sans-serif'><p>{html.escape(greet)}</p>"
            f"<p><b>{html.escape(name)}</b> (Roll {html.escape(str(roll or 'N/A'))}) has attendance below "
            f"<b>{threshold:g}%</b> in:</p>"
            f"<table cellpadding='0' cellspacing='0' style='border:1px solid #eee;min-width:360px'>"
            f"<tr style='background:#f8f9fa'><th style='padding:8px;text-align:left'>Subject</th>"
            f"<th>Classes</th><th>Percentage</th></tr>{rows_html}</table>"
            f"<p style='color:#856404'>Please ensure regular attendance.</p>"
            f"<p style='color:#999;font-size:12px'>Automated alert from SnapClass.</p></body></html>")
    sms = f"SnapClass: {name}'s attendance is below {threshold:g}% in " + \
          ", ".join(n for n, *_ in items[:3]) + ". Please ensure regular attendance."
    return page, plain, sms[:300]
 
 
DEFAULT_MAX_EMAILS = 400   # stay under Gmail's ~500/day cap; the rest go out on the next daily run
 
 
def _once(student_id, channel, period, send_fn, dry_run, stats, max_emails=None):
    is_email = channel.startswith('email')
    if is_email and max_emails and stats['emails_attempted'] >= max_emails:
        stats['deferred'] += 1
        return
    if dry_run:
        stats['would_send'] += 1
        if is_email:
            stats['emails_attempted'] += 1
        return
    if not alerts.claim(student_id, KIND, channel, period):
        stats['skipped_duplicate'] += 1
        return
    if is_email:
        stats['emails_attempted'] += 1
    try:
        send_fn()
        alerts.mark_sent(student_id, KIND, channel, period)
        stats['sent'] += 1
    except Exception as e:
        alerts.release(student_id, KIND, channel, period)
        stats['failed'] += 1
        log.error("alert failed (%s): %s", channel, type(e).__name__)
 
 
def _sms(phone, body):
    ok, err = alerts.send_message(phone, body)
    if not ok:
        raise RuntimeError(err)
 
 
def run(threshold=75.0, min_classes=3, dry_run=False, max_emails=DEFAULT_MAX_EMAILS):
    stats = defaultdict(int)
    low = _low_rows(threshold, min_classes)
    stats['students_below'] = len(low)
    if not low:
        return dict(stats)
    students = _fetch_students(low.keys())
    subj = {str(s['subject_id']): s for s in fetch_all(
        lambda: supabase.table('subjects').select('subject_id, name').order('subject_id'))}
    period, mode = iso_week_key(), alerts.channel_mode()
 
    for sid, items in low.items():
        stu = students.get(sid)
        if not stu:
            continue
        try:
            named = [(subj.get(i[0], {}).get('name', 'Subject'), i[1], i[2], i[3]) for i in items]
            title = f"⚠️ Low attendance alert — {stu['name']}"
            if stu.get('email'):
                h, p, _ = _bodies(stu['name'], stu.get('roll_no'), named, threshold)
                _once(sid, 'email_student', period,
                      lambda: _send(stu['email'], title, h, p), dry_run, stats, max_emails)
            if stu.get('parent_email'):
                h, p, _ = _bodies(stu['name'], stu.get('roll_no'), named, threshold, stu.get('parent_name'))
                _once(sid, 'email_parent', period,
                      lambda: _send(stu['parent_email'], title, h, p), dry_run, stats, max_emails)
            if mode != 'off' and stu.get('alert_opt_in'):
                _, _, sms = _bodies(stu['name'], stu.get('roll_no'), named, threshold)
                if stu.get('parent_phone'):
                    _once(sid, f'{mode}_parent', period,
                          lambda: _sms(stu['parent_phone'], sms), dry_run, stats)
                if stu.get('phone'):
                    _once(sid, f'{mode}_student', period,
                          lambda: _sms(stu['phone'], sms), dry_run, stats)
        except Exception as e:
            stats['failed'] += 1
            log.error("student %s failed: %s", sid, type(e).__name__)
    return dict(stats)
