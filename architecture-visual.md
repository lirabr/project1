# Trading Desk v3 — visual guide

These diagrams describe **target responsibilities**, not proof that every box is implemented. The [architecture capability register](trading-agents-architecture.md) is authoritative for current status.

## 1. Domains and cross-cutting controls

```mermaid
flowchart TB
  CP["Control plane: operator, scheduler, HALT, config, secrets"]
  D1["D1 Data and features"] --> D2["D2 Research and model lifecycle"]
  D1 --> D3["D3 Decision support"]
  D2 -->|Approved frozen signals| D3
  D6["D6 Memory and evaluation"] -->|Eligible lessons only| D3
  D3 -->|Typed intent, no credentials| D4["D4 Portfolio and deterministic risk"]
  D4 -->|Bounded authorization| D5["D5 Execution and accounting"]
  D5 -->|Reconciled outcomes| D6
  D5 -->|Current ledger and reservations| D4
  CP -.-> D1
  CP -.-> D2
  CP -.-> D3
  CP -.-> D4
  CP -.-> D5
  CP -.-> D6
  E["Evidence plane: lineage, tests, audit, monitoring"]
  D1 -.-> E
  D2 -.-> E
  D3 -.-> E
  D4 -.-> E
  D5 -.-> E
  D6 -.-> E
```

LLM routing is an optional adapter inside decision support/reflection. Storage and frameworks are implementations of domain interfaces, not mandatory layers. Laptop deployment remains one Python package and one writer.

## 2. Target authority and economic-effect boundary

```mermaid
flowchart LR
  S["Dated data + current model + reconciled portfolio"] --> P["Deterministic proposal"]
  P --> A["Schema, provenance and citations"]
  A --> R["Projected risk + reservation"]
  R --> H["Human approval bound to intent hash"]
  H --> V["Expiry + fresh risk + HALT recheck"]
  V --> O["Durable outbox and stable order ID"]
  O --> B["Paper broker first; live optional"]
  B --> Q["Reconcile fills, fees, cancels and cash"]
  Q --> M["Matured outcome + lesson"]
  B -->|Ambiguous submit| U["UNKNOWN: stop new risk and reconcile"]
  U --> Q
```

Current graph ends at a toy local book; it has no outbox/broker/reconciliation service. HALT blocks new risk and is not a flatten command.

## 3. Implemented portfolio and simulator paths

```mermaid
flowchart LR
  DATA["Frozen inputs / approved model or explicit rules"] --> SCORE["Scores"]
  SCORE --> ALLOC["Shared capped allocation + optional reductions"]
  ALLOC --> TARGET["Immutable PortfolioTarget + cash + lineage"]
  TARGET --> LEGACY["cycle / graph: shared decisions, legacy toy fills"]
  TARGET --> PLAN["Fresh-mark rebalance plan"]
  PLAN --> APPROVE["Local per-order approval + atomic reservation"]
  APPROVE --> PAPER["Internal partial fills / sells / fees / sessions"]
  PAPER --> EVENT["Transactional ledger events"]
  DATA --> REPORT["Read-only research HTML"]
```

The internal simulator is not a broker adapter. Its local reviewer string is not authentication, and manually supplied marks/fills are not a venue feed. Cash preservation and shared allocation do not prove backtest/execution equivalence. The original packaged PDFs predate this implementation update; the Markdown capability register is the current source of truth.

## 4. Evidence-gated phases

```mermaid
flowchart TB
  P0["0: reproducible laptop, lockfile, offline tests"] --> P1["1: causal research, baselines, holdout, candidate or refusal"]
  P1 --> P2["2: marked ledger, realistic paper, replay safety; 20 sessions"]
  P2 --> P3["3: PIT memory, measured ablations, controlled policy"]
  P3 --> P4["4: broker-paper certification; 20 broker-paper sessions"]
  P4 --> PAPER["Remain paper-only"]
  P4 -->|Separate approval and all P0 closed| LIVE["Optional supervised tiny-live canary"]
  PAPER --> P5["5: operating SLOs, restore, releases, controlled expansion"]
  LIVE --> P5
  P5 --> REVIEW["Stay small, retire, or separately approve one change"]
  REVIEW -. New venue or frequency .-> P1
```

Calendar windows are minimum operating observations, not proof of alpha. Failed research does not bar simulator engineering; it bars real model/live admission. Phase 5 has a 30-day operational evidence floor, plus restore/rollback drills.

## 5. State ownership

```mermaid
flowchart LR
  RAW[("Frozen raw data and features")] --> LAB["Research"]
  LAB --> REG[("Immutable model registry and evidence")]
  REG --> DEC["Decision service"]
  CK[("Graph checkpoints")] --- DEC
  DEC --> LED[("Execution ledger + orders + reservations")]
  LED --> EP[("Episodes + mature outcomes")]
  EP --> IDX[("Rebuildable FTS/vector indexes")]
  IDX -->|Outcome available before decision| DEC
  LED --> AUD[("Independent evidence export and backup")]
```

Checkpoint recovery does not authorize a new economic effect. Rebuildable indexes cannot replace a ledger. Outcome updates cannot rewrite the entry situation.

## 6. Test pyramid

```mermaid
flowchart BT
  U["Offline units: math, labels, gates, invalid numbers"] --> I["Synthetic integration: research pipeline, graph, ledger"]
  I --> C["Chaos: duplicate events, ambiguous submit, restart, restore"]
  C --> BP["Explicitly authorized broker-paper certification"]
  BP --> OP["Operational observation and independent release review"]
```

Current automated tests cover only portions of the first two levels. Use [testing and acceptance](testing-and-acceptance.md) for unmet obligations. Mermaid can be viewed in GitHub, Obsidian or an editor with Mermaid support; no binary slide deck is required.
