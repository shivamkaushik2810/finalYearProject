from unittest.mock import MagicMock

ROW = {"student_id": 1, "subject_id": 2, "timestamp": "t", "is_present": True}


def test_upsert_args_and_only_inserted_rows_returned(monkeypatch):
    from src.database import db
    fake = MagicMock()
    fake.table.return_value.upsert.return_value.execute.return_value.data = [ROW]
    monkeypatch.setattr(db, "supabase", fake)
    assert db.create_attendance_idempotent([ROW]) == [ROW]
    _, kwargs = fake.table.return_value.upsert.call_args
    assert kwargs == {"on_conflict": "student_id,subject_id,timestamp",
                      "ignore_duplicates": True}


def test_empty_input_does_nothing(monkeypatch):
    from src.database import db
    fake = MagicMock()
    monkeypatch.setattr(db, "supabase", fake)
    assert db.create_attendance_idempotent([]) == []
    fake.table.assert_not_called()
