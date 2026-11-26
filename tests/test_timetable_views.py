from src.components.timetable_views import all_sections_html, section_grid_html, section_sort_key, teacher_matrix_html
from src.services.timetable_validator import Entry

SLOTS = {1: "09:00-10:00", 2: "10:00-10:50", 3: "11:00-11:50", 4: "11:50-12:40",
         5: "12:40-13:30", 6: "14:20-15:10", 7: "15:10-16:00", 8: "16:00-16:55"}


def E(**kw):
    base = dict(id=None, section_id=1, section_code="3D", weekday=1, period_no=1, block_len=1,
                kind="theory", subject_code="BCS 601", subject_name="SE", faculty_code="PS", room=None)
    base.update(kw)
    return Entry(**base)


def test_lunch_column_sits_after_period_five():
    html = section_grid_html([], SLOTS)
    assert html.index(">P5<") < html.index("LUNCH") < html.index(">P6<")


def test_lab_spans_two_columns():
    html = section_grid_html([E(kind="lab", block_len=2, period_no=3, subject_code="BCAI651",
                                subject_name="MLT", faculty_code="VU")], SLOTS)
    assert "colspan='2'" in html


def test_block_crossing_lunch_spans_the_lunch_column():
    html = section_grid_html([E(kind="training", block_len=3, period_no=4, subject_code=None,
                                subject_name="Full Stack Java", faculty_code="VK")], SLOTS)
    assert "colspan='4'" in html


def test_block_ending_before_lunch_leaves_lunch_cell_in_every_row():
    html = section_grid_html([E(kind="lab", block_len=2, period_no=4, subject_code="X",
                                subject_name="X", faculty_code="VU")], SLOTS)
    assert "colspan='2'" in html
    assert html.count("LUNCH</td>") == 6


def test_database_text_is_escaped():
    html = section_grid_html([E(subject_name="<img src=x onerror=alert(1)>", subject_code="A")], SLOTS)
    assert "<img" not in html and "&lt;img" in html


def test_all_sections_are_listed_in_year_order():
    html = all_sections_html([E(section_code="3D"), E(section_code="P1", weekday=2)], SLOTS)
    assert html.index("Section P1") < html.index("Section 3D")


def test_section_sort_key_order():
    assert sorted(["3A", "P1", "2B", "C1"], key=section_sort_key) == ["C1", "P1", "2B", "3A"]


def test_teacher_matrix_lists_every_section_and_totals_periods():
    ents = [E(id=1, period_no=1, section_code="3D"),
            E(id=2, weekday=2, period_no=4, block_len=2, section_code="2A", faculty_code="PS"),
            E(id=3, period_no=3, kind="activity", faculty_code=None, subject_code=None, subject_name="SPORTS")]
    html = teacher_matrix_html(ents, teachers=["RM"])
    assert "P1 BCS 601 3D" in html
    assert "P4-5 BCS 601 2A" in html
    assert "RM" in html
    assert ">3</td>" in html  # PS: 1 + 2 periods
