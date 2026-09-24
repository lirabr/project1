from __future__ import annotations

import argparse
from pathlib import Path

from desk.io_utils import CONFIG_DIR
from desk.models import available_strategies


def _p(name: str) -> Path:
    return CONFIG_DIR / name


def cmd_download(args: argparse.Namespace) -> None:
    from desk.data import download_universe

    download_universe(Path(args.universe))


def cmd_features(args: argparse.Namespace) -> None:
    from desk.features import build_feature_store
    from desk.io_utils import load_yaml

    wf = load_yaml(args.walkforward)
    build_feature_store(Path(args.universe), horizon=int(wf.get("label_horizon_days", 5)))


def cmd_backtest(args: argparse.Namespace) -> None:
    from desk.walkforward import run_walkforward

    names = args.strategy or available_strategies()
    for name in names:
        run_walkforward(name, Path(args.universe), Path(args.walkforward), Path(args.costs))


def cmd_compare(_: argparse.Namespace) -> None:
    from desk.walkforward import compare

    df = compare(available_strategies())
    cols = [
        "strategy",
        "n_folds",
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "excess_return",
        "hit_rate",
        "turnover",
    ]
    show = df[cols].copy()
    for c in ["total_return", "cagr", "max_drawdown", "excess_return", "hit_rate"]:
        show[c] = show[c].map(lambda x: f"{x:+.2%}" if isinstance(x, float) else x)
    for c in ["sharpe", "sortino", "turnover"]:
        show[c] = show[c].map(lambda x: f"{x:.3f}" if isinstance(x, float) else x)
    print(show.to_string(index=False))
    print()
    print("Promote only if excess_return > 0 after costs AND max_drawdown is tolerable on most folds.")
    print("Buy-and-hold of the benchmark is the bar. Do not promote on one lucky fold.")


def cmd_promote(args: argparse.Namespace) -> None:
    from desk.tracking import promote

    promote(args.strategy, args.stage)


def cmd_cycle(args: argparse.Namespace) -> None:
    from desk.cycle import run_cycle

    run_cycle(
        desk_path=Path(args.desk),
        universe_path=Path(args.universe),
        risk_path=Path(args.risk),
        submit=args.submit,
    )


def cmd_reflect(_: argparse.Namespace) -> None:
    from desk.reflect import reflect

    reflect()


def cmd_book(_: argparse.Namespace) -> None:
    from desk.memory import book_state, connect

    book = book_state(connect())
    print(f"cash={book['cash']:.2f}  gross={book['gross']:.2f}  equity={book['equity']:.2f}  crypto_w={book['crypto_weight']:.2%}")
    for p in book["positions"]:
        print(f"  {p['symbol']:8} qty={p['qty']:.6f} avg={p['avg_px']:.4f} notional={p['notional']:.2f}")
    if not book["positions"]:
        print("  (no positions — intents only until you submit with approve off)")


def cmd_memory(args: argparse.Namespace) -> None:
    from desk.memory import connect, retrieve

    hits = retrieve(connect(), args.query, k=args.k)
    if not hits:
        print("no episodes")
        return
    for h in hits:
        print(
            f"#{h['id']} {h['symbol']} {h['side']} {h.get('outcome')} "
            f"r={h.get('realized_r')} | {(h.get('lesson') or h.get('thesis') or '')[:160]}"
        )


def cmd_heartbeat(_: argparse.Namespace) -> None:
    from desk.heartbeat import pulse

    pulse()


def cmd_drift(_: argparse.Namespace) -> None:
    from desk.drift import check_drift

    check_drift()


def cmd_trust(_: argparse.Namespace) -> None:
    from desk.trust import TRUST_PATH, load_trust

    w = load_trust()
    print(f"{TRUST_PATH}")
    for k, v in w.items():
        print(f"  {k:8} {v:.3f}")


def cmd_policy_show(_: argparse.Namespace) -> None:
    from desk.policy import read_policy

    print(read_policy())


def cmd_policy_propose(args: argparse.Namespace) -> None:
    from desk.policy import propose

    path = propose(args.note)
    print(f"pending policy → {path}")
    print("edit that file if needed, then: desk-research policy-approve")


def cmd_live_preflight(_: argparse.Namespace) -> None:
    from desk.live import preflight

    blockers = preflight()
    if not blockers:
        print("preflight clear — starter still will not place a live order")
        return
    print("live blocked:")
    for b in blockers:
        print(f"  - {b}")


def cmd_live_intent(args: argparse.Namespace) -> None:
    from desk.contracts import TradeProposal
    from desk.live import route_live_intent
    from desk.risk_gate import evaluate, load_risk_cfg

    prop = TradeProposal(
        symbol=args.symbol.upper(),
        side="long",
        urgency="low",
        thesis="manual phase-4 intent",
        invalidation="human",
        horizon_days=5,
        score=0.7,
        suggested_notional_usd=250,
    )
    risk = evaluate(
        prop,
        book_gross_usd=0,
        book_name_usd=0,
        day_pnl_usd=0,
        orders_this_cycle=0,
        crypto_weight=0,
        is_crypto="-" in args.symbol or "/" in args.symbol,
        live=True,
        cfg=load_risk_cfg(),
    )
    event = route_live_intent(prop, risk, is_crypto="-" in args.symbol or "/" in args.symbol, submit=args.submit)
    print(event["status"], event.get("blockers") or event.get("note") or event.get("risk_reason"))


def cmd_policy_approve(_: argparse.Namespace) -> None:
    from desk.policy import approve

    path = approve()
    print(f"approved → {path}")


def cmd_halt(args: argparse.Namespace) -> None:
    from desk.risk_gate import halt_path, load_risk_cfg

    path = halt_path(load_risk_cfg(Path(args.risk)))
    if args.clear:
        if path.exists():
            path.unlink()
            print("kill switch cleared")
        else:
            print("kill switch was not set")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("halt\n")
    print(f"kill switch ON → {path}")


def cmd_graph(args: argparse.Namespace) -> None:
    try:
        from desk.graph import run_graph
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"LangGraph not installed ({exc.name}). Install the extra: uv sync --extra graph"
        ) from exc
    run_graph(args.thread)


def cmd_graph_resume(args: argparse.Namespace) -> None:
    try:
        from desk.graph import resume_graph
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"LangGraph not installed ({exc.name}). Install the extra: uv sync --extra graph"
        ) from exc
    resume_graph(args.thread, args.decision)


def cmd_folds(args: argparse.Namespace) -> None:
    from desk.io_utils import ARTIFACT_DIR, load_yaml

    path = ARTIFACT_DIR / args.strategy / "folds.yaml"
    data = load_yaml(path)
    for row in data.get("folds", []):
        print(
            f"fold {row['fold_id']:2}  train {row['train_start']}→{row['train_end']}  "
            f"test {row['test_start']}→{row['test_end']}  "
            f"ret={row['total_return']:+.2%}  sharpe={row['sharpe']:.2f}  dd={row['max_drawdown']:.2%}"
        )


def cmd_report(args: argparse.Namespace) -> None:
    from desk.io_utils import ARTIFACT_DIR
    from desk.reports import render_report

    print(render_report(available_strategies(), Path(args.output) if args.output else ARTIFACT_DIR / "research-report.html"))


def cmd_train(args: argparse.Namespace) -> None:
    from desk.artifacts import train_candidate

    print(train_candidate(args.strategy, args.cutoff))


def cmd_approve_model(args: argparse.Namespace) -> None:
    from desk.artifacts import approve_model, file_hash

    approve_model(args.model_id, args.reviewer, file_hash(Path(args.evidence)))
    print(f"Approved local inference artifact: {args.model_id}")


def _marks(path):
    import json

    from desk.portfolio import Mark

    return {s: Mark(**m) for s, m in json.loads(Path(path).read_text()).items()} if path else {}


def cmd_portfolio(args: argparse.Namespace) -> None:
    import json
    from datetime import UTC, datetime

    from desk.decisions import target_for_cards
    from desk.io_utils import load_yaml
    from desk.ledger import marked_book
    from desk.memory import connect
    from desk.risk_gate import load_risk_cfg
    from desk.snapshot import cards_for_focus

    now = datetime.now(UTC)
    cfg = load_yaml(args.desk)
    if args.execute_after:
        cfg["execute_after"] = args.execute_after
    conn = connect()
    try:
        book = marked_book(conn, _marks(args.marks), now)
        cards = cards_for_focus(cfg, Path(args.universe))
        target = target_for_cards(cards, cfg, load_risk_cfg(Path(args.risk)), book["equity"], now.isoformat())
        print(json.dumps(target.to_dict(), indent=2))
    finally:
        conn.close()


def cmd_paper(args: argparse.Namespace) -> None:
    import json
    from dataclasses import asdict
    from datetime import UTC, datetime, timedelta

    from desk import ledger
    from desk.memory import connect
    from desk.portfolio import PortfolioTarget, digest, plan_rebalance, timestamp
    from desk.risk_gate import load_risk_cfg

    now = datetime.now(UTC)
    marks = _marks(args.marks)
    cfg = load_risk_cfg(Path(args.risk))
    conn = connect()
    try:
        if args.action == "session":
            ledger.open_session(conn, args.session, marks, now)
            print("Session baseline recorded; existing baselines are never reset")
        elif args.action == "book":
            state = ledger.marked_book(conn, marks, now)
            if args.session:
                state["session_pnl"] = ledger.session_pnl(conn, args.session, state["equity"])
            from desk.reports import paper_statistics

            state["statistics"] = paper_statistics(conn)
            print(json.dumps(state, indent=2))
        elif args.action in {"plan", "approve"}:
            if not args.target:
                raise ValueError("--target is required")
            target = PortfolioTarget.from_dict(json.loads(Path(args.target).read_text()))
            state = ledger.marked_book(conn, marks, now)
            orders = plan_rebalance(target, {p["symbol"]: p["qty"] for p in state["positions"]}, state["cash"], marks, now)
            if args.action == "plan":
                print(json.dumps({"target_id": target.target_id, "orders": [asdict(o) for o in orders]}, indent=2))
            else:
                order = next((o for o in orders if o.order_id == args.order_id), None)
                if order is None:
                    raise ValueError("Order no longer matches the plan; review a fresh plan")
                ttl = float(cfg.get("approval_ttl_seconds", 300))
                approval = ledger.Approval(target.target_id, digest(cfg), args.reviewer,
                                           min(now + timedelta(seconds=ttl), timestamp(target.expires_at)).isoformat(), order.order_id, args.cost_bps)
                print(ledger.accept_order(conn, order, approval, marks, now, cfg, args.session, cost_bps=args.cost_bps))
        elif args.action == "fill":
            ledger.record_fill(conn, args.order_id, args.fill_id, args.quantity, args.price, args.fee, now, cfg, marks=marks)
            print(json.dumps(ledger.order_state(conn, args.order_id), indent=2))
        elif args.action == "cancel":
            ledger.cancel_order(conn, args.order_id)
            print("Internal paper order cancelled; no broker contacted")
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="desk-research", description="Research lab + paper desk")
    p.add_argument("--universe", default=str(_p("universe.research.yaml")))
    p.add_argument("--walkforward", default=str(_p("walkforward.yaml")))
    p.add_argument("--costs", default=str(_p("costs.yaml")))
    p.add_argument("--desk", default=str(_p("desk.yaml")))
    p.add_argument("--risk", default=str(_p("risk.paper.yaml")))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("download", help="Download OHLCV into data/raw")
    s.set_defaults(func=cmd_download)

    s = sub.add_parser("features", help="Build the feature panel")
    s.set_defaults(func=cmd_features)

    s = sub.add_parser("backtest", help="Walk-forward train + backtest one or all strategies")
    s.add_argument("--strategy", nargs="*", default=None)
    s.set_defaults(func=cmd_backtest)

    s = sub.add_parser("compare", help="Print tear sheets side by side")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("folds", help="Print per-fold results for a strategy")
    s.add_argument("strategy")
    s.set_defaults(func=cmd_folds)

    s = sub.add_parser("report", help="Render a read-only HTML research report")
    s.add_argument("--output")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("train", help="Freeze a model candidate using only mature labels")
    s.add_argument("strategy", choices=available_strategies())
    s.add_argument("--cutoff", required=True)
    s.set_defaults(func=cmd_train)

    s = sub.add_parser("approve-model", help="Record local human review of a frozen model")
    s.add_argument("model_id")
    s.add_argument("--reviewer", required=True)
    s.add_argument("--evidence", required=True)
    s.set_defaults(func=cmd_approve_model)

    s = sub.add_parser("portfolio", help="Print a versioned target allocation, not orders")
    s.add_argument("--marks")
    s.add_argument("--execute-after")
    s.set_defaults(func=cmd_portfolio)

    s = sub.add_parser("paper", help="Durable internal simulator; never contacts a broker")
    s.add_argument("action", choices=["session", "book", "plan", "approve", "fill", "cancel"])
    s.add_argument("--marks")
    s.add_argument("--target")
    s.add_argument("--session", default="")
    s.add_argument("--order-id", default="")
    s.add_argument("--reviewer", default="")
    s.add_argument("--fill-id", default="")
    s.add_argument("--quantity", type=float, default=0)
    s.add_argument("--price", type=float, default=0)
    s.add_argument("--fee", type=float, default=0)
    s.add_argument("--cost-bps", type=float, default=0)
    s.set_defaults(func=cmd_paper)

    s = sub.add_parser("promote", help="Mark a strategy in the local registry")
    s.add_argument("strategy")
    s.add_argument("--stage", default="candidate", choices=["dev", "candidate", "paper", "retired"])
    s.set_defaults(func=cmd_promote)

    s = sub.add_parser("cycle", help="Run one paper-desk cycle (model → debate → PM → risk gate)")
    s.add_argument("--submit", action="store_true", help="Fill paper book if risk allows AND require_human_approve is false")
    s.set_defaults(func=cmd_cycle)

    s = sub.add_parser("reflect", help="Write lessons for submitted paper fills")
    s.set_defaults(func=cmd_reflect)

    s = sub.add_parser("book", help="Show paper cash and positions")
    s.set_defaults(func=cmd_book)

    s = sub.add_parser("memory", help="Search episodic lessons")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("-k", type=int, default=5)
    s.set_defaults(func=cmd_memory)

    s = sub.add_parser("halt", help="Engage or clear the file kill switch")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(func=cmd_halt)

    s = sub.add_parser("heartbeat", help="Cheap crypto pulse; tells you whether to run a full cycle")
    s.set_defaults(func=cmd_heartbeat)

    s = sub.add_parser("drift", help="PSI drift vs the feature reference")
    s.set_defaults(func=cmd_drift)

    s = sub.add_parser("trust", help="Show per-agent trust weights")
    s.set_defaults(func=cmd_trust)

    s = sub.add_parser("policy-show", help="Print the approved desk policy")
    s.set_defaults(func=cmd_policy_show)

    s = sub.add_parser("policy-propose", help="Write a pending policy patch for human review")
    s.add_argument("note")
    s.set_defaults(func=cmd_policy_propose)

    s = sub.add_parser("policy-approve", help="Promote the pending policy after you have read it")
    s.set_defaults(func=cmd_policy_approve)

    s = sub.add_parser("graph", help="Run the desk as a LangGraph (checkpoints + human interrupt); needs [graph] extra")
    s.add_argument("--thread", required=True, help="Thread id, e.g. desk-2026-09-22-scheduled")
    s.set_defaults(func=cmd_graph)

    s = sub.add_parser("graph-resume", help="Resume a paused graph thread with a human decision")
    s.add_argument("--thread", required=True)
    s.add_argument("decision", choices=["approve", "reject"], help="Human decision at the approve interrupt")
    s.set_defaults(func=cmd_graph_resume)

    s = sub.add_parser("live-preflight", help="Print why live is still blocked (default: everything)")
    s.set_defaults(func=cmd_live_preflight)

    s = sub.add_parser("live-intent", help="Audit a tiny-live intent; never sends an order in this starter")
    s.add_argument("symbol")
    s.add_argument("--submit", action="store_true")
    s.set_defaults(func=cmd_live_intent)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
