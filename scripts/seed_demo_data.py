"""
Seed SnapClass with ~2000 fully-populated demo students.
Everything is filled except email / parent_email (left NULL on purpose,
so no fake address ever receives OTP or weekly-report mail).

Run AFTER the SQL wipe:   python scripts/seed_demo_data.py
Optional env vars: TARGET_STUDENTS=2000 SESSIONS=10 WITH_EMBEDDINGS=1
"""
import os, random, tomllib
from datetime import datetime, timedelta
from supabase import create_client

random.seed(42)
TARGET_STUDENTS = int(os.getenv("TARGET_STUDENTS", 2000))
SESSIONS        = int(os.getenv("SESSIONS", 10))
WITH_EMBEDDINGS = os.getenv("WITH_EMBEDDINGS") == "1"

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)
sb = create_client(secrets["SUPABASE_URL"], secrets["SUPABASE_KEY"])

# ── Data pools ────────────────────────────────────────────────
FIRST = ["Aarav","Vivaan","Aditya","Arjun","Rohan","Karan","Nikhil","Shivam","Rahul","Amit",
         "Saurabh","Ankit","Harsh","Yash","Manish","Deepak","Vikas","Sumit","Pankaj","Mohit",
         "Ananya","Priya","Neha","Sneha","Pooja","Riya","Kavya","Isha","Nisha","Shreya",
         "Divya","Anjali","Meera","Tanvi","Simran","Aditi","Komal","Sakshi","Muskan","Khushi"]
LAST  = ["Sharma","Verma","Gupta","Singh","Kumar","Yadav","Tomar","Kaushik","Mishra","Pandey",
         "Tiwari","Chauhan","Rawat","Saini","Jain","Agarwal","Bansal","Malik","Thakur","Joshi",
         "Rana","Chaudhary","Bhatia","Kapoor","Mehta","Nagar","Goyal","Garg","Dubey","Srivastava"]
FATHER = ["Rajesh","Sunil","Anil","Mahesh","Suresh","Ramesh","Vinod","Dinesh","Sanjay","Manoj",
          "Ashok","Rakesh","Naresh","Vijay","Pramod"]

SUBJECTS = {
 "B.Tech": {1:["Engineering Mathematics","Engineering Physics","Programming in C","Basic Electrical Engineering"],
            2:["Data Structures","Database Management Systems","Operating Systems","Discrete Mathematics"],
            3:["Machine Learning","Computer Networks","Software Engineering","Theory of Computation"],
            4:["Deep Learning","Cloud Computing","Cyber Security","Project Management"]},
 "BCA":    {1:["Computer Fundamentals","Programming in C","Business Communication","Mathematics for Computing"],
            2:["Data Structures","Java Programming","Database Systems","Web Technologies"],
            3:["Python Programming","Software Engineering","Computer Networks","Cloud Basics"]},
 "B.Sc":   {1:["Calculus","Physics Fundamentals","Chemistry Basics","Statistics"],
            2:["Linear Algebra","Electronics","Organic Chemistry","Probability"],
            3:["Numerical Methods","Quantum Physics","Data Analysis","Research Methods"]},
 "MCA":    {1:["Advanced Algorithms","Advanced DBMS","Operating Systems","Software Architecture"],
            2:["Machine Learning","Big Data Analytics","Information Security","Mobile Computing"]},
 "MBA":    {1:["Managerial Economics","Financial Accounting","Marketing Management","Organizational Behaviour"],
            2:["Strategic Management","Business Analytics","Operations Management","Corporate Finance"]},
 "M.Tech": {1:["Advanced Data Structures","Soft Computing","Research Methodology","Advanced Computer Architecture"],
            2:["Natural Language Processing","Computer Vision","Distributed Systems","Reinforcement Learning"]},
 "M.Sc":   {1:["Advanced Calculus","Statistical Inference","Mathematical Modelling","Scientific Computing"],
            2:["Optimization Techniques","Stochastic Processes","Data Mining","Dissertation Seminar"]},
}
COURSE_META = {  # share of students, sections, short code
 "B.Tech": (0.46, "ABCDEF", "BT"), "BCA": (0.14, "AB", "BC"), "B.Sc": (0.08, "AB", "BS"),
 "MCA": (0.12, "AB", "MC"), "MBA": (0.10, "AB", "MB"), "M.Tech": (0.05, "AB", "MT"), "M.Sc": (0.05, "AB", "MS"),
}
EXAMS = [("Internal", 50), ("Mid Term", 100), ("Assignment", 20)]

groups, weights = [], []
for course, (share, sections, _) in COURSE_META.items():
    years = list(SUBJECTS[course].keys())
    n = len(years) * len(sections)
    for y in years:
        for s in sections:
            groups.append((course, y, s)); weights.append(share / n)

# ── Helpers ───────────────────────────────────────────────────
def insert_batches(table, rows, size=500, optional=()):
    out, opt = [], list(optional)
    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        try:
            res = sb.table(table).insert(chunk).execute()
        except Exception as e:
            if not opt:
                raise
            print(f"  {table}: retrying without {opt} ({str(e)[:90]})")
            rows = [{k: v for k, v in r.items() if k not in opt} for r in rows]
            opt = []
            res = sb.table(table).insert(rows[i:i + size]).execute()
        out.extend(res.data or [])
        print(f"  {table}: {len(out)}/{len(rows)}", end="\r")
    print()
    return out

def rand_unit(dim, std):
    v = [random.gauss(0, std) for _ in range(dim)]
    return [round(x, 6) for x in v]

def pick_sessions(n):
    days, d = [], datetime.now().date() - timedelta(days=1)
    while len(days) < 40:                       # last ~8 weeks of weekdays
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.sort()
    idx = sorted({round(k * (len(days) - 1) / max(n - 1, 1)) for k in range(n)})
    return [days[i] for i in idx]

# ── Safety checks ─────────────────────────────────────────────
for fname in ("model.pkl", "learning_log.txt"):
    if os.path.exists(fname):
        os.remove(fname); print(f"Removed old {fname}")

existing = sb.table("students").select("student_id", count="exact").limit(1).execute()
if (existing.count or 0) > 0:
    raise SystemExit("students table is not empty - run the SQL wipe first.")

teachers = sb.table("teachers").select("teacher_id, name").execute().data or []
if not teachers:
    raise SystemExit("No teachers found - register a teacher in the app first.")
print(f"Using {len(teachers)} existing teacher(s) for subjects")

# ── 1. Students ───────────────────────────────────────────────
this_year = datetime.now().year
counters, student_rows, meta = {}, [], {}
for _ in range(TARGET_STUDENTS):
    course, year, section = random.choices(groups, weights)[0]
    cidx = list(COURSE_META).index(course) + 1
    counters[(course, year)] = counters.get((course, year), 0) + 1
    adm = (this_year - year + 1) % 100
    roll = f"{adm:02d}02311{cidx:02d}{counters[(course, year)]:04d}"
    last = random.choice(LAST)
    name = f"{random.choice(FIRST)} {last}"
    p = random.random()
    prop = random.uniform(0.75, 0.97) if p < 0.70 else random.uniform(0.50, 0.75) if p < 0.88 else random.uniform(0.20, 0.50)
    student_rows.append({
        "name": name, "roll_no": roll, "section": section, "year": str(year), "course": course,
        "parent_name": f"{random.choice(FATHER)} {last}",
        "email": None, "parent_email": None,
        "face_embedding":  rand_unit(128, 0.09) if WITH_EMBEDDINGS else None,
        "voice_embedding": rand_unit(256, 0.0625) if WITH_EMBEDDINGS else None,
    })
    meta[roll] = {"group": (course, year, section), "prop": prop}

print(f"Inserting {len(student_rows)} students...")
inserted = insert_batches("students", student_rows)
students = [{"student_id": r["student_id"], **meta[r["roll_no"]]} for r in inserted]

# ── 2. Subjects (4 per course/year/section group) ─────────────
used_groups = sorted({s["group"] for s in students})
subject_rows, t_i = [], 0
for course, year, section in used_groups:
    code = COURSE_META[course][2]
    for n, sname in enumerate(SUBJECTS[course][year], start=1):
        subject_rows.append({
            "subject_code": f"{code}{year}{section}{n:02d}", "name": sname, "section": section,
            "teacher_id": teachers[t_i % len(teachers)]["teacher_id"],
            "year": str(year), "course": course,
        })
        t_i += 1
print(f"Inserting {len(subject_rows)} subjects...")
sub_out = insert_batches("subjects", subject_rows, optional=("year", "course"))
sub_by_group = {}
for r in sub_out:
    course = next(c for c, v in COURSE_META.items() if r["subject_code"].startswith(v[2]))
    key = (course, int(r["subject_code"][2]), r["section"])
    sub_by_group.setdefault(key, []).append(r)

# ── 3. Enrollments ────────────────────────────────────────────
enroll_rows = [{"student_id": s["student_id"], "subject_id": sub["subject_id"]}
               for s in students for sub in sub_by_group[s["group"]]]
print(f"Enrolling ({len(enroll_rows)} enrollments)...")
insert_batches("subject_students", enroll_rows)

# ── 4. Attendance logs ────────────────────────────────────────
days = pick_sessions(SESSIONS)
att_rows, marks_rows = [], []
for key, subs in sub_by_group.items():
    for si, sub in enumerate(subs):
        hour = [9, 10, 11, 12, 14, 15][(si + hash(sub["subject_code"])) % 6]
        stamps = [datetime(d.year, d.month, d.day, hour, random.randint(0, 10), 0).strftime("%Y-%m-%dT%H:%M:%S")
                  for d in days]
        for s in (x for x in students if x["group"] == key):
            p = min(0.99, max(0.1, s["prop"] + random.gauss(0, 0.05)))
            for ts in stamps:
                present = random.random() < p
                att_rows.append({
                    "student_id": s["student_id"], "subject_id": sub["subject_id"],
                    "timestamp": ts, "is_present": present,
                    "confidence_score": round(random.uniform(0.72, 0.98), 2) if present else 0.0,
                })
            for exam, mx in EXAMS:                      # ── marks
                pct = min(100, max(5, 30 + 60 * p + random.gauss(0, 8)))
                got = round(mx * pct / 100, 1)
                remark = "Excellent performance" if pct >= 75 else "Satisfactory" if pct >= 50 else "Needs improvement"
                marks_rows.append({
                    "student_id": s["student_id"], "subject_id": sub["subject_id"],
                    "teacher_id": sub["teacher_id"], "marks_obtained": got,
                    "max_marks": mx, "exam_type": exam, "remarks": remark,
                })

print(f"Inserting {len(att_rows)} attendance rows...")
insert_batches("attendance_logs", att_rows, size=1000, optional=("confidence_score",))
print(f"Inserting {len(marks_rows)} marks rows...")
insert_batches("marks", marks_rows, size=1000)

print(f"\nDone: {len(students)} students, {len(subject_rows)} subjects, "
      f"{len(enroll_rows)} enrollments, {len(att_rows)} attendance rows, {len(marks_rows)} marks.")
