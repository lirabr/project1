from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pandas as pd

from desk.agents import bear_brief, bull_brief, maybe_refine, pm_proposal
from desk.auditor import enforce
from desk.contracts import ModelCard, RiskDecision
from desk.policy import stand_aside
from desk.portfolio import PortfolioTarget, allocate, digest, finite, regime_scale, timestamp
from desk.trust import apply_trust


def decide(card: ModelCard, memories: list[dict], desk_cfg: dict, risk_cfg: dict,
           trust: dict, *, desired_notional: float | None = None, target_id: str = ""):
    bull, bear = bull_brief(card, memories), bear_brief(card, memories)
    proposal = pm_proposal(card, bull, bear, memories, float(risk_cfg.get("min_score", .55)),
                           float(risk_cfg.get("max_notional_per_name_usd", 2000)))
    if desired_notional is not None:
        proposal.suggested_notional_usd = finite(desired_notional) if proposal.side == "long" else 0.
    regime = card.note.split("regime=")[-1] if "regime=" in card.note else "range"
    aside = stand_aside(regime, card.score, trust.get("model", 1.))
    score, size, note = apply_trust(proposal.score, proposal.suggested_notional_usd, trust, regime, aside)
    proposal.score, proposal.suggested_notional_usd = score, size
    proposal.thesis += " " + note
    proposal.target_id = target_id
    if aside:
        proposal.side = "flat"
    proposal = maybe_refine(proposal, card, desk_cfg)
    return enforce(proposal, card, memories, expected_score=score)


def target_for_cards(cards: list[ModelCard], desk_cfg: dict, risk_cfg: dict,
                     equity: float, as_of: str) -> PortfolioTarget:
    if finite(equity) <= 0:
        raise ValueError("Positive marked equity is required")
    if len({c.symbol for c in cards}) != len(cards) or len({c.as_of for c in cards}) > 1:
        raise ValueError("Cards must have unique symbols and a common data date")
    allocation = desk_cfg.get("allocation") or {}
    cap = min(float(risk_cfg.get("max_name_weight", .25)),
              float(risk_cfg.get("max_notional_per_name_usd", 2000)) / equity)
    weights = allocate({c.symbol: c.score for c in cards}, float(risk_cfg.get("min_score", .55)), cap,
                       method=allocation.get("method", "equal"),
                       volatility={c.symbol: c.features.get("vol_20", 0) for c in cards},
                       exposure_scale=float(allocation.get("exposure_scale", 1)),
                       risk_scales={c.symbol: regime_scale(c.features, allocation.get("regime_scales")) for c in cards})
    gross_cap = finite(risk_cfg.get("max_gross_exposure_usd", 10000)) / equity
    total = sum(weights.values())
    if total > gross_cap:
        weights = {s: w * gross_cap / total for s, w in weights.items()}
    execute_after = desk_cfg.get("execute_after") or (timestamp(as_of) + timedelta(seconds=1)).isoformat()
    return PortfolioTarget(weights, as_of, execute_after,
                           digest(sorted({c.model_version for c in cards})),
                           digest(sorted({c.data_version for c in cards})), digest([desk_cfg, risk_cfg]),
                           tuple(item["id"] for c in cards for item in c.evidence))


def evaluate_book(proposal, book: dict, day_pnl: float, orders: int, cfg: dict) -> RiskDecision:
    from desk.risk_gate import evaluate

    if book.get("has_unknown_orders"):
        return RiskDecision(False, "unresolved order outcome", 0, {"known_orders": False})
    reserved = book.get("reserved_by_name", {})
    exposure = {s: book["by_name"].get(s, 0) + reserved.get(s, 0) for s in set(book["by_name"]) | set(reserved)}
    gross = sum(exposure.values())
    crypto = sum(v for s, v in exposure.items() if s.endswith("-USD") or "/" in s)
    available = max(0., book["cash"] - sum(reserved.values()))
    bounded = replace(proposal, suggested_notional_usd=min(finite(proposal.suggested_notional_usd), available))
    return evaluate(bounded, book_gross_usd=gross, book_name_usd=exposure.get(proposal.symbol, 0),
                    day_pnl_usd=day_pnl, orders_this_cycle=orders, crypto_weight=crypto / gross if gross else 0,
                    is_crypto=proposal.symbol.endswith("-USD") or "/" in proposal.symbol, cfg=cfg)


def eligible_memories(conn, card: ModelCard, candidates: list[dict], k: int) -> list[dict]:
    cutoff = pd.Timestamp(card.as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    result = []
    seen = set()
    for candidate in candidates:
        eid = candidate.get("id", candidate.get("episode_id"))
        if eid is None or eid in seen:
            continue
        row = conn.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
        if row is None or not row["lesson"] or not row["exit_ts"] or row["outcome"] in {"intent", "rejected", "open"}:
            continue
        if pd.Timestamp(row["exit_ts"]) > cutoff or pd.Timestamp(row["ts"]) > cutoff:
            continue
        result.append(dict(row))
        seen.add(eid)
        if len(result) == k:
            break
    return result
