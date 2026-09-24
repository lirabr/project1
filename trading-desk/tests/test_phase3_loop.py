from __future__ import annotations

import numpy as np

from desk.drift import _psi
from desk.policy import approve, propose, read_policy, stand_aside
from desk.regime import classify_row, situation_vector
from desk.trust import apply_trust, save_trust, update_from_outcome


def test_regime_labels_cover_corners():
    assert classify_row({"ret_20": 0.08, "vol_20": 0.005}) == "trend_up_calm"
    assert classify_row({"ret_20": 0.08, "vol_20": 0.03}) == "trend_up_volatile"
    assert classify_row({"ret_20": -0.08, "vol_20": 0.03}) == "risk_off"
    assert classify_row({"ret_20": 0.0, "vol_20": 0.01}) == "range"


def test_situation_vector_unit_norm():
    v = situation_vector({"ret_5": 0.01, "ret_20": 0.04, "vol_20": 0.01, "rsi_14": 55, "sma_ratio_20_50": 0.01, "dist_sma_20": 0.0, "regime_id": 0})
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-6


def test_trust_moves_on_loss_and_clips(tmp_path, monkeypatch):
    from desk import trust as trust_mod

    monkeypatch.setattr(trust_mod, "TRUST_PATH", tmp_path / "trust.yaml")
    save_trust({"model": 1.0, "bull": 1.0, "bear": 1.0})
    w = update_from_outcome("loss", 0.7)
    assert w["model"] < 1.0
    assert w["bear"] > 1.0
    w2 = apply_trust(0.7, 1000, {"model": 1.0, "bull": 1.0, "bear": 1.5}, "range", False)
    assert w2[1] == 500  # bear-dominant half size


def test_policy_stand_aside_risk_off():
    assert stand_aside("risk_off", score=0.6, model_trust=1.0) is True
    assert stand_aside("risk_off", score=0.75, model_trust=1.2) is False
    assert stand_aside("trend_up_calm", score=0.6, model_trust=1.0) is False


def test_policy_propose_approve_roundtrip(tmp_path, monkeypatch):
    from desk import policy as policy_mod

    src = tmp_path / "policy.md"
    src.write_text("# Desk policy v1\n\nStatus: approved\n")
    monkeypatch.setattr(policy_mod, "POLICY_PATH", src)
    monkeypatch.setattr(policy_mod, "PENDING_PATH", tmp_path / "pending.md")
    monkeypatch.setattr(policy_mod, "HISTORY_DIR", tmp_path / "hist")
    propose("cut size in risk_off")
    approve()
    assert "cut size in risk_off" in read_policy()


def test_psi_zero_on_identical():
    x = np.linspace(0, 1, 200)
    assert _psi(x, x) < 0.01
