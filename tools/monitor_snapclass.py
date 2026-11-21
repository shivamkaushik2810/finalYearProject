import cProfile
import os
import pstats
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
LOGS = ROOT / "performance_logs"
LOGS.mkdir(exist_ok=True)

print("=" * 60)
print(" SNAPCLASS PERFORMANCE MONITOR")
print("=" * 60)

if not (ROOT / "app.py").exists():
    print("ERROR: app.py not found. Run from your project root.")
    raise SystemExit(1)

print("\n[1/3] Measuring Python import times...")
import_log = LOGS / "import_times.log"

cmd = [
    sys.executable, "-X", "importtime",
    "-m", "streamlit", "run", "app.py",
    "--server.port", "8502",
    "--server.headless", "true",
]

start = time.perf_counter()

with import_log.open("w") as log:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        for line in process.stdout:
            print(line, end="")
            log.write(line)
            log.flush()

            if "You can now view your Streamlit app" in line:
                print(
                    f"\nStartup marker detected: "
                    f"{time.perf_counter() - start:.2f}s"
                )
    except KeyboardInterrupt:
        print("\nStopping Streamlit...")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

print("\n[2/3] Analyzing import times...")
text = import_log.read_text(errors="ignore").splitlines()

matches = [
    line for line in text
    if "import time:" in line
    and any(
        name in line.lower()
        for name in (
            "streamlit", "cv2", "face_recognition",
            "tensorflow", "torch", "supabase", "src."
        )
    )
]

(LOGS / "important_imports.txt").write_text(
    "\n".join(matches) + "\n"
)

for line in matches[-50:]:
    print(line)

print("\n[3/3] Reports saved:")
print("Import log:", import_log)
print("Filtered imports:", LOGS / "important_imports.txt")
print("\nTo inspect the full log:")
print("less performance_logs/import_times.log")
