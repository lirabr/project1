from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("DESK_CONFIG_DIR", str(ROOT / "configs"))).expanduser().resolve()
DATA_DIR = Path(os.environ.get("DESK_DATA_DIR", str(ROOT / "data"))).expanduser().resolve()
RAW_DIR = DATA_DIR / "raw"
FEATURE_DIR = DATA_DIR / "features"
ARTIFACT_DIR = DATA_DIR / "artifacts"
REGISTRY_PATH = ARTIFACT_DIR / "registry.yaml"


def load_yaml(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected mapping in {path}")
    return data


def write_yaml(path: Path | str, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def ensure_dirs() -> None:
    for p in (RAW_DIR, FEATURE_DIR, ARTIFACT_DIR):
        p.mkdir(parents=True, exist_ok=True)
