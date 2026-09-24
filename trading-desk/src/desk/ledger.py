from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime

from desk.portfolio import Mark, PlannedOrder, digest, finite, timestamp

OPEN = ("OPEN", "PARTIAL", "UNKNOWN")


@dataclass(frozen=True)
class Approval:
    target_id: str
    policy_version: str
    reviewer: str
    expires_at: str
    order_id: str
    max_cost_bps: float = 0


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS desk_orders (
            order_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, symbol TEXT NOT NULL,
            side TEXT NOT NULL, quantity REAL NOT NULL, filled REAL NOT NULL DEFAULT 0,
            max_unit_cost REAL NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
            session_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS desk_fills (
            fill_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, quantity REAL NOT NULL,
            price REAL NOT NULL, fee REAL NOT NULL, realized REAL NOT NULL, ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS desk_events (
            seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS desk_cashflows (
            seq INTEGER PRIMARY KEY, flow_id TEXT UNIQUE NOT NULL, amount REAL NOT NULL, ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS desk_sessions (
            session_id TEXT PRIMARY KEY, equity REAL NOT NULL, flow_seq INTEGER NOT NULL, ts TEXT NOT NULL
        );
    """)


def _event(conn, kind, entity_id, payload):
    conn.execute("INSERT INTO desk_events(kind, entity_id, payload) VALUES (?,?,?)",
                 (kind, entity_id, json.dumps(payload, sort_keys=True, allow_nan=False)))


def order_state(conn, order_id: str) -> dict:
    row = conn.execute("SELECT * FROM desk_orders WHERE order_id=?", (order_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown order")
    return dict(row)


def marked_book(conn, marks: dict[str, Mark], now: datetime, max_age_seconds: float = 300) -> dict:
    positions = [dict(r) for r in conn.execute("SELECT * FROM book WHERE qty > 0")]
    missing = {p["symbol"] for p in positions} - marks.keys()
    if missing:
        raise ValueError(f"Missing position marks: {sorted(missing)}")
    cash = finite(conn.execute("SELECT usd FROM cash WHERE id=1").fetchone()[0])
    by_name = {p["symbol"]: finite(p["qty"]) * marks[p["symbol"]].validate(now, max_age_seconds) for p in positions}
    reserved_by_name = {}
    pending = conn.execute("SELECT * FROM desk_orders WHERE status IN ('OPEN','PARTIAL','UNKNOWN')").fetchall()
    for order in pending:
        if order["side"] == "buy":
            s = order["symbol"]
            reserved_by_name[s] = reserved_by_name.get(s, 0) + (order["quantity"] - order["filled"]) * order["max_unit_cost"]
    gross = sum(by_name.values())
    reserved = sum(reserved_by_name.values())
    realized = float(conn.execute("SELECT COALESCE(SUM(realized),0) FROM desk_fills").fetchone()[0])
    fees = float(conn.execute("SELECT COALESCE(SUM(fee),0) FROM desk_fills").fetchone()[0])
    return {"positions": positions, "cash": cash, "equity": cash + gross, "gross": gross,
            "by_name": by_name, "reserved_cash": reserved, "reserved_by_name": reserved_by_name,
            "available_cash": cash - reserved, "realized_pnl": realized, "fees": fees,
            "unrealized_pnl": sum(by_name[p["symbol"]] - p["notional"] for p in positions)}


def open_session(conn, session_id: str, marks: dict[str, Mark], now: datetime) -> None:
    if not session_id.strip():
        raise ValueError("Explicit venue session ID required")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM desk_sessions WHERE session_id=?", (session_id,)).fetchone():
            return
        state = marked_book(conn, marks, now)
        flow_seq = conn.execute("SELECT COALESCE(MAX(seq),0) FROM desk_cashflows").fetchone()[0]
        conn.execute("INSERT INTO desk_sessions VALUES (?,?,?,?)", (session_id, state["equity"], flow_seq, now.isoformat()))
        _event(conn, "session_open", session_id, {"equity": state["equity"], "ts": now.isoformat()})


def session_pnl(conn, session_id: str, equity: float, now: datetime | None = None) -> float:
    row = conn.execute("SELECT * FROM desk_sessions WHERE session_id=?", (session_id,)).fetchone()
    if row is None:
        raise ValueError("Session baseline missing; initialize at the session boundary")
    if now is not None and not 0 <= (now - timestamp(row["ts"])).total_seconds() <= 26 * 3600:
        raise ValueError("Session baseline is stale or in the future")
    flows = conn.execute("SELECT COALESCE(SUM(amount),0) FROM desk_cashflows WHERE seq>?", (row["flow_seq"],)).fetchone()[0]
    return finite(equity) - row["equity"] - flows


def cashflow(conn, flow_id: str, amount: float, now: datetime) -> None:
    finite(abs(amount))
    if not flow_id:
        raise ValueError("Cashflow ID required")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT amount, ts FROM desk_cashflows WHERE flow_id=?", (flow_id,)).fetchone()
        if row:
            if row["amount"] != amount:
                raise ValueError("Conflicting cashflow ID")
            return
        cash = conn.execute("SELECT usd FROM cash WHERE id=1").fetchone()[0]
        reserved = conn.execute("SELECT COALESCE(SUM((quantity-filled)*max_unit_cost),0) FROM desk_orders WHERE side='buy' AND status IN ('OPEN','PARTIAL','UNKNOWN')").fetchone()[0]
        if cash + amount < reserved:
            raise ValueError("Cashflow would consume reserved cash")
        conn.execute("UPDATE cash SET usd=usd+? WHERE id=1", (amount,))
        conn.execute("INSERT INTO desk_cashflows(flow_id,amount,ts) VALUES (?,?,?)", (flow_id, amount, now.isoformat()))
        _event(conn, "cashflow", flow_id, {"amount": amount, "ts": now.isoformat()})


def _validate_approval(approval: Approval, order: PlannedOrder, now: datetime, cfg: dict):
    if (approval.target_id != order.target_id or approval.order_id != order.order_id
            or approval.policy_version != digest(cfg) or not approval.reviewer.strip()
            or not 0 < (timestamp(approval.expires_at) - now).total_seconds() <= finite(cfg.get("approval_ttl_seconds", 300))):
        raise ValueError("Invalid, expired or changed approval")
    from desk.risk_gate import halt_path

    if halt_path(cfg).exists():
        raise ValueError("HALT is active")


def _buy_risk(conn, state, symbol, notional, cfg, session_id):
    if conn.execute("SELECT 1 FROM desk_orders WHERE status='UNKNOWN'").fetchone():
        raise ValueError("Unresolved order outcome")
    if session_pnl(conn, session_id, state["equity"]) <= -finite(cfg.get("max_daily_loss_usd", 250)):
        raise ValueError("Session loss limit")
    if notional > state["available_cash"] + 1e-8:
        raise ValueError("Insufficient unreserved cash")
    name = state["by_name"].get(symbol, 0) + state["reserved_by_name"].get(symbol, 0) + notional
    name_cap = min(finite(cfg.get("max_notional_per_name_usd", 2000)),
                   finite(cfg.get("max_name_weight", 1)) * state["equity"])
    if name > name_cap + 1e-8:
        raise ValueError("Projected name limit")
    gross = state["gross"] + state["reserved_cash"] + notional
    if gross > finite(cfg.get("max_gross_exposure_usd", 10000)) + 1e-8:
        raise ValueError("Projected gross limit")
    crypto = sum(v for s, v in state["by_name"].items() if s.endswith("-USD") or "/" in s)
    crypto += sum(v for s, v in state["reserved_by_name"].items() if s.endswith("-USD") or "/" in s)
    if symbol.endswith("-USD") or "/" in symbol:
        crypto += notional
    limit = finite(cfg.get("max_crypto_weight", .3))
    if limit > 1 or (gross and crypto / gross > limit + 1e-10):
        raise ValueError("Projected crypto limit")


def accept_order(conn, order: PlannedOrder, approval: Approval, marks: dict[str, Mark], now: datetime,
                 cfg: dict, session_id: str, *, cost_bps: float = 0) -> str:
    _validate_approval(approval, order, now, cfg)
    expected_id = digest([order.target_id, order.symbol, order.side, order.quantity, order.reference_price])
    if order.order_id != expected_id or cost_bps != approval.max_cost_bps or finite(cost_bps) > finite(cfg.get("max_paper_cost_bps", 100)):
        raise ValueError("Order or cost allowance differs from approval")
    if order.side not in {"buy", "sell"} or finite(order.quantity) <= 0 or finite(order.reference_price) <= 0:
        raise ValueError("Invalid order")
    price = marks[order.symbol].validate(now) if order.symbol in marks else 0
    if price != order.reference_price:
        raise ValueError("Mark changed; replan and approve")
    payload = {"order": asdict(order), "approval": asdict(approval), "cost_bps": finite(cost_bps),
               "marks": {s: asdict(m) for s, m in marks.items()}}
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    unit = price * (1 + cost_bps / 10000)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM desk_orders WHERE order_id=?", (order.order_id,)).fetchone()
        if existing:
            if existing["payload"] != encoded or existing["session_id"] != session_id:
                raise ValueError("Conflicting order ID")
            return order.order_id
        state = marked_book(conn, marks, now)
        session_pnl(conn, session_id, state["equity"], now)
        count = conn.execute("SELECT COUNT(*) FROM desk_orders WHERE target_id=?", (order.target_id,)).fetchone()[0]
        if count >= int(cfg.get("max_orders_per_cycle", 4)):
            raise ValueError("Order budget exhausted")
        if order.side == "buy":
            _buy_risk(conn, state, order.symbol, order.quantity * unit, cfg, session_id)
        else:
            held = next((p["qty"] for p in state["positions"] if p["symbol"] == order.symbol), 0)
            reserved = conn.execute("SELECT COALESCE(SUM(quantity-filled),0) FROM desk_orders WHERE symbol=? AND side='sell' AND status IN ('OPEN','PARTIAL','UNKNOWN')", (order.symbol,)).fetchone()[0]
            if order.quantity > held - reserved + 1e-10:
                raise ValueError("Insufficient unreserved shares")
        conn.execute("INSERT INTO desk_orders VALUES (?,?,?,?,?,0,?,'OPEN',?,?)",
                     (order.order_id, order.target_id, order.symbol, order.side, order.quantity, unit, encoded, session_id))
        _event(conn, "order_accepted", order.order_id, payload)
    return order.order_id


def record_fill(conn, order_id: str, fill_id: str, quantity: float, price: float, fee: float,
                now: datetime, cfg: dict, *, marks: dict[str, Mark] | None = None) -> None:
    if finite(quantity) <= 0 or finite(price) <= 0:
        raise ValueError("Fill quantity and price must be positive")
    finite(fee)
    if not fill_id:
        raise ValueError("Fill ID required")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT order_id,quantity,price,fee FROM desk_fills WHERE fill_id=?", (fill_id,)).fetchone()
        values = (order_id, quantity, price, fee)
        if previous:
            if tuple(previous) != values:
                raise ValueError("Conflicting fill ID")
            return
        row = order_state(conn, order_id)
        payload = json.loads(row["payload"])
        order = PlannedOrder(**payload["order"])
        _validate_approval(Approval(**payload["approval"]), order, now, cfg)
        if row["status"] not in {"OPEN", "PARTIAL"} or quantity > row["quantity"] - row["filled"] + 1e-10:
            raise ValueError("Order not fillable or quantity exceeds remainder")
        marks = dict(marks) if marks is not None else {s: Mark(**m) for s, m in payload["marks"].items()}
        marks[order.symbol] = Mark(price, now.isoformat())
        state = marked_book(conn, marks, now)
        session_pnl(conn, row["session_id"], state["equity"], now)
        if order.side == "sell" and price - fee / quantity < order.reference_price * (1 - payload["cost_bps"] / 10000) - 1e-8:
            raise ValueError("Sell fill exceeds approved all-in cost")
        if order.side == "buy":
            if price + fee / quantity > row["max_unit_cost"] + 1e-8:
                raise ValueError("Fill exceeds approved all-in cost")
            _buy_risk(conn, state, order.symbol, 0, cfg, row["session_id"])
        held = conn.execute("SELECT * FROM book WHERE symbol=?", (order.symbol,)).fetchone()
        old_qty, old_cost = (held["qty"], held["notional"]) if held else (0., 0.)
        if order.side == "buy":
            debit = quantity * price + fee
            other_reserved = state["reserved_cash"] - (row["quantity"] - row["filled"]) * row["max_unit_cost"]
            remaining_reserve = (row["quantity"] - row["filled"] - quantity) * row["max_unit_cost"]
            if state["cash"] - debit < other_reserved + remaining_reserve - 1e-8:
                raise ValueError("Fill would overdraw reserved cash")
            new_qty, new_cost, realized = old_qty + quantity, old_cost + debit, 0.
            cash_delta = -debit
        else:
            if quantity > old_qty + 1e-10:
                raise ValueError("Cannot sell unowned shares")
            released = old_cost * quantity / old_qty
            new_qty, new_cost = old_qty - quantity, old_cost - released
            cash_delta = quantity * price - fee
            realized = cash_delta - released
        if new_qty <= 1e-10:
            conn.execute("DELETE FROM book WHERE symbol=?", (order.symbol,))
        else:
            opened = held["opened_ts"] if held else now.isoformat()
            conn.execute("INSERT INTO book VALUES (?, 'long', ?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET qty=excluded.qty,avg_px=excluded.avg_px,notional=excluded.notional",
                         (order.symbol, new_qty, new_cost / new_qty, new_cost, opened))
        if state["cash"] + cash_delta < -1e-8:
            raise ValueError("Fill would overdraw cash")
        conn.execute("UPDATE cash SET usd=usd+? WHERE id=1", (cash_delta,))
        filled = row["filled"] + quantity
        status = "FILLED" if abs(filled - row["quantity"]) < 1e-10 else "PARTIAL"
        conn.execute("UPDATE desk_orders SET filled=?,status=? WHERE order_id=?", (filled, status, order_id))
        conn.execute("INSERT INTO desk_fills VALUES (?,?,?,?,?,?,?)", (fill_id, order_id, quantity, price, fee, realized, now.isoformat()))
        _event(conn, "fill", fill_id, {"order_id": order_id, "quantity": quantity, "price": price,
                                     "fee": fee, "realized": realized, "ts": now.isoformat()})


def _transition(conn, order_id: str, status: str) -> None:
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = order_state(conn, order_id)
        if row["status"] == status:
            return
        if row["status"] not in {"OPEN", "PARTIAL"}:
            raise ValueError("Terminal or unresolved order cannot transition")
        conn.execute("UPDATE desk_orders SET status=? WHERE order_id=?", (status, order_id))
        _event(conn, status.lower(), order_id, {"filled": row["filled"]})


def cancel_order(conn, order_id: str) -> None:
    _transition(conn, order_id, "CANCELLED")


def mark_unknown(conn, order_id: str) -> None:
    _transition(conn, order_id, "UNKNOWN")
