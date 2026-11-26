import pytest

from src.services.sample_timetable import (
    CATALOGUE, build, crosses_lunch, expand, sample_code, sample_faculty_codes, to_csv_rows)
from src.services.timetable_validator import validate

REAL = frozenset({"HU", "PS", "RM", "RO", "SH", "SN", "VK", "VU"})


def test_full_section_is_placed():
    r = build(real_codes=REAL)
    assert r["unplaced"] == []
    assert len(r["entries"]) == sum(row[3] for row in CATALOGUE)  # one entry per block


def test_every_subject_gets_its_full_weekly_periods():
    entries = build(real_codes=REAL)["entries"]
    for subject, _, _, count, block, _ in CATALOGUE:
        got = sum(e.block_len for e in entries if e.subject_code == subject)
        assert got == count * block, subject


def test_no_placed_class_clashes_with_another():
    entries = build(real_codes=REAL)["entries"]
    for i, e in enumerate(entries):
        others = entries[:i] + entries[i + 1:]
        assert validate(e, others) == [], (e.subject_code, e.weekday, e.period_no)


def test_no_block_crosses_lunch():
    for e in build(real_codes=REAL)["entries"]:
        assert not crosses_lunch(e.period_no, e.block_len)


def test_build_is_deterministic():
    assert to_csv_rows(build(real_codes=REAL)) == to_csv_rows(build(real_codes=REAL))


def test_sample_codes_are_prefixed_and_distinct_from_real_ones():
    codes = sample_faculty_codes(real_codes=REAL)
    assert all(c.startswith("S") and len(c) == 3 for c in codes.values())
    assert not set(codes.values()) & REAL


def test_sample_code_drops_titles():
    assert sample_code("Prof. Rohit Sharma") == "SRS"
    assert sample_code("Mr. Deepak Kumar") == "SDK"


def test_code_collision_with_real_code_is_refused():
    with pytest.raises(ValueError):
        sample_faculty_codes(real_codes=frozenset({"SRS"}))


def test_impossible_load_is_reported_not_forced():
    too_many = [("X1", "Overload", "theory", 49, 1, "Dr. Anon Person")]
    r = build(catalogue=too_many)
    assert len(r["unplaced"]) > 0
    assert len(r["entries"]) + len(r["unplaced"]) == 49


def test_labs_are_expanded_first():
    jobs = expand()
    assert jobs[0]["block_len"] == 2


def test_csv_rows_have_the_importer_columns():
    row = to_csv_rows(build(real_codes=REAL))[0]
    assert set(row) == {"section_code", "weekday", "period_no", "kind", "subject_code",
                        "subject_name", "faculty_code", "room", "block_len"}
