#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "== compile"
python -m py_compile src/services/load_balancer.py tests/test_load_balancer.py scripts/benchmark_scan.py

echo "== balancer tests"
python -m pytest -q tests/test_load_balancer.py

echo "== full existing suite"
python -m pytest -q

echo "ALL CHECKS PASSED"
