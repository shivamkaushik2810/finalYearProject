"""Tests for src/services/schedule_service.py (timetable gate, slots, location rules).

Note: save_geofence calls upsert(), which tests/fake_supabase.py does not implement.
The tests replace schedule_service.supabase with a recorder that captures upserts and
delegates everything else to the fake. authz.teacher_owns_subject still uses the fake.
"""
from datetime import datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.services import schedule_service as sched

IST = ZoneInfo("Asia/Kolkata")
SUBJECT = "10"          # the schedule tables store subject ids as text
TEACHER = 7
OTHER_TEACHER = 8
MONDAY = datetime(2026, 11, 23, 9, 55, tzinfo=IST)   # 2026-11-23 is a Monday


@pytest.fixture
def owned(fake_db):
    fake_db.tables["subjects"] = [
        {"subject_id": SUBJECT, "teacher_id": TEACHER, "name": "Maths"},
    ]
    fake_db.tables.setdefault("subject_slots", [])
    fake_db.tables.setdefault("subject_geofence", [])
    return fake_db


def _slot(weekday, start, end, grace=10, slot_id=1, subject=SUBJECT):
    return {"id": slot_id, "subject_id": subject, "weekday": weekday,
            "start_time": start, "end_time": end, "grace_minutes": grace}


# ── slots ───────────────────────────────────────────────────────────

def test_add_slot_for_owner_stores_normalised_row(owned):
    ok, msg = sched.add_slot(TEACHER, SUBJECT, 0, time(9, 0), time(10, 0), 10)
    assert ok is True
    row = owned.tables["subject_slots"][0]
    assert row["subject_id"] == SUBJECT and row["weekday"] == 0
    assert row["start_time"] == "09:00:00" and row["end_time"] == "10:00:00"
    assert row["grace_minutes"] == 10


def test_add_slot_refused_for_non_owner(owned):
    ok, msg = sched.add_slot(OTHER_TEACHER, SUBJECT, 0, time(9), time(10))
    assert ok is False and msg == "Not your subject."
    assert owned.tables["subject_slots"] == []


@pytest.mark.parametrize("weekday, start, end, grace", [
    (0, time(10), time(10), 10),   # end equal to start
    (0, time(11), time(10), 10),   # end before start
    (7, time(9), time(10), 10),    # weekday out of range
    (-1, time(9), time(10), 10),
    (0, time(9), time(10), 61),    # grace too large
    (0, time(9), time(10), -1),    # grace negative
])
def test_add_slot_rejects_invalid_values(owned, weekday, start, end, grace):
    ok, msg = sched.add_slot(TEACHER, SUBJECT, weekday, start, end, grace)
    assert ok is False and "Invalid slot" in msg
    assert owned.tables["subject_slots"] == []


def test_list_slots_sorted_by_day_then_start(owned):
    owned.tables["subject_slots"] = [
        _slot(2, "09:00:00", "10:00:00", slot_id=1),
        _slot(0, "14:00:00", "15:00:00", slot_id=2),
        _slot(0, "09:00:00", "10:00:00", slot_id=3),
    ]
    order = [s["id"] for s in sched.list_slots(SUBJECT)]
    assert order == [3, 2, 1]


def test_delete_slot_by_owner(owned):
    owned.tables["subject_slots"] = [_slot(0, "09:00:00", "10:00:00", slot_id=1)]
    assert sched.delete_slot(TEACHER, 1) == (True, "Slot removed.")
    assert owned.tables["subject_slots"] == []


def test_delete_slot_refused_for_non_owner(owned):
    owned.tables["subject_slots"] = [_slot(0, "09:00:00", "10:00:00", slot_id=1)]
    assert sched.delete_slot(OTHER_TEACHER, 1) == (False, "Not allowed.")
    assert len(owned.tables["subject_slots"]) == 1


def test_delete_missing_slot_is_not_allowed(owned):
    assert sched.delete_slot(TEACHER, 999) == (False, "Not allowed.")


# ── timetable gate ──────────────────────────────────────────────────

def test_no_timetable_allows_session_by_default(owned):
    ok, msg = sched.check_session_allowed(SUBJECT, MONDAY)
    assert ok is True and "No timetable set" in msg


def test_no_timetable_blocks_when_enforced(owned, monkeypatch):
    monkeypatch.setattr(sched, "ENFORCE_WHEN_NO_SLOTS", True)
    ok, msg = sched.check_session_allowed(SUBJECT, MONDAY)
    assert ok is False and "No timetable set for this subject" in msg


def test_inside_slot_allowed(owned):
    owned.tables["subject_slots"] = [_slot(0, "09:00:00", "10:00:00", grace=0)]
    ok, _ = sched.check_session_allowed(SUBJECT, MONDAY)
    assert ok is True


def test_grace_extends_window_both_ways(owned):
    owned.tables["subject_slots"] = [_slot(0, "10:00:00", "11:00:00", grace=10)]
    assert sched.check_session_allowed(SUBJECT, datetime(2026, 11, 23, 9, 50, tzinfo=IST))[0] is True
    assert sched.check_session_allowed(SUBJECT, datetime(2026, 11, 23, 11, 10, tzinfo=IST))[0] is True
    assert sched.check_session_allowed(SUBJECT, datetime(2026, 11, 23, 11, 11, tzinfo=IST))[0] is False


def test_outside_slot_same_day_is_blocked_with_window_in_message(owned):
    owned.tables["subject_slots"] = [_slot(0, "09:00:00", "10:00:00", grace=0)]
    ok, msg = sched.check_session_allowed(SUBJECT, datetime(2026, 11, 23, 8, 0, tzinfo=IST))
    assert ok is False
    assert "Outside the scheduled slot today" in msg and "09:00-10:00" in msg


def test_no_class_on_this_weekday_is_blocked(owned):
    owned.tables["subject_slots"] = [_slot(0, "09:00:00", "10:00:00")]   # Monday only
    tuesday = datetime(2026, 11, 24, 9, 30, tzinfo=IST)
    ok, msg = sched.check_session_allowed(SUBJECT, tuesday)
    assert ok is False and "No class scheduled for this subject on Tue" in msg


def test_any_of_several_same_day_slots_allows(owned):
    owned.tables["subject_slots"] = [
        _slot(0, "09:00:00", "10:00:00", grace=0, slot_id=1),
        _slot(0, "14:00:00", "15:00:00", grace=0, slot_id=2),
    ]
    assert sched.check_session_allowed(SUBJECT, datetime(2026, 11, 23, 14, 30, tzinfo=IST))[0] is True


# ── location rules: saving ──────────────────────────────────────────

class _Recorder:
    """Captures upsert() on subject_geofence; delegates all other tables to the fake."""

    def __init__(self, base):
        self.base = base
        self.rows = []

    def table(self, name):
        if name == "subject_geofence":
            return _GeoUpsert(self.rows)
        return self.base.table(name)


class _GeoUpsert:
    def __init__(self, rows):
        self.rows = rows

    def upsert(self, row):
        self.rows.append(row)
        return self

    def execute(self):
        return SimpleNamespace(data=[])


@pytest.fixture
def recorder(owned, monkeypatch):
    rec = _Recorder(owned)
    monkeypatch.setattr(sched, "supabase", rec)
    return rec


def test_save_geofence_refused_for_non_owner(recorder):
    ok, msg = sched.save_geofence(OTHER_TEACHER, SUBJECT, True, 28.0, 77.0, 100, [])
    assert ok is False and msg == "Not your subject."
    assert recorder.rows == []


@pytest.mark.parametrize("radius", [19, 2001])
def test_save_geofence_rejects_radius_out_of_range(recorder, radius):
    ok, msg = sched.save_geofence(TEACHER, SUBJECT, True, 28.0, 77.0, radius, [])
    assert ok is False and "20-2000" in msg
    assert recorder.rows == []


def test_save_geofence_rejects_bad_latitude(recorder):
    ok, msg = sched.save_geofence(TEACHER, SUBJECT, True, 91.0, 77.0, 100, [])
    assert ok is False and msg == "Invalid coordinates."


def test_save_geofence_rejects_bad_cidr(recorder):
    ok, msg = sched.save_geofence(TEACHER, SUBJECT, True, None, None, 100, ["10.0.0.0/33"])
    assert ok is False and "Invalid IP/CIDR: 10.0.0.0/33" in msg


def test_enabled_needs_coordinates_or_network(recorder):
    ok, msg = sched.save_geofence(TEACHER, SUBJECT, True, None, None, 100, ["", "   "])
    assert ok is False and "Enable needs coordinates" in msg


def test_disabled_rule_can_be_saved_without_location(recorder):
    ok, _ = sched.save_geofence(TEACHER, SUBJECT, False, None, None, 100, [])
    assert ok is True and recorder.rows[0]["enabled"] is False


def test_save_geofence_stores_cleaned_values(recorder):
    ok, _ = sched.save_geofence(TEACHER, SUBJECT, True, 28.5, 77.25, 150,
                                ["  10.1.0.0/16 ", "", "203.0.113.5"])
    assert ok is True
    row = recorder.rows[0]
    assert row["enabled"] is True and row["latitude"] == 28.5 and row["longitude"] == 77.25
    assert row["radius_m"] == 150 and isinstance(row["radius_m"], int)
    assert row["allowed_ips"] == ["10.1.0.0/16", "203.0.113.5"]
    assert row["updated_by"] == str(TEACHER)


def test_get_geofence_none_then_row(owned):
    assert sched.get_geofence(SUBJECT) is None
    owned.tables["subject_geofence"] = [{"subject_id": SUBJECT, "enabled": True}]
    assert sched.get_geofence(SUBJECT)["enabled"] is True


# ── location rules: checking a scan ─────────────────────────────────

FENCE = {"enabled": True, "latitude": 28.0, "longitude": 77.0, "radius_m": 50, "allowed_ips": []}


def test_no_fence_or_disabled_fence_passes(owned):
    assert sched.check_scan_location(SUBJECT, None, None, fence=None)[0] is True
    assert sched.check_scan_location(SUBJECT, None, None, fence={"enabled": False})[0] is True


def test_allowed_network_passes_without_gps():
    fence = {"enabled": True, "allowed_ips": ["10.1.0.0/16"], "latitude": None}
    ok, msg = sched.check_scan_location(SUBJECT, None, "10.1.2.3", fence=fence)
    assert ok is True and "network verified" in msg


def test_inside_radius_passes():
    ok, _ = sched.check_scan_location(SUBJECT, (28.0001, 77.0, 5), None, fence=FENCE)
    assert ok is True


def test_outside_radius_is_refused():
    # 0.01 degrees of latitude is about 1.1 km, well outside 50 m
    ok, msg = sched.check_scan_location(SUBJECT, (28.01, 77.0, 5), None, fence=FENCE)
    assert ok is False and "outside the classroom" in msg


def test_gps_accuracy_tolerance_is_applied():
    # 0.0011 deg is about 122 m. With 100 m accuracy the effective distance is about 22 m, inside 50 m.
    assert sched.check_scan_location(SUBJECT, (28.0011, 77.0, 100), None, fence=FENCE)[0] is True
    assert sched.check_scan_location(SUBJECT, (28.0011, 77.0, 5), None, fence=FENCE)[0] is False


def test_accuracy_tolerance_is_capped_at_100m():
    # About 1.1 km away: even a 5 km accuracy report must not grant a pass
    assert sched.check_scan_location(SUBJECT, (28.01, 77.0, 5000), None, fence=FENCE)[0] is False


def test_missing_gps_fix_asks_for_location():
    ok, msg = sched.check_scan_location(SUBJECT, None, None, fence=FENCE)
    assert ok is False and "Location needed" in msg


def test_no_coordinates_and_wrong_network_is_refused():
    fence = {"enabled": True, "latitude": None, "allowed_ips": ["10.1.0.0/16"]}
    ok, msg = sched.check_scan_location(SUBJECT, None, "192.168.0.9", fence=fence)
    assert ok is False and "not on the classroom network" in msg
