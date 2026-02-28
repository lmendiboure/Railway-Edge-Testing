#!/usr/bin/env bash
set -euo pipefail

MANIFEST=${MANIFEST:-configs/paper_manifest.json}
OUTPUT=${OUTPUT:-runs_paper_v3}
PYTHON=${PYTHON:-python3}

JOBS_HIGH=${JOBS_HIGH:-3}
JOBS_MED=${JOBS_MED:-4}
JOBS_LOW=${JOBS_LOW:-6}

run_group() {
  local jobs=$1
  shift
  printf "%s\n" "$@" | xargs -n1 -P"${jobs}" -I{} "$PYTHON" -m scripts.run --manifest "$MANIFEST" --output "$OUTPUT" --only {}
}

echo "Running high-load runs with JOBS_HIGH=${JOBS_HIGH}"
run_group "$JOBS_HIGH" P1-D P1-E

echo "Running medium-load runs with JOBS_MED=${JOBS_MED}"
run_group "$JOBS_MED" P2-A P2-B P2-C P2-D P2-E P2-F P2-G P3-B P3-C P3-D

echo "Running low-load runs with JOBS_LOW=${JOBS_LOW}"
run_group "$JOBS_LOW" P1-A P1-B P1-C
