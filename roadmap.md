# Delivery roadmap — dependency and evidence gates

## Scheduling rules

This is a gate-based development schedule, not a promise that a trading system becomes safe after a fixed number of evenings. Separate implementation work, validation work, and calendar observation. Do not compress evidence windows because code is finished. Research can end with “no candidate”; that permits simulator engineering, not live admission.

No start date, weekly capacity, budget, venue eligibility, or independent reviewer has been specified. Set these with the project owner at Phase 0. Until then the schedule is ordered work packages, not invented calendar deadlines. Review progress weekly and reforecast from actual throughput. Keep no more than one risk-changing feature in flight.

## Phase contracts

| Phase | Entry | Ordered work packages | Output / evidence gate | Dependency |
|---|---|---|---|---|
| 0 Reproducible laptop | Source pack | 0.1 tools; 0.2 locked environment; 0.3 isolated tests; 0.4 operating decisions | Clean install, green tests/lint, no accounts required, owner and budget recorded | None |
| 1 Credible research | Phase 0 | 1.1 frozen data; 1.2 timing/labels; 1.3 baselines; 1.4 cost stress/holdout; 1.5 versioned model | Reproducible evidence, at least 3 valid folds where history permits, candidate or explicit refusal | 0 |
| 2 Correct internal paper lifecycle | Validated harness; baseline enough for engineering | 2.1 marked ledger; 2.2 order/exit state machine; 2.3 risk/reservations; 2.4 approval/replay; 2.5 paper observation | Accounting balances, negative tests and recovery drills; at least 20 equity sessions of prospective evidence | 1 infrastructure gate |
| 3 Measured memory and decision support | Stable Phase 2 baseline | 3.1 PIT lessons; 3.2 retrieval evaluation; 3.3 fixed/adaptive ablations; 3.4 drift/freshness; 3.5 optional LLM/policy | Frozen champion/challenger evidence; no increase in authority; disable additions without benefit | 2 |
| 4 Broker-paper certification; optional tiny-live canary | Phase 2/3 gates; approved candidate required for live | 4.1 separate adapter/account; 4.2 reconciliation; 4.3 fault injection; 4.4 broker-paper observation; 4.5 independent live decision | At least 20 broker-paper equity sessions, no unresolved safety incidents, venue evidence; optional supervised canary | 2 and 3; all P0 closed |
| 5 Reliable operation and governed expansion | Certified paper release, or separately approved tiny-live release | 5.1 deploy/recover; 5.2 SLOs/budget; 5.3 release/rollback; 5.4 champion/challenger; 5.5 scope review | 30 calendar days of operational evidence plus successful restore/reconciliation drill; paper-only completion is valid | 4 paper certification; no requirement for real capital |

Observation windows are **minimum operating-policy gates**, not statistical proof of profit or completion estimates. Twenty sessions need not contain an unusual market event: supplement observed sessions with dated historical shock replay and outage injection. Do not claim a simulated shock was observed live. Extend observation if reliability or statistical evidence is insufficient. No need to manufacture orders to satisfy a count.

## Work sequencing and permitted parallel work

Critical path: data/clock correctness → research → marked ledger → risk → durable execution/reconciliation → broker paper → optional live → governed operations.

- During Phase 1 data collection, develop synthetic research tests and the instrument/contract schema.
- During Phase 2 observation, implement Phase 3 offline retrieval experiments against an immutable copy. Do not mutate the champion book.
- During broker-paper observation, design Phase 5 backup/monitoring and run restore drills on a separate copy.
- Security, documentation, dependency review, and evidence collection run through every phase.
- A production adapter cannot be “parallelized around” unfinished accounting or risk gates.

## Roles and approvals

| Role | Responsibility | Approval boundary |
|---|---|---|
| Project owner/operator | Universe, lawful venue access, budget, observation, incident handling | Signs phase evidence and stops operation |
| Research engineer | Data/feature/model versions and holdout integrity | Proposes candidates, cannot unilaterally certify live |
| Platform/execution engineer | Ledger, adapter, idempotency, recovery | Produces operational evidence |
| Risk/release reviewer | Independent challenge of gates and changes | Approves live admission, risk changes and rollback criteria |

One person can perform the development roles. Before any live admission, obtain an independent review of the execution/risk release. Lack of a reviewer means paper-only; do not invent sign-off.

## Weekly review and change control

Review: outstanding P0/P1 items; fresh evidence; changes to source/config/data; all experiments including failures; operational incidents; spending; whether scope should shrink. Record release identity, reviewer, evidence references, unresolved issues, and next work package in the project's chosen tracker.

Promotion and completion are distinct: phase tooling may be complete with no approved model. Every gate has four possible results: PASS, FAIL, BLOCKED, or NOT APPLICABLE with an explicit reason. Only PASS permits the dependent capability. Reopening a P0 sends the affected capability back to its earlier phase.

The phase guides contain commands that exist today and clearly labelled work that must be built. There is no hidden `deploy`, `train`, `reconcile`, or live-submit command in the current CLI.
