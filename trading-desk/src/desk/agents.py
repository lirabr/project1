from __future__ import annotations

import json
import math
import os
from typing import Any

from desk.contracts import ModelCard, TradeProposal


def _mem_lines(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "No prior episodes retrieved."
    lines = []
    for m in memories:
        lesson = m.get("lesson") or "(no lesson yet)"
        lines.append(
            f"- #{m.get('id')} {m.get('symbol')} {m.get('side')} "
            f"outcome={m.get('outcome') or 'open'} r={m.get('realized_r')} | {lesson}"
        )
    return "\n".join(lines)


def analyst_evidence(card: ModelCard) -> list[dict[str, Any]]:
    from desk.portfolio import digest

    rules = [("bull", "sma_ratio_20_50", "positive trend", lambda v: v > 0),
             ("bull", "ret_20", "positive momentum", lambda v: v > 0),
             ("bull", "rsi_14", "not overbought", lambda v: v < 70),
             ("bear", "rsi_14", "overbought", lambda v: v > 70),
             ("bear", "vol_20", "elevated volatility", lambda v: v > .02),
             ("bear", "ret_20", "negative momentum", lambda v: v < 0)]
    items = list(card.evidence)
    for role, feature, rule, check in rules:
        value = card.features.get(feature)
        valid = value is not None and math.isfinite(value)
        item = {"role": role, "feature": feature, "value": value if valid else None,
                "rule": rule, "triggered": bool(check(value)) if valid else False,
                "missing": not valid, "as_of": card.as_of, "symbol": card.symbol,
                "model_version": card.model_version, "data_version": card.data_version}
        items.append({"id": digest(item), **item})
    return items


def model_signal_brief(card: ModelCard) -> str:
    f = card.features
    return (
        f"{card.symbol} as_of={card.as_of} strategy={card.strategy} score={card.score:.3f} "
        f"close={card.last_close:.4f} ret_20={f.get('ret_20', float('nan')):.3f} "
        f"vol_20={f.get('vol_20', float('nan')):.4f} rsi={f.get('rsi_14', float('nan')):.1f} "
        f"{card.note}"
    )


def bull_brief(card: ModelCard, memories: list[dict[str, Any]]) -> str:
    f = card.features
    bits = []
    if f.get("sma_ratio_20_50", 0) > 0:
        bits.append("price regime is above the slow average")
    if f.get("ret_20", 0) > 0:
        bits.append("20d momentum is positive")
    if f.get("rsi_14", 50) < 70:
        bits.append("RSI is not obviously stretched")
    if not bits:
        bits.append("the model score is the main long argument")
    return (
        f"BULL {card.symbol}: score {card.score:.2f}. " + "; ".join(bits) + ". "
        f"Lessons:\n{_mem_lines(memories)}"
    )


def bear_brief(card: ModelCard, memories: list[dict[str, Any]]) -> str:
    f = card.features
    bits = []
    if f.get("rsi_14", 50) > 70:
        bits.append("RSI is extended")
    if f.get("vol_20", 0) > 0.02:
        bits.append("realized vol is elevated")
    if f.get("ret_20", 0) < 0:
        bits.append("20d momentum is already negative")
    if card.score < 0.6:
        bits.append("model conviction is modest")
    if not bits:
        bits.append("costs and a failed T+1 fill can erase a thin edge")
    return (
        f"BEAR {card.symbol}: " + "; ".join(bits) + ". "
        f"Lessons:\n{_mem_lines(memories)}"
    )


def pm_proposal(card: ModelCard, bull: str, bear: str, memories: list[dict[str, Any]], min_score: float, cap: float) -> TradeProposal:
    cited = [int(m["id"]) for m in memories if m.get("id") is not None]
    if card.score >= min_score:
        side = "long"
        thesis = (
            f"Take a small paper long. Model {card.strategy} score {card.score:.2f} "
            f"on {card.as_of}. {card.note}."
        )
        invalidation = "Exit idea if close drops 1.5x the 20d vol below entry or thesis breaks."
        notional = cap * min(1.0, (card.score - min_score) / max(1e-6, 1 - min_score) * 0.8 + 0.2)
    else:
        side = "flat"
        thesis = f"Stand aside. Score {card.score:.2f} is below threshold {min_score:.2f}."
        invalidation = "Revisit next cycle."
        notional = 0.0
    return TradeProposal(
        symbol=card.symbol,
        side=side,  # type: ignore[arg-type]
        urgency="low",
        thesis=thesis,
        invalidation=invalidation,
        horizon_days=5,
        score=card.score,
        suggested_notional_usd=round(notional, 2),
        cited_memory_ids=cited,
        bull_brief=bull,
        bear_brief=bear,
        evidence=analyst_evidence(card),
    )


def try_llm_refine(proposal: TradeProposal, card: ModelCard, api_key: str, base_url: str, model: str, timeout_s: int) -> TradeProposal:
    """Optional OpenAI-compatible refinement. Falls back to the rule proposal on any error."""
    try:
        import urllib.request

        body = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the portfolio manager on a paper trading desk. "
                        "Return ONLY JSON with keys thesis, invalidation. "
                        "Do not change side. Be brief. Cite memory ids if given."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "symbol": card.symbol,
                            "side": proposal.side,
                            "score": card.score,
                            "features": card.features,
                            "bull": proposal.bull_brief,
                            "bear": proposal.bear_brief,
                            "cited_memory_ids": proposal.cited_memory_ids,
                        }
                    ),
                },
            ],
        }
        req = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode())
        text = payload["choices"][0]["message"]["content"]
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1])
        if data.get("thesis"):
            proposal.thesis = str(data["thesis"])[:800]
        if data.get("invalidation"):
            proposal.invalidation = str(data["invalidation"])[:400]
    except Exception as exc:  # noqa: BLE001 — paper desk must fail closed to rules
        proposal.thesis = proposal.thesis + f" (llm skipped: {type(exc).__name__})"
    return proposal


def maybe_refine(proposal: TradeProposal, card: ModelCard, desk_cfg: dict) -> TradeProposal:
    llm = desk_cfg.get("llm") or {}
    if not llm.get("enabled"):
        return proposal
    key = os.environ.get("DESK_LLM_API_KEY") or os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return proposal
    return try_llm_refine(
        proposal,
        card,
        api_key=key,
        base_url=str(llm.get("base_url") or "https://api.x.ai/v1"),
        model=str(llm.get("model") or "grok-4"),
        timeout_s=int(llm.get("timeout_s") or 45),
    )
