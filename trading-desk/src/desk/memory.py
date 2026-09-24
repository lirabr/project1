from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from desk.io_utils import ARTIFACT_DIR, ensure_dirs

DB_PATH = ARTIFACT_DIR / "desk.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    db = path or DB_PATH
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    _init(conn)
    from desk.ledger import initialize

    initialize(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT,
            regime TEXT,
            score REAL,
            notional REAL,
            entry_px REAL,
            thesis TEXT,
            bull_brief TEXT,
            bear_brief TEXT,
            risk_reason TEXT,
            submitted INTEGER DEFAULT 0,
            exit_ts TEXT,
            exit_px REAL,
            realized_r REAL,
            mae REAL,
            mfe REAL,
            holding_bars INTEGER,
            outcome TEXT,
            lesson TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS episode_fts USING fts5(
            symbol, regime, thesis, lesson, outcome,
            content='episodes', content_rowid='id'
        );
        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS book (
            symbol TEXT PRIMARY KEY,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            avg_px REAL NOT NULL,
            notional REAL NOT NULL,
            opened_ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_fills (
            fill_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            notional REAL NOT NULL,
            px REAL NOT NULL,
            ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cash (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usd REAL NOT NULL
        );
        """
    )
    if conn.execute("SELECT COUNT(*) FROM cash").fetchone()[0] == 0:
        conn.execute("INSERT INTO cash (id, usd) VALUES (1, 100000)")
    # Forward-compatible migration for older desk.sqlite files.
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)").fetchall()}
    for col, decl in (("mae", "REAL"), ("mfe", "REAL"), ("holding_bars", "INTEGER")):
        if col not in existing:
            conn.execute(f"ALTER TABLE episodes ADD COLUMN {col} {decl}")
    conn.commit()


def write_episode(conn: sqlite3.Connection, row: dict[str, Any]) -> int:
    cols = [
        "ts",
        "symbol",
        "side",
        "strategy",
        "regime",
        "score",
        "notional",
        "entry_px",
        "thesis",
        "bull_brief",
        "bear_brief",
        "risk_reason",
        "submitted",
        "lesson",
        "outcome",
    ]
    values = [row.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO episodes ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        values,
    )
    eid = int(cur.lastrowid)
    try:
        conn.execute(
            "INSERT INTO episode_fts(rowid, symbol, regime, thesis, lesson, outcome) VALUES (?,?,?,?,?,?)",
            (
                eid,
                row.get("symbol") or "",
                row.get("regime") or "",
                row.get("thesis") or "",
                row.get("lesson") or "",
                row.get("outcome") or "",
            ),
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return eid


def retrieve(conn: sqlite3.Connection, query: str, k: int = 3) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE lesson IS NOT NULL AND lesson != '' ORDER BY id DESC LIMIT ?",
            (k,),
        ).fetchall()
        return [dict(r) for r in rows]
    safe = q.replace('"', " ")
    try:
        rows = conn.execute(
            """
            SELECT e.* FROM episodes e
            JOIN episode_fts f ON f.rowid = e.id
            WHERE episode_fts MATCH ?
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (safe, k),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE thesis LIKE ? OR lesson LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", k),
        ).fetchall()
    return [dict(r) for r in rows]


def pending_reflections(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM episodes WHERE submitted = 1 AND lesson IS NULL AND entry_px IS NOT NULL"
    ).fetchall()
    return [dict(r) for r in rows]


def close_episode(
    conn: sqlite3.Connection,
    eid: int,
    exit_px: float,
    lesson: str,
    outcome: str,
    *,
    mae: float | None = None,
    mfe: float | None = None,
    holding_bars: int | None = None,
) -> None:
    row = conn.execute("SELECT entry_px FROM episodes WHERE id = ?", (eid,)).fetchone()
    if not row or not row["entry_px"]:
        return
    realized = float(exit_px) / float(row["entry_px"]) - 1.0
    ts = datetime.now(UTC).isoformat()
    conn.execute(
        """
        UPDATE episodes
        SET exit_ts = ?, exit_px = ?, realized_r = ?, mae = ?, mfe = ?,
            holding_bars = ?, lesson = ?, outcome = ?
        WHERE id = ?
        """,
        (ts, exit_px, realized, mae, mfe, holding_bars, lesson, outcome, eid),
    )
    conn.execute(
        "UPDATE episode_fts SET lesson = ?, outcome = ? WHERE rowid = ?",
        (lesson, outcome, eid),
    )
    conn.commit()


def book_state(conn: sqlite3.Connection, marks: dict[str, float] | None = None) -> dict[str, Any]:
    positions = [dict(r) for r in conn.execute("SELECT * FROM book").fetchall()]
    cash = float(conn.execute("SELECT usd FROM cash WHERE id = 1").fetchone()["usd"])
    if marks is not None and any(p["symbol"] not in marks or not math.isfinite(marks[p["symbol"]]) or marks[p["symbol"]] <= 0 for p in positions):
        raise ValueError("Every held position needs a valid mark")
    by_name = {p["symbol"]: p["notional"] if marks is None else p["qty"] * marks[p["symbol"]] for p in positions}
    gross = sum(abs(value) for value in by_name.values())
    crypto_notional = sum(value for symbol, value in by_name.items() if symbol.endswith("-USD") or "/" in symbol)
    pending = conn.execute("SELECT symbol,SUM((quantity-filled)*max_unit_cost) AS value FROM desk_orders WHERE side='buy' AND status IN ('OPEN','PARTIAL','UNKNOWN') GROUP BY symbol").fetchall()
    reserved = {r["symbol"]: r["value"] for r in pending}
    crypto_weight = (crypto_notional / gross) if gross else 0.0
    return {
        "cash": cash,
        "gross": gross,
        "positions": positions,
        "by_name": by_name,
        "crypto_weight": crypto_weight,
        "equity": cash + gross,
        "valuation": "cost" if marks is None else "marked",
        "reserved_cash": sum(reserved.values()),
        "reserved_by_name": reserved,
        "has_unknown_orders": bool(conn.execute("SELECT 1 FROM desk_orders WHERE status='UNKNOWN'").fetchone()),
    }


def unrealized_pnl(conn: sqlite3.Connection, marks: dict[str, float]) -> float:
    """Mark-to-market P&L of the open book against provided last closes.

    `marks` maps symbol -> latest close. Positions without a mark contribute 0.
    This is the number the daily-loss circuit breaker consumes; it is computed
    from the deterministic book, never from an agent.
    """
    total = 0.0
    for p in conn.execute("SELECT symbol, qty, avg_px FROM book").fetchall():
        mark = marks.get(p["symbol"])
        if mark is None:
            continue
        total += (float(mark) - float(p["avg_px"])) * float(p["qty"])
    return total


def apply_fill(conn: sqlite3.Connection, symbol: str, notional: float, px: float, ts: str, *, fill_id: str | None = None) -> bool:
    if not all(math.isfinite(v) and v > 0 for v in (notional, px)):
        return False
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if fill_id:
            recorded = conn.execute("SELECT * FROM paper_fills WHERE fill_id = ?", (fill_id,)).fetchone()
            if recorded:
                if (recorded["symbol"], recorded["notional"], recorded["px"]) != (symbol, notional, px):
                    raise ValueError("Conflicting reuse of fill_id")
                return True
        if conn.execute("SELECT 1 FROM desk_orders LIMIT 1").fetchone():
            return False
        qty = notional / px
        existing = conn.execute("SELECT * FROM book WHERE symbol = ?", (symbol,)).fetchone()
        cash = float(conn.execute("SELECT usd FROM cash WHERE id = 1").fetchone()["usd"])
        reserved = conn.execute("SELECT COALESCE(SUM((quantity-filled)*max_unit_cost),0) FROM desk_orders WHERE side='buy' AND status IN ('OPEN','PARTIAL','UNKNOWN')").fetchone()[0]
        if cash < notional + reserved or conn.execute("SELECT 1 FROM desk_orders WHERE status='UNKNOWN'").fetchone():
            return False
        if existing:
            new_qty = existing["qty"] + qty
            new_notional = existing["notional"] + notional
            avg = new_notional / new_qty
            conn.execute(
                "UPDATE book SET qty=?, avg_px=?, notional=? WHERE symbol=?",
                (new_qty, avg, new_notional, symbol),
            )
        else:
            conn.execute(
                "INSERT INTO book (symbol, side, qty, avg_px, notional, opened_ts) VALUES (?,?,?,?,?,?)",
                (symbol, "long", qty, px, notional, ts),
            )
        conn.execute("UPDATE cash SET usd = usd - ? WHERE id = 1", (notional,))
        if fill_id:
            conn.execute("INSERT INTO paper_fills VALUES (?, ?, ?, ?, ?)", (fill_id, symbol, notional, px, ts))
    return True
