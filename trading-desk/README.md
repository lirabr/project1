# Trading desk starter — v3

Python 3.12 research and internal-paper prototype. **No live broker adapter. No required credentials, Docker, or LLM.** Companion architecture and phase guides live in the enclosing project pack; the starter ZIP contains code/config/tests only.

## Install and verify

```bash
uv sync --locked --python 3.12 --extra dev --extra graph
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests
uv run --no-sync desk-research --help
```

The lockfile is authoritative. `--no-sync` avoids unintentionally removing optional extras during subsequent commands. Tests use temporary state, reject network access, and include a synthetic research pipeline and cross-process SQLite graph resume. Installation downloads packages; tests do not contact Yahoo, brokers or LLMs.

Core-only installation is `uv sync --locked --extra dev`; graph tests then skip and graph commands are unavailable. Do not call that a full graph verification. Optional MLflow requires `--extra tracking` in the sync command.

## Implemented commands

```bash
uv run --no-sync desk-research download
uv run --no-sync desk-research features
uv run --no-sync desk-research backtest
uv run --no-sync desk-research backtest --strategy sma_cross
uv run --no-sync desk-research compare
uv run --no-sync desk-research folds sma_cross
uv run --no-sync desk-research cycle
uv run --no-sync desk-research book
uv run --no-sync desk-research memory AAPL
uv run --no-sync desk-research live-preflight
```

Default research: six equity symbols, daily frequency, SMA/momentum/HGB, separated walk-forward windows with matured training labels, next-open vectorized screening and costs. Unknown labels remain missing. `DESK_DATA_DIR` optionally selects an absolute alternate raw/features/artifacts root; keep equity and crypto experiments separate. Global CLI options such as `--universe configs/universe.crypto.yaml` precede the subcommand.

Additional commands include `train`, `approve-model`, `portfolio`, `paper`, and `report` (described below). `promote`, `reflect`, `trust`, `drift`, `heartbeat`, policy commands and graph fills retain demonstration semantics. There is no broker `reconcile`, deployment, or real live-submit command.

## Shared portfolio targets and allocation

`portfolio.py` defines a validated immutable `PortfolioTarget`: weights, residual cash, decision time, earliest execution time, model/data/config identities and evidence IDs. Targets are not approvals. `plan_rebalance()` requires fresh marks for every held/target symbol, includes reductions and exits, and returns sells before buys without assuming unfilled sale proceeds are available.

`configs/desk.yaml` accepts `allocation.method: equal` (default) or `inverse_vol`, `exposure_scale` in [0,1], and optional `regime_scales`, for example `{risk_off: 0.5}`. The latter uses the fixed row-local regime classifier and only reduces exposure. Use the same allocation block in `configs/walkforward.yaml` for comparable research; research shifts the signal, volatility and regime reduction exactly once to the next open. Neither method redistributes capped exposure back into assets. These alternatives are experiments, not promoted strategies.

`cycle` writes `data/artifacts/portfolio_target.json`. `portfolio` prints a fresh target as JSON; with existing positions it requires `--marks`. Supply `--execute-after` to bind the intended future execution time. Without it, the lower bound is decision time plus one second, **not an exchange-calendar scheduling guarantee**. Targets expire five minutes after that bound, capped at one day from the decision; planning rejects expired targets, and CLI approvals cannot outlive them. Recompute after a long pause rather than extending an old target.

## Frozen data and model inference

Downloads preserve content-addressed snapshots under `data/artifacts/snapshots/raw/`; feature builds preserve snapshots under `snapshots/features/`. Latest working Parquet files still change on rerun. Research creates unique `research_runs/<id>/` directories with input/config/code lineage, weights, returns and reports. Preserve those directories and the dependency lock for comparisons.

Optional universe fields:

```yaml
sessions_file: sessions.json
membership:
  SPY:
    - from: "2020-01-01"
      to: null
      known_at: "2019-12-31T00:00:00+00:00"
```

`sessions.json` contains `{"sessions": ["2026-07-02", "2026-07-06"]}` covering the entire downloaded interval, not just this two-date example. Supply an authoritative schedule for the selected calendar; the code rejects missing/extra sessions rather than assuming weekdays are exchange sessions. Membership limits selection and training to eligible, already-known intervals; an omitted membership configuration is explicitly a static convenience universe, not survivorship-free data. Neither supplied metadata nor Yahoo-adjusted history proves vendor PIT correctness.

Inference modes in `desk.yaml`:

- `rules` (default): explicit stateless `sma_cross` baseline.
- `approved`: requires `approved_model_id`; loads a locally approved frozen artifact, validates digests/code/schema/runtime and applies the trained estimator. Missing approval/artifact or an incompatible model fails closed.
- `replay`: requires an exact-date historical OOS score, with no fallback. Use isolated research state.

`max_bar_age_days` defaults to 7 calendar days; `max_model_age_days` defaults to 90. Missing configured symbols and incomplete latest bars are rejected. Daily dates are not intraday freshness certification.

```bash
uv run --no-sync desk-research train sma_cross --cutoff 2026-09-01
uv run --no-sync desk-research approve-model --help
```

`train` prints the content-addressed model ID and uses only labels matured by the supplied cutoff. After reviewing independent evidence, `approve-model MODEL_ID --reviewer NAME --evidence FILE` records a local attestation and evidence-file digest. Then set `inference_mode: approved` and that `approved_model_id` in your experiment config. This is not authenticated production authorization or automatic statistical promotion. Joblib artifacts are executable serialization: load only artifacts generated in your trusted local store. The old `promote` command still changes metadata only.

## Durable internal paper workflow

Use a separate data profile from legacy graph/toy-fill experiments. Once durable orders exist in a book, the legacy immediate-fill helper refuses new fills so it cannot bypass the order ledger. Set `DESK_DATA_DIR` before invoking commands; `DESK_CONFIG_DIR` optionally selects a separate config directory. No broker credentials or network requests are involved.

A marks file maps symbols to positive prices and timezone-aware observation timestamps:

```json
{"SPY": {"price": 100.0, "as_of": "2026-09-24T14:00:00+00:00"}}
```

The timestamp above is illustrative: marks older than 300 seconds or in the future are rejected. Supply all held/target symbols. Do not relabel an old quote as current.

1. At your declared venue-session boundary, run `paper session --session SESSION_ID --marks MARKS.json`. Reusing a session ID never resets its baseline. A baseline older than 26 hours cannot authorize more fills; there is no automatic scheduler.
2. Generate a target with `portfolio --marks MARKS.json --execute-after TIMESTAMP` and save the JSON output. Keep execution later than the decision.
3. Run `paper plan --target TARGET.json --marks MARKS.json`. This returns a target ID and immutable order IDs without reserving cash or filling anything.
4. Review each order, then run `paper approve --target TARGET.json --marks MARKS.json --session SESSION_ID --order-id ORDER_ID --reviewer NAME --cost-bps 10`. This reserves resources, **not a fill**. Quote/quantity/policy changes require a fresh plan and approval. Cash from pending sells is not spendable.
5. Feed an explicit simulated execution using `paper fill --order-id ORDER_ID --fill-id UNIQUE_FILL_ID --quantity QTY --price PRICE --fee FEE --marks MARKS.json`. Partial fills are supported; buy and sell all-in prices must stay inside the approved cost allowance. Approval expires after 300 seconds by default; replay of the identical recorded fill has no second economic effect.
6. Inspect `paper book --marks MARKS.json --session SESSION_ID`, or cancel an unfilled remainder with `paper cancel --order-id ORDER_ID`. This cancels only an internal simulated order.

The ledger supports average-cost realized P&L, fees, marked equity, explicit cashflows through its Python API, and persistent session baselines. Reservations and fill/event updates use SQLite write transactions. UNKNOWN orders retain reservations and block new buys; no broker-resolution shortcut is provided. Float arithmetic, manual marks/session boundaries, no automatic liquidity/fill model, no corporate actions, and no broker cancel/fill race handling mean this is **not certified execution**. Keep one operator/writer.

## Read-only reports and optional language research

```bash
uv run --no-sync desk-research report
```

Open the printed HTML path locally. It reports real stored research artifacts, exposure/cash, total cost drag, matched-exposure/cash benchmarks, fold dispersion and doubled-cost sensitivity. Research interval counts are not completed trades; `paper book` reports separate simulator order/fill/fee totals.

The four model/bull/bear/PM roles now include structured evidence and provenance. Direct and graph workflows share decisions and portfolio targets; prose cannot change scores, allocations or risk limits. Decision retrieval filters out open/future lessons, but historical vector immutability and outcome accounting still need work.

`sentiment.analyze_news()` is a shadow-only callback boundary, disabled by `news_sentiment.enabled: false`. It validates source/availability times, caps request counts and declared costs, and records model identity. No provider adapter is wired; provider-side spending enforcement and licensed news require a separately reviewed integration. Neither sentiment output nor the static report has execution authority.

## Graph demonstration

```bash
uv run --no-sync desk-research graph --thread equity-demo-001
uv run --no-sync desk-research graph-resume --thread equity-demo-001 reject
```

Resume only a reported pending interrupt. A unique thread is required for new work. Approve creates only a toy local fill; approval expires after 300 seconds from snapshot by default, and risk/HALT are rechecked. Fill IDs deduplicate local economic effects, not all episode/log writes. One writer only.

## Safety and correctness boundaries

- Live preflight always reports missing execution/reconciliation, even if booleans are changed. Never wire a broker behind the legacy manual-intent stub.
- Legacy `cycle --submit`/graph fills remain buy-only immediate-close demonstrations, not the durable `paper` engine or next-open parity. `reflect` does not sell a position. `book` without marks is a cost view; use `paper book --marks ...` for marked equity. The legacy risk input remains since-entry P&L; only the new session-aware simulator provides session P&L.
- The old metadata registry does not authorize inference. Frozen artifacts and `approve-model` now provide an explicit local reviewed-inference path, not production admission or authenticated authorization.
- Decision retrieval filters future/open lessons, but vector immutability, attribution, reflection semantics and retrieval quality remain incomplete. Trust/policy/drift/heartbeat remain diagnostics. LLM and shadow sentiment are off; connected providers need separate security and spending controls.
- Per-row JSONL hashes and a local copy are not independently tamper-evident off-host audit.
- Several inherited configuration keys are not consumed. The outer architecture capability register lists these gaps; a YAML key is not proof of enforcement.
- HALT uses the same resolver in the CLI and both risk paths. The standard path follows `DESK_DATA_DIR`; custom paths follow the selected risk config. Verify the intended profile and file before use.

## Structure

- `src/desk/`: research, prototype book, decision helpers, risk, memory and optional graph.
- `configs/`: default daily equity research, separate crypto universe, paper limits, prototype adaptation, disabled live stub.
- `tests/`: offline units, regressions and synthetic integration.
- `uv.lock`, `pyproject.toml`: reproducible dependencies and Python compatibility.
- `Makefile`, `.github/workflows/ci.yml`: local verification and CI when this directory is the repository root.
- `infra/docker-compose.yml`, `.env.example`: unused legacy integration experiments; not setup requirements and not production-ready infrastructure.
- `data/`: runtime output, created on demand and excluded from distribution/version control.

Latest working data/reports can be overwritten by reruns; content-addressed snapshots and versioned research/model artifacts retain prior evidence. Back up those stores and the dependency lock. New simulator tables are created additively, without replacing legacy positions or episodes; use fresh isolated state for certification rather than silently reclassifying old toy fills. Do not migrate a v2 database implicitly. See the companion requirements, acceptance matrix and six phase guides before claiming operational readiness.
