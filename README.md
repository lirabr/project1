# Trading Desk — v3

A research-first project for testing models, memory, and bounded AI decision support in equities and spot crypto. **Start with daily equities on a laptop. Real broker submission is not implemented and remains blocked.**

The design uses six responsibility domains with cross-cutting control/evidence planes, rather than requiring an eight-layer infrastructure stack. The starter is a single Python package using Parquet and SQLite; optional graph orchestration does not own execution authority.

## Read in this order

1. [Architecture and capability register](trading-agents-architecture.md) — intent, domains, trade-offs, verified gaps and production boundaries.
2. [Visual architecture](architecture-visual.md) — domains, authority, phases and state ownership.
3. [Roadmap](roadmap.md) — ordered work packages, dependencies, observation gates and owners.
4. [Phase 0: laptop setup](phase-0-laptop-setup.md).
5. [Phase 1: credible research](phase-1-research-lab.md).
6. [Phase 2: correct paper lifecycle](phase-2-paper-desk.md).
7. [Phase 3: measured memory/adaptation](phase-3-tighten-loop.md).
8. [Phase 4: broker-paper certification and optional tiny live](phase-4-tiny-live.md).
9. [Phase 5: reliable operations and governed expansion](phase-5-operations.md).

Supporting development references:

- [Requirements and contracts](requirements-and-contracts.md): invariants, schemas, order state machine and ownership.
- [Testing and acceptance](testing-and-acceptance.md): existing tests versus unimplemented certification scenarios.
- [Tools and resources](tools-and-resources.md): required/optional tooling, adoption gates, budget and official references.
- [Operations runbook](operations-runbook.md): daily routine, incidents, stop/recovery and release controls.
- [LangGraph integration](langgraph-integration.md): actual topology, approval expiry, persistent resume and replay limits.
- [Starter README](trading-desk/README.md): installation and implemented commands.

## Quick start — no keys, no Docker

```bash
cd trading-desk
uv sync --locked --python 3.12 --extra dev --extra graph
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests
uv run --no-sync desk-research --help
```

Optional networked research after the tests:

```bash
uv run --no-sync desk-research download
uv run --no-sync desk-research features
uv run --no-sync desk-research backtest
uv run --no-sync desk-research compare
uv run --no-sync desk-research cycle
```

The cycle is intent-only by default. Test logs are isolated from operator data. Research outputs are demonstrations, not certification of profitability or execution readiness. Read the phase guides before promoting metadata, filling the toy book, or experimenting with trust/policy.

## What is included

- Revised architecture, all phase guides, explicit requirements and development acceptance criteria.
- A complete Phase 5 design covering reliability, monitoring, recovery, releases, model governance, costs and controlled expansion.
- A hardened research/demo starter with regression coverage for causal scoring, label maturity, fill timing, projected risk limits, finite inputs, graph revalidation/reset/expiry and local fill deduplication.
- A Python 3.12 dependency lock and offline test isolation; persistent graph resume and a synthetic end-to-end research test.
- Separate crypto research configuration and state-directory support; mixed-calendar portfolio runs are rejected until the accounting engine supports them.
- A refreshed `trading-desk-complete.zip` containing source/config/tests/lockfile, not a virtual environment, credentials, market datasets or old test-generated artifacts.
- `source-manifest.json` plus pack validation/bundling tools to check source preservation and packaging integrity.

## Readiness and evidence

The capability register deliberately leaves real gaps visible: full marked/session accounting, realistic exits/fills, PIT memory, frozen inference artifacts, broker reconciliation, authenticated approvals, remote audit and production operations remain development gates. The revised design does not claim those features exist because a runbook describes them.

Minimum operating observation windows are defined in the roadmap; they are not completion estimates or evidence of alpha. A decision to remain paper-only is a valid outcome, including in Phase 5.

## Provenance

`project1-v2` is the untouched input. Every source file was inventoried; the original ZIP was checked against its expanded starter. Finder metadata, the old ZIP and generated test/audit state are not imported as active v3 runtime state. `conversation-transcript.md` is preserved **verbatim as historical provenance**, including obsolete statements such as “no Phase 5”; it is not current guidance. Source code inherited from the prototype can likewise contain historical explanatory wording; the capability register distinguishes implemented guarantees from target behavior.

Run outer-pack checks with `python3 tools/validate_pack.py` and source preservation with `python3 tools/project_pack.py verify-source ../project1-v2`. The included CI workflow is for a Git repository rooted at `trading-desk`; no remote repository, deployment, broker account or live order is created by this pack.

Not investment advice. This project is an engineering/research framework, not a promise of trading returns.
