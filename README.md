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

## Agents

The starter implements **four agent roles** in [agents.py](trading-desk/src/desk/agents.py). They are deterministic Python functions, not separate autonomous LLM agents. **No LLM calls are enabled in the shipped configuration**; one optional integration can refine the Portfolio Manager's explanation.

### Roles and responsibilities

| Role | Function | Responsibility and current behavior |
|---|---|---|
| Model Signal | `model_signal_brief()` | Summarizes an existing model card: symbol, timestamp, strategy, score, price, 20-day return and volatility, RSI, and notes. It does not train a model or calculate the score. |
| Bull Analyst | `bull_brief()` | Builds the case for buying from a positive moving-average ratio, positive 20-day momentum, and RSI below 70. Falls back to the model score as its main argument when none of those checks apply. Includes retrieved historical lessons. |
| Bear Analyst | `bear_brief()` | Highlights RSI above 70, 20-day volatility above 0.02, negative 20-day momentum, and model scores below 0.6. If none apply, highlights costs and fill risk. Includes retrieved historical lessons. |
| Portfolio Manager (PM) | `pm_proposal()` | Produces a structured `TradeProposal`: long when the score meets the supplied threshold, otherwise flat. Calculates suggested notional from the score and supplied cap, adds thesis and invalidation text, sets a five-day horizon and low urgency, and attaches memory IDs and both analyst briefs. |

The PM **does not currently weigh the Bull/Bear arguments to decide direction or size**. It attaches their briefs, but its initial decision and sizing use numeric rules. Invalidation and horizon fields describe the proposal; they do not implement automatic exits. None of these roles independently executes trades.

### Optional LLM refinement

The `llm` section in [configs/desk.yaml](trading-desk/configs/desk.yaml) contains the provider settings:

```yaml
llm:
  enabled: false
  base_url: https://api.x.ai/v1
  model: grok-4
  timeout_s: 45
```

- `maybe_refine()` checks the enabled flag and reads the first available key from `DESK_LLM_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY`. Without an enabled flag and a key, it returns the rule-based proposal unchanged.
- `try_llm_refine()` contains the PM system prompt and OpenAI-compatible `/chat/completions` call. It sends the features, score, direction, analyst briefs, and cited memory IDs, and requests JSON containing only `thesis` and `invalidation`.
- Only those two text fields are applied to the proposal. The LLM cannot change direction, score, sizing, or risk limits through this integration. Request or parsing failures retain the rule-based decision and append an error-type note to the thesis.
- This is an optional PM text rewrite, **not a fifth autonomous agent**. Keep credentials out of source/config files and leave LLM access off until the provider/key binding and other controls in the [security and failure boundaries](trading-agents-architecture.md#9-security-and-failure-boundaries) are implemented.

### Workflow and authority boundaries

[cycle.py](trading-desk/src/desk/cycle.py) retrieves memories for each model card, calls Bull → Bear → PM, applies trust/policy adjustments, optionally refines the prose, then runs the auditor and risk gate. The Model Signal function formats the card summary for the decision record rather than making an additional decision.

The optional [LangGraph workflow](trading-desk/src/desk/graph.py) groups Bull, Bear, PM, trust/policy, refinement, and auditing in `node_debate_and_pm()`. They are not separate parallel LLM nodes. See [LangGraph integration](langgraph-integration.md) for routing, human approval, and replay limits.

Trust/policy logic, the auditor, and the risk gate are **separate deterministic controls**, not additional LLM agents. They adjust or validate proposals before any permitted toy paper fill. Human approval and fill handling belong to the orchestration/execution path, not to the four agent roles; real broker submission remains unimplemented.

## Portfolio-first implementation

The [FinRL-X review](https://github.com/AI4Finance-Foundation/FinRL-Trading/tree/4409abe925c904e570be78ebfb5e77ac3491dff8) informed the **interfaces**, not a dependency or code import. The reviewed execution code's fabricated-price fallback and inconsistent cash normalization were explicitly not adopted. Keep one package and a deterministic execution boundary:

```text
Versioned data/model → scores → selection/allocation → PortfolioTarget
  → fresh-mark rebalance plan → per-order human approval + risk reservation
  → internal paper fills/events → marked accounting and reports
```

Implemented additions:

- [portfolio.py](trading-desk/src/desk/portfolio.py): immutable, content-identified targets with explicit cash and lineage; equal-weight/inverse-volatility allocation; optional reduce-only regime scaling; fresh-mark rebalance plans including exits. Cash is never normalized back into risk assets.
- [decisions.py](trading-desk/src/desk/decisions.py): shared direct/graph proposal and projected-risk logic; structured agent evidence; decision-time filtering of retrieved lessons. Target allocations express desired exposure, not authority to execute.
- [artifacts.py](trading-desk/src/desk/artifacts.py): immutable raw/feature snapshots, frozen trained models, digest/schema/runtime verification, and explicit local model review. Default inference is stateless SMA rules; approved inference and historical replay are explicit modes, with no silent fallback.
- [ledger.py](trading-desk/src/desk/ledger.py): a separate durable internal simulator with marked positions, session baselines, cashflows, buy/sell partial fills, fees, cash/share reservations, order cancellation, UNKNOWN blocking, duplicate detection, and transactional fill/event updates.
- Research evidence: versioned run directories, weights/exposure/cash histories, comparable benchmark costs, matched-exposure and cash benchmarks, fold dispersion, and doubled-cost sensitivity.
- [reports.py](trading-desk/src/desk/reports.py): an escaped, static, read-only HTML research report and paper-order statistics. No dashboard trading controls or synthetic performance presented as real.
- [sentiment.py](trading-desk/src/desk/sentiment.py): disabled shadow-only adapter boundary with publication/availability timestamps, model/cost metadata, request limits and response validation. No news provider is connected and these results never enter sizing or execution.
- Data validation: optional explicit exchange-session schedules and dated universe-membership intervals with `known_at`; Yahoo downloads remain research data, not a certified PIT feed.

The four existing agent roles remain. Their proposals now carry structured evidence and target identity; the shared allocator supplies desired position deltas, while trust and risk can reduce them. Standalone `pm_proposal()` retains its compatibility sizing rule. Bull/Bear prose still does not control numeric decisions.

### Commands and configuration

From `trading-desk`:

```bash
uv run --no-sync desk-research report
uv run --no-sync desk-research portfolio --help
uv run --no-sync desk-research train --help
uv run --no-sync desk-research approve-model --help
uv run --no-sync desk-research paper --help
```

See the [starter README](trading-desk/README.md) for mark/target file formats and the explicit session → plan → approve → fill workflow. Use separate `DESK_DATA_DIR` and, when needed, `DESK_CONFIG_DIR` profiles for experiments. No dependencies were added; the existing lock remains authoritative.

The legacy `cycle --submit` and graph approval paths remain immediate-close **demonstrations**, not the new order engine. They share decision/allocation logic but do not establish execution parity. Use `paper` for durable order/fee/session experiments; do not mix experimental writers or treat toy fills as broker observations.

## Readiness and evidence

The capability register distinguishes implemented foundations from certification: realistic exchange fills, corporate actions, independent full-ledger parity, authenticated/revocable approvals, broker reconciliation, immutable outcome/vector semantics, remote audit and prospective observations remain gates. Local hashes detect corruption, not malicious replacement by an actor who controls the entire artifact store. Load only locally produced trusted model artifacts.

Minimum operating observation windows are defined in the roadmap; they are not completion estimates or evidence of alpha. A decision to remain paper-only is a valid outcome, including in Phase 5.

## Provenance

`project1-v2` is the untouched input. Every source file was inventoried; the original ZIP was checked against its expanded starter. Finder metadata, the old ZIP and generated test/audit state are not imported as active v3 runtime state. `conversation-transcript.md` is preserved **verbatim as historical provenance**, including obsolete statements such as “no Phase 5”; it is not current guidance. Source code inherited from the prototype can likewise contain historical explanatory wording; the capability register distinguishes implemented guarantees from target behavior.

Run outer-pack checks with `python3 tools/validate_pack.py` and source preservation with `python3 tools/project_pack.py verify-source ../project1-v2`. The included CI workflow is for a Git repository rooted at `trading-desk`; no remote repository, deployment, broker account or live order is created by this pack.

Not investment advice. This project is an engineering/research framework, not a promise of trading returns.
