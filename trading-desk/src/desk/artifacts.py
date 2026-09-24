from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
import sklearn

from desk.features import FEATURE_COLS, read_panel
from desk.io_utils import ARTIFACT_DIR, FEATURE_DIR
from desk.models import build_strategy
from desk.portfolio import digest


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(f"Immutable artifact conflict: {path.name}") from None


def _id(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid artifact ID")
    return value


def freeze_frame(frame: pd.DataFrame, kind: str, metadata: dict) -> str:
    if kind not in {"raw", "features"}:
        raise ValueError("Unknown snapshot kind")
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    data = buffer.getvalue()
    manifest = {"sha256": hashlib.sha256(data).hexdigest(), "metadata": metadata, "kind": kind}
    snapshot_id = digest(manifest)
    directory = ARTIFACT_DIR / "snapshots" / kind / snapshot_id
    _write_once(directory / "data.parquet", data)
    _write_once(directory / "manifest.json", json.dumps(manifest, sort_keys=True, allow_nan=False).encode())
    return snapshot_id


def read_frame(snapshot_id: str, kind: str) -> pd.DataFrame:
    if kind not in {"raw", "features"}:
        raise ValueError("Unknown snapshot kind")
    directory = ARTIFACT_DIR / "snapshots" / kind / _id(snapshot_id)
    manifest = json.loads((directory / "manifest.json").read_text())
    if digest(manifest) != snapshot_id or file_hash(directory / "data.parquet") != manifest["sha256"]:
        raise ValueError("Snapshot digest mismatch")
    return pd.read_parquet(directory / "data.parquet")


def _feature_version() -> str:
    return file_hash(Path(__file__).with_name("features.py"))


def publish_model(model, *, strategy: str, trained_through: str, data_version: str) -> str:
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    data = buffer.getvalue()
    manifest = {"strategy": strategy, "trained_through": str(trained_through), "data_version": data_version,
                "features": FEATURE_COLS, "feature_version": _feature_version(),
                "model_code": file_hash(Path(__file__).with_name("models.py")),
                "python": list(sys.version_info[:2]), "sklearn": sklearn.__version__,
                "sha256": hashlib.sha256(data).hexdigest()}
    model_id = digest(manifest)
    directory = ARTIFACT_DIR / "models" / model_id
    _write_once(directory / "model.joblib", data)
    _write_once(directory / "manifest.json", json.dumps(manifest, sort_keys=True).encode())
    return model_id


def _manifest(model_id: str) -> tuple[Path, dict]:
    directory = ARTIFACT_DIR / "models" / _id(model_id)
    manifest = json.loads((directory / "manifest.json").read_text())
    if digest(manifest) != model_id or file_hash(directory / "model.joblib") != manifest["sha256"]:
        raise ValueError("Model digest mismatch")
    if (manifest["features"] != FEATURE_COLS or manifest["feature_version"] != _feature_version()
            or manifest["model_code"] != file_hash(Path(__file__).with_name("models.py"))
            or manifest["sklearn"] != sklearn.__version__ or manifest["python"] != list(sys.version_info[:2])):
        raise ValueError("Incompatible model feature schema or runtime")
    return directory, manifest


def approve_model(model_id: str, reviewer: str, evidence_digest: str) -> None:
    _manifest(model_id)
    if not reviewer.strip() or not evidence_digest.strip():
        raise ValueError("Reviewer and evidence digest are required")
    payload = {"model_id": model_id, "reviewer": reviewer, "evidence_digest": evidence_digest,
               "approved_at": datetime.now(UTC).isoformat()}
    _write_once(ARTIFACT_DIR / "approvals" / f"{_id(model_id)}.json", json.dumps(payload, sort_keys=True).encode())


def load_model(model_id: str):
    directory, manifest = _manifest(model_id)
    approval = ARTIFACT_DIR / "approvals" / f"{model_id}.json"
    if not approval.exists():
        raise ValueError("Model is not approved")
    if json.loads(approval.read_text()).get("model_id") != model_id:
        raise ValueError("Approval mismatch")
    data = (directory / "model.joblib").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise ValueError("Model digest changed during load")
    return joblib.load(io.BytesIO(data)), manifest


def train_candidate(strategy: str, cutoff: str) -> str:
    frame = read_panel()
    end = pd.Timestamp(cutoff)
    dates = pd.to_datetime(frame.get("date", frame.index))
    train = frame[(dates <= end) & (pd.to_datetime(frame["label_end"]) <= end)]
    train = train.dropna(subset=FEATURE_COLS + ["y", "fwd_ret", "label_end"])
    if train.empty:
        raise ValueError("No mature training observations")
    model = build_strategy(strategy)
    model.fit(train)
    return publish_model(model, strategy=strategy, trained_through=str(end),
                         data_version=file_hash(FEATURE_DIR / "panel.parquet"))
