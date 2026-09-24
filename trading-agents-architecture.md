# Trading Desk v3 — architecture and capability boundaries

## 1. Purpose and success criteria

Build a laptop-first research system for equities and spot crypto that can test whether model signals, structured memory, and bounded language assistance improve decisions **after costs**. Research validity and operational correctness are independent requirements. Neither passing tests nor making money for a month proves both.

The delivered application is a **research and internal-paper prototype**, not a production trading platform. Real broker submission is absent and live preflight always reports that blocker. A useful negative research result is a successful project outcome; live trading is optional.

Start with daily, long/flat, unlevered equities. Evaluate crypto in a separate data directory and calendar. Exclude options, shorts, borrowing, derivatives, high-frequency trading, online reinforcement learning, and autonomous capital increases. Add markets only through the Phase 5 change process.

## 2. Six domains, two cross-cutting planes

The old stack mixed storage products, runtime responsibilities, and authority levels. Use a modular monolith with explicit ports instead. A module is not necessarily a process or service.

| Domain | Owns | Inputs → outputs | Must not do |
|---|---|---|---|
| D1 Data and features | Immutable source snapshots, instrument master, calendars, quality, feature definitions | Vendor records → validated dated features | Invent availability timestamps or impute tradable prices across closed sessions |
| D2 Research and model lifecycle | Hypotheses, training, walk-forward, benchmarks, artifact registry | Versioned data/config → frozen candidate and evidence | Promote on a single metric or silently overwrite a candidate |
| D3 Decision support | Deterministic proposals, optional LLM prose, provenance checks | Current signal + eligible lessons → typed intent | Submit orders, change numeric signals, approve itself, or alter limits |
| D4 Portfolio and risk | Valuation, session P&L, limits, reservations, approval validity | Intent + current portfolio → bounded authorization/rejection | Trust a stale checkpoint as current risk state |
| D5 Execution and accounting | Durable order lifecycle, broker adapters, fills, cash, reconciliation | Authorization → execution events and reconciled ledger | Accept agent prose as an order or blindly retry an unknown submit |
| D6 Memory and evaluation | Decision episodes, outcomes, retrieval, ablations, policy proposals | Decisions + matured outcomes → point-in-time lessons | Rewrite entry situations with exit features or promote its own policy |

**Control plane:** human approval, scheduler, mode/environment selection, HALT, release/change control, secrets, ownership, recovery. It governs every domain, not just execution.

**Evidence plane:** append-only events, lineage, run manifests, metrics, alerts, audit export, tests. It observes every domain. Hashes detect accidental edits only when compared with an independently trusted reference.

**LLM access is an adapter within D3/D6**, not a mandatory layer between market data and risk. The hot risk path and position watchdog need no LLM, embeddings, or LangGraph.

## 3. Deployment and code boundaries

Keep one package, `trading-desk/src/desk/`, one CLI, and one writer on the laptop. Use Parquet for research data, SQLite for prototype state, and a separate SQLite file for graph checkpoints. Do not install TimescaleDB, Redis, Qdrant, Kubernetes, or a scheduler framework merely to satisfy a diagram.

Current module mapping:

- D1: `data.py`, `features.py`, `leakage.py`, snapshot storage in `artifacts.py`.
- D2: `models.py`, `walkforward.py`, `backtest.py`, `tracking.py`, frozen models in `artifacts.py`, `reports.py`.
- D3: `snapshot.py`, `agents.py`, `auditor.py`, shared `decisions.py`, `cycle.py`, `graph.py`; disabled shadow boundary in `sentiment.py`.
- D4: `portfolio.py`, `risk_gate.py`, marked state/reservations in `ledger.py`; full venue/account accounting remains a gate.
- D5: durable internal simulator in `ledger.py`; legacy toy book helpers in `memory.py`; `live.py` remains an intent-only stub.
- D6: `memory.py`, `reflect.py`, `vectors.py`, `regime.py`, `trust.py`, `drift.py`, `policy.py`.
- Shared boundaries: `contracts.py`, `io_utils.py`, `audit.py`, `cli.py`.

Refactor by extracting tested boundaries, not by immediately creating a `packages/` tree. `decisions.py` now shares direct/graph proposal and projected-risk logic, while `portfolio.py` supplies the common allocation/target/planning contract. `ledger.py` separates durable order/fill/session tables from episodes within the existing SQLite file. Direct/graph orchestration and legacy fills remain distinct; full execution parity and clock/store/config injection are still work. Domain code depends on contracts/ports; adapters depend on domain code; never import a broker client into an agent module.

FinRL-X inspired the weight-centric interface, not a package dependency or copied execution code. Preserve residual cash, never substitute a fabricated price, and keep requested portfolio weights separate from authorization. Both the research allocator and desk use equal/inverse-volatility weights and optional bounded regime reductions. `PortfolioTarget` carries immutable weights, explicit cash, decision/execution times and model/data/config/evidence identities. The rebalance planner covers all holdings and targets, requires fresh marks, includes exits and orders sells before buys; reservations do not spend unfilled sale proceeds.

Move to PostgreSQL only when multiple writers, transactional reservations, migrations, or operational recovery require it. A PostgreSQL checkpointer does not itself make the portfolio safe for concurrent writers. Run a single execution owner until locking, reservation, and fencing tests pass. Keep durable research artifacts in object storage when laptop backups become inadequate. Add a vector service only after retrieval quality or measured latency justifies it.

## 4. Decision and execution flow

Target flow:

1. Acquire the environment's single-writer lease; reject overlapping runs.
2. Validate complete bars, market calendar, availability, corporate-action basis, and freshness.
3. Value **all** positions and open-order reservations, not only the focus list.
4. Load an approved immutable model artifact and generate current inference. Historical OOS scores are replay evidence, not a model server.
5. Retrieve only lessons whose outcomes were available at the decision timestamp.
6. Produce a deterministic signal/intent; optionally rewrite prose with bounded LLM access.
7. Validate schema, symbol, finite numbers, model provenance, citations, and policy version.
8. Reserve projected risk and cash; persist the immutable intent and its hash.
9. Obtain a human decision tied to intent hash, account, environment, expiry, and policy version.
10. Recheck HALT, approvals, current marks, caps, cash, open orders, and market session immediately before execution. Any material change invalidates the authorization.
11. Atomically persist order intent/outbox; dispatch with a stable client-order ID. An ambiguous timeout becomes UNKNOWN and reconciliation, not a fresh order.
12. Reconcile acknowledgments, partial fills, cancels, rejects, positions, fees, and cash. Store deduplicated events.
13. Reflect only on matured outcomes. Preserve the original situation; keep counterfactual outcomes distinct from executed returns.

Steps 1–13 remain the **target contract**, not a claim that the starter implements them end to end. Legacy cycle/graph fills still use the snapshot close immediately. The separate `paper` simulator now has explicit planned/approved partial buys/sells, fees, session baselines and atomic local events, but manually supplied marks/fills are not a realistic exchange fill model. Do not equate either path with next-open research or broker certification.

## 5. Research correctness

- Daily observations are not vendor point-in-time data. Yahoo adjusted history can change; record vendor, retrieval time, adjustment basis, and raw-data hashes. A hand-picked modern universe has survivorship/selection bias.
- `label_horizon_days` is a legacy name: its unit is **observed bars per instrument**, not calendar days. Feature rows carry `label_end`; training uses only labels matured by the training cutoff.
- Momentum scoring must depend on training-fitted reference distributions, not ranks across an entire future test batch.
- Walk-forward windows must not overlap. All transforms fit on training only. Preserve a final holdout and a trial ledger; repeatedly tuning on OOS results makes them training evidence.
- Starter execution convention: close-t signal → open-(t+1) allocation → following open return; one signal shift, entry/exit costs, terminal liquidation. Interval returns are indexed by entry-open date. Folds start flat and liquidate independently; the total report compounds those same fold intervals without bridging gaps. This is a vectorized weight approximation, not a full share/cash ledger; weight drift, liquidity, dividends, and corporate actions need explicit treatment before promotion.
- Separate equity and crypto runs. Mixed calendars currently fail closed rather than create synthetic weekend equity trades.
- Compare with cash and asset-appropriate buy-and-hold, then a matched-exposure baseline. SPY is not the sole benchmark for crypto. Walk-forward reports now charge benchmark entry/exit costs and include cash/matched-exposure results; the standalone `buy_and_hold_returns()` helper is still gross. Optional additional benchmarks must be present in the declared data universe.
- Report net returns, drawdown, turnover, exposure, independent trades, uncertainty, cost sensitivity, and fold dispersion. Current `hit_rate` means positive-return intervals and `n_trades` counts turnover-active intervals, not completed trades. Neither is an execution statistic.
- Candidate selection must account for multiple trials and correlated overlapping labels. No fixed Sharpe or trade-count threshold establishes alpha. Use block bootstrap/robust uncertainty estimates and a holdout suited to the horizon.

## 6. Portfolio invariants

Define session P&L as `current_equity - session_start_equity - net_external_cashflows`, including realized/unrealized P&L and fees. Equity is marked cash plus positions; preserve session baselines across restart and use an explicit venue calendar/timezone. Crypto's risk session can use UTC, but must be declared.

Risk is evaluated on **projected** exposure including pending orders. Use the same denominator everywhere: the prototype crypto limit is crypto/gross invested notional, so a first all-crypto order correctly fails a 30% cap. A separate crypto sleeve needs its own declared policy; do not silently reinterpret the denominator as account equity.

Unknown or stale marks, malformed/nonfinite numbers, stale approvals, unknown order status, unreconciled cash, exhausted order budgets, and failed audit persistence all prevent new risk. Cancel and independently authorized reduce-only actions need their own safe path. HALT is **not** flatten: the starter never cancels or closes a broker position.

## 7. Memory and adaptation

Store decision-time features and evidence IDs separately from outcome-time prices and availability timestamps. Checkpoints resume one workflow; they are not historical lessons. Do not retrieve open intents as proven lessons. Retain immutable entry vectors and attach outcomes later.

Unit-normalizing raw RSI, returns, and ordinal regime IDs does not produce a useful similarity metric. Fit scaling on past data, encode categorical regimes appropriately, filter by instrument/asset/horizon, and evaluate retrieval against labelled examples before adopting it.

Adaptive trust is a hypothesis, not learning proven to improve returns. Keep the model score unchanged; any experimental adjustment may only reduce proposed size. Freeze default weights for baseline comparisons. Require attribution/calibration evidence, sufficient independent outcomes, and held-out ablations before enabling updates. LLM prose does not currently change numeric decisions, so a claimed trading benefit from the prose alone would be misleading.

Policy markdown is explanatory. The starter's string-matched `risk_off` rule is not a general policy engine. Planned executable policy must be versioned typed configuration with bounds, tests, explicit approval, and rollback. Never translate arbitrary markdown into execution authority.

## 8. Capability and gap register

Priority: **P0** blocks credible research or any external execution; **P1** blocks reliable operation/adaptation; **P2** is optional optimization. “Target” entries remain development work.

| Priority / area | Verified starter boundary | Required completion / owning phase |
|---|---|---|
| P0 causal research | Unknown labels, train-based momentum ranking, nonoverlapping folds, actual label-end purge, next-open timing have regression coverage | Independent ledger cross-check, full corporate-action/calendar tests, holdout/trial accounting — Phase 1 |
| P0 risk accounting | Durable `paper` ledger has marked equity, session/cashflow baselines, missing/stale-mark rejection and atomic cash/share reservations. Legacy graph/cycle loss remains since-entry | Independent accounting parity, exact precision, venue-defined session automation, weekly controls and recovery — Phase 2 |
| P0 order lifecycle | Durable simulator supports partial buys/sells, fees, cancellation, UNKNOWN blocking and fill/event atomicity. Legacy toy fills remain separate | Realistic liquidity/fill model, broker state machine, outbox/reconciliation, cancel-fill races and corporate actions — Phases 2/4 |
| P0 graph safety | Shared allocation/proposal/projected-risk helpers, parity regression, per-card reset, approval timeout and local toy-fill deduplication | Full execution parity, authenticated intent-bound authorization, transactional episode/outbox and process-crash drills — Phases 2/4 |
| P0 model lifecycle | Frozen estimator/transform bytes with feature/model code hashes, explicit local approval, current inference and no silent fallback in approved mode; old YAML registry remains metadata | Enforced statistical/holdout promotion policy, revocation and trusted release provenance — Phase 1 |
| P0 data quality | Content-addressed Yahoo/feature snapshots; explicit optional sessions and dated membership; missing/stale/incomplete latest bars rejected | Authentic PIT availability/calendar sources, symbol master, corrections/corporate actions/delistings — Phases 1/4 |
| P0 live | No broker API; preflight always blocked; live gross/day-order config is not implemented | Separate account/mode configs, broker-paper certification, independently reviewed adapter — Phase 4 |
| P1 reflection | Historical-mark annotation remains separate from simulator sell/fee events; not a realized R-multiple | Executed net outcomes versus counterfactual labels; immutable situations and maturity checks — Phases 2/3 |
| P1 retrieval | Shared decision service filters candidate lessons by entry/exit availability; raw search remains exploratory and vectors can be overwritten at reflection | Immutable entry vectors, true outcome-type eligibility, frozen scaling, precision/diversity evaluation — Phase 3 |
| P1 trust/policy | Heuristic trust; markdown approval; only a hardcoded policy condition executes | Shadow-only adaptation, typed policy and causal ablation — Phase 3 |
| P1 drift/heartbeat | Daily-feature diagnostics, no scheduler/position watchdog; several config fields unused | Explicit freshness states, tail-sensitive PSI, train-only references, deduplicated triggers — Phase 3 |
| P1 audit | Durable simulator order/fill/event writes are transactional; legacy JSONL hashes/local copy remain separate; no remote anchoring or universal decision stream | Independent retention, decision-to-fill lineage, sequence/gap verification and restore drills — Phases 4/5 |
| P1 LLM safety | Prose rewrite and shadow-news config disabled; shadow callback validates timestamps, bounded requests/declared costs and typed outputs, but has no provider integration | Provider-specific secrets/egress, billed-cost enforcement, redaction, injection tests and measured utility — Phase 3 |
| P1 reproducibility | Python 3.12, lockfile, isolated/offline unit tests | Multi-platform CI, artifact/source hashes, clean smoke, dependency review — Phase 0 onward |
| P2 scale | SQLite/Parquet sufficient for current single operator | Measure bottlenecks before adding PostgreSQL, queues, vector servers, cloud — Phase 5 |

Other misleading legacy knobs include `vol_target_annual`, research `initial_capital`, `paper.starting_cash`, `paper.auto_submit`, `min_bars` in the paper risk file, heartbeat polling, custom policy paths, and drift thresholds that are not consistently read. `max_name_weight` is now consumed by shared target allocation and durable simulator risk; this does not turn the other legacy knobs into controls. They are not controls. The development acceptance rule is: implement and test a knob or reject/remove it in a versioned config migration; never silently accept it as enforced.

## 9. Security and failure boundaries

Market/news text is untrusted data. Agents receive no shell, write-enabled broker, withdrawal, or policy-approval tools. Research-generated code belongs in a sandbox without account credentials. Keep read-only data and trading credentials separate; check the venue's actual permission model rather than assume all brokers offer “withdraw-disabled” API keys.

Do not reuse a provider key with an arbitrary OpenAI-compatible base URL. Bind the selected provider and key explicitly, allowlist HTTPS origins, redact credentials, cap response sizes and tokens, and account for spend. Leave optional LLM access off until these controls are implemented.

Authentication and per-intent authorization are separate from a confirmation phrase. A boolean in YAML is neither an authenticated approval nor proof of venue permissions. No mode switch may turn a research process into a live execution owner.

## 10. Decisions and trade-offs

| Decision | Why | Revisit when |
|---|---|---|
| Modular monolith | Shared contracts without distributed failure modes | Measured independent scaling or security boundary requires a process |
| Daily equities first | Simplifies session accounting and validation | Separate crypto calendar/sleeve evidence passes |
| Agents optional | Establish numeric baseline and isolate benefit | Ablations demonstrate useful decision support after cost |
| SQLite + Parquet | Minimal installation and inspectable state | Multiple writers or tested HA requirement |
| Graph is orchestration, not authority | Replay/checkpoints do not authorize side effects | Never; retain boundary when changing framework |
| No live adapter in this pack | Missing execution/accounting safeguards are material | Phase 4 certification and explicit human authorization |
| Phase 5 is operations and governed expansion | Reliability must precede scale | Each scope change is a separately reviewed release |

Use [requirements and contracts](requirements-and-contracts.md), [roadmap](roadmap.md), [acceptance tests](testing-and-acceptance.md), and [operations](operations-runbook.md) as the detailed development contract. Historical conversation statements do not override this document.
