# Verification and acceptance matrix

Passing current unit tests certifies only their stated invariants. It does not certify the complete design, broker execution, alpha, or live readiness. The [capability register](trading-agents-architecture.md) tracks the missing implementations.

## Local verification commands

From `trading-desk`:

```bash
uv sync --locked --python 3.12 --extra dev --extra graph
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests
uv run --no-sync desk-research --help
```

Current reviewed environment: macOS, Python 3.12, locked core/dev/graph dependencies. The expanded suite has **71 tests**. Test fixtures redirect runtime/config state into temporary directories and reject Python socket connection attempts. This is a test guard, not an OS-level network sandbox; native SDK/network isolation belongs in integration infrastructure. A synthetic research pipeline and separate-process graph restart avoid dependence on downloaded prices.

From the outer pack:

```bash
python3 tools/validate_pack.py
python3 tools/project_pack.py verify-source ../project1-v2
python3 tools/project_pack.py bundle
```

Pack validation checks Python/TOML syntax, local Markdown links/fences, documented CLI subcommand names and ZIP contents if present. It does not render Mermaid, authenticate providers, prove all prose claims, or certify operational controls. The source check compares every original file hash. ZIP generation excludes runtime data, caches, environments and credentials.

## Current automated coverage

| Area | Files | What is actually asserted |
|---|---|---|
| Research primitives | `test_risk_free_research.py`, `test_leakage.py` | Feature list, bounded scores, fit, cost monotonicity, forward folds, forward label reconstruction |
| New research regressions | `test_v3_invariants.py` | Unknown labels remain missing, future-batch-independent momentum, exact small next-open calculation, terminal liquidation, initial-loss drawdown, disjoint fold boundaries |
| Synthetic pipeline | `test_v3_pipeline.py` | At least three folds, labels mature before fit cutoff, finite returns, no duplicate symbol/date OOS rows, overall return equals compounded fold returns, real Parquet/tear-sheet outputs |
| Prototype risk | `test_phase2_desk.py`, `test_risk_gate_consistency.py`, `test_v3_invariants.py` | Live flag, flat/no-order, clipping, kill/order/loss gates, projected crypto cap, nonfinite portfolio and invalid amount rejection |
| Legacy P&L | `test_risk_daily_loss.py` | Since-entry unrealized P&L arithmetic and rejection when that supplied number crosses a threshold; **not session-P&L correctness** |
| Auditor | `test_auditor.py`, `test_v3_invariants.py` | Structured score provenance, dangling citations, side/size, finite notional and card-symbol binding; **not arbitrary prose fact checking** |
| Paper fills | `test_phase2_desk.py`, `test_v3_invariants.py` | Cash debit, position update, insufficient-cash failure return, repeated fill-ID one economic effect |
| Graph | `test_graph_langgraph.py`, `test_v3_pipeline.py` | Interrupt/reject/approve, HALT including after pause, reset between cards, order count, expired snapshot, no size increase, duplicate local fill, persistent resume in a new process |
| Snapshot/reflection/trust | `test_v3_pipeline.py`, `test_v3_invariants.py` | Stale OOS score not relabelled current, no pre-entry excursion fallback, trust does not inflate score or amplify size |
| Prototype adaptation | `test_phase3_loop.py` | Regime corners, vector norm, heuristic weight changes, hardcoded policy condition, markdown propose/approve, identical-distribution PSI |
| Live disabled | `test_phase4_live.py`, `test_v3_invariants.py`, `test_v3_pipeline.py` | No broker invocation, default flags off, preflight permanently blocks unimplemented live path, hash/copy file existence |

The original 42 tests passed before hardening. Added regressions demonstrated 18 failures against the original behavior (15 research/risk/book cases and 3 graph cases) before the targeted fixes. Later tests extend coverage rather than implying all were initially failing. No production account or broker order was used.

## Required but not yet implemented acceptance

These are development gates, not skipped green tests. Create test cases alongside each feature and keep the associated requirement BLOCKED until they pass.

| Requirement | Positive case | Mandatory negative/fault cases | Gate |
|---|---|---|---|
| DATA-1/2 | Complete timestamped licensed snapshot, corporate-action lineage | Revised/future/incomplete bar, missing delisted symbol, timezone/holiday mismatch, stale unchanged price | 1/2/4 |
| RES-1/2 | Frozen manifest and independent cash/share replay match | Future appended rows change features, costs absent on exits, mixed calendar, overlap labels, holdout reuse, missing benchmark | 1 |
| MOD-1 | Approved model artifact produces current compatible inference | Tampered digest, wrong feature schema, unapproved registry stage, stale artifact, silent fallback | 1 |
| RISK-1/2 | Correct MTM equity, fees, cashflows, daily/weekly baselines | Missing mark outside focus, profitable lifetime but losing day, restart/session rollover, pending-order overcommit, negative buying power | 2 |
| AUTH-1 | Correct human/account/intent/version approval within bounds | Wrong identity/account, modified symbol/size, changed policy, expiry, revoked approval, agent auto-approval | 2/4 |
| EXEC-1/2 | One accepted order, multiple fills, consistent ledger | Timeout after acceptance, duplicate/out-of-order events, cancel-fill race, restart before/after commit, simultaneous writers, external/manual position | 2/4 |
| MEM-1 | Mature outcome retrieved at correct past decision time | Future lesson via FTS or vectors, open intent treated as evidence, entry vector overwritten, counterfactual labelled realized | 3 |
| POL-1 | Typed approved policy deployed then rolled back | Unknown keys, prose silently controlling execution, unreviewed change, trust raises limits, challenger mutates champion | 3 |
| Drift/watchdog | Separate quiet/closed/fresh/stale states | All missing data reported quiet, out-of-reference PSI tail ignored, stale shock repeatedly invokes council, failed feed hidden by a live process | 3 |
| SEC-1 | Provider/account scope bound to allowlisted adapter | Wrong provider key sent to another origin, prompt injection, unbounded response/tool loop, leaked secret in log | 3/4 |
| AUD-1 | Complete ordered external evidence stream | Truncation/reordering, rewritten local hashes, full disk, copy/export failure, missing intent before dispatch | 4/5 |
| OPS-1 | Halted restore and broker reconciliation before restart | Expired checkpoint auto-submits, missing WAL/events, corrupted backup, wrong account restored, second owner becomes active | 5 |

## Test levels and entry criteria

1. **Unit:** synthetic numerical examples and invalid inputs; no network or keys.
2. **Integration:** temporary real storage, end-to-end decisions and independently checked accounting; fixed clock/config.
3. **Fault/replay:** crash points around state/effect boundaries, duplicate delivery, UNKNOWN outcomes, unavailable dependencies, fill/cancel races. Check economic invariants, not only status strings.
4. **External paper:** only with explicit operator approval and dedicated paper credentials. Verify the actual venue API's behavior and account restrictions. Never run this tier in default CI.
5. **Observation/operations:** minimum sessions from the roadmap, independently reviewed evidence, restore drills and tested alerts. Real live orders require a separate release decision.

## Evidence record for a gate review

Record requirement/phase, PASS/FAIL/BLOCKED, release and lock hashes, data/model/policy IDs, command/scenario, expected positive and forbidden effects, actual result, timestamps, reviewer and unresolved exceptions. Include negative results and incident links. Do not record secrets, full private account identifiers or unnecessary personal information.

## Verification boundaries

This pack is verified offline on the local macOS environment. Linux CI is configured but has not been executed here. Market-data network availability, live or paper venue integration, optional MLflow UI/provider calls, Docker services, Mermaid rendering and Phase 5 infrastructure are not validated by these unit tests. They require their own phase evidence; no claimed green status is inferred.
