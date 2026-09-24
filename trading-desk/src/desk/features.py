from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from desk.data import load_universe, read_bars
from desk.io_utils import FEATURE_DIR, ensure_dirs

FEATURE_COLS = [
    "ret_1",
    "ret_5",
    "ret_20",
    "vol_20",
    "rsi_14",
    "sma_ratio_20_50",
    "dist_sma_20",
    "volume_z_20",
    "high_low_20",
]


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / window, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / window, adjust=False).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    return 100 - (100 / (1 + rs))


def make_features(bars: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    df = bars.copy()
    close = df["Close"]
    df["ret_1"] = close.pct_change(1)
    df["ret_5"] = close.pct_change(5)
    df["ret_20"] = close.pct_change(20)
    df["vol_20"] = df["ret_1"].rolling(20).std()
    df["sma_20"] = close.rolling(20).mean()
    df["sma_50"] = close.rolling(50).mean()
    df["sma_ratio_20_50"] = df["sma_20"] / df["sma_50"] - 1.0
    df["dist_sma_20"] = close / df["sma_20"] - 1.0
    df["rsi_14"] = _rsi(close, 14)
    vol = df["Volume"].replace(0, np.nan)
    df["volume_z_20"] = (vol - vol.rolling(20).mean()) / vol.rolling(20).std()
    df["high_low_20"] = (df["High"].rolling(20).max() - df["Low"].rolling(20).min()) / close

    # Point-in-time label: forward close-to-close over horizon.
    # Decision at bar t uses features at t and is filled at t+1 open in the backtest.
    df["fwd_ret"] = close.shift(-horizon) / close - 1.0
    df["y"] = (df["fwd_ret"] > 0).astype(float).where(df["fwd_ret"].notna())
    df["label_end"] = pd.Series(pd.to_datetime(df.index), index=df.index).shift(-horizon)
    df["feature_available"] = df[FEATURE_COLS].notna().all(axis=1)
    keep = FEATURE_COLS + ["Open", "High", "Low", "Close", "Volume", "fwd_ret", "y", "label_end", "feature_available", "symbol"]
    out = df[keep].copy()
    out["date"] = pd.to_datetime(out.index)
    return out


def build_feature_store(universe_path: Path, horizon: int = 5) -> Path:
    ensure_dirs()
    instruments, _ = load_universe(universe_path)
    frames = []
    for inst in instruments:
        bars = read_bars(inst.symbol)
        feat = make_features(bars, horizon=horizon)
        feat["asset_class"] = inst.asset_class
        frames.append(feat)
    panel = pd.concat(frames).sort_index()
    path = FEATURE_DIR / "panel.parquet"
    panel.to_parquet(path)
    from desk.artifacts import file_hash, freeze_frame
    from desk.io_utils import RAW_DIR

    sources = {i.symbol: file_hash(RAW_DIR / f"{i.symbol}.parquet") for i in instruments}
    snapshot_id = freeze_frame(panel, "features", {"horizon": horizon, "sources": sources,
                                                 "feature_code": file_hash(Path(__file__))})
    path.with_suffix(".json").write_text(json.dumps({"snapshot_id": snapshot_id, "sources": sources}, sort_keys=True))
    usable = int(panel["feature_available"].sum())
    print(f"feature panel {len(panel)} rows, {usable} complete, {panel['symbol'].nunique()} symbols → {path}")
    return path


def read_panel() -> pd.DataFrame:
    path = FEATURE_DIR / "panel.parquet"
    if not path.exists():
        raise FileNotFoundError("Missing feature panel. Run: desk-research features")
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df
