from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from desk.io_utils import ARTIFACT_DIR, ROOT


def _path(p: str | Path) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT / path


def append_audit(event: dict[str, Any], path: Path | None = None, copy_path: Path | None = None) -> Path:
    """Append-only JSONL. A second copy is the cheap 'off-box' stand-in on a laptop."""
    dest = path or (ARTIFACT_DIR / "audit.jsonl")
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        **event,
    }
    line = json.dumps(payload, default=str, sort_keys=True)
    payload["sha256"] = hashlib.sha256(line.encode()).hexdigest()
    record = json.dumps(payload, default=str, sort_keys=True) + "\n"
    with dest.open("a") as f:
        f.write(record)
    if copy_path:
        copy = _path(copy_path)
        copy.parent.mkdir(parents=True, exist_ok=True)
        with copy.open("a") as f:
            f.write(record)
    return dest
