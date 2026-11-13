#!/usr/bin/env bash
echo "--- branch and changed files"
git branch --show-current
git status --short
echo "--- src/pipelines contents"
ls src/pipelines 2>&1 | head -40
echo "--- where predict_attendance is defined"
grep -rn "def predict_attendance" src || echo "not found under src"
echo "--- files my scripts import (MISSING means the app would fail on import)"
for p in src/database/config.py src/database/db.py \
  src/pipelines/face_pipeline.py src/pipelines/image_quality.py \
  src/pipelines/liveness_detection.py src/pipelines/voice_pipeline.py \
  src/components/ai_insights.py src/components/dialog_add_photo.py \
  src/components/dialog_create_subject.py src/components/dialog_share_subject.py \
  src/components/dialog_enroll.py src/components/marks_management.py \
  src/components/self_learning_ui.py src/components/footer.py \
  src/services/otp_service.py src/services/scheduler.py; do
  if [ -f "$p" ]; then echo "ok       $p"; else echo "MISSING  $p"; fi
done
echo "--- what tests/test_ui.py imports"
sed -n 25,40p tests/test_ui.py
echo "--- history of that test file"
git log --oneline -3 -- tests/test_ui.py
echo "--- components folder"
ls src/components | head -60
