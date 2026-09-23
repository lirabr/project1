# Phase 4 — Broker-paper certification and optional tiny-live canary

**Status:** development specification. The shipped code cannot submit to a real broker. Preflight always reports that live execution/reconciliation are not implemented. This phase cannot be completed by changing booleans or setting a confirmation phrase.

## Entry and outputs

Entry: Phase 2 marked ledger/replay gate, Phase 3 controlled decision support, all relevant P0 gaps closed. A genuinely admitted model is required for any live branch; “no candidate” means remain research/paper-only.

Output A: certified broker-paper release and operating evidence. Output B, optional and separately authorized: a supervised tiny-live canary. No live capital is required for project success or entry into Phase 5 operations.

Resources added only now: legally available broker-paper account and SDK, official market-data entitlement, least-privilege secrets, independent execution/risk reviewer, remote monitoring/audit storage, dependable host if supervision requires it. Verify actual venue permissions, fractional-share support, order types, market hours, account restrictions and tax/regulatory obligations. Never assume US venue eligibility or a key's withdrawal restrictions from a checkbox in this project.

## 1. Confirm the starter's boundary safely

From a clean/default workspace:

```bash
uv run --no-sync desk-research live-preflight
uv run --no-sync desk-research live-intent AAPL --submit
```

Expected: a blocked intent with `broker_called=false`; no network call to a broker. The legacy intent command uses a fabricated example proposal and zero portfolio inputs. It is an audit demonstration, **not** live risk verification. `max_live_gross_usd`, `max_live_orders_per_day`, and several other live config fields are not enforced. Do not attach an SDK to that function and assume the rest is safe.

Leave `enabled: false`, `allow_live: false`, and human approval enabled. Do not request/store live keys to execute this demonstration.

## 2. Build a separate execution adapter

1. Define immutable PAPER and LIVE runtime configurations with separate account IDs, endpoint allowlists, storage namespaces and secrets. Startup must fail on mismatched account/endpoint/environment. Never toggle `risk.paper.yaml` into live mode.
2. Implement broker ports for account, orders, positions, fills and cancel. Only the execution owner has trading scope; agent/research processes cannot import the secret or submit tool.
3. Implement the [order state machine](requirements-and-contracts.md), stable client-order IDs, deduplicated broker event IDs, transactional outbox, projected reservations, and UNKNOWN resolution.
4. Reconcile on startup, after reconnect, periodically, and before risk-increasing activity. Unknown external orders/positions halt new risk rather than being silently adopted or deleted.
5. Bind human authorization to account, exact intent, maximum quantity/notional/price, policy/model digest and expiry. Approval may reduce an order, never enlarge it.
6. Add quote/session freshness, tradability, order precision/minimums, cash/settlement constraints, price collars and fill-time limits.
7. Persist intent and approval before dispatch. Export decision/order/fill events to an independently controlled durable destination, with sequence verification and trusted anchoring.

## 3. Broker-paper certification

Run deterministic fake-broker tests first. Then, with explicit operator authorization for the external paper orders, test the actual broker-paper environment:

- Submit/acknowledge/partial fill/full fill/reject/cancel and cancel-fill races.
- Timeout before acceptance versus timeout after acceptance; restart before/after local commit.
- Duplicate and out-of-order events; account/key mismatch; rate limits and reconnect.
- Manual external orders, unexpected positions, clock skew, missing quotes, market closure, and corporate actions.
- HALT while approval is pending and while an order is open; no new exposure, controlled cancels, reconcile any fills.
- Audit destination unavailable and recovery from backup.

Collect at least **20 broker-paper equity sessions** after those tests pass. Every cash/quantity/order discrepancy must be explained; no unresolved safety incident is acceptable. Paper fills omit important market effects; do not use a good paper month as proof of executable alpha. See the [official paper limitations](https://docs.alpaca.markets/docs/paper-trading) for the selected example venue.

## 4. Optional supervised tiny-live release

This is a future operational action, not a command supplied by the pack. Require a fresh independent review and explicit operator authorization for the actual release and orders.

Conservative starting policy example, to be approved rather than silently activated:

- One venue, equities only, long/reduce-only, no leverage.
- At most $250 per name and $500 gross including outstanding orders; at most two risk-increasing orders per session.
- Declare session and weekly loss limits **before** funding; “tiny” dollars are not a substitute for a loss rule.
- Human approval for every order; session supervision and a separate broker UI for emergencies.
- No automatic capital or universe increase; any expansion goes through Phase 5.

The paper bot must not receive live keys. Verify broker-side restrictions where supported. Restrict the funded account to the approved amount and account permissions; inability to restrict withdrawals through an API must be handled with the venue's actual account/security controls.

## 5. Stop and rollback

On unknown order state, unexplained fill/cash, stale risk inputs, audit failure or loss-limit breach: stop new risk, invalidate pending approvals, reconcile through the trusted execution owner/broker UI, then decide explicitly whether to cancel or reduce. HALT alone is not flatten. If credentials may be exposed, revoke them through the venue. Preserve evidence before restarting.

Return to the last certified paper release if cause or recovery is uncertain. Never raise caps, switch accounts, resubmit an ambiguous order or suppress a check to “unstick” a release.

## Tests and exit gate

```bash
uv run --no-sync pytest tests/test_phase4_live.py tests/test_graph_langgraph.py tests/test_v3_invariants.py -q
```

These shipped tests establish **no broker submission**, not broker integration certification. The adapter and chaos scenarios above must be implemented separately.

- [ ] All relevant P0 gaps closed with tests; independent reviewer signs evidence.
- [ ] At least 20 broker-paper sessions and reconciliation/incident/restore drills pass.
- [ ] Paper/live accounts and authority boundaries cannot be crossed by configuration accident.
- [ ] Operations handbook, alerts, loss limits and operator availability are explicit.
- [ ] Choose PAPER ONLY or separately authorized supervised canary; no default live admission.

Next: [Phase 5](phase-5-operations.md). It is about reliable operation and controlled changes, not unlimited autonomous trading.
