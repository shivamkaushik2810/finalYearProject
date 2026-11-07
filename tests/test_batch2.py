from datetime import date, time
from src.services import pure_logic as p
 
 
def test_effective_pct_excludes_excused_absence():
    logs = [{'is_present': True}, {'is_present': False, 'is_excused': True}, {'is_present': False}]
    assert p.effective_pct(logs) == 50.0
 
 
def test_effective_pct_empty_and_all_excused():
    assert p.effective_pct([]) == 0.0
    assert p.effective_pct([{'is_present': False, 'is_excused': True}]) == 0.0
 
 
def test_present_but_marked_excused_still_counts_present():
    assert p.effective_pct([{'is_present': True, 'is_excused': True}]) == 100.0
 
 
def test_classify_boundaries():
    assert p.classify(75) == 'eligible'
    assert p.classify(74.9) == 'condonable'
    assert p.classify(65) == 'condonable'
    assert p.classify(64.9) == 'detained'
    assert p.classify(80, 85, 70) == 'condonable'
 
 
def test_validate_thresholds():
    assert p.validate_thresholds(75, 65)
    assert not p.validate_thresholds(60, 70)
    assert not p.validate_thresholds(101, 50)
    assert not p.validate_thresholds(75, 0)
    assert not p.validate_thresholds('x', 1)
    assert not p.validate_thresholds(None, None)
 
 
def test_haversine_and_location():
    assert p.haversine_m(28.0, 77.0, 28.0, 77.0) == 0
    d = p.haversine_m(28.0, 77.0, 28.001, 77.0)
    assert 105 < d < 118
    assert p.location_ok(28.0, 77.0, 5, 28.0, 77.0, 50)
    assert not p.location_ok(28.001, 77.0, 5, 28.0, 77.0, 50)
    assert p.location_ok(28.001, 77.0, 100, 28.0, 77.0, 50)  # accuracy tolerance
    assert not p.location_ok(None, None, 5, 28.0, 77.0, 50)
 
 
def test_ip_allowed():
    assert p.ip_allowed('10.1.2.3', ['10.1.0.0/16'])
    assert not p.ip_allowed('11.1.2.3', ['10.1.0.0/16'])
    assert not p.ip_allowed('garbage', ['10.1.0.0/16'])
    assert not p.ip_allowed(None, ['10.1.0.0/16'])
    assert not p.ip_allowed('10.1.2.3', ['bad-entry'])
    assert p.ip_allowed('10.1.2.3', ['bad', '10.1.2.3'])
 
 
def test_normalize_phone():
    assert p.normalize_phone('98765 43210') == '+919876543210'
    assert p.normalize_phone('+91 98765-43210') == '+919876543210'
    assert p.normalize_phone('00919876543210') == '+919876543210'
    assert p.normalize_phone('12345') is None
    assert p.normalize_phone('') is None
    assert p.normalize_phone(None) is None
    assert p.normalize_phone('5876543210') is None
 
 
def test_within_slot():
    s, e = time(10, 0), time(11, 0)
    assert p.within_slot(time(10, 30), s, e, 0)
    assert p.within_slot(time(9, 55), s, e, 10)
    assert not p.within_slot(time(9, 40), s, e, 10)
    assert p.within_slot(time(11, 10), s, e, 10)
    assert not p.within_slot(time(11, 11), s, e, 10)
    assert p.parse_time('10:00:00') == time(10, 0)
 
 
def test_validate_leave_input():
    today = date(2026, 10, 31)
    ok = p.validate_leave_input('leave', today, today, 'fever and rest', today)
    assert ok is None
    assert p.validate_leave_input('x', today, today, 'fever and rest', today)
    assert p.validate_leave_input('leave', today, today, 'no', today)
    assert p.validate_leave_input('leave', date(2026, 11, 2), today, 'fever and rest', today)
    assert p.validate_leave_input('leave', date(2026, 9, 1), date(2026, 9, 2), 'fever and rest', today)
    assert p.validate_leave_input('leave', today, date(2026, 12, 15), 'fever and rest', today)
 
 
def test_doc_error():
    assert p.doc_error('a.pdf', b'%PDF-1.4 x') is None
    assert p.doc_error('a.jpg', b'\xff\xd8\xff') is None
    assert p.doc_error('a.png', b'\x89PNG....') is None
    assert p.doc_error('a.pdf', b'MZ-not-pdf')
    assert p.doc_error('a.exe', b'%PDF')
    assert p.doc_error('a.pdf', b'')
    assert p.doc_error('a.pdf', b'%PDF' + b'0' * (2 * 1024 * 1024))
 
 
def test_csv_safe_and_week_key():
    assert p.csv_safe('=cmd') == "'=cmd"
    assert p.csv_safe('Ravi') == 'Ravi'
    assert p.csv_safe(None) == ''
    assert p.iso_week_key(date(2026, 10, 31)) == '2026-W44'
