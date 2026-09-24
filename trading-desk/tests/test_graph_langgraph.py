from __future__ import annotations

import importlib.util
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="langgraph extra not installed (uv sync --extra graph)",
)


def _fake_card(symbol="AAPL", score=0.8):
    return {
        "symbol": symbol,
        "strategy": "sma_cross",
        "score": score,
        "last_close": 100.0,
        "as_of": "2026-01-01",
        "features": {
            "ret_20": 0.03, "vol_20": 0.01, "rsi_14": 55.0,
            "sma_ratio_20_50": 0.01, "dist_sma_20": 0.0, "ret_5": 0.01,
        },
        "note": "regime=trend_up_calm",
    }


@pytest.fixture()
def desk_env(tmp_path, monkeypatch):
    """Isolate all desk state under tmp and stub the data-dependent nodes."""
    from desk import graph as G
    from desk import memory as M
    from desk import vectors as V

    db = tmp_path / "desk.sqlite"
    monkeypatch.setattr(M, "DB_PATH", db)

    # snapshot: one high-score card, no data files needed
    monkeypatch.setattr(
        G, "node_snapshot",
        lambda state: {"ts": datetime.now(UTC).isoformat(), "cards": [_fake_card()], "focus_index": 0, "day_pnl": 0.0},
    )
    # retrieve: no memories
    monkeypatch.setattr(G, "node_retrieve", lambda state: {"memories": []})
    # keep vectors.upsert a no-op to avoid extra tables in this focused test
    monkeypatch.setattr(V, "upsert", lambda *a, **k: None)
    monkeypatch.setattr(G, "upsert", lambda *a, **k: None)
    return G, db


def _build(G, require_human=True, halt=False, tmp_path=None, monkeypatch=None):
    from langgraph.checkpoint.memory import MemorySaver

    cfg = {
        "allow_live": False, "max_notional_per_name_usd": 2000, "max_gross_exposure_usd": 10000,
        "max_daily_loss_usd": 250, "max_orders_per_cycle": 4, "max_crypto_weight": 0.3,
        "min_score": 0.55, "allowed_sides": ["long", "flat"], "require_human_approve": require_human,
        "kill_switch_path": str(tmp_path / "HALT") if halt else str(tmp_path / "NO_HALT"),
    }
    if halt:
        (tmp_path / "HALT").write_text("halt\n")
    monkeypatch.setattr(G, "load_risk_cfg", lambda *a, **k: cfg)
    monkeypatch.setattr("desk.desk_cfg_stub", cfg, raising=False)
    # desk.yaml / phase3.yaml loads inside nodes -> stub load_yaml minimal
    monkeypatch.setattr(G, "load_yaml", lambda *a, **k: {"llm": {"enabled": False}, "retrieve_k": 3})
    return G.build_desk(checkpointer=MemorySaver())


def test_halt_blocks_no_fill(desk_env, tmp_path, monkeypatch):
    G, db = desk_env
    graph = _build(G, require_human=False, halt=True, tmp_path=tmp_path, monkeypatch=monkeypatch)
    result = graph.invoke({"thread_id": "t-halt"}, {"configurable": {"thread_id": "t-halt"}})
    dec = result["decisions"][0]
    assert dec["risk"]["allow"] is False
    assert dec["submitted"] is False
    # book must be empty
    from desk.memory import book_state, connect
    conn = connect(db)
    assert book_state(conn)["gross"] == 0


def test_interrupt_pauses_then_resume_fills(desk_env, tmp_path, monkeypatch):
    from langgraph.types import Command

    G, db = desk_env
    graph = _build(G, require_human=True, halt=False, tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = {"configurable": {"thread_id": "t-hitl"}}

    out = graph.invoke({"thread_id": "t-hitl"}, config)
    # Paused at human_approve -> no decision written yet, book still empty
    from desk.memory import book_state, connect
    conn = connect(db)
    assert book_state(conn)["gross"] == 0
    assert "__interrupt__" in out or out.get("decisions") in (None, [])

    # Reject first -> still no fill
    graph.invoke(Command(resume="reject"), config)
    conn = connect(db)
    assert book_state(conn)["gross"] == 0


def test_interrupt_approve_fills(desk_env, tmp_path, monkeypatch):
    from langgraph.types import Command

    G, db = desk_env
    graph = _build(G, require_human=True, halt=False, tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = {"configurable": {"thread_id": "t-approve"}}
    graph.invoke({"thread_id": "t-approve"}, config)
    graph.invoke(Command(resume="approve"), config)
    from desk.memory import book_state, connect
    conn = connect(db)
    assert book_state(conn)["gross"] > 0


def test_halt_after_approval_pause_blocks(desk_env, tmp_path, monkeypatch):
    from langgraph.types import Command

    from desk.memory import book_state, connect

    G, db = desk_env
    graph = _build(G, tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = {"configurable": {"thread_id": "late-halt"}}
    graph.invoke({"thread_id": "late-halt"}, config)
    (tmp_path / "NO_HALT").write_text("halt")
    result = graph.invoke(Command(resume="approve"), config)
    assert not result["decisions"][0]["submitted"]
    assert book_state(connect(db))["gross"] == 0


def test_next_card_resets_submission_state(desk_env):
    G, _ = desk_env
    state = {"cards": [_fake_card()], "focus_index": 0, "submitted": True, "human": "approve"}
    update = G.node_pick_next(state)
    assert update.get("submitted") is False
    assert update.get("human") == ""


def test_graph_counts_orders(desk_env, tmp_path, monkeypatch):
    G, _ = desk_env
    _build(G, require_human=False, tmp_path=tmp_path, monkeypatch=monkeypatch)
    state = {"proposal": {"symbol": "AAPL", "side": "long", "urgency": "low", "thesis": "test",
                          "invalidation": "test", "horizon_days": 5, "score": .8,
                          "suggested_notional_usd": 1000.},
             "decisions": [{"submitted": True}] * 4, "day_pnl": 0.}
    assert not G.node_risk_gate(state)["risk"]["allow"]


def test_expired_snapshot_cannot_fill(desk_env):
    G, _ = desk_env
    state = {"ts": "2000-01-01T00:00:00+00:00", "card": _fake_card(),
             "human": "approve", "risk": {"allow": True, "clipped_notional_usd": 100.}}
    result = G.node_paper_fill(state)
    assert result["submitted"] is False
    assert result["risk"]["reason"] == "approval expired"


def test_revalidation_never_increases_approved_size(desk_env, monkeypatch):
    from desk.memory import book_state, connect

    G, db = desk_env
    monkeypatch.setattr(G, "node_risk_gate", lambda state: {"risk": {"allow": True, "clipped_notional_usd": 1000.}})
    state = {"ts": datetime.now(UTC).isoformat(), "card": _fake_card(), "thread_id": "bounded",
             "human": "approve", "risk": {"allow": True, "clipped_notional_usd": 100.}}
    assert G.node_paper_fill(state)["submitted"] is True
    assert G.node_paper_fill(state)["submitted"] is True
    assert book_state(connect(db))["gross"] == 100.
