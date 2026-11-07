"""Service-level tests against an in-memory fake Supabase (no network). Run: python tests/run_all.py"""
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
 
from tests.fakes import FakeSupabase, install, APIError
 
FAKE = FakeSupabase()
ST, SENT, EMAIL = install(FAKE)
 
from src.services import (alert_service, audit_service, eligibility_service, face_embeddings,  # noqa: E402
                          leave_service, low_attendance_job, schedule_service)
from src.services.db_utils import fetch_all  # noqa: E402
 
IST = ZoneInfo("Asia/Kolkata")
PDF = b'%PDF-1.4 test'
 
 
def fresh():
    FAKE.tables.clear(); FAKE.storage.files.clear(); FAKE.rpc_calls.clear(); SENT.clear()
    ST.secrets.clear()
    T = FAKE.tables
    T['subjects'] = [{'subject_id': 's1', 'name': 'Maths', 'subject_code': 'M1', 'teacher_id': 't1'},
                     {'subject_id': 's2', 'name': 'Physics', 'subject_code': 'P1', 'teacher_id': 't2'}]
    T['students'] = [{'student_id': f'st{i}', 'name': f'Student{i}', 'roll_no': f'R{i}', 'section': 'A',
                      'email': f'st{i}@x.com', 'parent_email': f'p{i}@x.com', 'parent_name': f'Parent{i}',
                      'phone': None, 'parent_phone': None, 'alert_opt_in': False} for i in range(1, 6)]
    T['subject_students'] = [{'id': i, 'student_id': f'st{i}', 'subject_id': 's1'} for i in range(1, 6)]
    T['attendance_logs'] = []
    return T
 
 
def add_logs(student, subject, pattern, day0=None):
    """pattern like 'PPAE' -> P present, A absent, E excused-absent; one session per char."""
    n = len(FAKE.tables['attendance_logs']) + 1
    base = day0 or date.today() - timedelta(days=10)
    for i, ch in enumerate(pattern):
        FAKE.tables['attendance_logs'].append({
            'id': n + i, 'student_id': student, 'subject_id': subject,
            'timestamp': f'{base + timedelta(days=i)}T09:00:00', 'is_present': ch == 'P', 'is_excused': ch == 'E'})
 
 
# ---------- db_utils ----------
def test_fetch_all_pages_past_the_1000_row_cap():
    fresh()
    FAKE.tables['big'] = [{'k': f'{i:05d}'} for i in range(2500)]
    assert len(FAKE.table('big').select('*').execute().data) == 1000        # the trap
    rows = fetch_all(lambda: FAKE.table('big').select('*').order('k'))
    assert len(rows) == 2500 and rows[0]['k'] == '00000' and rows[-1]['k'] == '02499'
    assert len({r['k'] for r in rows}) == 2500                               # no dupes / gaps
 
 
# ---------- leave ----------
def test_leave_submit_validation_and_ownership():
    fresh(); t = date.today()
    ok, _ = leave_service.submit_leave('st1', 's1', 'leave', t, t, 'fever and rest')
    assert ok
    ok, m = leave_service.submit_leave('st1', 's1', 'leave', t, t, 'fever again')
    assert not ok and 'already' in m                                          # overlap
    ok, m = leave_service.submit_leave('st1', 's2', 'leave', t, t, 'fever and rest')
    assert not ok and 'not enrolled' in m
    ok, m = leave_service.submit_leave('st2', 's1', 'leave', t, t, 'x')
    assert not ok                                                             # reason too short
    ok, m = leave_service.submit_leave('st2', 's1', 'medical', t, t, 'surgery', 'c.pdf', b'MZ-evil')
    assert not ok and 'genuine' in m and not FAKE.storage.files               # fake PDF rejected, nothing stored
    ok, _ = leave_service.submit_leave('st2', 's1', 'medical', t, t, 'surgery', 'c.pdf', PDF)
    assert ok and len(FAKE.storage.files) == 1
    path = next(iter(FAKE.storage.files))[1]
    assert path.startswith('st2/') and path.endswith('.pdf')
    assert len(FAKE.tables['leave_requests']) == 2
 
 
def test_leave_review_authorization_and_excusal():
    fresh(); t = date.today(); d0 = t - timedelta(days=3)
    add_logs('st1', 's1', 'PAAP', day0=d0)                    # absent on d0+1, d0+2
    leave_service.submit_leave('st1', 's1', 'medical', d0 + timedelta(days=1), d0 + timedelta(days=1), 'fever 1 day', 'c.pdf', PDF)
    req = FAKE.tables['leave_requests'][0]
    ok, m = leave_service.review_leave(req['id'], 't2', True)               # wrong teacher
    assert not ok and 'own subjects' in m and req['status'] == 'pending'
    assert leave_service.get_document_url(req['id'], 't2') is None           # no certificate access
    assert 'signed' in leave_service.get_document_url(req['id'], 't1')
    ok, _ = leave_service.review_leave(req['id'], 't1', True, 'get well')
    assert ok
    ex = [l['is_excused'] for l in FAKE.tables['attendance_logs']]
    assert ex == [False, True, False, False]                                  # only the covered absence
    ok, m = leave_service.review_leave(req['id'], 't1', False)               # double review
    assert not ok and 'already' in m
    assert [r['id'] for r in leave_service.list_for_teacher('t2', 'pending')] == []
    rows = leave_service.list_for_teacher('t1', None)
    assert len(rows) == 1 and rows[0]['students']['name'] == 'Student1' and rows[0]['subjects']['name'] == 'Maths'
    mine = leave_service.list_for_student('st1')
    assert len(mine) == 1 and mine[0]['subjects']['subject_code'] == 'M1' and mine[0]['status'] == 'approved'
 
 
def test_leave_rejected_does_not_excuse():
    fresh(); t = date.today(); d0 = t - timedelta(days=2)
    add_logs('st1', 's1', 'AA', day0=d0)
    leave_service.submit_leave('st1', 's1', 'leave', d0, d0 + timedelta(days=1), 'family event')
    leave_service.review_leave(FAKE.tables['leave_requests'][0]['id'], 't1', False, 'no')
    assert not any(l['is_excused'] for l in FAKE.tables['attendance_logs'])
 
 
# ---------- eligibility ----------
def test_eligibility_uses_excused_and_thresholds():
    fresh()
    add_logs('st1', 's1', 'PPPP')     # 100  eligible
    add_logs('st2', 's1', 'PPPA')     # 75   eligible (boundary)
    add_logs('st3', 's1', 'PPAA')     # 50   detained
    add_logs('st4', 's1', 'PPEE')     # excused -> 100 eligible
    add_logs('st5', 's1', 'PPPAA')    # 60 -> detained by default (65)
    rep = {r['student_id']: r for r in eligibility_service.subject_report('t1', 's1')}
    assert rep['st1']['final'] == 'eligible' and rep['st2']['final'] == 'eligible'
    assert rep['st3']['final'] == 'detained' and rep['st4']['pct'] == 100.0
    assert rep['st5']['status'] == 'detained'
    assert eligibility_service.subject_report('t2', 's1') == []              # not the owner
    ok, _ = eligibility_service.set_thresholds('t1', 's1', 80, 50)
    assert ok
    rep = {r['student_id']: r for r in eligibility_service.subject_report('t1', 's1')}
    assert rep['st2']['status'] == 'condonable' and rep['st3']['status'] == 'condonable'
    assert not eligibility_service.set_thresholds('t1', 's1', 60, 70)[0]
    assert not eligibility_service.set_thresholds('t2', 's1', 80, 50)[0]
 
 
def test_condonation_rules():
    fresh()
    add_logs('st1', 's1', 'PPPPPPPA')   # 87.5 eligible
    add_logs('st2', 's1', 'PPPPPAAA')   # 62.5? set bands so st2 is condonable
    eligibility_service.set_thresholds('t1', 's1', 80, 60)
    ok, m = eligibility_service.set_condonation('t1', 's1', 'st1', 'condoned', 'good reason')
    assert not ok and 'condonable band' in m
    assert not eligibility_service.set_condonation('t1', 's1', 'st2', 'condoned', 'x')[0]
    assert not eligibility_service.set_condonation('t2', 's1', 'st2', 'condoned', 'good reason')[0]
    assert eligibility_service.set_condonation('t1', 's1', 'st2', 'condoned', 'medical grounds')[0]
    r = {x['student_id']: x for x in eligibility_service.subject_report('t1', 's1')}
    assert r['st2']['final'] == 'condoned'
    assert eligibility_service.set_condonation('t1', 's1', 'st2', 'denied', 'changed mind ok')[0]
    r = {x['student_id']: x for x in eligibility_service.subject_report('t1', 's1')}
    assert r['st2']['final'] == 'detained'
    assert len(FAKE.tables['condonation_decisions']) == 1                    # upsert, not duplicate
 
 
# ---------- audit / corrections ----------
def test_corrections_and_audit_trail():
    fresh()
    add_logs('st1', 's1', 'PA')
    sess = audit_service.recent_sessions('t1', 's1')
    assert len(sess) == 2 and sess == sorted(sess, reverse=True)
    assert audit_service.recent_sessions('t2', 's1') == []
    rows = audit_service.session_logs('t1', 's1', sess[0])
    assert len(rows) == 1 and rows[0]['name'] == 'Student1' and rows[0]['is_present'] is False
    lid = rows[0]['log_id']
    assert not audit_service.correct_attendance('t1', lid, True, 'abc')[0]            # short reason
    ok, m = audit_service.correct_attendance('t2', lid, True, 'not my subject')
    assert not ok and 'not your subject' in m
    assert audit_service.correct_attendance('t1', lid, True, 'scanner missed him')[0]
    ok, m = audit_service.correct_attendance('t1', lid, True, 'again same value')
    assert not ok and 'No change' in m
    aud = audit_service.list_audit('t1', 's1')
    assert len(aud) == 1 and aud[0]['old_value'] is False and aud[0]['new_value'] is True
    assert aud[0]['student_name'] == 'Student1' and aud[0]['changed_by'] == 't1'
    assert audit_service.list_audit('t2', 's1') == []
 
 
# ---------- alerts + low-attendance job ----------
def test_claim_is_exactly_once():
    fresh()
    assert alert_service.claim('st1', 'k', 'email', '2026-W45') is True
    assert alert_service.claim('st1', 'k', 'email', '2026-W45') is False
    assert alert_service.claim('st1', 'k', 'email', '2026-W46') is True
    alert_service.release('st1', 'k', 'email', '2026-W45')
    assert alert_service.claim('st1', 'k', 'email', '2026-W45') is True
 
 
def _calls(monkey):
    calls = []
    class R: status_code = 201
    def post(url, auth=None, data=None, timeout=None):
        calls.append((url, auth, data)); return R()
    monkey.post = post
    return calls
 
 
def test_send_message_modes_and_validation():
    fresh()
    import requests
    calls, orig = [], requests.post
    class R: status_code = 201
    requests.post = lambda url, auth=None, data=None, timeout=None: (calls.append((url, auth, data)), R())[1]
    try:
        assert alert_service.send_message('9876543210', 'hi') == (False, 'alerts disabled')
        ST.secrets.update({'ALERT_CHANNEL': 'whatsapp', 'TWILIO_ACCOUNT_SID': 'AC1', 'TWILIO_AUTH_TOKEN': 'tok',
                           'TWILIO_WHATSAPP_FROM': '+14155238886', 'TWILIO_FROM': '+15550001'})
        assert alert_service.send_message('12345', 'hi') == (False, 'invalid phone')
        assert alert_service.send_message('98765 43210', 'hi')[0] is True
        d = calls[-1][2]
        assert d['To'] == 'whatsapp:+919876543210' and d['From'] == 'whatsapp:+14155238886'
        assert alert_service.send_message('9876543210', 'x' * 5000, mode='sms')[0] is True
        assert calls[-1][2]['From'] == '+15550001' and len(calls[-1][2]['Body']) == 1500
        ST.secrets['TWILIO_AUTH_TOKEN'] = ''
        assert alert_service.send_message('9876543210', 'hi') == (False, 'twilio not configured')
        class R500: status_code = 500
        requests.post = lambda *a, **k: R500()
        ST.secrets['TWILIO_AUTH_TOKEN'] = 'tok'
        assert alert_service.send_message('9876543210', 'hi') == (False, 'twilio http 500')
        def boom(*a, **k): raise requests.ConnectionError('secret-host')
        requests.post = boom
        ok, err = alert_service.send_message('9876543210', 'hi')
        assert not ok and err == 'ConnectionError' and 'secret' not in err
    finally:
        requests.post = orig
 
 
def _low_setup():
    fresh()
    add_logs('st1', 's1', 'PAAA')     # 25%  -> alert
    add_logs('st2', 's1', 'PPPP')     # ok
    add_logs('st3', 's1', 'AA')       # only 2 classes -> below min_classes, ignored
    add_logs('st4', 's1', 'PPEE')     # excused absences -> 100% -> no alert
    FAKE.tables['students'][0].update({'parent_phone': '9876543210', 'alert_opt_in': True})
 
 
def test_low_attendance_dry_run_sends_nothing():
    _low_setup()
    s = low_attendance_job.run(dry_run=True)
    assert s['students_below'] == 1 and s['would_send'] == 2 and not SENT
    assert not FAKE.tables.get('alert_log')
 
 
def test_low_attendance_email_only_then_idempotent():
    _low_setup()
    s = low_attendance_job.run()
    assert s['sent'] == 2 and {m[0] for m in SENT} == {'st1@x.com', 'p1@x.com'}
    assert 'Maths' in SENT[0][2] and '25.0%' in SENT[0][2]
    assert 'Parent1' in SENT[1][3]
    s2 = low_attendance_job.run()
    assert s2.get('sent', 0) == 0 and s2['skipped_duplicate'] == 2 and len(SENT) == 2
 
 
def test_low_attendance_sms_failure_releases_and_retries():
    _low_setup()
    import requests
    ST.secrets.update({'ALERT_CHANNEL': 'sms', 'TWILIO_ACCOUNT_SID': 'AC1', 'TWILIO_AUTH_TOKEN': 't', 'TWILIO_FROM': '+1555'})
    orig = requests.post
    class R500: status_code = 500
    requests.post = lambda *a, **k: R500()
    try:
        s = low_attendance_job.run()
        assert s['sent'] == 2 and s['failed'] == 1                           # emails ok, sms failed
        assert [r['channel'] for r in FAKE.tables['alert_log']] == ['email_student', 'email_parent']
        class R201: status_code = 201
        requests.post = lambda *a, **k: R201()
        s = low_attendance_job.run()
        assert s['sent'] == 1 and s['skipped_duplicate'] == 2                # only the failed sms retried
    finally:
        requests.post = orig
 
 
def test_low_attendance_one_bad_student_does_not_block_others():
    _low_setup()
    add_logs('st5', 's1', 'PAAA')
    real = EMAIL._send
    import src.services.low_attendance_job as job
    def flaky(to, *a):
        if to == 'st1@x.com': raise RuntimeError('smtp down')
        return real(to, *a)
    job._send = flaky
    try:
        s = low_attendance_job.run()
    finally:
        job._send = real
    assert s['failed'] == 1 and s['sent'] == 3                               # st1 student mail failed; rest sent
    assert 'st5@x.com' in {m[0] for m in SENT}
 
 
def test_low_attendance_handles_over_1000_rows():
    fresh()
    FAKE.tables['students'] = [{'student_id': f'u{i}', 'name': f'U{i}', 'email': f'u{i}@x.com'} for i in range(1200)]
    FAKE.tables['subjects'] = [{'subject_id': 's1', 'name': 'Maths', 'teacher_id': 't1'}]
    for i in range(1200):
        FAKE.tables['attendance_logs'] += [
            {'id': i * 10 + k, 'student_id': f'u{i}', 'subject_id': 's1', 'timestamp': f'2026-10-0{k+1}T09:00:00',
             'is_present': k == 0, 'is_excused': False} for k in range(4)]
    s = low_attendance_job.run(dry_run=True, max_emails=None)
    assert s['students_below'] == 1200 and s['would_send'] == 1200           # 1200 view rows > 1000 cap
 
 
def test_email_cap_defers_the_rest_to_next_run():
    _low_setup()
    for sid in ('st5',):
        add_logs(sid, 's1', 'PAAA')
    s = low_attendance_job.run(max_emails=3)                  # 2 students x 2 emails = 4 wanted
    assert s['sent'] == 3 and s['deferred'] == 1 and len(SENT) == 3
    s2 = low_attendance_job.run(max_emails=3)                 # next day: only the deferred one goes out
    assert s2['sent'] == 1 and s2['skipped_duplicate'] == 3 and len(SENT) == 4
 
 
def test_stale_pending_claim_is_taken_over_but_fresh_one_is_not():
    fresh()
    from datetime import datetime, timezone, timedelta
    iso = lambda m: (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()
    FAKE.tables['alert_log'] = [
        {'id': 1, 'student_id': 'a', 'kind': 'k', 'channel': 'email', 'period_key': 'W1', 'status': 'pending', 'created_at': iso(120)},
        {'id': 2, 'student_id': 'b', 'kind': 'k', 'channel': 'email', 'period_key': 'W1', 'status': 'pending', 'created_at': iso(2)},
        {'id': 3, 'student_id': 'c', 'kind': 'k', 'channel': 'email', 'period_key': 'W1', 'status': 'sent', 'created_at': iso(500)},
        {'id': 4, 'student_id': 'd', 'kind': 'k', 'channel': 'email', 'period_key': 'W1', 'status': 'pending'},   # unknown age
    ]
    assert alert_service.claim('a', 'k', 'email', 'W1') is True      # run died 2h ago -> retry allowed
    assert alert_service.claim('b', 'k', 'email', 'W1') is False     # another run is mid-send -> don't double send
    assert alert_service.claim('c', 'k', 'email', 'W1') is False     # already sent
    assert alert_service.claim('d', 'k', 'email', 'W1') is False     # unknown age -> safe side
    assert len([r for r in FAKE.tables['alert_log'] if r['student_id'] == 'a']) == 1
 
 
# ---------- schedule / geofence ----------
def test_timetable_guard():
    fresh()
    mon_10_30 = datetime(2026, 11, 2, 10, 30, tzinfo=IST)                    # Monday
    assert schedule_service.check_session_allowed('s1', mon_10_30)[0] is True       # no timetable -> allowed
    assert schedule_service.add_slot('t1', 's1', 0, time(10, 0), time(11, 0), 10)[0]
    assert not schedule_service.add_slot('t2', 's1', 0, time(10, 0), time(11, 0))[0]       # not owner
    assert not schedule_service.add_slot('t1', 's1', 0, time(11, 0), time(10, 0))[0]       # end<start
    assert schedule_service.check_session_allowed('s1', mon_10_30) == (True, 'Within scheduled slot.')
    assert schedule_service.check_session_allowed('s1', datetime(2026, 11, 2, 9, 55, tzinfo=IST))[0]   # grace
    ok, m = schedule_service.check_session_allowed('s1', datetime(2026, 11, 2, 12, 0, tzinfo=IST))
    assert not ok and '10:00-11:00' in m
    ok, m = schedule_service.check_session_allowed('s1', datetime(2026, 11, 3, 10, 30, tzinfo=IST))
    assert not ok and 'Tue' in m
    # UTC clock must be converted to IST by the caller default: 05:00 UTC == 10:30 IST
    assert schedule_service.check_session_allowed('s1', datetime(2026, 11, 2, 5, 0, tzinfo=ZoneInfo('UTC')).astimezone(IST))[0]
    slot_id = FAKE.tables['subject_slots'][0]['id']
    assert not schedule_service.delete_slot('t2', slot_id)[0]
    assert schedule_service.delete_slot('t1', slot_id)[0] and not FAKE.tables['subject_slots']
 
 
def test_geofence_rules():
    fresh()
    sv = schedule_service
    assert sv.check_scan_location('s1', None, None) == (True, 'Location check not required.')
    assert not sv.save_geofence('t2', 's1', True, 28.0, 77.0, 100, [])[0]
    assert not sv.save_geofence('t1', 's1', True, 91.0, 77.0, 100, [])[0]
    assert not sv.save_geofence('t1', 's1', True, 28.0, 77.0, 5, [])[0]
    assert not sv.save_geofence('t1', 's1', True, None, None, 100, ['not-an-ip'])[0]
    assert not sv.save_geofence('t1', 's1', True, None, None, 100, [])[0]
    assert sv.save_geofence('t1', 's1', True, 28.0, 77.0, 100, ['10.1.0.0/16', ''])[0]
    assert sv.check_scan_location('s1', None, '10.1.5.5')[0]                         # IP alone passes
    ok, m = sv.check_scan_location('s1', None, '8.8.8.8')
    assert not ok and 'Location needed' in m
    assert sv.check_scan_location('s1', (28.0, 77.0, 10), '8.8.8.8')[0]              # inside radius
    ok, m = sv.check_scan_location('s1', (28.01, 77.0, 10), '8.8.8.8')
    assert not ok and 'outside' in m                                                  # ~1.1 km away
    assert sv.save_geofence('t1', 's1', True, None, None, 100, ['10.0.0.0/8'])[0]
    ok, m = sv.check_scan_location('s1', (28.0, 77.0, 5), '8.8.8.8')
    assert not ok and 'network' in m
    assert sv.save_geofence('t1', 's1', False, None, None, 100, [])[0]
    assert sv.check_scan_location('s1', None, '8.8.8.8')[0]                          # disabled -> open
 
 
def test_session_guards_wiring():
    fresh()
    import types
    cl = types.ModuleType('src.components.client_location')
    cl.get_client_ip = lambda: '8.8.8.8'
    cl.get_client_location = lambda: (28.0, 77.0, 5)
    saved = {k: sys.modules.get(k) for k in ('src.components.client_location', 'src.components.session_guards')}
    sys.modules['src.components.client_location'] = cl
    sys.modules.pop('src.components.session_guards', None)
    try:
        from src.components import session_guards as g
        assert g.guard_scan('s1')[0] is True                                          # no fence
        schedule_service.save_geofence('t1', 's1', True, 28.0, 77.0, 100, [])
        assert g.guard_scan('s1')[0] is True
        g.get_client_location = lambda: None          # session_guards bound the name at import time
        ok, m = g.guard_scan('s1')
        assert not ok and 'Location needed' in m
        assert g.guard_start_session('s1')[0] is True
    finally:                                           # do not leak the fake into other tests
        for k, v in saved.items():
            if v is None: sys.modules.pop(k, None)
            else: sys.modules[k] = v
 
 
# ---------- face angles ----------
def test_face_angles_cap_and_validation():
    fresh()
    FAKE.tables['students'][0]['face_embedding'] = [0.1] * 128
    emb = lambda v: [v] * 128
    assert not face_embeddings.add_face_angle('st1', [1, 2, 3])[0]
    assert not face_embeddings.add_face_angle('nobody', emb(0.2))[0]
    for v in (0.2, 0.3, 0.4, 0.5):
        ok, msg, row = face_embeddings.add_face_angle('st1', emb(v))
        assert ok
    assert msg == 'Saved (5/5 samples).' and len(face_embeddings.all_embeddings(row)) == 5
    ok, msg, _ = face_embeddings.add_face_angle('st1', emb(0.6))
    assert not ok and 'Maximum 5' in msg
    assert face_embeddings.all_embeddings({'face_embedding': emb(0.1), 'face_embeddings': [emb(0.1), emb(0.2)]}) == [emb(0.1), emb(0.2)]
    assert face_embeddings.all_embeddings({}) == []
