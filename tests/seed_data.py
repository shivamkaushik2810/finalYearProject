import datetime


def subj(i, name="Maths", code="M1"):
    return {"subject_id": i, "name": name, "subject_code": code, "section": "A", "teacher_id": 7, "teachers": {"name": "Dr X"}}


def seed(db, n_classes=20):
    db.tables["students"] = [
        {"student_id": 1, "name": "Aarav", "roll_no": "A01", "section": "a", "course": "B.Tech", "year": "3"},
        {"student_id": 2, "name": "Diya", "roll_no": "A02", "section": "A ", "course": "B.Tech", "year": "3"},
        {"student_id": 3, "name": "Kabir", "roll_no": "B01", "section": "B", "course": "B.Tech", "year": "3"},
        {"student_id": 4, "name": "Nobody", "roll_no": "X01", "section": None, "course": "B.Tech", "year": "3"},
    ]
    db.tables["subject_students"] = [
        {"student_id": 1, "subject_id": 10, "subjects": subj(10)},
        {"student_id": 2, "subject_id": 10, "subjects": subj(10)},
        {"student_id": 3, "subject_id": 11, "subjects": subj(11, "Physics", "P1")},
    ]
    logs = []
    for i in range(n_classes):
        ts = (datetime.datetime(2026, 8, 3, 10) + datetime.timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%S")
        logs.append({"student_id": 1, "subject_id": 10, "timestamp": ts, "is_present": i < 15,
                     "status": "present" if i < 15 else "absent",
                     "subjects": {"name": "Maths", "subject_code": "M1", "teacher_id": 7, "teachers": {"name": "Dr X"}}})
    db.tables["attendance_logs"] = logs
    db.tables["marks"] = [
        {"id": 1, "student_id": 1, "subject_id": 10, "marks_obtained": 40, "max_marks": 50, "exam_type": "Mid Term",
         "remarks": "", "entry_status": "entered", "exam_date": "2026-09-01",
         "subjects": {"name": "Maths", "subject_code": "M1", "teacher_id": 7, "teachers": {"name": "Dr X"}}},
    ]
