"""Load pipeline config from config/domains.yaml (prompt counts, monitor limit)."""
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "domains.yaml"

DEFAULTS = {
    "prompt_generation": {
        "prompts_per_domain": 50,
        "prompt_count_total": 100,
    },
    "monitor": {
        "limit": 50,
    },
}


def get_pipeline_config() -> dict:
    """Load config from config/domains.yaml. Returns merged dict with defaults for prompt_generation and monitor."""
    result = {
        "prompt_generation": dict(DEFAULTS["prompt_generation"]),
        "monitor": dict(DEFAULTS["monitor"]),
    }
    if not CONFIG_PATH.exists():
        return result
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        if "prompt_generation" in data and isinstance(data["prompt_generation"], dict):
            result["prompt_generation"].update(data["prompt_generation"])
        if "monitor" in data and isinstance(data["monitor"], dict):
            result["monitor"].update(data["monitor"])
    except Exception:
        pass
    return result


def get_prompts_per_domain() -> int:
    return get_pipeline_config()["prompt_generation"].get("prompts_per_domain", DEFAULTS["prompt_generation"]["prompts_per_domain"])


def get_prompt_count_total() -> int:
    return get_pipeline_config()["prompt_generation"].get("prompt_count_total", DEFAULTS["prompt_generation"]["prompt_count_total"])


def get_monitor_limit() -> int:
    return get_pipeline_config()["monitor"].get("limit", DEFAULTS["monitor"]["limit"])
