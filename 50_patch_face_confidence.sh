#!/usr/bin/env bash
set -euo pipefail
python3 - << 'PY'
p = "src/pipelines/face_pipeline.py"
s = open(p).read()
old = """                    detected[final_match] = True
                    all_ids.append(final_match)
                    confidence = round(1 - final_dist, 2)
"""
new = """                    confidence = round(1 - final_dist, 2)
                    detected[final_match] = max(float(detected.get(final_match) or 0), confidence)
                    all_ids.append(final_match)
"""
if new in s:
    print("already patched")
elif old not in s:
    raise SystemExit("Anchor not found: your face_pipeline.py differs. Nothing changed.")
else:
    open(p + ".bak", "w").write(s)
    open(p, "w").write(s.replace(old, new, 1))
    print("patched", p, "(backup at", p + ".bak)")
PY
