import yaml
from pathlib import Path


def load_config(path="config.yml"):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config.yml not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
