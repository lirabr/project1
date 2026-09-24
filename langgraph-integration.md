# LangGraph integration — orchestration, not execution authority

**Implemented:** optional `graph` / `graph-resume` commands over deterministic domain helpers, SQLite checkpoints, and human interruption. **Not implemented:** a transactional execution service, realistic paper broker, authenticated approval service or live broker. See [architecture](trading-agents-architecture.md).

## Install and safe demonstration

From `trading-desk` after building an equity feature panel:

```bash
uv sync --locked --extra dev --extra graph
uv run --no-sync desk-research graph --thread equity-demo-001
uv run --no-sync desk-research graph-resume --thread equity-demo-001 reject
```

Run `graph-resume` only when the command reports a pending approval. A rejected/flat cycle may finish without an interrupt. A thread can pause once per allowed symbol; after each resume inspect the next result. Use a unique ID per new cycle. Completed/existing threads cannot be silently restarted through `graph`.

`approve` may create a toy internal fill, never an external order. It must be an explicit human action, not an agent-generated response. Default approval age is 300 seconds from cycle snapshot; expired approval logs a rejection. Recompute after long pauses instead of executing a stale close the next morning.

## Shipped topology

```text
START -> snapshot -> pick_next -> retrieve -> debate_pm -> risk_gate
                         ^                                | reject
                         |                                v
                         +--------------------------- log_episode
                         |                                ^
                         |                                |
                         |        human_approve ----------+ reject
                         |             | approve/auto
                         |             v
                         +----- log_episode <- paper_fill
```

When no cards remain, `pick_next` routes to END. `debate_pm` combines bull/bear/PM, trust sizing, optional prose rewrite, and structured auditor checks. `paper_fill` checks approval age and re-runs risk before applying a local fill. Per-card fields are reset so a later rejection cannot inherit `submitted=True`. Graph order counting includes prior submitted decisions.

The graph does not contain the heartbeat conditional edge described in historical material. `heartbeat` is a separate diagnostic; there is no scheduler or intraday feed in this pack. Direct `cycle` and graph now share `decisions.decide()`, projected-risk evaluation, target construction and decision-time lesson filtering, with an identical-input parity regression. They still have different orchestration/approval/logging paths; this is not full execution parity.

Snapshot state now includes the immutable portfolio-target payload and marked target equity. Missing held-symbol marks fail rather than silently valuing those positions at zero. Requested allocations preserve cash and are not approvals. The separate `paper` CLI provides durable orders, reservations, partial buys/sells and session accounting; graph `paper_fill` remains the legacy immediate-close demonstration. Do not connect a broker to that node.

## State and storage

`DeskState` contains cycle timestamp/thread, model cards, focus index, retrieved memories, proposal, risk, human response, submitted flag, snapshot P&L, and accumulated decisions. Decision accumulation uses an append reducer; per-card fields overwrite. Checkpoint payloads must never contain API keys or arbitrary whole histories.

| Storage | Purpose | Durability limit |
|---|---|---|
| `graph_checkpoints.sqlite` | Pending workflow/interrupt | Survives restart when the file is preserved; not portfolio truth |
| `desk.sqlite` | Episodes and prototype book/fill IDs | Local transactions; no transaction spanning graph checkpoint and episode writes |
| `trust.yaml`, policy files | Prototype adaptation and explanatory policy | File-based, no multi-writer release transaction |
| `desk_log.md` | Human-readable log | Diagnostic, not a tamper-resistant audit stream |
| `audit.jsonl` | Legacy live-intent example | Not automatically written by every graph/cycle decision |

The default saver holds a live SQLite connection for the invocation and closes it afterward. Durability comes from the file and checkpoint commits, not from leaving a Python connection open overnight. In-memory savers are for tests and do not survive process restart.

## Revalidation and replay limits

- Risk and fill nodes are plain Python. The name assertions in the builder are smoke checks, not proof of least privilege or replay safety.
- HALT and changed caps are re-read before a toy fill. Risk exposure now uses supplied snapshot marks and pending reservations, but the legacy loss input is not true session P&L and no current quote binding is supplied. The durable `paper` engine has separate session/mark/approval rules.
- Fill IDs protect repeated economic application at the local book boundary. They do not make episode/vector/log writes exactly-once, nor create atomic risk reservations across concurrent processes.
- Replaying/forking a checkpoint is not a new authorization. Experiments must use a separate state store and non-submitting execution adapter.
- A failure after a fill but before episode/checkpoint commit requires inspection/reconciliation. Never resolve it by creating a new thread and blindly approving again.
- A changed intent/config or expired snapshot needs a new decision, not an old resume value.

Keep only one desk writer. The CLI raises its recursion limit to accommodate the default multi-symbol cycle; that is a bounded graph traversal setting, not a trading budget. Hard order/cycle budgets must remain explicit.

## Target service extraction

The paths now share deterministic decision/allocation/risk helpers. Continue extracting orchestration behind a service taking immutable evidence/config plus explicit clock/store ports; helper parity is not a substitute for full lifecycle parity. The graph should emit an intent and wait for an authorization service, not own broker credentials. Execution owns outbox dispatch/reconciliation. Use a durable approval record keyed to intent/account/config hash and expiry, not a bare `"approve"` string as production authorization.

If later splitting bull/bear nodes, add a real barrier for convergence, for example `add_edge(["bull", "bear"], "pm")` with the appropriate state reducers. Do not assume two independent incoming edges always provide the barrier semantics needed across retries/unequal branches. Keep risk serialized against the authoritative portfolio.

## Verification

```bash
uv run --no-sync pytest tests/test_graph_langgraph.py tests/test_v3_invariants.py -q
```

Shipped tests cover HALT, interrupts, approve/reject, HALT after pause, per-card reset, order counting, expiry, no approved-size increase, local fill deduplication and persistent-saver resume in a new process. Additional acceptance requires crash-point injection across fill/episode/checkpoint commits, current-data/config binding, atomic reservations, and direct/graph parity. See [acceptance matrix](testing-and-acceptance.md) for which are currently automated versus still target work.

Official reference: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/durable-execution). Validate API examples against the pinned lockfile before adopting new persistence backends.
