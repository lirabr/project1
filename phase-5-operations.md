# Phase 5 — Reliable operation and governed expansion

**Goal:** turn a certified paper desk, or an independently approved tiny-live canary, into a maintainable system with measurable reliability, controlled model evolution, recovery, and cost discipline. This phase grants **no new trading authority by itself**.

**Status:** designed, not implemented as a Phase 5 CLI. The current starter has no deployment agent, production scheduler, broker reconciliation service, or automated recovery. Do not interpret the steps below as shipped functionality.

## Inputs, outputs, ownership

Inputs: Phase 4 broker-paper certification; immutable release/model/data/policy identities; marked ledger and execution records; chosen hosting/account/secret controls; approved SLOs and loss limits. Optional input: an explicitly approved tiny-live release.

Outputs: operating service, tested backups/restoration, alerts and escalation, release/rollback process, model monitoring, monthly risk/cost review, and a decision to stay small, retire, or pursue one bounded expansion.

Owner: named operator. Approvers: risk/release reviewer and project owner. A single hobby operator should choose supervised scheduled operation rather than pretend to offer 24/7 support. If nobody can respond, do not run new risk autonomously.

## 5.1 Establish the operating boundary

1. Select PAPER ONLY or the existing authorized live canary; record account/environment IDs. Phase 5 completion in paper-only mode is valid.
2. Freeze a release manifest: source revision, lockfile, schema/migration version, risk/policy/model/data digests and rollback release.
3. Choose an always-on host only if needed. Separate research from execution, use a single execution owner and persistent storage, synchronize time, apply OS updates, run as an unprivileged account, and restrict outbound access to approved services.
4. Establish secret rotation/revocation, access review, account MFA and tested operator access outside the bot. Backups never contain plaintext provider/trading keys.
5. Add a scheduler with a market-aware clock, single-flight lease, idempotent run IDs and missed-run policy. A missed signal is skipped/recomputed after reconciliation, not replayed blindly.

Deliverable: inspectable deployment/configuration with no new risk permissions. Acceptance: cold start stays halted until state and broker reconciliation succeed; a second worker cannot acquire execution ownership.

## 5.2 Reliability and observability

Agree thresholds before operation; these are proposed daily-desk targets to validate with the venue, not assertions about this prototype:

| Indicator | Initial operating objective / action |
|---|---|
| New-risk gate coverage | 100% of submitted risk-increasing orders have linked current authorization; any violation is a critical incident |
| Broker/ledger reconciliation | Zero unexplained cash, quantity or open-order mismatch before new risk |
| Scheduled job delivery | At least 99% within the declared session window over a rolling month; a missed job must never cause uncontrolled catch-up |
| Data freshness | Venue/calendar-specific maximum age; unknown/incomplete data blocks new risk, including a stale but unchanged price |
| UNKNOWN order age | Page operator immediately; no new risk until resolved within the approved response window |
| Recovery point | No accepted broker fill may be lost economically; reconstruct missing local events from broker history before restart |
| Recovery time | Operator-approved target, initially 60 minutes in supervised daily operation; remain halted if missed |
| Audit export | Confirm external receipt and sequence continuity at least each session; local copies are not off-host durability |
| Spend | Enforced per-cycle/daily LLM limits and monthly data/hosting ceilings; no inference budget means deterministic fallback/no new decision |

Track feed age, last successful job, process heartbeat, clock skew, authorization rejects, order lag, reconciliation age, net exposure, session/weekly P&L, slippage, model/feature drift, retrieval quality, audit lag and spend. Alert channels must be tested with the actual operator. Do not put an LLM on the failure-response path.

## 5.3 Backup and disaster recovery

1. Define retention by data rights, operational needs and legal obligations; do not promise a universal regulatory retention period.
2. Snapshot SQLite using its backup API or migrate to tested PostgreSQL backups; copying an active `.sqlite` file without WAL handling is not sufficient.
3. Back up ledger/events, model/config manifests and source identities separately from rebuildable feature/vector indexes. A lost index can be rebuilt; a lost economic ledger needs reconciliation before use.
4. Use encrypted, access-controlled off-host storage with retention/versioning. Store trusted audit roots/checksums separately from writable application logs.
5. Restore into an isolated environment with all execution disabled. Validate schema, digests, event sequence, balances, pending approval expiry and broker history.
6. Reconcile and create fresh approvals before an operator authorizes restart. Never resume a restored live checkpoint directly into submission.

Acceptance: perform both a full-machine-loss drill and an interrupted-write drill, recording actual recovery time and any unaccounted events. Repeat after schema/storage changes and at an agreed recurring cadence.

## 5.4 Model, memory and release management

Use champion/challenger operation: challenger receives the same dated inputs in a separate state namespace and cannot trade. Model retraining can create a candidate, never automatically replace the champion.

For every model/policy change: hypothesis → immutable artifacts → unit/integration tests → historical holdout → shadow paper comparison → independent review → bounded canary → rollback/retain. Keep all failed trials. Compare after matched costs/exposure, not raw P&L from different books.

Memory compaction and embedding/scaling changes count as model changes because they alter retrieved evidence. Evaluate both accuracy and latency; retaining more memories is not automatically better. Keep every deployed release reproducible and reversible. Breaking migrations need a tested forward/recovery path and preserved pre-migration backup.

Rollback triggers: safety invariant violation, unexplained divergence, miscalibrated sizing, material unexpected cost/slippage, uncontrolled spend, or inability to reconstruct decisions. A roll-forward cannot erase incident evidence.

## 5.5 Controlled expansion, one axis at a time

Expansion is optional. First try reducing complexity or retiring weak strategies. For a justified change, choose only one of: more capital, another symbol/sleeve, a new venue, a higher frequency, another model, or greater automation.

Required change request:

- Objective and measured bottleneck/opportunity.
- Incremental worst-case exposure, liquidity/capacity/slippage stress and correlation impact.
- Data/calendar/venue/legal differences; account and permission changes.
- New risk limits and emergency response; explicit reviewer approval.
- Shadow evaluation, broker-paper re-certification and bounded canary.
- Stop conditions and exact rollback artifact.

A change in venue or frequency reopens Phase 1 data/execution assumptions and Phase 4 adapter certification. Raising capital reopens loss limits and capacity analysis. Do not increase capital just because a fixed calendar window elapsed or trust weights rose.

## Cadence

- Each run: data quality, reconciliation, authorization, budget, evidence persistence.
- Each session: balance/exposure review, unresolved orders, audit export, cost/slippage and backup health.
- Weekly: incidents, challenger results, dependency/security advisories, access changes, drift and costs.
- Monthly: actual reliability against SLOs, restore drill status, model/strategy retirement and capacity review.
- Quarterly or after a material change: independent risk/release review and full recovery exercise.

For daily paper development, shorten operational scope rather than claiming unavailable 24/7 supervision. Crypto live remains outside the initial canary until its continuous-operation requirements have a real owner.

## Exit gate and deliverables

Collect **30 calendar days** of operational evidence after the certified release is stable; this is an observation floor, not proof of future performance. Required:

- [ ] SLO dashboard and tested alerts with a named responder.
- [ ] Restore/reconciliation drills pass; no unexplained economic events.
- [ ] A shadow release and a rollback rehearsal succeed without changing live authority.
- [ ] Model/policy/retrieval changes are attributable and reproducible.
- [ ] Spending and data licenses reviewed; access and secret rotation rehearsed.
- [ ] Risk reviewer records STAY SMALL, PAPER ONLY, RETIRE, or one separately approved expansion.

Successful Phase 5 may mean permanently remaining paper-only or discontinuing an unprofitable strategy. That is governance working, not a reason to weaken a gate. See [operations runbook](operations-runbook.md) and [acceptance matrix](testing-and-acceptance.md).
