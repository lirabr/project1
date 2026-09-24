# Requirements and boundary contracts

This is the implementation contract for the target system. The starter schemas implement only a subset: `PortfolioTarget` and simulator boundaries validate their invariants explicitly, while legacy dataclasses remain smaller and do not automatically enforce all runtime constraints. See the [capability register](trading-agents-architecture.md) before treating a field/control as implemented.

## Required invariants

| ID | Requirement | Admission gate |
|---|---|---|
| DATA-1 | Every input has instrument identity, event time, availability time, retrieval time and source/adjustment lineage | Credible research |
| DATA-2 | A decision uses only available completed observations; missing/stale data cannot create an order | Paper lifecycle |
| RES-1 | Training labels mature before training cutoff; transforms fit only on past data; OOS intervals are unambiguous | Research |
| RES-2 | A reproducible experiment includes all trials, costs, holdout identity and independently checked timing | Candidate admission |
| MOD-1 | Current inference binds a frozen model/feature artifact; registry metadata alone cannot authorize it | Paper model admission |
| RISK-1 | Nonfinite/unknown portfolio state fails closed; projected positions and reserved cash remain within limits | Paper lifecycle |
| RISK-2 | Session loss uses marked equity change net of external cashflows, not lifetime unrealized gain/loss | Paper lifecycle |
| AUTH-1 | Approval is human-controlled, scoped to exact intent/account/environment/version, expiring and revocable | Any submitted order |
| EXEC-1 | Durable economic effects are idempotent; ambiguous outcomes reconcile before retries | Broker paper |
| EXEC-2 | Every broker fill/cash movement maps to ledger events; discrepancies block new exposure | Broker paper |
| MEM-1 | Original situations are immutable; outcome availability controls retrieval; executed and counterfactual outcomes differ | Adaptive memory |
| POL-1 | Policy changes are typed, bounded, versioned, reviewed and reversible; hard limits cannot be rewritten by agents | Adaptation |
| OPS-1 | Restart begins halted until reconciliation; backup restore cannot replay old approval into submission | Certified operation |
| AUD-1 | Decision → authorization → order → fill → outcome lineage is durable and externally verifiable | Broker paper/live |
| SEC-1 | Agents and research have no trading/withdrawal authority; secret and environment boundaries are enforced | External integrations |

## Envelope for events and artifacts

Every target event includes `schema_version`, `event_id`, `correlation_id`, `causation_id`, `environment`, `account_id` where applicable, `occurred_at`, `recorded_at`, `producer_version`, and payload hash. Use UTC-aware ISO timestamps for interchange; retain venue timezone/session ID separately. IDs are stable across retry. Decimal quantities/money or integer minor units must have explicit precision; binary floats in the prototype are not an accounting standard.

Immutable artifacts include `artifact_id`, content digest, source revision, dependency-lock digest, input manifest IDs, creation time and schema version. New revisions create new identities; do not mutate promoted objects in place. Validate deserialized payloads at boundaries, reject extra/unknown policy keys, and reject NaN/Infinity, invalid enums, unsupported precision, and stale schemas.

## Domain schemas to implement

| Contract | Essential fields / constraints |
|---|---|
| Instrument | Stable ID, venue symbol, asset class, currency, timezone/calendar, tick/lot size, active interval, corporate-action identity; never infer crypto solely from punctuation |
| BarSnapshot | Instrument, timeframe, interval start/end, availability/retrieval time, OHLCV, complete flag, source, adjustment basis, quality result and hash |
| FeatureSnapshot | Instrument, decision cutoff, feature schema/hash, source snapshot IDs, values; all source availability at/before cutoff |
| Label | Horizon in instrument bars, start/end/availability timestamps, outcome and costs basis; absent until mature |
| ModelArtifact / Signal | Frozen estimator/transforms, training range, max label-end, feature schema, trial/holdout IDs; signal includes score kind, horizon, calibrated confidence if actually available, expiry |
| PortfolioSnapshot | Account/environment, valuation time, cash/settled buying power, marked positions, realized/unrealized P&L, fees, session baseline, open orders/reservations, reconciliation status |
| TradeIntent | Intent ID/hash, symbol/instrument, action BUY/REDUCE/CLOSE, quantity or bounded notional, limit/price collar, time-in-force, strategy/model/policy/data identities, rationale references, expiry |
| RiskAuthorization | Exact intent hash, portfolio/config version, allowed quantity/notional, checks and reasons, reservation ID, expiry; cannot exceed request |
| HumanApproval | Approval ID, authenticated operator, account/environment, intent and authorization hashes, decision, bounded amount/price, issued/expiry times and revocation status |
| Order / Fill | Stable client-order ID, broker-order/event IDs, state, cumulative filled quantity, price, fees, timestamps; cumulative quantities are monotonic and cannot exceed approved amount |
| DecisionEpisode | Situation snapshot ID, proposal/gate/approval IDs, evidence/citation set and eventual outcome link; an intent is not an executed trade |
| Outcome / Reflection | Executed or counterfactual type, entry/exit/fill IDs, return after costs, realized P&L, initial risk if R-multiple used, close-only versus high/low excursion definition, outcome availability and lesson |
| PolicyRelease | Typed bounds, digest, effective time, evidence/approver, previous version; separate from explanatory markdown |

## Implemented portfolio and simulator subset

`PortfolioTarget` validates nonnegative finite weights totaling at most one, explicit residual cash, timezone-aware decision/execution bounds, and lineage. Its mapping is immutable and its canonical hash identifies the whole requested allocation. `PlannedOrder` identities bind target, symbol, direction, quantity and reference price. This interface is shared by allocation research and the decision service; it does not grant execution authority.

The durable `paper` simulator binds each approval to target ID, order ID, risk-policy digest, reviewer, expiry and all-in cost allowance. It serializes reservations with SQLite `BEGIN IMMEDIATE`, handles buy/sell partial fills and average-cost accounting, and commits each fill and its audit event together. Reusing an ID with changed economic payload is rejected. Session baselines and cashflow offsets survive reconnects. Its order states are `OPEN`, `PARTIAL`, `FILLED`, `CANCELLED`, and `UNKNOWN`; rejection occurs before insertion and expiry blocks fills without silently releasing reservations. UNKNOWN requires investigation and has no automatic resolution API.

These are local single-environment simulator contracts, **not completion of AUTH-1/EXEC-1/EXEC-2**. Missing work includes authenticated identities, account/environment binding, revocation, exact decimal/lot precision, broker acknowledgments/outbox/reconciliation, cancel-fill races and full event-based recovery. Legacy graph approvals remain a separate immediate-close demonstration. Never feed real broker fills into the simulator's rejection-on-cancel/expiry API; actual external fills must be reconciled even after local authorization expires.

Model artifacts bind serialized bytes, feature definitions, model source and runtime versions. Local approval records bind model ID and a human-reviewed evidence-file digest. Source snapshots and research runs are retained by identity, but hashes are not signatures and the repository does not provide external trusted retention or statistical promotion certification.

## Target order state machine

```text
PROPOSED -> REJECTED
PROPOSED -> AUTHORIZED -> EXPIRED / REVOKED
AUTHORIZED -> RESERVED -> DISPATCH_PENDING -> ACKNOWLEDGED
DISPATCH_PENDING -> UNKNOWN -> reconciled existing order OR proven-not-accepted
ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED
ACKNOWLEDGED / PARTIALLY_FILLED -> CANCEL_PENDING -> CANCELED
ACKNOWLEDGED -> REJECTED_BY_VENUE
```

A fill may race a cancel; reconcile cumulative fills before releasing the remaining reservation. Never undo an actual fill because the local order was marked canceled. UNKNOWN is not rejected. Query by stable client-order ID and broker history before deciding whether submission is safe to retry. Manual/external orders are quarantined for review rather than ignored.

Target transaction boundary: reserve + persist authorization/order/outbox together; later, deduplicate fill + update ledger + persist event together. Broker APIs and the local database cannot share a transaction, so reconciliation is mandatory. A graph checkpoint does not provide exactly-once broker execution.

## Approval and change semantics

A signature/identity alone does not imply approval of a modified order. If symbol, environment, model/policy, quantity, price bounds, or expiry changes, make a new immutable intent. Risk may reduce or reject approved size, never increase it. A changed risk config invalidates outstanding approvals unless a reviewed compatibility rule explicitly proves the change only tightens bounds.

HALT prevents new risk. Canceling orders and flattening/reducing exposure are distinct, authenticated operations with separate evidence and broker confirmation. Config switches and confirmation phrases are not authentication.

## Data and state ownership

Research reads frozen snapshots; it never writes the execution ledger. Execution owns economic truth, broker reconciliation and reservations. Memory derives lessons from execution events and cannot edit fills. Graph checkpoint storage holds orchestration state, not the authoritative portfolio. Feature/vector indexes are rebuildable; ledger/evidence records are not disposable caches.

## Migration and compatibility

Use numbered schema migrations, backup before upgrade, test forward migration from the previous release and recovery with an interrupted migration. Do not point v3 experiments at a v2 SQLite database and assume compatible semantics. Start fresh research/demo state; import historical logs only through an explicitly designed labelled importer. Never copy test-generated audit logs into a new operational account.
