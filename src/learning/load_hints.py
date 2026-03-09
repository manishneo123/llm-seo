"""Load learning hints from config/learning_hints.yaml (written by the learning job)."""
from pathlib import Path


def load_learning_hints() -> dict | None:
    """Load config/learning_hints.yaml. Returns dict with prompt_gen_hints, brief_gen_system_extra, channel_weights or None."""
    path = Path(__file__).resolve().parents[2] / "config" / "learning_hints.yaml"
    if not path.exists():
        return None
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def get_prompt_gen_hints() -> str:
    """Return prompt_gen_hints string or empty."""
    hints = load_learning_hints()
    if not hints:
        return ""
    return (hints.get("prompt_gen_hints") or "").strip()


def get_brief_gen_system_extra() -> str:
    """Return brief_gen_system_extra string or empty."""
    hints = load_learning_hints()
    if not hints:
        return ""
    return (hints.get("brief_gen_system_extra") or "").strip()


def get_channel_weights() -> dict[str, float]:
    """Return channel_weights dict (e.g. {devto: 0.6, reddit: 0.4}). Default if missing: devto 0.6, reddit 0.4."""
    hints = load_learning_hints()
    if not hints or not isinstance(hints.get("channel_weights"), dict):
        return {"devto": 0.6, "reddit": 0.4}
    return hints["channel_weights"]
