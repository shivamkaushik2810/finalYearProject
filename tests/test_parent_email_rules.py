import pytest
from src.services import parent_email_rules as r


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.flt = None

    def select(self, *_):
        return self

    def ilike(self, col, pattern):
        val = pattern.replace("\\_", "_").replace("\\%", "%").replace("\\\\", "\\").lower()
        self.flt = (col, val)
        return self

    def execute(self):
        col, val = self.flt
        return _Res([{"student_id": x["student_id"]} for x in self.rows
                     if (x.get(col) or "").strip().lower() == val])


class _DB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _):
        return _Query(self.rows)


@pytest.fixture
def use_rows(monkeypatch):
    def _set(rows):
        monkeypatch.setattr(r, "supabase", _DB(rows))
    return _set


def test_valid_parent_email_allowed(use_rows):
    use_rows([])
    assert r.validate_parent_email("kid@x.com", "mom@x.com")[0] is True


@pytest.mark.parametrize("bad", ["", None, "nope", "  "])
def test_invalid_format_rejected(use_rows, bad):
    use_rows([])
    assert r.validate_parent_email("kid@x.com", bad)[0] is False


def test_own_email_rejected_ignoring_case_and_spaces(use_rows):
    use_rows([])
    assert r.validate_parent_email("Kid@X.com", "  kid@x.COM ")[0] is False


def test_other_students_email_rejected(use_rows):
    use_rows([{"student_id": 2, "email": "friend@x.com", "parent_email": None}])
    ok, msg = r.validate_parent_email("kid@x.com", "friend@x.com", student_id=1)
    assert ok is False and "student account" in msg


def test_own_row_is_ignored_when_updating(use_rows):
    use_rows([{"student_id": 1, "email": "kid@x.com", "parent_email": "mom@x.com"}])
    assert r.validate_parent_email("kid@x.com", "mom@x.com", student_id=1)[0] is True


def test_cap_blocks_extra_student(use_rows):
    use_rows([{"student_id": i, "email": f"s{i}@x.com", "parent_email": "mom@x.com"}
              for i in range(10, 10 + r.MAX_STUDENTS_PER_PARENT)])
    assert r.validate_parent_email("new@x.com", "mom@x.com")[0] is False


def test_below_cap_allowed(use_rows):
    use_rows([{"student_id": i, "email": f"s{i}@x.com", "parent_email": "mom@x.com"}
              for i in range(10, 10 + r.MAX_STUDENTS_PER_PARENT - 1)])
    assert r.validate_parent_email("new@x.com", "mom@x.com")[0] is True
