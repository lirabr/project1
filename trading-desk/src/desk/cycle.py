from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from desk.agents import model_signal_brief
from desk.decisions import decide, eligible_memories, evaluate_book, target_for_cards
from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR, ensure_dirs, load_yaml
from desk.memory import apply_fill, book_state, connect, retrieve, unrealized_pnl, write_episode
from desk.risk_gate import load_risk_cfg
from desk.snapshot import cards_for_focus
from desk.trust import load_trust
from desk.vectors import similar, upsert


def _is_crypto(symbol: str) -> bool:
    return symbol.endswith("-USD") or "/" in symbol


def run_cycle(
    desk_path: Path | None = None,
    universe_path: Path | None = None,
    risk_path: Path | None = None,
    submit: bool = False,
) -> dict:
    ensure_dirs()
    desk_cfg = load_yaml(desk_path or (CONFIG_DIR / "desk.yaml"))
    risk_cfg = load_risk_cfg(risk_path)
    universe_path = universe_path or (CONFIG_DIR / "universe.research.yaml")
    conn = connect()
    cards = cards_for_focus(desk_cfg, universe_path)
    marks = {c.symbol: c.last_close for c in cards}
    book = book_state(conn, marks)
    ts = datetime.now(UTC).isoformat()
    decisions = []
    orders = 0
    phase3 = load_yaml(CONFIG_DIR / "phase3.yaml") if (CONFIG_DIR / "phase3.yaml").exists() else {}
    k = int((phase3.get("vectors") or {}).get("k") or desk_cfg.get("retrieve_k", 3))
    target = target_for_cards(cards, desk_cfg, risk_cfg, book["equity"], ts)
    (ARTIFACT_DIR / "portfolio_target.json").write_text(json.dumps(target.to_dict(), indent=2))
    max_props = int(desk_cfg.get("max_proposals_per_cycle", 3))
    weights = load_trust(phase3)
    ranked = sorted(cards, key=lambda c: c.score, reverse=True)

    # Real day P&L feeds the daily-loss circuit breaker. Marks come from the
    # deterministic snapshot (latest close per card), never from an agent.
    marks = {c.symbol: c.last_close for c in cards}
    day_pnl = unrealized_pnl(conn, marks)

    for card in ranked:
        row = {"symbol": card.symbol, **card.features, "regime_id": None}
        from desk.regime import regime_id as _rid

        row["regime_id"] = _rid(card.note.split("regime=")[-1] if "regime=" in card.note else "range")
        vec_hits = similar(conn, row, k=k) if (phase3.get("vectors") or {}).get("enabled", True) else []
        text_hits = retrieve(conn, f"{card.symbol} {card.note}", k=k)
        memories = vec_hits + [h for h in text_hits if h.get("id") not in {v.get("episode_id") for v in vec_hits}]
        # normalize vector hits to episode-like dicts
        norm = []
        for m in memories:
            if "episode_id" in m and "id" not in m:
                m = {**m, "id": m.get("episode_id"), "side": "long", "realized_r": None, "outcome": "closed"}
            norm.append(m)
        memories = eligible_memories(conn, card, norm, k)
        regime = card.note.split("regime=")[-1] if "regime=" in card.note else "range"
        # Auditor: numbers must trace to tools and citations must be real.
        # The expected score is the deterministic trust transform of the model
        # card score; anything else means a number appeared from prose.
        desired = max(0., target.weights.get(card.symbol, 0) * book["equity"] - book["by_name"].get(card.symbol, 0) - book["reserved_by_name"].get(card.symbol, 0))
        proposal, _audit = decide(card, memories, desk_cfg, risk_cfg, weights,
                                  desired_notional=desired, target_id=target.target_id)
        if sum(d["risk"]["allow"] for d in decisions) >= max_props:
            proposal.side = "flat"
            proposal.suggested_notional_usd = 0.0
            proposal.thesis = "Proposal budget exhausted. " + proposal.thesis
        decision = evaluate_book(proposal, book, day_pnl, orders, risk_cfg)
        submitted = False
        if decision.allow and submit and not risk_cfg.get("require_human_approve", True):
            submitted = apply_fill(conn, card.symbol, decision.clipped_notional_usd, card.last_close, ts)
            orders += int(submitted)
            book = book_state(conn, marks)
        elif decision.allow and submit and risk_cfg.get("require_human_approve", True):
            # Logged as intent only. Human must flip require_human_approve to submit.
            submitted = False

        eid = write_episode(
            conn,
            {
                "ts": ts,
                "symbol": card.symbol,
                "side": proposal.side,
                "strategy": card.strategy,
                "regime": card.note,
                "score": card.score,
                "notional": decision.clipped_notional_usd if decision.allow else 0.0,
                "entry_px": card.last_close if submitted else None,
                "thesis": proposal.thesis,
                "bull_brief": proposal.bull_brief,
                "bear_brief": proposal.bear_brief,
                "risk_reason": decision.reason,
                "submitted": int(submitted),
                "lesson": None,
                "outcome": "intent" if decision.allow else "rejected",
            },
        )
        upsert(
            conn,
            eid,
            card.symbol,
            regime,
            row,
            lesson=None,
        )
        decisions.append(
            {
                "episode_id": eid,
                "card": model_signal_brief(card),
                "proposal": proposal.to_dict(),
                "risk": decision.to_dict(),
                "submitted": submitted,
                "cited_memory_ids": proposal.cited_memory_ids,
            }
        )
        if len([d for d in decisions if d["proposal"]["side"] != "flat"]) >= max_props:
            # still record remaining cards as skipped
            continue

    payload = {
        "ts": ts,
        "mode": desk_cfg.get("mode", "paper"),
        "book": {k: book[k] for k in ("cash", "gross", "crypto_weight", "equity") if k in book},
        "decisions": decisions,
        "portfolio_target": target.to_dict(),
        "target_id": target.target_id,
    }
    conn.execute("INSERT INTO cycles (ts, payload_json) VALUES (?, ?)", (ts, json.dumps(payload, default=str)))
    conn.commit()
    log_path = ARTIFACT_DIR / "desk_log.md"
    _append_log(log_path, payload)
    print(f"cycle {ts}  symbols={len(cards)}  logged={len(decisions)}  file={log_path}")
    for d in decisions:
        flag = "SUBMIT" if d["submitted"] else ("ALLOW" if d["risk"]["allow"] else d["risk"]["reason"])
        print(f"  {d['proposal']['symbol']:8} {d['proposal']['side']:4}  score={d['proposal']['score']:.2f}  "
              f"{flag}  mem={d['cited_memory_ids']}  ep=#{d['episode_id']}")
    return payload


def _append_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"\n## Cycle {payload['ts']}\n"]
    for d in payload["decisions"]:
        p = d["proposal"]
        r = d["risk"]
        lines.append(
            f"- **{p['symbol']}** {p['side']} score={p['score']:.2f} "
            f"gate={'ALLOW' if r['allow'] else 'BLOCK'} ({r['reason']}) "
            f"cited={p.get('cited_memory_ids')}\n"
            f"  thesis: {p['thesis']}\n"
        )
    with path.open("a") as f:
        f.write("".join(lines))
