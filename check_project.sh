#!/bin/bash

set -u

ROOT="$(pwd)"
REPORT="$ROOT/project_error_report.txt"

echo "=========================================="
echo "       SNAPCLASS PROJECT ERROR CHECK"
echo "=========================================="

if [ ! -f "$ROOT/app.py" ]; then
    echo "ERROR: app.py not found. Open the project root first."
    exit 1
fi

if [ -f "$ROOT/.venv/bin/activate" ]; then
    source "$ROOT/.venv/bin/activate"
fi

echo "Project: $ROOT"
echo "Report:  $REPORT"

{
    echo "SNAPCLASS ERROR REPORT"
    echo "Date: $(date)"
    echo "Project: $ROOT"
    echo ""

    echo "========== 1. PYTHON SYNTAX CHECK =========="

    python - <<'PY'
from pathlib import Path
import ast

root = Path.cwd()
errors = 0
skipped = {".venv", "venv", "__pycache__", ".git"}

for file in root.rglob("*.py"):
    if any(part in skipped for part in file.parts):
        continue

    try:
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    except SyntaxError as e:
        errors += 1
        print(f"\nSYNTAX ERROR: {file}")
        print(f"Line: {e.lineno}, Column: {e.offset}")
        print(f"Reason: {e.msg}")
    except (OSError, UnicodeDecodeError) as e:
        print(f"\nFILE READ ERROR: {file}: {e}")

print(f"\nTotal Python syntax errors: {errors}")
if errors == 0:
    print("No Python syntax errors found.")
PY

    echo ""
    echo "========== 2. DEPENDENCY CHECK =========="

    python -m pip check
    echo "pip check exit code: $?"

    echo ""
    echo "========== 3. TEST SUITE =========="

    if [ -f "$ROOT/tests/run_full_test.py" ]; then
        python tests/run_full_test.py \
            --skip-ui --skip-perf --cleanup
        echo "Test suite exit code: $?"
    else
        echo "Test runner not found: tests/run_full_test.py"
    fi

    echo ""
    echo "========== 4. ANALYTICS CODE LOCATIONS =========="

    grep -R -n --include="*.py" \
        --exclude-dir=.venv \
        --exclude-dir=__pycache__ \
        -E 'float\(|pd\.NA|pct|fillna' \
        "$ROOT/src" "$ROOT/tests" "$ROOT/app.py" 2>/dev/null \
        || echo "No matching analytics code found."

} 2>&1 | tee "$REPORT"

echo ""
echo "=========================================="
echo "CHECK FINISHED"
echo "Report saved to: $REPORT"
echo "=========================================="
