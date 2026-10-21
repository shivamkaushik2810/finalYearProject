import math
import random
import tomllib
from datetime import datetime, timedelta

import bcrypt
from supabase import create_client

random.seed(7)
TEACHER_PASS = "Snap@Prof2026"
SESSIONS_PER_SUBJECT = 12
POOL_SIZE = {"CS": 19, "SCI": 9, "MGT": 4}   # plus demoprof inside CS
DEPT = {"B.Tech": "CS", "BCA": "CS", "MCA": "CS", "M.Tech": "CS",
        "B.Sc": "SCI", "M.Sc": "SCI", "MBA": "MGT"}
CODES = {"B.Tech": "BT", "BCA": "BC", "B.Sc": "BS", "MCA": "MC",
         "M.Tech": "MT", "MBA": "MB", "M.Sc": "MS"}
# semester index 0 = odd (current term), 1 = even (completed term)
TERM_LABEL = {0: "2026-27", 1: "2025-26"}
FIRST = """Rajesh Sunita Anil Meena Vinod Kavita Sanjay Rekha Manoj Pooja Suresh Anita Rakesh Neelam
Ashok Seema Dinesh Geeta Mukesh Shweta Ramesh Alka Naveen Poonam Pradeep Ritu Ajay Mamta Sunil Deepa
Yogesh Nisha Harish Kiran Vivek Swati Amit Preeti""".split()
LAST = """Sharma Verma Gupta Singh Tomar Chauhan Yadav Mishra Pandey Tiwari Saxena Agarwal Jain Bansal
Goyal Mittal Rana Rajput Thakur Malik Tyagi Sethi Kapoor Khan Bhatia Arora Joshi Rawat Dubey Shukla
Srivastava Dixit Baliyan Saini Nagar Kashyap""".split()

CUR_ODD = {
    "B.Tech": {1: ["Engineering Mathematics", "Engineering Physics", "Programming in C", "Basic Electrical Engineering"],
               2: ["Data Structures", "Discrete Mathematics", "Digital Electronics", "Object Oriented Programming"],
               3: ["Database Management Systems", "Operating Systems", "Computer Networks", "Design and Analysis of Algorithms"],
               4: ["Machine Learning", "Cloud Computing", "Software Engineering", "Information Security"]},
    "BCA": {1: ["Computer Fundamentals", "Programming in C", "Mathematics for Computing", "Communication Skills"],
            2: ["Data Structures", "Database Management", "Web Technologies", "Operating Systems"],
            3: ["Java Programming", "Software Engineering", "Computer Networks", "Python Programming"]},
    "B.Sc": {1: ["Chemistry Basics", "Calculus", "Mechanics", "Statistics"],
             2: ["Electronics", "Linear Algebra", "Organic Chemistry", "Thermodynamics"],
             3: ["Numerical Methods", "Research Methods", "Quantum Physics", "Data Analysis"]},
    "MCA": {1: ["Advanced Data Structures", "Advanced DBMS", "Java Programming", "Discrete Mathematics"],
            2: ["Machine Learning", "Cloud Computing", "Mobile App Development", "Big Data Analytics"]},
    "M.Tech": {1: ["Advanced Algorithms", "Research Methodology", "Soft Computing", "Advanced Computer Architecture"],
               2: ["Deep Learning", "Distributed Systems", "Cyber Security", "Dissertation Seminar"]},
    "MBA": {1: ["Principles of Management", "Managerial Economics", "Financial Accounting", "Marketing Management"],
            2: ["Strategic Management", "Business Analytics", "Human Resource Management", "Operations Management"]},
    "M.Sc": {1: ["Advanced Mathematics", "Analytical Techniques", "Research Methodology", "Computational Methods"],
             2: ["Advanced Statistics", "Project Work", "Spectroscopy", "Scientific Writing"]},
}
CUR_EVEN = {
    "B.Tech": {1: ["Engineering Chemistry", "Mathematics II", "Engineering Graphics", "Communication Skills"],
               2: ["Computer Organization", "Probability and Statistics", "Theory of Computation", "Web Technologies"],
               3: ["Compiler Design", "Artificial Intelligence", "Software Testing", "Data Mining"],
               4: ["Deep Learning", "Big Data Analytics", "Internet of Things", "Major Project"]},
    "BCA": {1: ["Digital Logic", "Business Mathematics", "C++ Programming", "Environmental Studies"],
            2: ["Computer Architecture", "Software Engineering Basics", "Computer Graphics", "Statistics for Computing"],
            3: ["Android Development", "Data Mining", "Cyber Security", "Project Work"]},
    "B.Sc": {1: ["Organic Chemistry Basics", "Differential Equations", "Waves and Optics", "Probability"],
             2: ["Analog Electronics", "Real Analysis", "Physical Chemistry", "Electromagnetism"],
             3: ["Nuclear Physics", "Project Work", "Advanced Statistics", "Scientific Computing"]},
    "MCA": {1: ["Operating Systems", "Computer Networks", "Python Programming", "Software Engineering"],
            2: ["Information Security", "Data Science", "Dissertation", "Internet of Things"]},
    "M.Tech": {1: ["Advanced Operating Systems", "Machine Learning", "Data Mining", "Seminar"],
               2: ["Dissertation Phase I", "Natural Language Processing", "Blockchain Technology", "Computer Vision"]},
    "MBA": {1: ["Organizational Behaviour", "Business Statistics", "Corporate Finance", "Business Communication"],
            2: ["Entrepreneurship", "International Business", "Supply Chain Management", "Project Report"]},
    "M.Sc": {1: ["Numerical Analysis", "Advanced Instrumentation", "Data Analysis", "Seminar"],
             2: ["Dissertation", "Nanoscience", "Environmental Science", "Research Seminar"]},
}
CURRICULA = (CUR_ODD, CUR_EVEN)

c = tomllib.load(open(".streamlit/secrets.toml", "rb"))
sb = create_client(c["SUPABASE_URL"], c["SUPABASE_KEY"])


def insert_chunks(table, rows, size=1000):
    out = []
    for i in range(0, len(rows), size):
        res = sb.table(table).insert(rows[i:i + size]).execute()
        out.extend(res.data or [])
        print(f"  {table}: {min(i + size, len(rows))}/{len(rows)}")
    return out


def tid_of(t):
    return t["teacher_id"] if "teacher_id" in t else t["id"]


def weekdays_between(a, b):
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ---------------- teachers ----------------
hashed = bcrypt.hashpw(TEACHER_PASS.encode(), bcrypt.gensalt()).decode()
specs = [("demoprof", "Demo Professor", "CS")]
used = {"demoprof"}
for dept, n in POOL_SIZE.items():
    made = 0
    while made < n:
        f, l = random.choice(FIRST), random.choice(LAST)
        uname = f"prof.{l.lower()}" if f"prof.{l.lower()}" not in used else f"prof.{f.lower()}.{l.lower()}"
        if uname in used:
            continue
        used.add(uname)
        specs.append((uname, f"Prof. {f} {l}", dept))
        made += 1

existing = {t["username"] for t in sb.table("teachers").select("username")
            .in_("username", [s[0] for s in specs]).execute().data}
new_rows = [{"username": u, "password": hashed, "name": n,
             "email": f"{u}@example.com"} for u, n, d in specs if u not in existing]
if new_rows:
    try:
        sb.table("teachers").insert(new_rows).execute()
    except Exception as e:
        print("insert with email failed, retrying without:", str(e)[:100])
        sb.table("teachers").insert([{k: v for k, v in r.items() if k != "email"} for r in new_rows]).execute()
sb.table("teachers").update({"password": hashed}).eq("username", "demoprof").execute()
try:
    sb.table("teachers").update({"status": "approved"}).in_("username", [s[0] for s in specs]).execute()
except Exception:
    print("(no 'status' column on teachers - skipped approval)")

trows = sb.table("teachers").select("*").in_("username", [s[0] for s in specs]).execute().data
by_user = {t["username"]: tid_of(t) for t in trows}
pools = {}
for u, n, d in specs:
    pools.setdefault(d, []).append(u)
print(f"Teachers ready: {len(specs)} (password for all: {TEACHER_PASS})")

if sb.table("subjects").select("subject_id", count="exact").in_("teacher_id", list(by_user.values())).limit(1).execute().count:
    print("Demo teachers already have subjects. Run the cleanup SQL first. Aborting.")
    raise SystemExit

# ---------------- students ----------------
students, start = [], 0
while True:
    b = sb.table("students").select("student_id,course,year,section").range(start, start + 999).execute().data
    students.extend(b)
    if len(b) < 1000:
        break
    start += 1000
print("students loaded:", len(students))
groups = {}
for s in students:
    if s.get("course") in CODES and s.get("year") and s.get("section"):
        groups.setdefault((s["course"], str(s["year"]), s["section"]), []).append(s["student_id"])

# ---------------- subjects (two semesters per class) + workload split ----------------
subject_defs = []   # (course, year, sec, sem_idx, i, name)
for (course, year, sec), ids in groups.items():
    for sem_idx in (0, 1):
        for i, nm in enumerate(CURRICULA[sem_idx].get(course, {}).get(int(year), [])):
            subject_defs.append((course, year, sec, sem_idx, i, nm))
subject_defs.sort(key=lambda d: (DEPT[d[0]], d[5], d[0], d[1], d[2], d[3]))


def code_of(course, year, sec, sem_idx, i):
    return f"{CODES[course]}{year}{sec}{sem_idx + 1}{i + 1:02d}"


per_dept = {}
for d in subject_defs:
    per_dept[DEPT[d[0]]] = per_dept.get(DEPT[d[0]], 0) + 1
load = {u: 0 for u in by_user}
name_owner, assign = {}, {}
for course, year, sec, sem_idx, i, nm in subject_defs:
    dept = DEPT[course]
    pool = pools[dept]
    cap = math.ceil(per_dept[dept] / len(pool)) + 1
    pref = [u for u in name_owner.get((dept, nm), []) if load[u] < cap]
    pick = min(pref, key=lambda u: load[u]) if pref else min(pool, key=lambda u: load[u])
    assign[code_of(course, year, sec, sem_idx, i)] = pick
    load[pick] += 1
    owners = name_owner.setdefault((dept, nm), [])
    if pick not in owners:
        owners.append(pick)


def mk_rows(year_int, sem_text):
    rows = []
    for course, year, sec, sem_idx, i, nm in subject_defs:
        code = code_of(course, year, sec, sem_idx, i)
        sem = int(year) * 2 - 1 + sem_idx
        rows.append({"subject_code": code, "name": nm, "section": sec,
                     "teacher_id": by_user[assign[code]], "course": course,
                     "year": int(year) if year_int else str(year),
                     "academic_year": TERM_LABEL[sem_idx],
                     "semester": str(sem) if sem_text else sem})
    return rows


created = None
for year_int, sem_text in ((False, False), (True, False), (False, True)):
    try:
        created = insert_chunks("subjects", mk_rows(year_int, sem_text), 200)
        break
    except Exception as e:
        print("subjects insert failed:", str(e)[:150])
if created is None:
    raise SystemExit("Could not insert subjects - paste the error above.")
code_to_sub = {r["subject_code"]: r for r in created}
print("subjects created:", len(created))

# ---------------- enrolment, attendance, marks ----------------
habit = {}
for s in students:
    r = random.random()
    habit[s["student_id"]] = (random.uniform(0.78, 0.96) if r < 0.70 else
                              random.uniform(0.55, 0.78) if r < 0.90 else random.uniform(0.30, 0.55))

today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
term_days = {
    0: weekdays_between(datetime(2026, 7, 27), today - timedelta(days=1)),   # current term
    1: weekdays_between(datetime(2026, 1, 12), datetime(2026, 5, 15)),       # completed term
}
term_exams = {0: (("Internal", 30),),
              1: (("Internal", 30), ("Mid Term", 50), ("End Term", 100))}

enrol, logs, marks = [], [], []
for course, year, sec, sem_idx, i, nm in subject_defs:
    sub = code_to_sub[code_of(course, year, sec, sem_idx, i)]
    sid, teacher_id = sub["subject_id"], sub["teacher_id"]
    dates = sorted(random.sample(term_days[sem_idx], SESSIONS_PER_SUBJECT))
    for stu in groups[(course, year, sec)]:
        enrol.append({"student_id": stu, "subject_id": sid})
        for d in dates:
            ts = (d + timedelta(hours=9 + i)).strftime("%Y-%m-%dT%H:%M:%S")
            logs.append({"student_id": stu, "subject_id": sid, "timestamp": ts,
                         "is_present": random.random() < habit[stu]})
        for et, mx in term_exams[sem_idx]:
            got = max(0, min(mx, round(mx * (0.35 + 0.6 * habit[stu] + random.uniform(-0.12, 0.12)), 1)))
            marks.append({"student_id": stu, "subject_id": sid, "teacher_id": teacher_id,
                          "exam_type": et, "marks_obtained": got, "max_marks": mx, "remarks": None})

print("enrolling...");  insert_chunks("subject_students", enrol)
print("attendance..."); insert_chunks("attendance_logs", logs)
print("marks...");      insert_chunks("marks", marks)

print(f"\nDone. Subjects {len(created)}, enrolments {len(enrol)}, logs {len(logs)}, marks {len(marks)}")
print("\nWorkload (subjects per teacher):")
for d, users in pools.items():
    print(f"  [{d}] " + ", ".join(f"{u}:{load[u]}" for u in users))
