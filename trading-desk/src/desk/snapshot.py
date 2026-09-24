from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from desk.contracts import ModelCard
from desk.data import load_universe, membership_mask
from desk.features import FEATURE_COLS, read_panel
from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR, load_yaml
from desk.models import build_strategy
from desk.regime import classify_row


def _latest_row(panel: pd.DataFrame, symbol: str) -> pd.Series | None:
    sub = panel[panel["symbol"] == symbol]
    if sub.empty:
        return None
    if "date" in sub.columns:
        sub = sub.sort_values("date")
    else:
        sub = sub.sort_index()
    row = sub.iloc[-1]
    if not np.isfinite(row[FEATURE_COLS + ["Close"]].astype(float).to_numpy()).all() or row["Close"] <= 0:
        raise ValueError(f"Latest bar is incomplete or invalid for {symbol}")
    return row


def _score_from_oos(symbol: str, strategy: str, as_of: pd.Timestamp | None = None) -> float | None:
    path = ARTIFACT_DIR / strategy / "oos_scores.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    hit = df[df["symbol"] == symbol] if "symbol" in df.columns else df
    if hit.empty or "score" not in hit.columns or as_of is None:
        return None
    dates = pd.to_datetime(hit["date"] if "date" in hit.columns else hit.index)
    hit = hit[dates == pd.Timestamp(as_of)]
    if len(hit) != 1 or not pd.notna(hit["score"].iloc[0]):
        return None
    return float(hit["score"].iloc[0])


def _score_from_rules(row: pd.Series, strategy: str) -> float:
    frame = pd.DataFrame([row])
    strat = build_strategy(strategy)
    if strategy != "hgb_tab":
        strat.fit(frame)
        return float(strat.scores(frame).iloc[0])
    # Unfitted HGB cannot score; use sma as fallback signal.
    fallback = build_strategy("sma_cross")
    fallback.fit(frame)
    return float(fallback.scores(frame).iloc[0])


def regime_tag(row: pd.Series) -> str:
    phase3 = load_yaml(CONFIG_DIR / "phase3.yaml") if (CONFIG_DIR / "phase3.yaml").exists() else {}
    return classify_row(row, phase3)


def cards_for_focus(desk_cfg: dict, universe_path: Path) -> list[ModelCard]:
    panel = read_panel()
    from desk.artifacts import file_hash, load_model
    from desk.io_utils import FEATURE_DIR

    preferred = desk_cfg.get("preferred_strategy", "hgb_tab")
    fallback = desk_cfg.get("fallback_strategy", "sma_cross")
    mode = desk_cfg.get("inference_mode", "rules")
    if mode not in {"rules", "approved", "replay"}:
        raise ValueError("Unknown inference_mode")
    model_id = desk_cfg.get("approved_model_id", "")
    model, manifest = load_model(model_id) if mode == "approved" else (None, {})
    data_version = file_hash(FEATURE_DIR / "panel.parquet")
    instruments, universe_cfg = load_universe(universe_path)
    class_of = {i.symbol: i.asset_class for i in instruments}
    cards: list[ModelCard] = []
    for symbol in desk_cfg.get("focus", []):
        row = _latest_row(panel, symbol)
        if row is None:
            raise ValueError(f"Missing configured focus symbol: {symbol}")
        if not membership_mask(pd.DataFrame([row]), universe_cfg).all():
            raise ValueError(f"Focus symbol is outside the point-in-time universe: {symbol}")
        row_date = pd.Timestamp(row.get("date", row.name))
        age = (pd.Timestamp.now(tz="UTC").date() - row_date.date()).days
        if mode != "replay" and not 0 <= age <= int(desk_cfg.get("max_bar_age_days", 7)):
            raise ValueError(f"Stale or future bar for {symbol}")
        if mode == "approved":
            model_age = (row_date - pd.Timestamp(manifest["trained_through"])).days
            if not 0 < model_age <= int(desk_cfg.get("max_model_age_days", 90)):
                raise ValueError("Inference date must follow a non-stale training cutoff")
            score = float(model.scores(pd.DataFrame([row])).iloc[0])
            used = manifest["strategy"]
        elif mode == "replay":
            score = _score_from_oos(symbol, preferred, row_date)
            if score is None:
                raise ValueError(f"Missing exact-date replay score for {symbol}")
            used = preferred
        else:
            if fallback != "sma_cross":
                raise ValueError("Fitted strategies require approved inference; rules mode uses sma_cross")
            score = _score_from_rules(row, fallback)
            used = fallback
        as_of = str(row["date"].date()) if "date" in row.index and not pd.isna(row["date"]) else str(pd.Timestamp(row.name).date())
        feats = {c: float(row[c]) for c in FEATURE_COLS if c in row.index and pd.notna(row[c])}
        cards.append(
            ModelCard(
                symbol=symbol,
                strategy=used,
                score=float(score),
                last_close=float(row["Close"]),
                as_of=as_of,
                features=feats,
                note=f"{class_of.get(symbol, 'equity')} regime={regime_tag(row)}",
                model_version=model_id if mode == "approved" else f"{mode}:{used}",
                data_version=data_version,
                evidence=[{"id": f"bar:{data_version}:{symbol}:{as_of}", "role": "model",
                           "as_of": as_of, "source": "feature_panel", "inference_mode": mode}],
            )
        )
    return cards
