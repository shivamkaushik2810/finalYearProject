from src.services.notification_messages import (
    absence_for_original, assigned_to_substitute, key_for, unassigned_for_admin)

SUB = {"id": 5, "subject_code": "BCS 603", "section_code": "3D", "period_no": 6,
       "substitution_date": "2026-11-25", "room": "B 202", "reasons": None}


def test_key_is_stable_and_specific():
    assert key_for("assigned", 5, "t1") == key_for("assigned", 5, "t1")
    assert key_for("assigned", 5, "t1") != key_for("assigned", 5, "t2")
    assert key_for("assigned", 5, "t1") != key_for("covered", 5, "t1")


def test_assignment_message_has_the_details_a_teacher_needs():
    subject, body = assigned_to_substitute(SUB)
    assert "BCS 603" in subject and "P6" in subject
    assert "3D" in body and "B 202" in body and "accept or decline" in body


def test_missing_room_is_stated_not_blank():
    _, body = assigned_to_substitute({**SUB, "room": None})
    assert "to be confirmed" in body


def test_original_teacher_is_told_who_covers():
    _, body = absence_for_original(SUB, "Nikhil Tomar")
    assert "Nikhil Tomar" in body


def test_unassigned_message_gives_the_reason():
    _, body = unassigned_for_admin({**SUB, "reasons": "no eligible teacher"})
    assert "no eligible teacher" in body
