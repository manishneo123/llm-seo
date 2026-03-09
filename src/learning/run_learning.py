"""Run the learning job: collect success data, generate hints via LLM, write config/learning_hints.yaml."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from src.learning.collect import collect_all_for_hints
from src.learning.hints import generate_hints


def run_learning_job(hints_path: Path | None = None) -> dict:
    """Collect data, call LLM for hints, write YAML. Returns the hints dict."""
    data = collect_all_for_hints()
    hints = generate_hints(data["summary"])
    if hints_path is None:
        hints_path = Path(__file__).resolve().parents[2] / "config" / "learning_hints.yaml"
    hints_path.parent.mkdir(parents=True, exist_ok=True)
    with open(hints_path, "w") as f:
        yaml.safe_dump(hints, f, default_flow_style=False, allow_unicode=True)
    return hints


if __name__ == "__main__":
    p = Path(__file__).resolve().parents[2] / "config" / "learning_hints.yaml"
    run_learning_job(hints_path=p)
    print("Learning hints written to", p)
