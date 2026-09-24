# Phase 3 — Measured memory and bounded adaptation

**Goal:** establish whether memory or decision support adds value over a fixed numerical baseline. Entry: Phase 2 accounting and prospective-paper evidence, not merely a populated SQLite file. No live keys.

## Inputs, outputs, resources

Input: immutable decision-time situations, matured outcomes, frozen model/policy, baseline results. Output: PIT retrieval, evaluation dataset, champion/challenger comparisons, approved policy artifacts, freshness/drift alerts. Existing stack is sufficient; no external vector DB or embedding provider is required.

## 1. Inspect the current diagnostics

```bash
uv run --no-sync desk-research trust
uv run --no-sync desk-research policy-show
uv run --no-sync desk-research drift
uv run --no-sync desk-research heartbeat
```

These are diagnostic commands, not an automated scheduler. The default equity panel has no BTC/ETH rows, so heartbeat reports `no_data`; that is expected, **not proof of a quiet market**. In a separate crypto-data shell, it examines the last daily feature row. Polling it every minute cannot create intraday observations. `fire_full_cycle=false` says nothing about service health or freshness.

Current PSI can miss distribution tails and does not reliably consume all YAML thresholds. Vectors still normalize mixed-scale raw features. The shared decision service now filters both text/vector candidates against stored entry/exit times and excludes open/future lessons, but raw memory search is exploratory and the original vector/outcome semantics remain incomplete. Treat these outputs as prototypes, not certified adaptation.

Bull/Bear outputs now include structured feature evidence, missing-value flags, timestamps and model/data identities. The default allocator remains capped equal weight; inverse volatility and explicit regime reductions are optional comparative experiments. `sentiment.analyze_news()` adds a disabled shadow-only callback boundary with availability and request/cost checks. It has no connected provider and never changes numeric decisions. A static HTML report replaces the need for a trading-enabled dashboard. Provider integration, empirical benefit and billed-spend controls remain admission work.

## 2. Correct the memory data model

1. Persist the entry situation exactly once, including feature/model/policy/data IDs and decision timestamp.
2. Attach executed net outcomes only after actual closure, or counterfactual outcomes after their defined horizon; include `outcome_available_at`.
3. Require `outcome_available_at <= decision_at` in **both** FTS and vector retrieval. Replaying an old decision with today's database must not reveal future lessons.
4. Never replace the stored entry vector with exit-day features. Fit vector scaling on past training data and version it; use categorical regime encodings, not ordinal distances by accident.
5. Filter compatible asset class/horizon, then rank and diversify. Measure precision/relevance against an operator-labelled set; citation count alone is not usefulness.
6. Establish retention and provenance. Pruning checkpoint state cannot delete the ledger or invalidate episode citations.

## 3. Evaluate before enabling adaptation

Freeze a champion (model only, fixed sizing). Compare challengers on identical snapshots, costs, fills, budgets, and eligible information:

| Arm | Variable being tested |
|---|---|
| A | Numerical model, no memory, fixed sizing |
| B | Same model plus PIT retrieval; deterministic memory rule |
| C | B plus optional LLM prose; evaluate explanation quality and cost, not assumed alpha |
| D | B plus bounded adaptive sizing; no change to model score or hard caps |

Predeclare metrics and decision rule: net return/drawdown at matched exposure, calibration, turnover, rejection rate, retrieval quality, operator utility, latency, and spend. Record negative results. Account for correlated outcomes and repeated trials; do not infer causal value from one winning week or force trades to increase sample count.

Trust heuristics are not calibrated per-agent attribution. The current code preserves the model score and never amplifies size through trust, but `reflect` still updates weights heuristically. Do not run reflection on the champion's production state during an ablation; use isolated frozen copies and explicit replay. A future shadow/adaptation flag must be wired and tested before adoption.

## 4. Turn policy prose into governed configuration

The existing demonstration is:

```bash
uv run --no-sync desk-research policy-propose "Evaluate a risk-off sizing hypothesis in shadow mode"
```

Read `data/artifacts/policy_pending.md`. Only after review:

```bash
uv run --no-sync desk-research policy-approve
uv run --no-sync desk-research policy-show
```

This archives/replaces markdown; it does **not** compile arbitrary English into sizing logic. A phrase such as “halve size for 48 hours” is not an implemented rule. Build typed policy parameters with bounds, effective time, digest, approver, test evidence, rollout scope, and rollback version. Policy permissions cannot modify hard risk limits or enable a broker.

## 5. Operational diagnostics, then optional language

- Fit drift references only on the approved training snapshot; compare matched instrument distributions. Include underflow/overflow bins, constant features, missingness and insufficient-sample states. Alert does not automatically retrain/promote.
- Add a true feed/process watchdog independent of agents. Distinguish CLOSED_SESSION, QUIET, STALE, MISSING, and ERROR. Deduplicate shocks by data/event ID with cooldown and a daily cycle budget.
- A scheduled daily desk runs on new completed bars, not every poll. Laptop sleep is expected; it is not suitable for unattended position control.
- Before optional LLM calls, implement provider/key binding, HTTPS allowlist, typed responses, redaction, injection isolation, per-call timeout/token cap, cycle/spend budgets and observable fallback. The current optional rewrite lacks this full boundary; leave `llm.enabled: false`.

## Tests and exit gate

```bash
uv run --no-sync pytest tests/test_phase3_loop.py tests/test_auditor.py tests/test_v3_invariants.py -q
```

Add acceptance cases for future-lesson exclusion, immutable vectors, no-data watchdog failure, PSI tails, replay isolation, and typed-policy rollback. Existing unit tests are not substitutes for these missing behaviors.

- [ ] PIT lesson eligibility and immutable situations verified through replay.
- [ ] Frozen champion/challenger experiment complete; insufficient benefit means keep the simpler baseline.
- [ ] Model scores remain unchanged and adaptation cannot raise hard limits.
- [ ] Drift/watchdog alerts have an owner and tested response; no automatic promotion.
- [ ] LLM remains disabled unless its safety, utility, and budget gates pass.
- [ ] Policy deployment is versioned/tested; markdown approval is not treated as executable authority.

Next: [Phase 4](phase-4-tiny-live.md), beginning with broker-paper certification, not a live configuration flip.
