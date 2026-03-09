#!/usr/bin/env bash
# Run Phase B learning job: collect success data, generate hints via LLM, write config/learning_hints.yaml
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.
python3 -m src.learning.run_learning
