from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from desk.contracts import AssetClass, Instrument
from desk.io_utils import RAW_DIR, ensure_dirs, load_yaml


def load_universe(path: Path) -> tuple[list[Instrument], dict]:
    cfg = load_yaml(path)
    instruments: list[Instrument] = []
    for s in cfg.get("equities", []):
        instruments.append(Instrument(symbol=s, asset_class="equity"))
    for s in cfg.get("crypto", []):
        instruments.append(Instrument(symbol=s, asset_class="crypto"))
    if not instruments:
        raise ValueError("Universe is empty")
    return instruments, cfg


def _download_one(symbol: str, start: str, end: str | None) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False,
        group_by="column",
    )
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.title)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise RuntimeError(f"{symbol} missing columns {missing}: {list(df.columns)}")
    out = df[needed].copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.dropna(subset=["Open", "Close"])
    out["symbol"] = symbol
    return out


def membership_mask(frame: pd.DataFrame, cfg: dict) -> pd.Series:
    intervals = cfg.get("membership")
    if intervals is None:
        return pd.Series(True, index=frame.index)
    dates = pd.to_datetime(frame.get("date", frame.index), utc=True)
    result = np.zeros(len(frame), dtype=bool)
    for symbol, periods in intervals.items():
        for period in periods:
            start = pd.to_datetime(period["from"], utc=True)
            known = pd.to_datetime(period["known_at"], utc=True)
            end = pd.to_datetime(period["to"], utc=True) if period.get("to") else pd.Timestamp.max.tz_localize("UTC")
            if start > end:
                raise ValueError("Invalid membership interval")
            result |= np.asarray((frame["symbol"] == symbol) & (dates >= start) & (dates <= end) & (dates >= known))
    return pd.Series(result, index=frame.index)


def validate_sessions(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> None:
    actual = pd.DatetimeIndex(frame.index).normalize()
    expected = pd.DatetimeIndex(sessions).normalize()
    if actual.has_duplicates or expected.has_duplicates or set(actual) != set(expected):
        raise ValueError("Bars do not match the supplied exchange sessions")


def download_universe(universe_path: Path) -> list[Path]:
    from desk.artifacts import freeze_frame

    ensure_dirs()
    instruments, cfg = load_universe(universe_path)
    start = str(cfg.get("start", "2018-01-01"))
    end = cfg.get("end")
    written: list[Path] = []
    for inst in instruments:
        df = _download_one(inst.symbol, start, end)
        if df.index.has_duplicates or not np.isfinite(df[["Open", "High", "Low", "Close", "Volume"]].to_numpy()).all():
            raise ValueError(f"Invalid or duplicate bars for {inst.symbol}")
        if (df[["Open", "High", "Low", "Close"]] <= 0).any().any() or (df["Volume"] < 0).any():
            raise ValueError(f"Invalid prices or volume for {inst.symbol}")
        calendar_verified = False
        if cfg.get("sessions_file"):
            session_path = universe_path.parent / cfg["sessions_file"]
            sessions = pd.DatetimeIndex(pd.to_datetime(json.loads(session_path.read_text())["sessions"]))
            validate_sessions(df, sessions)
            calendar_verified = True
        metadata = {"source": "yahoo", "retrieved_at": datetime.now(UTC).isoformat(),
                    "adjustment": "auto_adjust", "symbol": inst.symbol,
                    "calendar_verified": calendar_verified, "point_in_time_vendor": False}
        snapshot_id = freeze_frame(df, "raw", metadata)
        path = RAW_DIR / f"{inst.symbol}.parquet"
        df.to_parquet(path)
        path.with_suffix(".json").write_text(json.dumps({**metadata, "snapshot_id": snapshot_id}, sort_keys=True))
        written.append(path)
        print(f"saved {inst.symbol:8} {len(df):5} rows  {df.index.min().date()} → {df.index.max().date()}")
    return written


def read_bars(symbol: str) -> pd.DataFrame:
    path = RAW_DIR / f"{symbol}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run: desk-research download")
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def asset_class_of(symbol: str, universe_path: Path) -> AssetClass:
    instruments, _ = load_universe(universe_path)
    for inst in instruments:
        if inst.symbol == symbol:
            return inst.asset_class
    raise KeyError(symbol)
