from __future__ import annotations

from desk.auditor import audit_proposal, enforce
from desk.contracts import ModelCard, TradeProposal


def _card(score: float = 0.7) -> ModelCard:
    return ModelCard(
        symbol="AAPL",
        strategy="sma_cross",
        score=score,
        last_close=100.0,
        as_of="2026-01-01",
        features={"ret_20": 0.03, "vol_20": 0.01, "rsi_14": 55.0},
        note="regime=trend_up_calm",
    )


def _prop(**kw) -> TradeProposal:
    base = {
        "symbol": "AAPL",
        "side": "long",
        "urgency": "low",
        "thesis": "t",
        "invalidation": "x",
        "horizon_days": 5,
        "score": 0.7,
        "suggested_notional_usd": 1000.0,
    }
    base.update(kw)
    return TradeProposal(**base)  # type: ignore[arg-type]


def test_clean_proposal_passes():
    card = _card(0.7)
    res = audit_proposal(_prop(score=0.7), card, [{"id": 1}], )
    assert res.ok, res.violations


def test_untraceable_score_blocks():
    card = _card(0.7)
    p, res = enforce(_prop(score=0.95), card, [])
    assert not res.ok
    assert p.side == "flat"
    assert p.suggested_notional_usd == 0.0
    assert "AUDIT BLOCK" in p.thesis


def test_dangling_citation_blocks():
    card = _card(0.7)
    p = _prop(score=0.7, cited_memory_ids=[999])
    p2, res = enforce(p, card, [{"id": 1}, {"id": 2}])
    assert not res.ok
    assert p2.side == "flat"
    assert any("#999" in v for v in res.violations)


def test_expected_score_allows_trust_transform():
    card = _card(0.7)
    # trust model weight 1.2 → adjusted 0.84; audit must accept it when told
    res = audit_proposal(_prop(score=0.84), card, [], expected_score=0.84)
    assert res.ok


def test_side_without_size_blocks():
    card = _card(0.7)
    p, res = enforce(_prop(score=0.7, side="long", suggested_notional_usd=0.0), card, [])
    assert not res.ok
    assert p.side == "flat"
