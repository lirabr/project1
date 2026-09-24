from datetime import UTC, datetime, timedelta

import pytest

from desk import ledger
from desk.memory import connect
from desk.portfolio import Mark, PortfolioTarget, digest, plan_rebalance

NOW = datetime(2026, 9, 24, 14, tzinfo=UTC)


@pytest.fixture
def desk(tmp_path):
    conn = connect(tmp_path / "ledger.sqlite")
    ledger.initialize(conn)
    marks = {"A": Mark(100, NOW.isoformat())}
    ledger.open_session(conn, "session", marks, NOW)
    cfg = {"max_notional_per_name_usd": 2000, "max_gross_exposure_usd": 10000,
           "max_daily_loss_usd": 250, "max_orders_per_cycle": 4, "max_crypto_weight": .3,
           "kill_switch_path": str(tmp_path / "HALT")}
    t = PortfolioTarget({"A": .01}, (NOW - timedelta(seconds=2)).isoformat(),
                        (NOW - timedelta(seconds=1)).isoformat(), "model", "data", "config")
    order = plan_rebalance(t, {}, 100000, marks, NOW)[0]
    approval = ledger.Approval(t.target_id, digest(cfg), "operator", (NOW + timedelta(minutes=5)).isoformat(), order.order_id, 100)
    yield conn, marks, cfg, order, approval
    conn.close()


def accept(desk):
    conn, marks, cfg, order, approval = desk
    ledger.accept_order(conn, order, approval, marks, NOW, cfg, "session", cost_bps=100)
    return order


def test_partial_fills_fees_exit_and_duplicate(desk):
    conn, marks, cfg, order, approval = desk
    accept(desk)
    ledger.record_fill(conn, order.order_id, "f1", 4, 100, 1, NOW, cfg)
    state = ledger.marked_book(conn, marks, NOW)
    assert state["cash"] == 99599
    assert state["reserved_cash"] == 606
    assert ledger.order_state(conn, order.order_id)["status"] == "PARTIAL"
    ledger.record_fill(conn, order.order_id, "f1", 4, 100, 1, NOW + timedelta(hours=1), cfg)
    assert ledger.marked_book(conn, marks, NOW)["cash"] == 99599
    with pytest.raises(ValueError, match="Conflicting"):
        ledger.record_fill(conn, order.order_id, "f1", 5, 100, 1, NOW, cfg)
    ledger.record_fill(conn, order.order_id, "f2", 6, 100, 1, NOW, cfg)
    assert ledger.order_state(conn, order.order_id)["status"] == "FILLED"
    from desk.memory import apply_fill

    assert not apply_fill(conn, "A", 100, 100, NOW.isoformat())
    changed = {"A": Mark(110, NOW.isoformat())}
    t = PortfolioTarget({"A": 0.}, (NOW - timedelta(seconds=2)).isoformat(),
                        (NOW - timedelta(seconds=1)).isoformat(), "model", "data", "config")
    sell = plan_rebalance(t, {"A": 10}, 98998, changed, NOW)[0]
    auth = ledger.Approval(t.target_id, digest(cfg), "operator", approval.expires_at, sell.order_id, 100)
    ledger.accept_order(conn, sell, auth, changed, NOW, cfg, "session", cost_bps=100)
    ledger.record_fill(conn, sell.order_id, "exit", 10, 110, 1, NOW, cfg)
    state = ledger.marked_book(conn, {}, NOW)
    assert state["positions"] == []
    assert state["equity"] == 100097
    assert state["realized_pnl"] == pytest.approx(97)
    assert ledger.session_pnl(conn, "session", state["equity"]) == pytest.approx(97)


def test_reservations_halt_policy_expiry_and_unknown_fail_closed(desk):
    conn, marks, cfg, order, approval = desk
    accept(desk)
    assert ledger.marked_book(conn, marks, NOW)["reserved_cash"] == 1010
    assert ledger.accept_order(conn, order, approval, marks, NOW, cfg, "session", cost_bps=100) == order.order_id
    with pytest.raises(ValueError):
        ledger.record_fill(conn, order.order_id, "bad", 1, 100, 0, NOW, {**cfg, "max_daily_loss_usd": 500})
    with pytest.raises(ValueError):
        ledger.record_fill(conn, order.order_id, "late", 1, 100, 0, NOW + timedelta(hours=1), cfg)
    ledger.mark_unknown(conn, order.order_id)
    with pytest.raises(ValueError):
        ledger.cancel_order(conn, order.order_id)
    assert ledger.marked_book(conn, marks, NOW)["reserved_cash"] == 1010


def test_cancel_and_overfill_are_atomic(desk):
    conn, marks, cfg, order, _approval = desk
    accept(desk)
    with pytest.raises(ValueError):
        ledger.record_fill(conn, order.order_id, "bad", 11, 100, 0, NOW, cfg)
    assert ledger.marked_book(conn, marks, NOW)["cash"] == 100000
    ledger.cancel_order(conn, order.order_id)
    assert ledger.marked_book(conn, marks, NOW)["reserved_cash"] == 0
    with pytest.raises(ValueError):
        ledger.record_fill(conn, order.order_id, "cancelled", 1, 100, 0, NOW, cfg)


def test_missing_mark_and_cashflow_adjusted_session(desk):
    conn, marks, cfg, order, _approval = desk
    accept(desk)
    ledger.record_fill(conn, order.order_id, "fill", 10, 100, 0, NOW, cfg)
    with pytest.raises(ValueError):
        ledger.marked_book(conn, {}, NOW)
    ledger.cashflow(conn, "deposit", 500, NOW)
    assert ledger.session_pnl(conn, "session", ledger.marked_book(conn, marks, NOW)["equity"]) == 0
    ledger.open_session(conn, "session", marks, NOW)
    assert ledger.session_pnl(conn, "session", 100400) == -100


def test_reservations_cannot_overcommit_across_connections(desk):
    conn, marks, cfg, order, approval = desk
    accept(desk)
    from dataclasses import replace

    other_id = digest([order.target_id, order.symbol, order.side, 20., order.reference_price])
    other = replace(order, order_id=other_id, quantity=20.)
    other_approval = replace(approval, order_id=other_id)
    from pathlib import Path

    second = connect(Path(conn.execute("PRAGMA database_list").fetchone()[2]))
    try:
        with pytest.raises(ValueError, match="Projected name limit"):
            ledger.accept_order(second, other, other_approval, marks, NOW, cfg, "session", cost_bps=100)
    finally:
        second.close()
    assert len(conn.execute("SELECT * FROM desk_orders").fetchall()) == 1


def test_audit_write_failure_rolls_back_fill_and_cash(desk):
    import sqlite3

    conn, marks, cfg, order, _approval = desk
    accept(desk)
    conn.execute("CREATE TEMP TRIGGER reject_fill_event BEFORE INSERT ON desk_events WHEN NEW.kind='fill' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_fill(conn, order.order_id, "f1", 4, 100, 0, NOW, cfg)
    assert ledger.marked_book(conn, marks, NOW)["cash"] == 100000
    assert ledger.order_state(conn, order.order_id)["filled"] == 0
    assert conn.execute("SELECT COUNT(*) FROM desk_fills").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 0


def test_halt_and_price_cost_changes_cannot_fill(desk):
    from pathlib import Path

    conn, _marks, cfg, order, _approval = desk
    accept(desk)
    with pytest.raises(ValueError, match="all-in cost"):
        ledger.record_fill(conn, order.order_id, "cost", 1, 102, 0, NOW, cfg)
    Path(cfg["kill_switch_path"]).write_text("halt")
    with pytest.raises(ValueError, match="HALT"):
        ledger.record_fill(conn, order.order_id, "halted", 1, 100, 0, NOW, cfg)
    assert ledger.order_state(conn, order.order_id)["filled"] == 0


def test_unknown_blocks_new_risk_and_preserves_cash_reservation(desk):
    from dataclasses import replace

    conn, marks, cfg, order, approval = desk
    accept(desk)
    ledger.mark_unknown(conn, order.order_id)
    other_id = digest([order.target_id, order.symbol, order.side, 1., order.reference_price])
    other = replace(order, order_id=other_id, quantity=1.)
    with pytest.raises(ValueError, match="Unresolved"):
        ledger.accept_order(conn, other, replace(approval, order_id=other_id), marks, NOW, cfg, "session", cost_bps=100)
    assert ledger.marked_book(conn, marks, NOW)["reserved_cash"] == 1010


def test_reopen_preserves_fill_and_session_baseline(desk):
    from pathlib import Path

    conn, marks, cfg, order, _approval = desk
    accept(desk)
    ledger.record_fill(conn, order.order_id, "f1", 4, 100, 1, NOW, cfg)
    second = connect(Path(conn.execute("PRAGMA database_list").fetchone()[2]))
    try:
        ledger.record_fill(second, order.order_id, "f1", 4, 100, 1, NOW, cfg)
        state = ledger.marked_book(second, marks, NOW)
        assert state["cash"] == 99599
        assert ledger.session_pnl(second, "session", state["equity"]) == -1
        assert ledger.order_state(second, order.order_id)["status"] == "PARTIAL"
    finally:
        second.close()
