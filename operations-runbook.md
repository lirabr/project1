# Operations runbook

This document separates **current local commands** from **target operational procedures**. The starter has no broker connection. Never infer a real cancel, close, reconciliation, deployment or restore from a local success message.

## Operator preflight

Before any session: identify environment/account, source/model/policy version, state directory, data cutoff, next market session, operator and stop rules. Confirm no other writer. Unrecognized state or a restored database means remain halted until reviewed.

For the current default equity prototype, from `trading-desk`:

```bash
uv run --no-sync desk-research book
uv run --no-sync desk-research live-preflight
```

Expect live blocked. Book values are cost-based diagnostics, not independently reconciled equity. Do not use them to assess real account risk.

## Safe daily prototype routine

1. Preserve any research snapshot/results that the next download/run would overwrite.
2. Download and build completed daily features; examine missing/changed dates. Yahoo may include a still-forming daily row during the session; use completed bars after the close and validate the vendor/calendar before any certified deployment.
3. Run one intent-only cycle and inspect the strategy source, scores, gate reasons and citations.
4. Record whether the result is a research demo or a certified-paper session; never mix the evidence.
5. Keep reflection/trust experiments in a separate copied state; current reflection is not a realized trade close.

```bash
uv run --no-sync desk-research download
uv run --no-sync desk-research features
uv run --no-sync desk-research cycle
uv run --no-sync desk-research book
```

No scheduled job is installed by the pack. Laptop sleep, internet failure, missing data and graph expiry must not be treated as successful runs.

## Durable simulator routine

Use a dedicated `DESK_DATA_DIR` and, when needed, `DESK_CONFIG_DIR`. At the declared session boundary, initialize `paper session` with complete fresh marks. Generate a versioned portfolio target, inspect `paper plan`, approve a specific order with reviewer/cost allowance, and feed explicit simulated fills. Inspect `paper book --marks ... --session ...` for marked equity, net-of-cashflow session P&L, reserved resources and fill/fee statistics. Full formats are in the [starter README](trading-desk/README.md#durable-internal-paper-workflow).

These commands do not observe a broker. Do not relabel old marks as current, assume pending sale proceeds are cash, reset a session to hide a loss, or mix legacy toy fills with a certification dataset. UNKNOWN preserves reservations and blocks new buys; retain evidence rather than deleting state. A ledger event write failure rolls back the simulated fill. Research reports are available with `desk-research report` and contain no execution controls.

Model artifacts and snapshots are trusted-local executable/data inputs. Preserve manifests and approved evidence separately, and never load an arbitrary downloaded joblib file. Model approval is local review, not authentication or live admission.

## Stop procedure

Current default-path command:

```bash
uv run --no-sync desk-research halt
```

Inspect/reconcile before any intentional `halt --clear`. CLI, legacy risk gate and durable simulator now use one HALT resolver. The standard path follows `DESK_DATA_DIR`; custom paths come from the selected `--risk` config. Verify the resolved file in the intended profile before relying on it.

Target external-execution procedure:

1. Disable new risk at the execution boundary; revoke pending approvals and stop the scheduler.
2. Query broker-side open orders, recent fills, positions and cash through a trusted operator channel.
3. Determine which orders can be canceled; preserve filled portions. Flatten/reduce is a separate explicit operator decision with market/liquidity consequences.
4. Reconcile all economic events and preserve local/remote evidence.
5. Diagnose, test a corrected release, and require fresh authorization to restart.

## Incident playbook

| Symptom | Immediate action | Recovery evidence |
|---|---|---|
| HALT after graph pause | Reject/expire pending approval; do not create a replacement thread blindly | No new fill; new snapshot if restarting |
| Snapshot/approval expired | Recompute current data and decision | New intent, no reuse of expired authorization |
| Broker submit timeout | Mark UNKNOWN; never resend with a new client ID | Broker history resolves accepted versus not accepted |
| Duplicate or out-of-order fill | Deduplicate by broker event ID and reconcile cumulative state | Cash/quantity unchanged on duplicate; monotonic fills |
| Missing/stale quote or price for held symbol | Block new risk, alert operator | Complete current portfolio valuation restored |
| Unexplained cash/position drift | Halt and compare ledger with broker | Every discrepancy linked to a fill, fee, cashflow or corporate action |
| Audit export failed | Preserve local evidence, block certified new-risk operation per policy | Independent destination acknowledges contiguous sequence |
| Credential exposure suspicion | Stop integration, revoke through provider, inspect access | Replacement credentials and access review; never print secrets |
| Model/policy divergence | Freeze champion; disable challenger/rollback approved artifact | Reproducible comparison and independent review |
| Database/host failure | Stop execution; restore into isolated halted environment | Validated backup plus broker reconstruction of missing events |
| LLM unavailable or budget exhausted | Deterministic reports or no new decision | Numeric signals and limits unchanged; recorded fallback/cost |

## Backup and restore

Current local state is disposable **only if it contains research/demo records and no external economic state**. Do not delete databases to resolve an unknown fill. Use SQLite's backup API for live databases; include all manifests needed to recreate a run. Do not copy a running main database file alone and ignore its WAL.

For certified operation, use encrypted off-host storage and tested retention. Restore ledger/evidence first, rebuild indexes second, reconcile broker history third, then require new approvals. Never restore a graph and auto-resume `approve`. Record the recovery point, missing interval, actual recovery time and reviewer.

## Release and rollback checklist

- Run locked unit/integration/lint checks and environment-specific adapter certification.
- Verify source/config/model/data manifests and schema migration compatibility.
- Test rollback or forward recovery with no live credentials.
- Deploy first to shadow/paper; compare against the frozen champion on matching evidence.
- Require explicit review before account/mode/capital changes.
- Preserve old artifacts and incident evidence; rollback must not erase the ledger.

## Prototype versus operating success

A green `cycle`, a matching local audit copy, or an approval interrupt is not certification. Operational success means current risk inputs, correct accounting, unique economic effects, reconciled external state, attributable decisions, tested recovery and a human who can respond. See [Phase 5](phase-5-operations.md) for SLOs and recurring review.
