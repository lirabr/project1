from __future__ import annotations

from desk.contracts import TradeProposal
from desk.memory import apply_fill, book_state, connect, retrieve, write_episode
from desk.risk_gate import evaluate


def _prop(**kwargs) -> TradeProposal:
    base = {
        "symbol": "AAPL",
        "side": "long",
        "urgency": "low",
        "thesis": "test",
        "invalidation": "x",
        "horizon_days": 5,
        "score": 0.7,
        "suggested_notional_usd": 1000,
    }
    base.update(kwargs)
    return TradeProposal(**base)  # type: ignore[arg-type]


def test_risk_rejects_live_when_disallowed(tmp_path, monkeypatch):
    cfg = {
        "allow_live": False,
        "max_notional_per_name_usd": 2000,
        "max_gross_exposure_usd": 10000,
        "max_daily_loss_usd": 250,
        "max_orders_per_cycle": 4,
        "max_crypto_weight": 0.3,
        "min_score": 0.55,
        "allowed_sides": ["long", "flat"],
        "kill_switch_path": str(tmp_path / "HALT"),
    }
    d = evaluate(
        _prop(),
        book_gross_usd=0,
        book_name_usd=0,
        day_pnl_usd=0,
        orders_this_cycle=0,
        crypto_weight=0,
        is_crypto=False,
        live=True,
        cfg=cfg,
    )
    assert d.allow is False
    assert "live" in d.reason


def test_risk_clips_and_allows_paper():
    cfg = {
        "allow_live": False,
        "max_notional_per_name_usd": 500,
        "max_gross_exposure_usd": 10000,
        "max_daily_loss_usd": 250,
        "max_orders_per_cycle": 4,
        "max_crypto_weight": 0.3,
        "min_score": 0.55,
        "allowed_sides": ["long", "flat"],
        "kill_switch_path": "data/artifacts/NO_HALT",
    }
    d = evaluate(
        _prop(suggested_notional_usd=2000),
        book_gross_usd=0,
        book_name_usd=0,
        day_pnl_usd=0,
        orders_this_cycle=0,
        crypto_weight=0,
        is_crypto=False,
        live=False,
        cfg=cfg,
    )
    assert d.allow is True
    assert d.clipped_notional_usd == 500


def test_risk_daily_loss_breaker():
    cfg = {
        "allow_live": False,
        "max_notional_per_name_usd": 2000,
        "max_gross_exposure_usd": 10000,
        "max_daily_loss_usd": 250,
        "max_orders_per_cycle": 4,
        "max_crypto_weight": 0.3,
        "min_score": 0.55,
        "allowed_sides": ["long", "flat"],
        "kill_switch_path": "data/artifacts/NO_HALT",
    }
    d = evaluate(
        _prop(),
        book_gross_usd=0,
        book_name_usd=0,
        day_pnl_usd=-251,
        orders_this_cycle=0,
        crypto_weight=0,
        is_crypto=False,
        live=False,
        cfg=cfg,
    )
    assert d.allow is False


def test_memory_roundtrip(tmp_path):
    conn = connect(tmp_path / "desk.sqlite")
    eid = write_episode(
        conn,
        {
            "ts": "2026-01-01T00:00:00Z",
            "symbol": "NVDA",
            "side": "long",
            "strategy": "sma_cross",
            "regime": "trend_up_calm",
            "score": 0.7,
            "notional": 500,
            "entry_px": 100,
            "thesis": "momentum continuation after quiet vol",
            "bull_brief": "trend",
            "bear_brief": "extended",
            "risk_reason": "passed",
            "submitted": 1,
            "lesson": "half size when RSI > 70",
            "outcome": "loss",
        },
    )
    assert eid >= 1
    hits = retrieve(conn, "NVDA RSI", k=3)
    assert any(h["symbol"] == "NVDA" for h in hits)
    apply_fill(conn, "NVDA", 500, 100, "2026-01-01T00:00:00Z")
    book = book_state(conn)
    assert book["by_name"]["NVDA"] == 500
    assert book["cash"] == 99500
