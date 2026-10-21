import random
import tomllib
from supabase import create_client

random.seed(42)
TOTAL = 2000
CURRENT_YEAR = 2026

MALE = """Aarav Aditya Akash Amit Ankit Arjun Ashish Deepak Gaurav Harsh Himanshu Ishaan Karan Kunal
Lakshay Manish Mohit Naveen Nikhil Pankaj Piyush Pranav Rahul Rajat Rohan Sachin Sahil Sandeep Shivam
Siddharth Sumit Tanmay Utkarsh Vaibhav Varun Vikas Vikram Vishal Yash Abhishek Anuj Chirag Dhruv Mayank
Nitin Parth Raghav Saurabh Tushar Kartik Vivek Ayush Devansh Lokesh Mukul Prateek Rishabh Shubham""".split()
FEMALE = """Aanya Aditi Akanksha Ananya Anjali Anushka Archana Bhavya Chhavi Diya Divya Garima Isha Jyoti
Kajal Kavya Khushi Kritika Megha Mansi Muskan Neha Nidhi Nisha Pooja Prachi Pragya Priya Priyanka
Riya Rashi Ritika Sakshi Sanya Shreya Shruti Simran Sneha Srishti Swati Tanvi Tanya Vani Vidhi Afsha Ayesha Zoya Charu""".split()
SURNAMES = """Sharma Verma Gupta Singh Kumar Tomar Chauhan Yadav Mishra Pandey Tiwari Saxena Agarwal Jain
Bansal Goyal Mittal Kaushik Rana Rajput Thakur Malik Choudhary Tyagi Sethi Kapoor Khan Ansari Siddiqui
Ishtiyaq Qureshi Naqvi Bhatia Arora Chopra Mehra Joshi Bisht Rawat Negi Dubey Shukla Srivastava Dixit
Pal Baliyan Dahiya Panwar Kashyap Prajapati Saini Kumari Nagar""".split()

# course: (years, roll code, weight)
COURSES = {
    "B.Tech": (4, "BT", 40), "BCA": (3, "BC", 12), "B.Sc": (3, "BS", 14),
    "MCA": (2, "MC", 10), "M.Tech": (2, "MT", 6), "MBA": (2, "MB", 10), "M.Sc": (2, "MS", 8),
}
SECTIONS = ["A", "B", "C", "D", "E", "F"]

course_names = list(COURSES)
weights = [COURSES[c][2] for c in course_names]

rows, serial_by_key = [], {}
for i in range(1, TOTAL + 1):
    course = random.choices(course_names, weights)[0]
    years, code, _ = COURSES[course]
    year = random.randint(1, years)
    admit = CURRENT_YEAR - (year - 1)
    key = (admit, code)
    serial_by_key[key] = serial_by_key.get(key, 0) + 1
    roll_no = f"{str(admit)[2:]}{code}{serial_by_key[key]:04d}"

    female = random.random() < 0.42
    first = random.choice(FEMALE if female else MALE)
    surname = random.choice(SURNAMES)
    father = random.choice(MALE)
    mother = random.choice(FEMALE)
    parent_first = father if random.random() < 0.7 else mother

    rows.append({
        "name": f"{first} {surname}",
        "email": f"{first.lower()}.{surname.lower()}{i}@example.com",
        "roll_no": roll_no,
        "section": random.choice(SECTIONS),
        "course": course,
        "year": str(year),
        "parent_name": f"{parent_first} {surname}",
        "parent_email": f"{parent_first.lower()}.{surname.lower()}{i}@example.com",
        "face_embedding": None,
        "voice_embedding": None,
    })

c = tomllib.load(open(".streamlit/secrets.toml", "rb"))
sb = create_client(c["SUPABASE_URL"], c["SUPABASE_KEY"])

existing = sb.table("students").select("student_id", count="exact") \
    .like("email", "%@example.com").limit(1).execute().count
if existing:
    print(f"Already {existing} demo students present. Delete them first (see cleanup SQL). Aborting.")
    raise SystemExit

done = 0
for start in range(0, len(rows), 250):
    batch = rows[start:start + 250]
    sb.table("students").insert(batch).execute()
    done += len(batch)
    print(f"inserted {done}/{len(rows)}")
print("Done.")
