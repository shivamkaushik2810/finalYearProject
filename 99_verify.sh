#!/usr/bin/env bash
set -euo pipefail
python3 -m compileall -q src tests
PYTHONPATH=. python3 -m unittest discover -s tests -v
echo "Now run: streamlit run app.py and walk through the checklist."
