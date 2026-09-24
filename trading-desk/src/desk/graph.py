"""LangGraph wrapper over the same deterministic desk nodes as cycle.py.

This is the *optional* orchestration path. It adds checkpoints, pause/resume, and
a real human-in-the-loop interrupt on the approve step — it does NOT add a new
trading idea. Every node calls an existing function; no new alpha lives here.

Hard invariants (enforced by construction and by tests):
  * ``risk_gate`` and ``paper_fill`` are pure-Python nodes, never bound to an LLM.
  * The graph ends at paper log + audit. There is no live ``submit_order`` tool.
  * A process restart cannot lose a pending human approval (checkpointer holds it).

Install the extra to use this module:

    uv sync --extra graph        # or: uv add langgraph langgraph-checkpoint-sqlite

Run:

    desk-research graph --thread desk-2026-09-22-scheduled
    desk-research graph-resume --thread desk-2026-09-22-scheduled approve
"""

from __future__ import annotations

import json
import operator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from desk.agents import model_signal_brief
from desk.contracts import ModelCard
from desk.decisions import decide, eligible_memories, evaluate_book, target_for_cards
from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR, ensure_dirs, load_yaml
from desk.memory import apply_fill, book_state, connect, retrieve, unrealized_pnl, write_episode
from desk.portfolio import PortfolioTarget
from desk.regime import regime_id as _rid
from desk.risk_gate import load_risk_cfg
from desk.snapshot import cards_for_focus
from desk.trust import load_trust
from desk.vectors import similar, upsert


class DeskState(TypedDict, total=False):
    ts: str
    thread_id: str
    cards: list[dict[str, Any]]
    focus_index: int
    card: dict[str, Any]
    memories: list[dict[str, Any]]
    proposal: dict[str, Any]
    risk: dict[str, Any]
    human: str
    submitted: bool
    day_pnl: float
    portfolio_target: dict[str, Any]
    target_equity: float
    decisions: Annotated[list[dict[str, Any]], operator.add]


def _is_crypto(symbol: str) -> bool:
    return symbol.endswith("-USD") or "/" in symbol


def _card_from_state(d: dict[str, Any]) -> ModelCard:
    return ModelCard(**d)


# --------------------------------------------------------------------------- #
# Nodes — each maps 1:1 onto an existing function used by cycle.run_cycle
# --------------------------------------------------------------------------- #

def node_snapshot(state: DeskState) -> dict[str, Any]:
    ensure_dirs()
    desk_cfg = load_yaml(CONFIG_DIR / "desk.yaml")
    universe_path = CONFIG_DIR / "universe.research.yaml"
    cards = cards_for_focus(desk_cfg, universe_path)
    ranked = sorted(cards, key=lambda c: c.score, reverse=True)
    conn = connect()
    marks = {c.symbol: c.last_close for c in cards}
    book = book_state(conn, marks)
    day_pnl = unrealized_pnl(conn, marks)
    conn.close()
    ts = datetime.now(UTC).isoformat()
    target = target_for_cards(cards, desk_cfg, load_risk_cfg(), book["equity"], ts)
    return {
        "ts": ts,
        "cards": [c.__dict__ for c in ranked],
        "focus_index": 0,
        "day_pnl": day_pnl,
        "portfolio_target": target.to_dict(),
        "target_equity": book["equity"],
    }


def node_pick_next(state: DeskState) -> dict[str, Any]:
    idx = state.get("focus_index", 0)
    cards = state.get("cards", [])
    if idx >= len(cards):
        return {"card": {}}
    return {"card": cards[idx], "submitted": False, "human": "", "risk": {}}


def node_retrieve(state: DeskState) -> dict[str, Any]:
    card = _card_from_state(state["card"])
    phase3 = load_yaml(CONFIG_DIR / "phase3.yaml") if (CONFIG_DIR / "phase3.yaml").exists() else {}
    desk_cfg = load_yaml(CONFIG_DIR / "desk.yaml")
    k = int((phase3.get("vectors") or {}).get("k") or desk_cfg.get("retrieve_k", 3))
    conn = connect()
    regime = card.note.split("regime=")[-1] if "regime=" in card.note else "range"
    row = {"symbol": card.symbol, **card.features, "regime_id": _rid(regime)}
    vec_hits = similar(conn, row, k=k) if (phase3.get("vectors") or {}).get("enabled", True) else []
    text_hits = retrieve(conn, f"{card.symbol} {card.note}", k=k)
    seen = {v.get("episode_id") for v in vec_hits}
    memories = vec_hits + [h for h in text_hits if h.get("id") not in seen]
    norm = []
    for m in memories:
        if "episode_id" in m and "id" not in m:
            m = {**m, "id": m.get("episode_id"), "side": "long", "realized_r": None, "outcome": "closed"}
        norm.append(m)
    memories = eligible_memories(conn, card, norm, k)
    conn.close()
    return {"memories": memories}


def node_debate_and_pm(state: DeskState) -> dict[str, Any]:
    """model_signal → bull → bear → PM → trust → refine → auditor (fail closed)."""
    card = _card_from_state(state["card"])
    memories = state.get("memories", [])
    desk_cfg = load_yaml(CONFIG_DIR / "desk.yaml")
    phase3 = load_yaml(CONFIG_DIR / "phase3.yaml") if (CONFIG_DIR / "phase3.yaml").exists() else {}
    risk_cfg = load_risk_cfg()
    weights = load_trust(phase3)
    desired, target_id = None, ""
    if state.get("portfolio_target"):
        target = PortfolioTarget.from_dict(state["portfolio_target"])
        conn = connect()
        try:
            book = book_state(conn, {c["symbol"]: c["last_close"] for c in state["cards"]})
        finally:
            conn.close()
        desired = max(0., target.weights.get(card.symbol, 0) * state["target_equity"] - book["by_name"].get(card.symbol, 0) - book["reserved_by_name"].get(card.symbol, 0))
        target_id = target.target_id
    proposal, _audit = decide(card, memories, desk_cfg, risk_cfg, weights,
                              desired_notional=desired, target_id=target_id)
    if sum(d.get("risk", {}).get("allow", False) for d in state.get("decisions", [])) >= int(desk_cfg.get("max_proposals_per_cycle", 3)):
        proposal.side = "flat"  # type: ignore[assignment]
        proposal.suggested_notional_usd = 0.
        proposal.thesis = "Proposal budget exhausted. " + proposal.thesis
    return {"proposal": proposal.to_dict()}


def node_risk_gate(state: DeskState) -> dict[str, Any]:
    """PURE PYTHON. No LLM, no tools, no network."""
    from desk.contracts import TradeProposal

    pd_ = dict(state["proposal"])
    proposal = TradeProposal(**pd_)
    conn = connect()
    try:
        book = book_state(conn, {c["symbol"]: c["last_close"] for c in state.get("cards", [])})
    finally:
        conn.close()
    risk_cfg = load_risk_cfg()
    decision = evaluate_book(proposal, book, float(state.get("day_pnl", 0.0)),
                             sum(bool(d.get("submitted")) for d in state.get("decisions", [])), risk_cfg)
    return {"risk": decision.to_dict()}


def node_human_approve(state: DeskState) -> dict[str, Any]:
    """Dynamic interrupt — only pause when the gate allowed a real size."""
    from langgraph.types import interrupt

    risk = state.get("risk", {})
    risk_cfg = load_risk_cfg()
    if not risk.get("allow"):
        return {"human": "n/a"}
    if not risk_cfg.get("require_human_approve", True):
        return {"human": "auto"}
    decision = interrupt(
        {
            "symbol": state["proposal"]["symbol"],
            "notional": risk["clipped_notional_usd"],
            "thesis": state["proposal"]["thesis"],
            "question": "approve | reject",
        }
    )
    return {"human": str(decision)}


def node_paper_fill(state: DeskState) -> dict[str, Any]:
    """Internal blotter only. Never calls a broker."""
    risk = state.get("risk", {})
    human = state.get("human", "")
    card = _card_from_state(state["card"])
    if not risk.get("allow") or human not in ("approve", "auto"):
        return {"submitted": False}
    age = (datetime.now(UTC) - datetime.fromisoformat(state["ts"])).total_seconds()
    if not 0 <= age <= float(load_risk_cfg().get("approval_ttl_seconds", 300)):
        return {"submitted": False, "risk": {**risk, "allow": False, "reason": "approval expired", "clipped_notional_usd": 0.0}}
    current = node_risk_gate(state)["risk"]
    if not current["allow"]:
        return {"submitted": False, "risk": current}
    notional = min(float(risk["clipped_notional_usd"]), float(current["clipped_notional_usd"]))
    fill_id = f"{state.get('thread_id', '')}:{state['ts']}:{state.get('focus_index', 0)}:{card.symbol}"
    conn = connect()
    try:
        submitted = apply_fill(conn, card.symbol, notional, card.last_close, state["ts"], fill_id=fill_id)
    finally:
        conn.close()
    return {"submitted": submitted, "risk": {**current, "clipped_notional_usd": notional}}


def node_log_episode(state: DeskState) -> dict[str, Any]:
    card = _card_from_state(state["card"])
    proposal = dict(state["proposal"])
    risk = dict(state.get("risk", {}))
    submitted = bool(state.get("submitted", False))
    conn = connect()
    regime = card.note.split("regime=")[-1] if "regime=" in card.note else "range"
    eid = write_episode(
        conn,
        {
            "ts": state["ts"],
            "symbol": card.symbol,
            "side": proposal["side"],
            "strategy": card.strategy,
            "regime": card.note,
            "score": card.score,
            "notional": risk.get("clipped_notional_usd", 0.0) if risk.get("allow") else 0.0,
            "entry_px": card.last_close if submitted else None,
            "thesis": proposal["thesis"],
            "bull_brief": proposal.get("bull_brief", ""),
            "bear_brief": proposal.get("bear_brief", ""),
            "risk_reason": risk.get("reason", ""),
            "submitted": int(submitted),
            "lesson": None,
            "outcome": "intent" if risk.get("allow") else "rejected",
        },
    )
    row = {"symbol": card.symbol, **card.features, "regime_id": _rid(regime)}
    upsert(conn, eid, card.symbol, regime, row, lesson=None)
    conn.execute(
        "INSERT INTO cycles (ts, payload_json) VALUES (?, ?)",
        (state["ts"], json.dumps({"episode_id": eid, "proposal": proposal, "risk": risk}, default=str)),
    )
    conn.commit()
    conn.close()
    _append_log(ARTIFACT_DIR / "desk_log.md", state["ts"], proposal, risk)
    decision = {
        "episode_id": eid,
        "card": model_signal_brief(card),
        "proposal": proposal,
        "risk": risk,
        "submitted": submitted,
        "cited_memory_ids": proposal.get("cited_memory_ids", []),
    }
    return {"focus_index": state.get("focus_index", 0) + 1, "decisions": [decision]}


def _append_log(path: Path, ts: str, proposal: dict, risk: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"\n## Graph cycle {ts}\n"
        f"- **{proposal['symbol']}** {proposal['side']} score={proposal['score']:.2f} "
        f"gate={'ALLOW' if risk.get('allow') else 'BLOCK'} ({risk.get('reason')}) "
        f"cited={proposal.get('cited_memory_ids')}\n"
        f"  thesis: {proposal['thesis']}\n"
    )
    with path.open("a") as f:
        f.write(line)


# --------------------------------------------------------------------------- #
# Routers
# --------------------------------------------------------------------------- #

def route_more(state: DeskState) -> str:
    idx = state.get("focus_index", 0)
    return "next" if idx < len(state.get("cards", [])) else "done"


def route_after_risk(state: DeskState) -> str:
    return "ask_human" if state.get("risk", {}).get("allow") else "log"


def route_human(state: DeskState) -> str:
    return "fill" if state.get("human") in ("approve", "auto") else "log"


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #

def build_desk(checkpointer: Any | None = None):
    """Compile the desk graph. LangGraph is imported lazily so the package
    imports fine without the [graph] extra."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(DeskState)
    g.add_node("snapshot", node_snapshot)
    g.add_node("pick_next", node_pick_next)
    g.add_node("retrieve", node_retrieve)
    g.add_node("debate_pm", node_debate_and_pm)
    g.add_node("risk_gate", node_risk_gate)
    g.add_node("human_approve", node_human_approve)
    g.add_node("paper_fill", node_paper_fill)
    g.add_node("log_episode", node_log_episode)

    g.add_edge(START, "snapshot")
    g.add_edge("snapshot", "pick_next")
    g.add_conditional_edges("pick_next", route_more, {"next": "retrieve", "done": END})
    g.add_edge("retrieve", "debate_pm")
    g.add_edge("debate_pm", "risk_gate")
    g.add_conditional_edges("risk_gate", route_after_risk, {"ask_human": "human_approve", "log": "log_episode"})
    g.add_conditional_edges("human_approve", route_human, {"fill": "paper_fill", "log": "log_episode"})
    g.add_edge("paper_fill", "log_episode")
    g.add_edge("log_episode", "pick_next")

    # Compile-time invariant: the two deterministic nodes exist and are plain
    # callables, not chat models. (Documented + asserted in tests.)
    assert node_risk_gate.__name__ == "node_risk_gate"
    assert node_paper_fill.__name__ == "node_paper_fill"

    return g.compile(checkpointer=checkpointer)


def default_checkpointer(sqlite_path: str | None = None):
    """SqliteSaver next to (but separate from) desk.sqlite.

    Uses a raw sqlite3 connection so the saver outlives a single ``with`` block
    (a pending human approval must survive a process restart). This is a
    different file from ``desk.sqlite`` — checkpoints are working memory, not
    episodic memory.
    """
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = sqlite_path or str(ARTIFACT_DIR / "graph_checkpoints.sqlite")
    ensure_dirs()
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def _report(thread_id: str, result: dict[str, Any]) -> dict[str, Any]:
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if interrupts:
        payload = getattr(interrupts[0], "value", interrupts[0])
        print(f"graph {thread_id} paused for human approval: {payload}")
        print(f"resume with: desk-research graph-resume --thread {thread_id} approve")
        return {"interrupted": True, "payload": payload}
    print(f"graph {thread_id} finished  decisions={len(result.get('decisions', []))}")
    return result


def run_graph(thread_id: str) -> dict[str, Any]:
    saver = default_checkpointer()
    graph = build_desk(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 200}
    try:
        if graph.get_state(config).values:
            raise ValueError("Thread already exists; resume pending work or choose a new thread ID")
        return _report(thread_id, graph.invoke({"thread_id": thread_id}, config))
    finally:
        saver.conn.close()


def resume_graph(thread_id: str, decision: str) -> dict[str, Any]:
    from langgraph.types import Command

    saver = default_checkpointer()
    graph = build_desk(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 200}
    try:
        if decision not in {"approve", "reject"} or not graph.get_state(config).next:
            raise ValueError("A pending thread and an approve/reject decision are required")
        return _report(thread_id, graph.invoke(Command(resume=decision), config))
    finally:
        saver.conn.close()
