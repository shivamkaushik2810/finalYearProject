import io
import zipfile

import pytest

from src.analytics import access
from src.services import section_export as sx


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(access.st, "session_state", {"admin_data": {"id": 1}})


def _att(sid):
    def pct_rows(present, total):
        return [{"is_present": i < present, "subjects": {"name": "Maths"}} for i in range(total)]
    return pct_rows(1, 4) if sid == 1 else pct_rows(4, 4)


def _fake(monkeypatch):
    students = [{"student_id": 1, "name": "Aarav", "roll_no": "A01"},
                {"student_id": 2, "name": "=HYPERLINK()", "roll_no": "A02"}]
    marks = {1: [{"marks_obtained": 40, "max_marks": 50, "exam_type": "Mid Term", "entry_status": "entered",
                  "subjects": {"name": "Maths"}},
                 {"marks_obtained": None, "max_marks": 50, "exam_type": "End Term", "subjects": {"name": "Maths"}}]}
    monkeypatch.setattr(sx.adb, "get_students", lambda sec: students)
    monkeypatch.setattr(sx.adb, "get_attendance", lambda sec, sid: _att(sid))
    monkeypatch.setattr(sx.adb, "get_marks", lambda sec, sid: marks.get(sid, []))


def _zip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode("utf-8", "ignore") if not n.endswith(".pdf") else z.read(n)
                for n in z.namelist()}


def test_zip_contains_all_files(admin, monkeypatch):
    _fake(monkeypatch)
    data, name, info = sx.build_section_export("A")
    files = _zip(data)
    assert set(files) == {"attendance_by_subject.csv", "marks.csv", "defaulters.csv", "defaulters.pdf", "README.txt"}
    assert name.startswith("section_A_") and name.endswith(".zip")
    assert info == {"students": 2, "attendance_rows": 2}
    assert files["defaulters.pdf"].startswith(b"%PDF")


def test_only_students_below_target_are_defaulters(admin, monkeypatch):
    _fake(monkeypatch)
    files = _zip(sx.build_section_export("A")[0])
    assert "A01" in files["defaulters.csv"]
    assert "A02" not in files["defaulters.csv"]


def test_formula_injection_is_neutralised(admin, monkeypatch):
    _fake(monkeypatch)
    files = _zip(sx.build_section_export("A")[0])
    assert "'=HYPERLINK()" in files["attendance_by_subject.csv"]
    assert "\n=HYPERLINK" not in files["attendance_by_subject.csv"]


def test_missing_marks_are_not_exported_as_zero(admin, monkeypatch):
    _fake(monkeypatch)
    files = _zip(sx.build_section_export("A")[0])
    rows = [r for r in files["marks.csv"].splitlines() if r]
    assert len(rows) == 2                       # header + the one real mark
    assert "End Term" not in files["marks.csv"]


def test_requires_admin(monkeypatch):
    monkeypatch.setattr(access.st, "session_state", {})
    with pytest.raises(PermissionError):
        sx.build_section_export("A")
