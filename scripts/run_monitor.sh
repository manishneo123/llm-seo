#!/usr/bin/env bash
# Run from project root: ./scripts/run_monitor.sh
cd "$(dirname "$0")/.."
export PYTHONPATH=.
python3 -m src.monitor.run_monitor "$@"
