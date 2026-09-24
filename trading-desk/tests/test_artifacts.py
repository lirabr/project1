import json

import numpy as np
import pandas as pd
import pytest

from desk import artifacts, io_utils
from desk.features import FEATURE_COLS
from desk.models import SmaCross


def publish():
    return artifacts.publish_model(SmaCross(), strategy="sma_cross", trained_through="2026-01-01",
                                   data_version="data-hash")


def test_model_requires_approval_and_verifies_bytes_before_loading():
    model_id = publish()
    with pytest.raises(ValueError, match="approved"):
        artifacts.load_model(model_id)
    artifacts.approve_model(model_id, "operator", "reviewed-evidence")
    model, manifest = artifacts.load_model(model_id)
    assert model.name == "sma_cross"
    assert manifest["data_version"] == "data-hash"
    path = io_utils.ARTIFACT_DIR / "models" / model_id / "model.joblib"
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest"):
        artifacts.load_model(model_id)


def test_manifest_tampering_and_unknown_schema_rejected():
    model_id = publish()
    artifacts.approve_model(model_id, "operator", "reviewed-evidence")
    path = io_utils.ARTIFACT_DIR / "models" / model_id / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["features"] = ["unexpected"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        artifacts.load_model(model_id)
    with pytest.raises(ValueError):
        artifacts.load_model("../model")


def test_snapshot_is_content_addressed_and_immutable():
    frame = pd.DataFrame({"Close": [100.]})
    first = artifacts.freeze_frame(frame, "raw", {"source": "fixture"})
    assert artifacts.freeze_frame(frame, "raw", {"source": "fixture"}) == first
    second = artifacts.freeze_frame(frame * 2, "raw", {"source": "fixture"})
    assert first != second
    assert artifacts.read_frame(first, "raw").iloc[0, 0] == 100


def test_train_only_uses_mature_labels(monkeypatch):
    dates = pd.date_range("2025-12-20", periods=20)
    frame = pd.DataFrame({name: np.ones(20) for name in FEATURE_COLS}, index=dates)
    frame["date"] = dates
    frame["label_end"] = dates + pd.Timedelta(days=5)
    frame["y"] = 1.
    frame["fwd_ret"] = .1
    frame.to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    seen = []

    class Checked(SmaCross):
        def fit(self, train):
            seen.extend(train["label_end"])

    monkeypatch.setattr(artifacts, "build_strategy", lambda name: Checked())
    monkeypatch.setattr(artifacts, "publish_model", lambda *args, **kwargs: kwargs)
    result = artifacts.train_candidate("sma_cross", "2026-01-01")
    assert seen and max(seen) <= pd.Timestamp("2026-01-01")
    assert result["data_version"]


def test_calendar_validation_uses_explicit_sessions_not_weekdays():
    from desk.data import validate_sessions

    sessions = pd.DatetimeIndex(["2026-07-02", "2026-07-06"])
    validate_sessions(pd.DataFrame({"Close": [1, 2]}, index=sessions), sessions)
    with pytest.raises(ValueError):
        validate_sessions(pd.DataFrame({"Close": [1]}, index=sessions[:1]), sessions)
    with pytest.raises(ValueError):
        validate_sessions(pd.DataFrame({"Close": [1, 2, 3]}, index=pd.to_datetime(["2026-07-02", "2026-07-03", "2026-07-06"])), sessions)


def test_historical_membership_requires_available_evidence():
    from desk.data import membership_mask

    frame = pd.DataFrame({"symbol": ["A"] * 3, "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})
    cfg = {"membership": {"A": [{"from": "2026-01-01", "to": "2026-01-02", "known_at": "2026-01-02"}]}}
    assert membership_mask(frame, cfg).tolist() == [False, True, False]
    assert membership_mask(frame, {}).all()


def test_snapshot_approved_inference_has_no_silent_fallback():
    from desk.snapshot import cards_for_focus

    now = pd.Timestamp.now().normalize()
    frame = pd.DataFrame([{**dict.fromkeys(FEATURE_COLS, .1), "date": now, "symbol": "SPY", "Close": 100.}], index=[now])
    frame.to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    model_id = artifacts.publish_model(SmaCross(), strategy="sma_cross", trained_through=str(now - pd.Timedelta(days=1)), data_version="training-data")
    cfg = {"focus": ["SPY"], "inference_mode": "approved", "approved_model_id": model_id}
    universe = io_utils.CONFIG_DIR / "universe.research.yaml"
    with pytest.raises(ValueError, match="approved"):
        cards_for_focus(cfg, universe)
    artifacts.approve_model(model_id, "reviewer", "evidence")
    cards = cards_for_focus(cfg, universe)
    assert cards[0].model_version == model_id and cards[0].score == 1
    frame.loc[now, "rsi_14"] = float("nan")
    frame.to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    with pytest.raises(ValueError, match="incomplete"):
        cards_for_focus(cfg, universe)


def test_snapshot_missing_focus_symbol_fails_instead_of_silently_omitting():
    from desk.snapshot import cards_for_focus

    frame = pd.DataFrame([{**dict.fromkeys(FEATURE_COLS, .1), "symbol": "SPY", "Close": 100., "date": pd.Timestamp.now().normalize()}])
    frame.to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    with pytest.raises(ValueError, match="Missing configured"):
        cards_for_focus({"focus": ["MISSING"]}, io_utils.CONFIG_DIR / "universe.research.yaml")
