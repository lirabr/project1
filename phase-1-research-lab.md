# Phase 1 — Credible research before agents

**Goal:** an honest, reproducible experiment and a candidate decision, including the valid decision to promote nothing. Entry: [Phase 0](phase-0-laptop-setup.md). No LLM or broker is required.

## Inputs and outputs

Inputs: daily bars, declared universe, costs, walk-forward configuration, prewritten hypothesis, benchmark and untouched holdout. Outputs: Parquet features/OOS scores, fold reports, tear sheets, and evidence-linked candidate/refusal. The YAML registry in the starter is only a metadata label; it neither saves fitted models nor enforces promotion gates.

## 1. Establish the experiment

Choose one asset class per run. Default `configs/universe.research.yaml` contains six equity symbols and SPY benchmark. The universe is a small convenience sample, not a survivorship-free investment universe. `configs/universe.crypto.yaml` contains BTC/ETH and BTC benchmark.

Before running, record hypothesis, features, training interval, final holdout, allowed trials, benchmark, cost stress, maximum tolerable drawdown, and candidate rejection rules. Do not tune those rules after seeing outcomes.

## 2. Build the default equity panel

From `trading-desk`:

```bash
uv run --no-sync desk-research download
uv run --no-sync desk-research features
uv run --no-sync python - <<'PY'
from desk.features import read_panel
from desk.leakage import lint_panel
panel = read_panel()
lint_panel(panel, horizon=5, strict=True)
print(panel.groupby('symbol').size())
assert panel.groupby('symbol')['y'].tail(5).isna().all()
PY
```

Expected: six symbols and a panel with feature availability. Data requests contact Yahoo; stop on missing history or rate limits and inspect before retrying. The download overwrites a symbol's working Parquet but now retains a content-addressed snapshot and source/retrieval/adjustment metadata. Preserve that store and the run manifest before treating results as reproducible. Do not mistake adjusted prices retrieved today for an immutable PIT dataset.

The sample command assumes the default 5-bar label horizon. If changed, pass the same value everywhere. The legacy key `label_horizon_days` counts instrument observations, not calendar days.

## 3. Run and challenge baselines

```bash
uv run --no-sync desk-research backtest
uv run --no-sync desk-research compare
uv run --no-sync desk-research folds sma_cross
uv run --no-sync desk-research folds momentum_vol
uv run --no-sync desk-research folds hgb_tab
```

Included strategies: SMA20/50; training-fitted momentum/volatility score; deterministic-seeded HGB. Signals are scores, not necessarily calibrated probabilities. `backtest` evaluates folds rather than promoting a deployed model; use the separate `train` and local `approve-model` commands for a frozen inference artifact.

Review every fold, costs, exposure, turnover, initial drawdown, and benchmark alignment. Signals at close t are allocated at open t+1 and earn the next open-to-open interval. Entry and terminal liquidation costs apply. Each fold starts flat and liquidates at its end; the overall report compounds those exact fold returns rather than silently carrying positions across fold boundaries. This reset convention is a screening assumption, not continuous deployment. The vectorized weight engine still lacks a full share/cash/corporate-action ledger; use it for research screening, not external execution certification.

Reports now include base/doubled-cost results on fixed signals, exposure/cash histories, fold dispersion, comparable-cost buy-and-hold, and cash/matched-exposure benchmarks. Unique `data/artifacts/research_runs/<id>` directories retain each run; `data/artifacts/<strategy>` remains a latest-result convenience view. Predeclare cost assumptions rather than selecting the winning case. `hit_rate` is positive intervals, not completed trades; share-level liquidity/corporate-action validation remains required.

## 4. Optional crypto experiment, isolated state

Use an absolute data directory outside the starter's default equity state. In a separate shell:

```bash
export DESK_DATA_DIR="$HOME/trading-desk-crypto-data"
uv run --no-sync desk-research --universe configs/universe.crypto.yaml download
uv run --no-sync desk-research --universe configs/universe.crypto.yaml features
uv run --no-sync desk-research --universe configs/universe.crypto.yaml backtest
uv run --no-sync desk-research compare
unset DESK_DATA_DIR
```

Global options go **before** the subcommand. `DESK_DATA_DIR` separates all raw/features/artifacts for that process. Do not run the default equity desk against a crypto-only panel. There is no mixed-calendar portfolio engine yet; mixed-asset walk-forward runs are rejected explicitly.

## 5. Frozen artifacts and remaining candidate work

The starter now provides immutable raw/feature snapshots, versioned `research_runs/<id>` evidence, shared equal/inverse-volatility allocation, optional bounded regime reductions, and comparable-cost/matched-exposure/cash benchmark reports. `desk-research report` renders those artifacts as read-only HTML. Optional universe `sessions_file` and `membership` inputs enforce supplied schedules and known-at membership dates; authentic PIT data must still be obtained independently.

`desk-research train STRATEGY --cutoff DATE` freezes an estimator and preprocessing with matured labels and code/data/schema/runtime digests. `approve-model MODEL_ID --reviewer NAME --evidence FILE` records local review. Set `inference_mode: approved` and `approved_model_id` in the desk profile; current inference then fails closed on missing, stale or incompatible artifacts instead of falling back. `rules` is the explicit default and `replay` is isolated historical evidence. See the [starter README](trading-desk/README.md) for formats.

The following packages remain **admission obligations**, even where a foundation is now implemented:

1. Freeze raw snapshots and instrument membership; record checksums, vendor/retrieval time and adjustment basis.
2. Cross-check vectorized returns against a tiny independently calculated cash/share ledger, including gaps, fees, corporate actions, and calendar boundaries.
3. Produce an immutable run manifest: source revision, dependency lock hash, data/feature/config hashes, seed, timestamps, fold boundaries and all attempted specifications.
4. Reserve a final holdout. Add trial accounting and uncertainty estimates suitable for overlapping returns. A minimum of three folds is bookkeeping, not statistical proof.
5. Save training-fitted model and transform artifacts; validate serialization, digest, feature schema, label maturity and current inference parity.
6. Enforce promotion policy in code; tie candidate and paper stages to evidence and reviewer approval. Remove any silent fallback from the certified path.

## 6. Candidate or refusal

For a local **metadata exercise only**:

```bash
uv run --no-sync desk-research promote sma_cross --stage candidate
```

This command currently checks that a tear sheet exists; it does not prove quality or gate execution. Never describe the registry entry as authorization. Real admission requires the work above and a review covering out-of-sample quality, drawdown, plausible economics after all costs, stability across folds/regimes, trial count, and operational reproducibility. A negative result means keep the baseline for simulator engineering, not invent an LLM alpha.

## Test and exit gate

```bash
uv run --no-sync pytest tests/test_risk_free_research.py tests/test_leakage.py tests/test_v3_invariants.py -q
```

- [ ] Unknown future labels remain unknown; label-end purge and no overlapping tests.
- [ ] Appending future rows cannot change earlier features or fitted-rule scores.
- [ ] Next-open timing, costs and initial drawdown agree with a hand calculation.
- [ ] Frozen run/holdout/trial evidence and model artifact requirements completed before candidate admission.
- [ ] Candidate or explicit refusal is signed; no production-quality claim from Yahoo screening alone.

Next: [Phase 2](phase-2-paper-desk.md), which may use a non-promoted baseline for engineering only.
