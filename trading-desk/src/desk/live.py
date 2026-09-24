from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from desk.audit import append_audit
from desk.contracts import RiskDecision, TradeProposal
from desk.io_utils import CONFIG_DIR, load_yaml


def load_live_cfg(path: Path | None = None) -> dict:
    return load_yaml(path or (CONFIG_DIR / "live.yaml"))


def preflight(live_cfg: dict | None = None, risk_cfg: dict | None = None) -> list[str]:
    """Return human-readable blockers. Empty list = may proceed to a dry live intent."""
    live_cfg = live_cfg or load_live_cfg()
    from desk.risk_gate import load_risk_cfg

    risk_cfg = risk_cfg or load_risk_cfg()
    blockers: list[str] = ["live execution and reconciliation are not implemented"]
    if not live_cfg.get("enabled"):
        blockers.append("live.yaml enabled=false")
    if not risk_cfg.get("allow_live"):
        blockers.append("risk allow_live=false")
    if risk_cfg.get("require_human_approve", True) is False:
        blockers.append("human approve is off — turn it back on for Phase 4")
    phrase = str(live_cfg.get("confirm_phrase") or "")
    if os.environ.get("DESK_LIVE_CONFIRM") != phrase:
        blockers.append("DESK_LIVE_CONFIRM does not match live.yaml confirm_phrase")
    if not live_cfg.get("withdraw_disabled_attested"):
        blockers.append("withdraw_disabled_attested=false — check the venue key has no transfer/withdraw")
    if float(live_cfg.get("max_live_notional_usd", 0)) > 500:
        blockers.append("max_live_notional_usd above the Phase 4 ceiling of 500")
    if live_cfg.get("equities_only") and False:
        pass
    return blockers


def live_size_ok(proposal: TradeProposal, live_cfg: dict, is_crypto: bool) -> tuple[bool, str, float]:
    cap = float(live_cfg.get("max_live_notional_usd", 0))
    if is_crypto and live_cfg.get("equities_only", True):
        return False, "crypto blocked in Phase 4 equities_only", 0.0
    clipped = min(proposal.suggested_notional_usd, cap)
    if proposal.side == "flat":
        return False, "flat", 0.0
    if clipped < 1:
        return False, "live cap is zero", 0.0
    return True, "live size clipped", clipped


def route_live_intent(
    proposal: TradeProposal,
    risk: RiskDecision,
    *,
    is_crypto: bool,
    submit: bool = False,
) -> dict[str, Any]:
    """
    Never talks to a broker unless every gate is green AND submit=True.
    Even then this starter only writes an audit row. Wire a venue client yourself
    after you have read the venue's paper vs live docs.
    """
    live_cfg = load_live_cfg()
    blockers = preflight(live_cfg)
    ok_size, size_reason, clipped = live_size_ok(proposal, live_cfg, is_crypto)
    event = {
        "kind": "live_intent",
        "symbol": proposal.symbol,
        "side": proposal.side,
        "thesis": proposal.thesis[:300],
        "risk_allow": risk.allow,
        "risk_reason": risk.reason,
        "submit_requested": submit,
        "blockers": blockers,
        "size_reason": size_reason,
        "clipped_usd": clipped,
        "broker_called": False,
    }
    if blockers or not risk.allow or not ok_size or not submit:
        event["status"] = "blocked_or_dry"
        append_audit(event, copy_path=live_cfg.get("audit_copy_path"))
        return event

    # Hard stop: this repo does not place a live order for you.
    event["status"] = "authorized_but_not_sent"
    event["note"] = (
        "Gates passed. Starter will not call a live broker API. "
        "Attach your own client behind this function if you still want tiny live."
    )
    append_audit(event, copy_path=live_cfg.get("audit_copy_path"))
    return event
