#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ $# -lt 1 ]]; then
    echo "Usage: bash scripts/run_benchmark.sh PHOTO_DIRECTORY"
    exit 1
fi

PHOTO_DIR="$1"

if [[ ! -d "$PHOTO_DIR" ]]; then
    echo "ERROR: Photo directory does not exist:"
    echo "$PHOTO_DIR"
    exit 1
fi

if [[ ! -f "scripts/benchmark_scan.py" ]]; then
    echo "ERROR: benchmark_scan.py not found."
    exit 1
fi

if [[ ! -f "src/services/load_balancer.py" ]]; then
    echo "ERROR: load_balancer.py not found."
    exit 1
fi

if [[ ! -f "src/pipelines/face_pipeline.py" ]]; then
    echo "ERROR: face_pipeline.py not found."
    exit 1
fi

export SCAN_CONCURRENCY=4

echo "=================================="
echo "SNAPCLASS FACE SCAN BENCHMARK"
echo "=================================="

echo ""
echo "== Sequential benchmark"
python scripts/benchmark_scan.py "$PHOTO_DIR" --workers 0

echo ""
echo "== Balanced benchmark: 2 workers"
python scripts/benchmark_scan.py "$PHOTO_DIR" --workers 2

echo ""
echo "== Balanced benchmark: 4 workers"
python scripts/benchmark_scan.py "$PHOTO_DIR" --workers 4

echo ""
echo "ALL BENCHMARKS COMPLETED"
