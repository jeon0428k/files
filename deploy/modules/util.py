import yaml
from pathlib import Path

def load_config(path: str = "config.yml") -> dict:
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"config.yml not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)