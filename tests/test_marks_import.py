from src.services.marks_import import parse_marks_csv, TEMPLATE

ROLLS = {"A01": 1, "A02": 2, "DUP": None}


def run(text, rolls=ROLLS):
    return parse_marks_csv(text.encode("utf-8"), rolls)


def test_template_parses_and_blank_marks_are_skipped_not_zero():
    rows, errors, skipped = run(TEMPLATE)
    assert errors == []
    assert [r["student_id"] for r in rows] == [1]
    assert skipped == 1
    assert rows[0]["marks_obtained"] == 40.0 and rows[0]["max_marks"] == 50.0


def test_utf8_bom_is_accepted():
    rows, errors, _ = parse_marks_csv(("\ufeff" + TEMPLATE).encode("utf-8"), ROLLS)
    assert errors == [] and len(rows) == 1


def test_missing_header_column_is_rejected():
    _, errors, _ = run("roll_no,exam_type,marks_obtained\nA01,Quiz,5\n")
    assert errors and "max_marks" in errors[0]


def test_unknown_roll_and_shared_roll_are_reported_with_line_numbers():
    text = ("roll_no,exam_type,marks_obtained,max_marks\n"
            "ZZ9,Quiz,5,10\n"
            "DUP,Quiz,5,10\n")
    rows, errors, _ = run(text)
    assert rows == []
    assert "Line 2" in errors[0] and "not enrolled" in errors[0]
    assert "Line 3" in errors[1] and "shared" in errors[1]


def test_marks_above_max_and_non_numbers_are_rejected():
    text = ("roll_no,exam_type,marks_obtained,max_marks\n"
            "A01,Quiz,11,10\n"
            "A02,Quiz,nan,10\n")
    rows, errors, _ = run(text)
    assert rows == [] and len(errors) == 2


def test_duplicate_student_and_exam_in_one_file():
    text = ("roll_no,exam_type,marks_obtained,max_marks\n"
            "A01,Quiz,5,10\n"
            "A01,quiz,6,10\n")
    rows, errors, _ = run(text)
    assert len(rows) == 1 and "already has" in errors[0]


def test_bad_exam_type_bad_date_and_long_remarks():
    text = ("roll_no,exam_type,marks_obtained,max_marks,remarks,exam_date\n"
            "A01,Oral,5,10,,\n"
            "A01,Quiz,5,10,,31-12-2026\n"
            "A02,Quiz,5,10," + "x" * 201 + ",\n")
    rows, errors, _ = run(text)
    assert rows == [] and len(errors) == 3


def test_empty_and_oversized_files():
    assert parse_marks_csv(b"", ROLLS)[1] == ["The file is empty."]
    big = b"roll_no,exam_type,marks_obtained,max_marks\n" + b"A01,Quiz,1,2\n" * 100000
    assert "larger than 1 MB" in parse_marks_csv(big, ROLLS)[1][0]


def test_non_utf8_is_rejected():
    _, errors, _ = parse_marks_csv(b"roll_no\xff", ROLLS)
    assert "UTF-8" in errors[0]
