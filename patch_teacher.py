import re, shutil, sys
p = "src/screens/teacher_screen.py"
src = open(p, encoding="utf-8").read()
if "run_balanced" in src:
    sys.exit("Already patched - nothing to do.")

a = "all_detected_ids = {}"
if src.count(a) != 1:
    sys.exit("Anchor 1 not found exactly once - aborting, file unchanged.")
src = src.replace(a, a + "\n                live_batch = []", 1)

pat = re.compile(
    r"detected, _, _ = predict_attendance\(img_np\)\s+if detected:\s+"
    r"for sid in detected\.keys\(\):\s+student_id = sid\s+"
    r"all_detected_ids\.setdefault\(student_id, \[\]\)\.append\(f\"Photo \{idx \+ 1\}\"\)"
)
src, n = pat.subn("live_batch.append((idx, img_np))", src, count=1)
if n != 1:
    sys.exit("Anchor 2 not found - aborting, file unchanged.")

b = "                enrolled_res = supabase.table('subject_students').select(\"*, students(*)\")"
if src.count(b) != 1:
    sys.exit("Anchor 3 not found exactly once - aborting, file unchanged.")
block = (
    "                from src.services.load_balancer import run_balanced\n"
    "                batch_results = run_balanced(lambda b: predict_attendance(b[1])[0], live_batch)\n"
    "                for (idx, _), detected in zip(live_batch, batch_results):\n"
    "                    if detected is None:\n"
    "                        st.warning(f\"Photo {idx + 1}: analysis failed. Skipped.\")\n"
    "                        continue\n"
    "                    for sid in detected.keys():\n"
    "                        all_detected_ids.setdefault(sid, []).append(f\"Photo {idx + 1}\")\n\n"
)
src = src.replace(b, block + b, 1)

shutil.copy(p, p + ".bak")
open(p, "w", encoding="utf-8").write(src)
print("Patched. Backup at", p + ".bak")
