#!/usr/bin/env bash
# Run from project root: ./scripts/run_api.sh
cd "$(dirname "$0")/.."
export PYTHONPATH=.
uvicorn api.main:app --reload --port 8000
