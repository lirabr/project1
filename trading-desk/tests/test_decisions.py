from datetime import UTC, datetime

import pytest

from desk.agents import analyst_evidence
from desk.contracts import ModelCard
from desk.decisions import eligible_memories
from desk.memory import connect, write_episode


def card():
    return ModelCard("SPY", "sma_cross", .8, 100, "2026-09-24",
                     {"ret_20": .03, "vol_20": .01, "rsi_14": 55, "sma_ratio_20_50": .02},
                     "equity regime=trend_up_calm", "rule-v1", "data-v1")


def test_analyst_evidence_has_provenance_and_missing_values():
    c = card()
    items = analyst_evidence(c)
    assert any(i["role"] == "bull" and i["triggered"] for i in items)
    assert all(i["as_of"] == c.as_of and i["data_version"] == "data-v1" for i in items)
    c.features.pop("rsi_14")
    missing = [i for i in analyst_evidence(c) if i["feature"] == "rsi_14"]
    assert all(i["missing"] and not i["triggered"] and i["value"] is None for i in missing)


def test_direct_and_graph_decisions_share_target_and_proposal(monkeypatch):
    pytest.importorskip("langgraph")
    from desk import cycle, graph

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 24, 14, tzinfo=UTC)

    for module in (cycle, graph):
        monkeypatch.setattr(module, "datetime", Clock)
        monkeypatch.setattr(module, "cards_for_focus", lambda *args: [card()])
    direct = cycle.run_cycle()
    state = graph.node_snapshot({})
    state.update(graph.node_pick_next(state))
    state.update(graph.node_retrieve(state))
    state.update(graph.node_debate_and_pm(state))
    state.update(graph.node_risk_gate(state))
    assert direct["portfolio_target"] == state["portfolio_target"]
    assert direct["decisions"][0]["proposal"] == state["proposal"]
    assert direct["decisions"][0]["risk"] == state["risk"]
    assert not direct["decisions"][0]["submitted"]


def test_future_and_open_memories_cannot_enter_decisions():
    conn = connect()
    ids = []
    for outcome, exit_ts in [("closed", "2026-09-20T00:00:00+00:00"),
                             ("closed", "2026-09-25T00:00:00+00:00"), ("intent", None)]:
        eid = write_episode(conn, {"ts": "2026-09-01T00:00:00+00:00", "symbol": "SPY", "side": "long",
                                   "thesis": "test", "lesson": "lesson", "outcome": outcome})
        conn.execute("UPDATE episodes SET exit_ts=? WHERE id=?", (exit_ts, eid))
        conn.commit()
        ids.append(eid)
    hits = eligible_memories(conn, card(), [{"id": i} for i in ids], 3)
    assert [h["id"] for h in hits] == ids[:1]
    conn.close()
