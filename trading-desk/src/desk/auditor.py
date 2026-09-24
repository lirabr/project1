"""Auditor — fail-closed schema + citation check on a TradeProposal.

Architecture L5 promises an Auditor: schema validation and a citation check
("did this number come from a tool?"). If the check fails, the cycle must fail
closed (no order). This runs no LLM and touches no network.

Rules enforced:
1. Schema: required fields present and typed; score in [0, 1]; notional >= 0.
2. Numeric provenance: the proposal's ``score`` must match the model card's
   ``score`` (numbers live in tools, not in prose). A PM cannot invent a score.
3. Citation integrity: every id in ``cited_memory_ids`` must be an int and must
   exist in the retrieved memory set handed to the PM (no dangling citations).
4. Side sanity: a non-flat side requires a positive suggested notional.

``audit_proposal`` returns an AuditResult. ``enforce`` mutates a failing
proposal to a safe flat/no-order state and returns it, so the deterministic risk
gate downstream will never receive an unverified order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from desk.contracts import ModelCard, TradeProposal


@dataclass
class AuditResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def audit_proposal(
    proposal: TradeProposal,
    card: ModelCard,
    memories: list[dict[str, Any]],
    *,
    expected_score: float | None = None,
    score_tol: float = 1e-6,
) -> AuditResult:
    """Validate schema, numeric provenance, and citation integrity.

    ``expected_score`` is the value the PM/trust pipeline is *allowed* to have
    produced from the model card (a tool output). When omitted it defaults to the
    raw model-card score, i.e. the PM may not invent a score. When trust scaling
    is applied upstream, pass the post-trust value so provenance still traces to a
    deterministic transform of a tool output rather than free prose.
    """
    v: list[str] = []
    ref_score = card.score if expected_score is None else expected_score

    # 1. schema
    if not proposal.symbol:
        v.append("missing symbol")
    if proposal.side not in ("long", "flat", "short"):
        v.append(f"invalid side {proposal.side!r}")
    if not (0.0 <= float(proposal.score) <= 1.0):
        v.append(f"score {proposal.score} out of [0,1]")
    if not math.isfinite(float(proposal.suggested_notional_usd)) or float(proposal.suggested_notional_usd) < 0:
        v.append("invalid suggested notional")
    if proposal.symbol != card.symbol:
        v.append("proposal symbol does not match model card")
    if not math.isfinite(float(ref_score)):
        v.append("nonfinite reference score")

    # 2. numeric provenance — score must trace to a tool output (model card,
    #    optionally through the deterministic trust transform)
    if abs(float(proposal.score) - float(ref_score)) > score_tol:
        v.append(
            f"score {proposal.score} not traceable to expected {ref_score} "
            "(number did not come from a tool)"
        )

    # 3. citation integrity — no dangling memory ids
    available = {int(m["id"]) for m in memories if m.get("id") is not None}
    for cid in proposal.cited_memory_ids:
        if not isinstance(cid, int):
            v.append(f"citation {cid!r} is not an int")
        elif cid not in available:
            v.append(f"citation #{cid} not in retrieved memory set")

    # 4. side sanity
    if proposal.side != "flat" and float(proposal.suggested_notional_usd) <= 0:
        v.append(f"side {proposal.side} with non-positive notional")

    return AuditResult(ok=not v, violations=v)


def enforce(
    proposal: TradeProposal,
    card: ModelCard,
    memories: list[dict[str, Any]],
    *,
    expected_score: float | None = None,
) -> tuple[TradeProposal, AuditResult]:
    """Fail closed: on any violation, force the proposal to flat/no-order."""
    result = audit_proposal(proposal, card, memories, expected_score=expected_score)
    if not result.ok:
        proposal.side = "flat"  # type: ignore[assignment]
        proposal.suggested_notional_usd = 0.0
        proposal.thesis = (
            "AUDIT BLOCK — forced flat. " + "; ".join(result.violations) + " | " + proposal.thesis
        )
    return proposal, result
