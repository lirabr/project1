from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

REGIME_LABELS = (
    "trend_up_calm",
    "trend_up_volatile",
    "range",
    "pullback",
    "risk_off",
)

REGIME_COLS = [
    "regime_vol_z",
    "regime_mom",
    "regime_trend",
    "regime_id",
]


def _cfg(phase3: dict | None) -> dict[str, float]:
    block = (phase3 or {}).get("regime") or {}
    return {
        "vol_calm": float(block.get("vol_calm", 0.010)),
        "vol_high": float(block.get("vol_high", 0.020)),
        "trend_up": float(block.get("trend_up", 0.04)),
        "trend_down": float(block.get("trend_down", -0.04)),
    }


def classify_row(row: pd.Series | dict[str, Any], phase3: dict | None = None) -> str:
    c = _cfg(phase3)
    vol = float(row.get("vol_20") or 0.0)
    mom = float(row.get("ret_20") or 0.0)
    vol_hi = vol >= c["vol_high"]
    if mom >= c["trend_up"] and not vol_hi:
        return "trend_up_calm"
    if mom >= c["trend_up"] and vol_hi:
        return "trend_up_volatile"
    if mom <= c["trend_down"] and vol_hi:
        return "risk_off"
    if mom <= c["trend_down"] / 2:
        return "pullback"
    return "range"


def regime_id(label: str) -> float:
    try:
        return float(REGIME_LABELS.index(label))
    except ValueError:
        return 2.0


def attach_regime(panel: pd.DataFrame, phase3: dict | None = None) -> pd.DataFrame:
    df = panel.copy()
    labels = df.apply(lambda r: classify_row(r, phase3), axis=1)
    vol = df["vol_20"] if "vol_20" in df.columns else pd.Series(0.0, index=df.index)
    med = vol.median() if vol.notna().any() else 0.0
    mad = (vol - med).abs().median() or 1e-6
    df["regime"] = labels
    df["regime_vol_z"] = (vol - med) / (1.4826 * mad)
    df["regime_mom"] = df["ret_20"] if "ret_20" in df.columns else 0.0
    df["regime_trend"] = df["sma_ratio_20_50"] if "sma_ratio_20_50" in df.columns else 0.0
    df["regime_id"] = labels.map(regime_id)
    return df


def situation_vector(row: pd.Series | dict[str, Any]) -> np.ndarray:
    keys = ["ret_5", "ret_20", "vol_20", "rsi_14", "sma_ratio_20_50", "dist_sma_20", "regime_id"]
    vals = []
    for k in keys:
        try:
            vals.append(float(row.get(k) or 0.0))
        except (TypeError, ValueError):
            vals.append(0.0)
    vec = np.asarray(vals, dtype=float)
    n = np.linalg.norm(vec)
    return vec / n if n > 0 else vec
