from __future__ import annotations

import math
from pathlib import Path

from desk.contracts import RiskDecision, TradeProposal
from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR, ROOT, load_yaml


def load_risk_cfg(path: Path | None = None) -> dict:
    return load_yaml(path or (CONFIG_DIR / "risk.paper.yaml"))


def halt_path(cfg: dict) -> Path:
    configured = str(cfg.get("kill_switch_path", "data/artifacts/HALT"))
    if configured == "data/artifacts/HALT":
        return ARTIFACT_DIR / "HALT"
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def evaluate(
    proposal: TradeProposal,
    *,
    book_gross_usd: float,
    book_name_usd: float,
    day_pnl_usd: float,
    orders_this_cycle: int,
    crypto_weight: float,
    is_crypto: bool,
    live: bool = False,
    cfg: dict | None = None,
) -> RiskDecision:
    """Deterministic risk gate. No LLM, no network, no side effects.

    Returns a RiskDecision whose `reason` is always consistent with `allow`:
    a rejecting reason never coexists with allow=True, and "passed" never
    coexists with allow=False.
    """
    cfg = cfg or load_risk_cfg()
    gates: dict[str, bool] = {}
    numeric = (proposal.score, proposal.suggested_notional_usd, book_gross_usd,
               book_name_usd, day_pnl_usd, crypto_weight, orders_this_cycle)
    if (not all(math.isfinite(float(value)) for value in numeric)
            or not 0 <= proposal.score <= 1 or proposal.suggested_notional_usd < 0
            or book_gross_usd < 0 or book_name_usd < 0 or not 0 <= crypto_weight <= 1
            or orders_this_cycle < 0):
        return RiskDecision(False, "invalid numeric input", 0.0, {"finite_inputs": False})

    halt = halt_path(cfg)

    is_flat = proposal.side == "flat"

    gates["not_halted"] = not halt.exists()
    gates["paper_only"] = (not live) or bool(cfg.get("allow_live", False))
    gates["side_ok"] = proposal.side in set(cfg.get("allowed_sides", ["long", "flat"]))
    gates["score_ok"] = is_flat or proposal.score >= float(cfg.get("min_score", 0.0))
    gates["order_budget"] = orders_this_cycle < int(cfg.get("max_orders_per_cycle", 4))
    gates["daily_loss"] = day_pnl_usd > -float(cfg.get("max_daily_loss_usd", 250))

    cap = float(cfg.get("max_notional_per_name_usd", 2000))
    room_name = max(0.0, cap - book_name_usd)
    room_gross = max(0.0, float(cfg.get("max_gross_exposure_usd", 10000)) - book_gross_usd)
    clipped = 0.0 if is_flat else min(proposal.suggested_notional_usd, room_name, room_gross)
    gates["size_room"] = is_flat or clipped >= 1.0

    if is_crypto and not is_flat:
        limit = float(cfg.get("max_crypto_weight", 0.30))
        room_crypto = max(0.0, (limit * book_gross_usd - crypto_weight * book_gross_usd) / (1 - limit)) if 0 <= limit < 1 else (clipped if limit == 1 else 0.0)
        clipped = min(clipped, room_crypto)
        gates["crypto_cap"] = clipped >= 1.0
        gates["size_room"] = clipped >= 1.0
    else:
        gates["crypto_cap"] = True

    # Flat: never an order. Only the two universal safety gates apply.
    if is_flat:
        reason = (
            f"kill switch present at {halt}"
            if not gates["not_halted"]
            else ("live blocked by allow_live=false" if not gates["paper_only"] else "flat / no order")
        )
        return RiskDecision(allow=False, reason=reason, clipped_notional_usd=0.0, gates=gates)

    # Ordered precedence so the reason matches the first failing gate.
    checks: list[tuple[str, str]] = [
        ("not_halted", f"kill switch present at {halt}"),
        ("paper_only", "live blocked by allow_live=false"),
        ("side_ok", f"side {proposal.side} not permitted"),
        ("score_ok", f"score {proposal.score:.2f} below min_score"),
        ("order_budget", "max_orders_per_cycle reached"),
        ("daily_loss", "daily loss circuit breaker"),
        ("crypto_cap", "crypto weight cap"),
        ("size_room", "no remaining size room"),
    ]
    for name, reason in checks:
        if not gates[name]:
            return RiskDecision(allow=False, reason=reason, clipped_notional_usd=clipped, gates=gates)

    allow = clipped > 0
    reason = "passed" if allow else "no remaining size room"
    return RiskDecision(allow=allow, reason=reason, clipped_notional_usd=clipped, gates=gates)
