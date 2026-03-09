#!/usr/bin/env bash
# Run from project root: bash scripts/run_orchestrator.sh [--dry-run]
cd "$(dirname "$0")/.."
export PYTHONPATH=.
python3 -m src.orchestrator.run "$@"
