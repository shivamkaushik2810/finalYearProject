#!/usr/bin/env bash
echo "--- where face_pipeline.py exists on this Mac"
find ~ -name face_pipeline.py -not -path "*/.venv/*" -not -path "*/node_modules/*" 2>/dev/null | head
echo "--- git root and branches"
git rev-parse --show-toplevel
git remote -v
git branch -a | head -20
echo "--- do the tarballs contain the real source?"
for t in snapclass-before-cleanup.tar.gz snapclass-before-graph-fixes.tar.gz; do
  echo "$t:"
  tar tzf "$t" 2>/dev/null | grep -E "face_pipeline|teacher_screen|leave_ui" | head -5
done
echo "--- files under src here"
find src -maxdepth 2 -type f -not -name "*.pyc" | sort | head -60
