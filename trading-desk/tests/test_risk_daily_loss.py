from __future__ import annotations

from desk.memory import apply_fill, connect, unrealized_pnl


def test_unrealized_pnl_matches_marks(tmp_path):
    conn = connect(tmp_path / "desk.sqlite")
    # Buy $1000 of AAA at 100 -> 10 shares.
    apply_fill(conn, "AAA", 1000.0, 100.0, "2026-01-01T00:00:00Z")
    # Mark down to 90 -> loss of 10 * (90-100) = -100.
    pnl = unrealized_pnl(conn, {"AAA": 90.0})
    assert abs(pnl - (-100.0)) < 1e-6
    # Mark up to 110 -> +100.
    assert abs(unrealized_pnl(conn, {"AAA": 110.0}) - 100.0) < 1e-6
    # Missing mark contributes zero.
    assert unrealized_pnl(conn, {}) == 0.0


def test_daily_loss_breaker_fires_from_book(tmp_path):
    """A losing open book must produce a day_pnl that trips the breaker in the gate."""
    from desk.contracts import TradeProposal
    from desk.risk_gate import evaluate

    conn = connect(tmp_path / "desk.sqlite")
    apply_fill(conn, "AAA", 5000.0, 100.0, "2026-01-01T00:00:00Z")  # 50 shares
    day_pnl = unrealized_pnl(conn, {"AAA": 90.0})  # -500
    assert day_pnl < -250

    cfg = {
        "allow_live": False,
        "max_notional_per_name_usd": 2000,
        "max_gross_exposure_usd": 10000,
        "max_daily_loss_usd": 250,
        "max_orders_per_cycle": 4,
        "max_crypto_weight": 0.3,
        "min_score": 0.55,
        "allowed_sides": ["long", "flat"],
        "kill_switch_path": str(tmp_path / "NO_HALT"),
    }
    prop = TradeProposal(
        symbol="BBB", side="long", urgency="low", thesis="t", invalidation="x",
        horizon_days=5, score=0.7, suggested_notional_usd=1000,
    )
    d = evaluate(
        prop,
        book_gross_usd=5000,
        book_name_usd=0,
        day_pnl_usd=day_pnl,
        orders_this_cycle=0,
        crypto_weight=0,
        is_crypto=False,
        live=False,
        cfg=cfg,
    )
    assert d.allow is False
    assert d.reason == "daily loss circuit breaker"
