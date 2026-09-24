from __future__ import annotations

from pathlib import Path

import numpy as np

from desk.features import FEATURE_COLS, read_panel
from desk.io_utils import ARTIFACT_DIR, load_yaml, write_yaml

REF_PATH = ARTIFACT_DIR / "feature_reference.yaml"


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 8) -> float:
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < 30 or len(actual) < 10:
        return 0.0
    qs = np.linspace(0, 100, bins + 1)
    edges = np.unique(np.percentile(expected, qs))
    if len(edges) < 3:
        return 0.0
    e_hist, _ = np.histogram(expected, bins=edges)
    a_hist, _ = np.histogram(actual, bins=edges)
    e = np.clip(e_hist / max(e_hist.sum(), 1), 1e-4, 1)
    a = np.clip(a_hist / max(a_hist.sum(), 1), 1e-4, 1)
    return float(np.sum((a - e) * np.log(a / e)))


def snapshot_reference(path: Path | None = None) -> Path:
    panel = read_panel()
    ref: dict[str, list[float]] = {}
    for col in FEATURE_COLS:
        if col not in panel.columns:
            continue
        s = panel[col].dropna().astype(float)
        ref[col] = s.tolist()[-2000:]
    out = path or REF_PATH
    # store compact stats + sample quantiles, not raw thousands of rows
    compact = {}
    for col, vals in ref.items():
        arr = np.asarray(vals, dtype=float)
        compact[col] = {
            "n": int(arr.size),
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "q": np.quantile(arr, [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]).tolist(),
            "tail": arr[-400:].tolist(),
        }
    write_yaml(out, compact)
    print(f"wrote feature reference → {out}")
    return out


def check_drift(lookback: int = 60, psi_alert: float = 0.20, psi_retrain: float = 0.25) -> dict:
    if not REF_PATH.exists():
        snapshot_reference()
    ref = load_yaml(REF_PATH)
    panel = read_panel()
    recent = panel.tail(lookback * max(1, panel["symbol"].nunique())) if "symbol" in panel.columns else panel.tail(lookback)
    report = {"psi": {}, "alert": False, "retrain": False}
    for col in FEATURE_COLS:
        if col not in ref or col not in recent.columns:
            continue
        expected = np.asarray(ref[col]["tail"], dtype=float)
        actual = recent[col].dropna().astype(float).to_numpy()
        val = _psi(expected, actual)
        report["psi"][col] = round(val, 4)
        if val >= psi_alert:
            report["alert"] = True
        if val >= psi_retrain:
            report["retrain"] = True
    worst = max(report["psi"].values()) if report["psi"] else 0.0
    print(f"drift max PSI={worst:.3f}  alert={report['alert']}  retrain={report['retrain']}")
    for col, val in sorted(report["psi"].items(), key=lambda x: -x[1])[:5]:
        print(f"  {col:18} PSI={val:.3f}")
    if report["retrain"]:
        print("action: re-run `desk-research backtest` and inspect folds before promoting again")
    return report
