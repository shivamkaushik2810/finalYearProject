import os
import sys
from pathlib import Path

# no file watchers outside `streamlit run` (they can hang on secrets.toml)
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.weekly_report_runner import send_weekly_reports_to_all_parents

if __name__ == "__main__":
    ok, failed = send_weekly_reports_to_all_parents(force=False)
    print(f"Result -> success: {ok}, failed: {failed}")
    sys.exit(1 if failed and not ok else 0)   # red run in GitHub if everything failed
