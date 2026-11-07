"""Headless UI smoke + click-path tests (Streamlit is stubbed; services hit the in-memory fake DB)."""
import datetime as dt
import io
import sys
import types
 
import numpy as np
from PIL import Image
 
from tests import ui_stub as U
from tests.test_services import FAKE, add_logs, fresh   # also installs the shared stubs
from src.services import audit_service, leave_service, schedule_service
 
st = U.STUB
today = dt.date.today()
 
# stubs for modules that need heavy deps (bcrypt, face_recognition, OpenCV pipelines)
dbm = types.ModuleType('src.database.db')
dbm.get_student_subjects = lambda sid: FAKE.table('subject_students').select('*, subjects(*)').eq('student_id', sid).execute().data
sys.modules['src.database.db'] = dbm
PIPE = {'detect': (True, 'ok'), 'faces': [np.array([0.1] * 128)], 'trained': 0}
fp = types.ModuleType('src.pipelines.face_pipeline')
fp.get_face_embeddings = lambda img: PIPE['faces']
def _train(): PIPE['trained'] += 1
fp.train_classifier = _train
lv = types.ModuleType('src.pipelines.liveness_detection')
lv.detect_screen_or_photo = lambda img: PIPE['detect']
for name, mod in (('src.pipelines', types.ModuleType('src.pipelines')),
                  ('src.pipelines.face_pipeline', fp), ('src.pipelines.liveness_detection', lv)):
    sys.modules[name] = mod
 
from src.components import leave_ui, teacher_tools, contact_prefs, client_location   # noqa: E402
from src.components import dialog_add_angles                                          # noqa: E402
 
 
def setup():
    fresh(); U.reset()
    return [s for s in FAKE.tables['subjects'] if s['teacher_id'] == 't1']
 
 
def test_more_tools_renders_empty_without_errors():
    subs = setup()
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is False
    heads = U.texts('header', 'subheader', 'info', 'caption')
    assert any('More Tools' in h for h in heads) and any('Audit' in h or 'No attendance sessions' in h for h in heads)
    assert any('No pending requests' in h for h in heads)
    U.reset()
    assert U.run(teacher_tools.teacher_more_tools, [], 't1') is False                 # teacher with no subjects
    assert any('Create a subject first' in h for h in U.texts('info'))
 
 
def test_teacher_approves_leave_through_ui():
    subs = setup(); d0 = today - dt.timedelta(days=2)
    add_logs('st1', 's1', 'AA', day0=d0)
    leave_service.submit_leave('st1', 's1', 'leave', d0, d0, 'family function')
    rid = FAKE.tables['leave_requests'][0]['id']
    U.CLICKS.add(f'ap_{rid}'); U.VALUES[f'note_{rid}'] = 'ok'
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is True                # st.rerun() reached
    assert FAKE.tables['leave_requests'][0]['status'] == 'approved'
    assert [l['is_excused'] for l in FAKE.tables['attendance_logs']] == [True, False]
 
 
def test_teacher_correction_through_ui_writes_audit():
    subs = setup()
    add_logs('st1', 's1', 'PA')
    lid = audit_service.session_logs('t1', 's1', audit_service.recent_sessions('t1', 's1')[0])[0]['log_id']
    U.VALUES[f'corr_reason_{lid}'] = 'scanner missed him'
    U.CLICKS.add(f'corr_btn_{lid}')
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is True
    assert FAKE.tables['attendance_logs'][1]['is_present'] is True
    assert len(FAKE.tables['attendance_audit_log']) == 1
    U.reset(); U.run(teacher_tools.teacher_more_tools, subs, 't1')                    # re-render shows history
    assert any(n == 'dataframe' for n, a, k in U.LOG)
 
 
def test_correction_without_reason_is_rejected_in_ui():
    subs = setup(); add_logs('st1', 's1', 'A')
    lid = audit_service.session_logs('t1', 's1', audit_service.recent_sessions('t1', 's1')[0])[0]['log_id']
    U.CLICKS.add(f'corr_btn_{lid}')
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is False
    assert any('reason' in e.lower() for e in U.texts('error')) and not FAKE.tables.get('attendance_audit_log')
 
 
def test_eligibility_ui_csv_is_formula_safe_and_condonation_works():
    subs = setup()
    FAKE.tables['students'][0]['name'] = '=HYPERLINK("http://evil")'
    add_logs('st1', 's1', 'PPPPPPAAA')     # 66.7 -> condonable
    add_logs('st2', 's1', 'PPPP')
    U.VALUES['cd_reason_s1'] = 'medical grounds'; U.CLICKS.add('cd_save_s1')
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is True
    assert FAKE.tables['condonation_decisions'][0]['decision'] == 'condoned'
    csv = next(a[1] for n, a, k in U.LOG if n == 'download_button').decode()
    assert csv.startswith('Name,Roll,Section') and "'=HYPERLINK" in csv and '\n=HYPERLINK' not in csv
    U.reset(); U.CLICKS.add('el_save_s1'); U.VALUES['el_e_s1'] = 60.0; U.VALUES['el_c_s1'] = 70.0   # invalid: c > e
    U.run(teacher_tools.teacher_more_tools, subs, 't1')
    assert any('condonable <= eligible' in e for e in U.texts('error')) and not FAKE.tables.get('eligibility_settings')
 
 
def test_schedule_and_geofence_ui():
    subs = setup()
    U.VALUES.update({'slot_start_s1': dt.time(9, 0), 'slot_end_s1': dt.time(10, 0)}); U.CLICKS.add('slot_add_s1')
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is True
    assert FAKE.tables['subject_slots'][0]['start_time'] == '09:00:00'
    U.reset(); U.VALUES.update({'slot_start_s1': dt.time(11, 0), 'slot_end_s1': dt.time(10, 0)}); U.CLICKS.add('slot_add_s1')
    U.run(teacher_tools.teacher_more_tools, subs, 't1')
    assert any('Invalid slot' in m for m in U.texts('error')) and len(FAKE.tables['subject_slots']) == 1
    U.reset(); U.VALUES.update({'gf_en_s1': True, 'gf_gps_s1': True, 'gf_lat_s1': 28.0, 'gf_lon_s1': 77.0,
                                'gf_ips_s1': '10.0.0.0/8\n'}); U.CLICKS.add('gf_save_s1')
    U.run(teacher_tools.teacher_more_tools, subs, 't1')
    g = FAKE.tables['subject_geofence'][0]
    assert g['enabled'] and g['allowed_ips'] == ['10.0.0.0/8'] and g['latitude'] == 28.0
    U.reset(); U.VALUES.update({'gf_en_s1': True, 'gf_ips_s1': 'bad-ip'}); U.CLICKS.add('gf_save_s1')
    U.run(teacher_tools.teacher_more_tools, subs, 't1')
    assert any('Invalid IP' in m for m in U.texts('error'))
    U.reset(); U.CLICKS.add(f"slot_del_{FAKE.tables['subject_slots'][0]['id']}")
    assert U.run(teacher_tools.teacher_more_tools, subs, 't1') is True and not FAKE.tables['subject_slots']
 
 
def test_student_leave_form_submit_and_bad_file():
    setup()
    class Up:
        def __init__(self, name, data): self.name, self._d = name, data
        def getvalue(self): return self._d
    U.VALUES.update({'leave_reason': 'viral fever', 'leave_doc': Up('cert.pdf', b'%PDF-1.4 x')}); U.CLICKS.add('leave_submit')
    U.run(leave_ui.student_leave_tab, 'st1')
    assert len(FAKE.tables['leave_requests']) == 1 and len(FAKE.storage.files) == 1
    assert any('pending' in str(a) or '🟡' in str(a) for n, a, k in U.LOG if n == 'write')
    U.reset(); FAKE.tables['leave_requests'].clear(); FAKE.storage.files.clear()
    U.VALUES.update({'leave_reason': 'viral fever', 'leave_doc': Up('cert.pdf', b'MZ-malware')}); U.CLICKS.add('leave_submit')
    U.run(leave_ui.student_leave_tab, 'st1')
    assert any('genuine' in e for e in U.texts('error')) and not FAKE.tables['leave_requests']
    U.reset(); U.run(leave_ui.student_leave_tab, 'st9')                                # not enrolled anywhere
    assert any('Enroll in a subject first' in m for m in U.texts('info'))
 
 
def test_contact_prefs_validation_and_save():
    setup()
    U.VALUES.update({'cp_parent_phone': '98765 43210', 'cp_consent': True}); U.CLICKS.add('cp_save')
    U.run(contact_prefs.contact_prefs_ui, 'st1')
    s = FAKE.tables['students'][0]
    assert s['parent_phone'] == '+919876543210' and s['alert_opt_in'] is True and s['phone'] is None
    U.reset(); U.VALUES.update({'cp_parent_phone': '12345', 'cp_consent': True}); U.CLICKS.add('cp_save')
    U.run(contact_prefs.contact_prefs_ui, 'st2')
    assert any('valid mobile' in e for e in U.texts('error')) and FAKE.tables['students'][1]['parent_phone'] is None
    U.reset(); U.VALUES.update({'cp_parent_phone': '9876543210', 'cp_consent': False}); U.CLICKS.add('cp_save')
    U.run(contact_prefs.contact_prefs_ui, 'st3')
    assert any('consent' in e.lower() for e in U.texts('error')) and FAKE.tables['students'][2]['parent_phone'] is None
 
 
def _png():
    b = io.BytesIO(); Image.new('RGB', (40, 40), 'white').save(b, 'PNG'); b.seek(0); return b
 
 
def test_add_angles_dialog_paths():
    setup()
    row = FAKE.tables['students'][0]; row['face_embedding'] = [0.5] * 128
    st.session_state.student_data = dict(row)
    PIPE.update(detect=(True, 'ok'), faces=[np.array([0.1] * 128)], trained=0)
    U.VALUES['angle_cam_1'] = _png(); U.CLICKS.add('Save this angle')
    dialog_add_angles.add_angles_dialog('st1')
    assert PIPE['trained'] == 1 and len(row['face_embeddings']) == 1
    assert len(st.session_state.student_data['face_embeddings']) == 1                  # session refreshed
    assert any('2/5' in m for m in U.texts('success'))
    PIPE.update(detect=(False, 'screen detected'))                                      # spoof attempt
    U.reset(); st.session_state.student_data = dict(row); U.VALUES['angle_cam_2'] = _png(); U.CLICKS.add('Save this angle')
    dialog_add_angles.add_angles_dialog('st1')
    assert any('screen detected' in e for e in U.texts('error')) and len(row['face_embeddings']) == 1
    PIPE.update(detect=(True, 'ok'), faces=[np.array([0.1] * 128), np.array([0.2] * 128)])   # two faces
    U.reset(); st.session_state.student_data = dict(row); U.VALUES['angle_cam_2'] = _png(); U.CLICKS.add('Save this angle')
    dialog_add_angles.add_angles_dialog('st1')
    assert any('Exactly one face' in e for e in U.texts('error')) and len(row['face_embeddings']) == 1
 
 
def test_client_location_helpers():
    st.context.headers = {'X-Forwarded-For': '1.2.3.4, 10.0.0.1'}
    assert client_location.get_client_ip() == '1.2.3.4'
    st.context.headers, st.context.ip_address = {}, '9.9.9.9'
    assert client_location.get_client_ip() == '9.9.9.9'
    sys.modules.pop('streamlit_js_eval', None)
    assert client_location.get_client_location() is None                                # package missing -> None, no crash
    m = types.ModuleType('streamlit_js_eval')
    m.get_geolocation = lambda: {'coords': {'latitude': 28.1, 'longitude': 77.2, 'accuracy': 12}}
    sys.modules['streamlit_js_eval'] = m
    assert client_location.get_client_location() == (28.1, 77.2, 12)
    m.get_geolocation = lambda: None
    assert client_location.get_client_location() is None
    sys.modules.pop('streamlit_js_eval')
