# Phase 2 — Correct paper lifecycle and bounded decisions

**Goal:** prove accounting, risk, approvals, and recovery before improving agent sophistication. Entry: a validated research harness; a baseline is sufficient for engineering, but not for later live admission.

## Current versus target

The starter has two explicitly different paths. Legacy `cycle --submit`/graph approval still creates immediate-close toy buys and uses since-entry loss, not certified session P&L. The new `paper` CLI uses a separate durable order/fill/session engine over the local book: fresh marks, buys/sells, partial fills, fees, cash/share reservations, cancellation, UNKNOWN blocking, and atomic fill/event writes. Session P&L is marked equity change net of cashflows from an explicit persisted baseline. Neither path is a realistic exchange or broker adapter; `reflect` still annotates episodes rather than consuming completed ledger trades.

Do not use current paper returns as promotion evidence. Those gaps are Phase 2 development work, not optional polish.

## Inputs, resources, outputs

Input: equity panel and an explicit baseline/candidate identity. Tools: core Python environment; optional installed graph extra; no keys, containers or external orders. Target output: reconciled marked ledger, durable decisions/approvals, repeatable paper sessions and evidence-linked lessons.

## 1. Run the existing intent-only path

```bash
uv run --no-sync desk-research cycle
uv run --no-sync desk-research book
uv run --no-sync desk-research memory AAPL
```

Expect `data/artifacts/desk.sqlite`, `desk_log.md`, and `portfolio_target.json`; a fresh default book is empty. Card output identifies strategy/model/data provenance. `rules` mode explicitly uses SMA by default. `approved` mode requires a locally reviewed frozen model and has no fallback; `replay` requires an exact-date OOS score. The old metadata registry does not govern inference.

## 2. Prove rejection without changing caps

```bash
uv run --no-sync desk-research halt
uv run --no-sync desk-research cycle
```

Expect no fills and kill-switch rejection. Inspect before deliberately clearing:

```bash
uv run --no-sync desk-research halt --clear
```

HALT blocks new intents/fills under the configured file path; it does not cancel orders or flatten positions. CLI and risk paths now share the same resolver, including alternate data directories and selected risk configs. Verify that profile explicitly before relying on it.

## 3. Optional graph demonstration

```bash
uv run --no-sync desk-research graph --thread equity-demo-001
uv run --no-sync desk-research graph-resume --thread equity-demo-001 reject
```

A graph pauses only if a proposal passes. Use a new thread ID for new work; resume only a pending thread. Start with rejection. Approval is an explicit local command, and may create a toy internal fill. The graph rechecks the current gate and expires approval after a short window (default 300 seconds from snapshot). Overnight approval must produce a new snapshot/decision, not execute yesterday's price.

Read [LangGraph details](langgraph-integration.md). A checkpoint is not a transaction spanning fill and episode. Do not run concurrent desk processes.

## 4. Exercise the durable paper foundation

Use the [starter README workflow](trading-desk/README.md#durable-internal-paper-workflow): explicit session baseline → target → dry plan → per-order approval/reservation → simulated partial fill → marked book. `paper fill` supports both buys and sells from approved plans; `paper cancel` releases an internal remainder. This is separate from legacy graph fills and never contacts a venue. Use fresh isolated state rather than importing old demonstration returns as real executions.

Foundations for marked accounting, reservations, partial fills/fees, local approval binding, and atomic events are implemented and regression-tested. The following remain the full acceptance contract, with real feed/venue semantics and evidence still required:

1. Separate immutable decision episodes from orders/fills/ledger. Implement buy, sell/reduce, cancel, reject, partial-fill, and fee events with unique IDs.
2. Reconstruct cash and quantities from the ledger; support lot cost and realized P&L. Mark every open position, including symbols removed from focus. Missing/stale marks mean UNKNOWN and block new exposure.
3. Persist session-start equity and external cashflows. Verify today's P&L independently of lifetime P&L and across restart/day rollover.
4. Reserve cash/exposure for pending orders and authorize projected state atomically. Include concentration, order/turnover budgets, available cash, and liquidity.
5. Add a realistic simulator using the same next-event timing, fees, spread, exits and cancellation semantics as the research contract. Do not “fix” parity by using same-close fills in both systems.
6. Bind human approvals to immutable intent hash, account, policy version, and expiry. Revalidate fresh portfolio/quotes and HALT at the final boundary.
7. Extract a shared application service so direct and graph paths cannot drift. Inject clock/config/store instead of reading mutable globals at every node.
8. Make ledger updates and event/outbox writes atomic. Repeated execution IDs cannot duplicate cash/quantity or silently change their payload.

See [contracts](requirements-and-contracts.md) for simulator versus broker order states. Internal sells use `paper plan`/`paper approve`/`paper fill`; no standalone broker `sell` or `reconcile` command exists. UNKNOWN cannot be cleared by pretending it was cancelled; preserve evidence and resolve it through a future reviewed reconciliation implementation.

## 5. Evidence and observation

After the accounting/replay gate passes, run at least **20 equity sessions** prospectively. Save each snapshot and policy/model identity. Daily: refresh/validate inputs, reconcile, run one scheduled cycle, review rejects, mark the book, check limits, export evidence. Add historical shock and outage replays if no unusual session occurs naturally. Count observed and replayed sessions separately.

Reflection is admitted only when an executed trade really closes or a separately defined counterfactual horizon matures. Keep those outcome types separate. Do not label a mark as realized R without a declared initial-risk denominator. Until reflection is connected to verified completed ledger outcomes, `reflect` remains a legacy diagnostic and must not drive promotion.

## Tests and exit gate

```bash
uv run --no-sync pytest tests/test_phase2_desk.py tests/test_risk_daily_loss.py tests/test_risk_gate_consistency.py tests/test_auditor.py tests/test_graph_langgraph.py tests/test_v3_invariants.py -q
```

Existing tests do not establish the unimplemented accounting guarantees. Add the negative/chaos tests in [acceptance](testing-and-acceptance.md) and require all of them before certification.

- [ ] Marked cash/position ledger and daily baseline match independent calculations.
- [ ] HALT, stale/missing data, exhausted caps, invalid numbers and stale approvals prevent new risk.
- [ ] Retries/restarts preserve one economic effect; reject/cancel/partial fills reconcile.
- [ ] Direct and graph paths agree on identical evidence/config.
- [ ] At least 20 prospective sessions recorded; no unresolved safety incident.
- [ ] Lessons distinguish executed from counterfactual outcomes and remain point-in-time eligible.

Next: [Phase 3](phase-3-tighten-loop.md). More agents are not a substitute for these gates.
