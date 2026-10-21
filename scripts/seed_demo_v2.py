import argparse
import csv
import os
import random
import sys
import time
import tomllib
from datetime import datetime, timedelta, date, time as dtime

import bcrypt
from supabase import create_client

DEMO_PASSWORD = "Demo@2026x"
# course: (code, years, weight)
PROGRAMS = {
    'B.Tech': ('BT', 4, 30), 'BCA': ('BCA', 3, 12), 'MCA': ('MCA', 2, 10),
    'MBA': ('MBA', 2, 10), 'B.Sc': ('BSC', 3, 10), 'M.Sc': ('MSC', 2, 6),
}
SECTIONS = ['A', 'B', 'C']
CATALOG = {
    'B.Tech': ["Data Structures", "Machine Learning", "Database Systems", "Operating Systems",
               "Computer Networks", "Software Engineering", "Algorithms", "Digital Electronics"],
    'BCA': ["Programming in C", "Web Development", "Database Management", "Computer Organization",
            "Java Programming", "Python Programming", "Data Communication", "Mathematics"],
    'MCA': ["Advanced Algorithms", "Cloud Computing", "Data Mining", "Cyber Security",
            "Mobile Computing", "Artificial Intelligence", "Big Data", "Software Testing"],
    'MBA': ["Marketing Management", "Financial Accounting", "Operations Management", "Business Analytics",
            "Human Resources", "Strategic Management", "Business Law", "Corporate Finance"],
    'B.Sc': ["Calculus", "Physics Fundamentals", "Organic Chemistry", "Statistics",
             "Linear Algebra", "Electronics Basics", "Environmental Science", "Numerical Methods"],
    'M.Sc': ["Quantum Mechanics", "Advanced Statistics", "Research Methods", "Mathematical Physics",
             "Data Science", "Spectroscopy", "Complex Analysis", "Computational Methods"],
}
EXAMS = [("Internal", 30), ("Mid Term", 50), ("Assignment", 20)]
FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Rahul", "Amit", "Nikhil", "Shivam",
         "Ananya", "Diya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Riya", "Sneha", "Tanvi",
         "Harsh", "Mohit", "Varun", "Yash", "Sachin", "Priya", "Divya", "Anjali", "Sakshi", "Komal",
         "Ishaan", "Kabir", "Aryan", "Dev", "Manav", "Sara", "Aditi", "Nisha", "Ritu", "Simran"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Yadav", "Mishra", "Tiwari", "Chauhan", "Tomar",
        "Kaushik", "Rajput", "Pandey", "Saxena", "Agarwal", "Jain", "Bansal", "Malik", "Thakur", "Joshi",
        "Reddy", "Nair", "Iyer", "Patel", "Shah", "Mehta", "Khan", "Ansari", "Dubey", "Srivastava"]

ap = argparse.ArgumentParser()
ap.add_argument("--students", type=int, default=5000)
ap.add_argument("--teachers", type=int, default=30)
ap.add_argument("--sessions", type=int, default=8, help="sessions per subject")
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--with-emails", action="store_true",
                help="also fill student/parent emails (fake .invalid addresses)")
args = ap.parse_args()
rnd = random.Random(args.seed)

with open(".streamlit/secrets.toml", "rb") as f:
    sec = tomllib.load(f)
sb = create_client(sec["SUPABASE_URL"], sec["SUPABASE_KEY"])

# ---- safety checks ----
if sb.table("teachers").select("username").like("username", "demo_t%").limit(1).execute().data \
        or sb.table("students").select("roll_no").like("roll_no", "DEMO%").limit(1).execute().data:
    sys.exit("Demo data already exists. Run the cleanup SQL first, then run this again.")
try:
    sb.table("subjects").select("course, year").limit(1).execute()
except Exception as e:
    sys.exit(f"subjects.course / subjects.year columns are missing. Run the ALTER TABLE SQL first.\n{e}")


def insert_batches(table, rows, size=500, returning=False):
    out = []
    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        for attempt in range(3):
            try:
                res = sb.table(table).insert(chunk).execute()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"\n  retrying {table} ({e})")
                time.sleep(2)
        if returning:
            out.extend(res.data)
        print(f"  {table}: {min(i + size, len(rows))}/{len(rows)}", end="\r")
    print()
    return out


def pick_group():
    x = rnd.random()
    if x < 0.60:
        return "regular", rnd.betavariate(9, 1.3)
    if x < 0.80:
        return "average", rnd.betavariate(6, 3)
    if x < 0.92:
        return "at_risk", rnd.betavariate(3, 4)
    return "declining", rnd.uniform(0.85, 0.95)


def p_present(group, base, k, n, mod):
    p = base - (base - 0.30) * (k / max(1, n - 1)) if group == "declining" else base
    return min(0.99, max(0.02, p + mod))


def last_weekdays(n):
    d, out = date.today() - timedelta(days=1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


os.makedirs("seed_output", exist_ok=True)

# ---- classes (course x year x section) ----
classes = []
for course, (ccode, years, weight) in PROGRAMS.items():
    for y in range(1, years + 1):
        for sec_name in SECTIONS:
            classes.append((course, ccode, str(y), sec_name, weight / years))
print(f"{len(classes)} classes (course x year x section)")

# ---- teachers ----
print("Creating teachers...")
pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
teachers = insert_batches("teachers", [
    {"username": f"demo_t{i + 1:02d}", "password": pw_hash,
     "name": f"Prof. {rnd.choice(FIRST)} {rnd.choice(LAST)}", "email": None}
    for i in range(args.teachers)], returning=True)

# ---- subjects ----
print("Creating subjects...")
s_rows, n = [], 0
for course, ccode, year, sec_name, _ in classes:
    names = CATALOG[course]
    for i in range(4):
        s_rows.append({
            "subject_code": f"DEMO-{ccode}{year}{sec_name}-{i + 1}",
            "name": names[(int(year) * 2 + i) % len(names)],
            "section": sec_name, "course": course, "year": year,
            "teacher_id": teachers[n % len(teachers)]["teacher_id"]})
        n += 1
subjects = insert_batches("subjects", s_rows, returning=True)
subs_by_class = {}
for s in subjects:
    subs_by_class.setdefault((s["course"], s["year"], s["section"]), []).append(s)

# ---- students ----
print("Creating students...")
weights = [c[4] for c in classes]
st_rows, meta = [], {}
for k in range(args.students):
    course, ccode, year, sec_name, _ = rnd.choices(classes, weights)[0]
    roll = f"DEMO{k + 1:05d}"
    first, last = rnd.choice(FIRST), rnd.choice(LAST)
    group, base = pick_group()
    meta[roll] = (group, base)
    st_rows.append({
        "name": f"{first} {last}", "face_embedding": None, "voice_embedding": None,
        "email": f"{first.lower()}.{last.lower()}{k + 1}@demo-college.invalid" if args.with_emails else None,
        "roll_no": roll, "section": sec_name,
        "parent_email": f"parent{k + 1}@demo-college.invalid" if args.with_emails else None,
        "parent_name": f"Parent of {last}", "year": year, "course": course})
students = insert_batches("students", st_rows, returning=True)
for s in students:
    s["group"], s["base"] = meta[s["roll_no"]]

by_class = {}
for s in students:
    by_class.setdefault((s["course"], s["year"], s["section"]), []).append(s)

# ---- enrolment ----
print("Enrolling students...")
enroll = [{"student_id": s["student_id"], "subject_id": sub["subject_id"]}
          for key, studs in by_class.items() for s in studs for sub in subs_by_class.get(key, [])]
insert_batches("subject_students", enroll, size=1000)

# ---- attendance + marks ----
print("Generating attendance and marks...")
wd = last_weekdays(args.sessions * 2 + 2)
logs, marks, tot, pres = [], [], {}, {}
for i, sub in enumerate(subjects):
    days = wd[(i % 2)::2][:args.sessions]
    times = [datetime.combine(d, dtime(9 + (i % 7), 0)).strftime("%Y-%m-%dT%H:%M:%S") for d in days]
    mod = rnd.uniform(-0.05, 0.05)
    for s in by_class.get((sub["course"], sub["year"], sub["section"]), []):
        got = 0
        for k, ts in enumerate(times):
            ok = rnd.random() < p_present(s["group"], s["base"], k, len(times), mod)
            got += ok
            logs.append({"student_id": s["student_id"], "subject_id": sub["subject_id"],
                         "timestamp": ts, "is_present": ok})
        sid = s["student_id"]
        tot[sid] = tot.get(sid, 0) + len(times)
        pres[sid] = pres.get(sid, 0) + got
        att = got / max(1, len(times))
        for exam, mx in EXAMS:
            frac = min(1.0, max(0.10, 0.35 + 0.55 * att + rnd.gauss(0, 0.08)))
            marks.append({"student_id": sid, "subject_id": sub["subject_id"],
                          "teacher_id": sub["teacher_id"], "marks_obtained": round(mx * frac, 1),
                          "max_marks": mx, "exam_type": exam, "remarks": None})

insert_batches("attendance_logs", logs, size=1000)
insert_batches("marks", marks, size=1000)

# ---- reference files ----
with open("seed_output/teachers.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["teacher_id", "username", "password", "name"])
    for t in teachers:
        w.writerow([t["teacher_id"], t["username"], DEMO_PASSWORD, t["name"]])
with open("seed_output/subjects.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["subject_id", "subject_code", "name", "course", "year", "section", "teacher_id"])
    for s in subjects:
        w.writerow([s["subject_id"], s["subject_code"], s["name"], s["course"], s["year"],
                    s["section"], s["teacher_id"]])
with open("seed_output/students.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["student_id", "roll_no", "name", "course", "year", "section",
                "true_group", "actual_attendance_pct", "actual_risk"])
    for s in students:
        pct = round(100 * pres[s["student_id"]] / max(1, tot[s["student_id"]]), 1)
        risk = "low" if pct >= 75 else "medium" if pct >= 50 else "high"
        w.writerow([s["student_id"], s["roll_no"], s["name"], s["course"], s["year"],
                    s["section"], s["group"], pct, risk])

print("\nDone.")
print(f"Teachers: {len(teachers)}  Subjects: {len(subjects)}  Students: {len(students)}")
print(f"Attendance rows: {len(logs)}  Marks rows: {len(marks)}")
print(f"\nTeacher logins: demo_t01 ... demo_t{len(teachers):02d}  password: {DEMO_PASSWORD}")
print("Reference files: seed_output/teachers.csv, subjects.csv, students.csv")
