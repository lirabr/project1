from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pandas.tseries.offsets import DateOffset

from desk.backtest import (
    buy_and_hold_returns,
    long_flat_from_scores,
    portfolio_returns,
    tear_sheet,
    total_cost_bps,
)
from desk.contracts import FoldResult, TearSheet
from desk.data import load_universe, membership_mask
from desk.features import FEATURE_COLS, read_panel
from desk.io_utils import ARTIFACT_DIR, ensure_dirs, load_yaml, write_yaml
from desk.models import Strategy, build_strategy
from desk.tracking import log_run


def _date_col(panel: pd.DataFrame) -> pd.Series:
    if "date" in panel.columns:
        return pd.to_datetime(panel["date"])
    return pd.to_datetime(panel.index)


def _unique_dates(panel: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(sorted(_date_col(panel).unique()))


def _slice_dates(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    d = _date_col(panel)
    return panel[(d >= start) & (d <= end)]


def make_folds(dates: pd.DatetimeIndex, cfg: dict) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    train_years = int(cfg["train_years"])
    test_months = int(cfg["test_months"])
    step_months = int(cfg["step_months"])
    embargo_days = int(cfg["embargo_days"])
    if train_years < 1 or test_months < 1 or step_months < test_months or embargo_days < 1:
        raise ValueError("Require positive windows, embargo, and non-overlapping test folds")
    folds = []
    start = dates.min()
    last = dates.max()
    train_end = start + DateOffset(years=train_years)
    while True:
        test_start = train_end + pd.Timedelta(days=embargo_days)
        test_end = test_start + DateOffset(months=test_months) - pd.Timedelta(days=1)
        if test_start > last:
            break
        test_end = min(test_end, last)
        if test_start >= test_end:
            break
        folds.append((start, train_end, test_start, test_end))
        train_end = train_end + DateOffset(months=step_months)
    return folds


def _ready(frame: pd.DataFrame, need_label: bool) -> pd.DataFrame:
    cols = FEATURE_COLS + (["y", "fwd_ret", "label_end"] if need_label else [])
    out = frame.dropna(subset=cols)
    if need_label:
        out = out[out["feature_available"]]
    return out


def run_walkforward(
    strategy_name: str,
    universe_path: Path,
    wf_path: Path,
    costs_path: Path,
) -> tuple[TearSheet, pd.DataFrame, list[FoldResult]]:
    ensure_dirs()
    panel = read_panel()
    wf_cfg = load_yaml(wf_path)
    cost_cfg = load_yaml(costs_path)
    instruments, uni = load_universe(universe_path)
    asset_map = {i.symbol: i.asset_class for i in instruments}
    panel = panel[panel["symbol"].isin(asset_map)].copy()
    panel["in_universe"] = membership_mask(panel, uni).to_numpy()
    if len(set(asset_map.values())) != 1:
        raise ValueError("Run equities and crypto separately until a multi-calendar ledger is implemented")
    from desk.leakage import lint_panel

    lint_panel(panel, int(wf_cfg.get("label_horizon_days", 5)), strict=True)
    horizon = int(wf_cfg.get("label_horizon_days", 5))
    threshold = float(wf_cfg.get("long_threshold", 0.55))
    max_w = float(wf_cfg.get("max_name_weight", 0.25))

    dates = _unique_dates(panel)
    folds = make_folds(dates, wf_cfg)
    if not folds:
        raise RuntimeError("No walk-forward folds. Download a longer history.")

    fold_rows: list[FoldResult] = []
    test_chunks: list[pd.DataFrame] = []
    return_chunks: list[pd.DataFrame] = []
    benchmark_chunks: list[pd.Series] = []
    bench_sym = uni.get("benchmark", "SPY")
    benchmarks = list(dict.fromkeys([bench_sym, *uni.get("benchmarks", [])]))
    benchmark_series: dict[str, list[pd.Series]] = {s: [] for s in benchmarks}
    matched_chunks = []
    allocation = wf_cfg.get("allocation") or {}
    weights_chunks = []

    for i, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        train = _ready(_slice_dates(panel, tr_s, tr_e), need_label=True)
        train = train[train["in_universe"]]
        # Purge last horizon days of train so labels do not leak into the test window.
        if not train.empty:
            train = train[pd.to_datetime(train["label_end"]) <= tr_e]
        test = _slice_dates(panel, te_s, te_e)
        test_ready = test.dropna(subset=FEATURE_COLS)
        if len(train) < int(wf_cfg.get("min_train_rows", 250)) or test_ready.empty:
            continue

        strat: Strategy = build_strategy(strategy_name)
        strat.fit(train)
        scores = strat.scores(test_ready)
        scores.name = "score"
        tagged = test_ready.copy()
        tagged["score"] = scores.to_numpy()
        tagged["fold_id"] = i
        test_chunks.append(tagged)

        # Per-fold equity on this window only.
        w = long_flat_from_scores(test_ready, scores, threshold, max_w,
                                  allocation_method=allocation.get("method", "equal"),
                                  exposure_scale=float(allocation.get("exposure_scale", 1)),
                                  regime_scales=allocation.get("regime_scales"))
        weights_chunks.append(w)
        pret = portfolio_returns(test_ready, w, cost_cfg, asset_map)
        return_chunks.append(pret)
        for symbol in benchmarks:
            b = buy_and_hold_returns(test_ready, symbol).reindex(pret.index)
            bps = total_cost_bps(cost_cfg, asset_map[symbol]) / 10000
            net_b = b.copy()
            net_b.iloc[0] -= bps
            net_b.iloc[-1] -= bps
            benchmark_series[symbol].append(net_b)
            if symbol == bench_sym:
                benchmark_chunks.append(net_b)
                exposure = pret["exposure"]
                turnover = exposure.diff().abs().fillna(exposure.iloc[0])
                matched_chunks.append(b * exposure - turnover * bps)
        fold_sheet = tear_sheet(pret["net"], None, strategy_name, 1, int((pret["turnover"] > 0).sum()))
        fold_rows.append(
            FoldResult(
                fold_id=i,
                train_start=str(tr_s.date()),
                train_end=str(tr_e.date()),
                test_start=str(te_s.date()),
                test_end=str(te_e.date()),
                n_train=len(train),
                n_test=len(test_ready),
                total_return=fold_sheet.total_return,
                sharpe=fold_sheet.sharpe,
                max_drawdown=fold_sheet.max_drawdown,
            )
        )

    if not test_chunks:
        raise RuntimeError("Every fold was skipped. Check data length and min_train_rows.")

    oos = pd.concat(test_chunks).sort_index()
    port = pd.concat(return_chunks).sort_index()
    bench = pd.concat(benchmark_chunks).sort_index().reindex(port.index)
    if port.index.duplicated().any():
        raise ValueError("OOS return dates overlap")
    if bench.isna().any():
        raise ValueError("Benchmark is missing OOS dates")

    n_trades = int((port["turnover"] > 1e-9).sum())
    sheet = tear_sheet(
        port["net"],
        bench,
        strategy=strategy_name,
        n_folds=len(fold_rows),
        n_trades=n_trades,
        extra_notes=[
            f"threshold={threshold}",
            f"horizon={horizon}",
            "fills=signal_at_t_position_from_tplus1",
            "costs_included=true",
            "folds=independent_flat_start_and_liquidation",
        ],
    )
    sheet.turnover = float(port["turnover"].mean())
    sheet.mean_exposure = float(port["exposure"].mean())
    sheet.mean_cash_weight = float(port["cash_weight"].mean())
    sheet.total_cost_return = float(port["cost"].sum())
    sheet.double_cost_total_return = float((1 + port["gross"] - 2 * port["cost"]).prod() - 1)
    sheet.fold_return_std = float(pd.Series([f.total_return for f in fold_rows]).std(ddof=0))
    sheet.benchmarks = {s: float((1 + pd.concat(chunks)).prod() - 1) for s, chunks in benchmark_series.items()}
    sheet.benchmarks["cash"] = 0.
    sheet.benchmarks[f"{bench_sym}_matched_exposure"] = float((1 + pd.concat(matched_chunks)).prod() - 1)

    from desk.artifacts import file_hash, freeze_frame
    from desk.portfolio import digest

    manifest = {"strategy": strategy_name, "created_at": datetime.now(UTC).isoformat(),
                "input_snapshot": freeze_frame(panel, "features", {"origin": "research_input"}),
                "configs": {"universe": file_hash(universe_path), "walkforward": file_hash(wf_path), "costs": file_hash(costs_path)},
                "code": {name: file_hash(Path(__file__).with_name(f"{name}.py"))
                         for name in ("walkforward", "models", "features", "backtest", "portfolio")}}
    run_id = digest(manifest)
    frozen_run = ARTIFACT_DIR / "research_runs" / run_id
    frozen_run.mkdir(parents=True, exist_ok=False)
    (frozen_run / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    port.to_parquet(frozen_run / "returns.parquet")
    pd.concat(weights_chunks).sort_index().to_parquet(frozen_run / "weights.parquet")
    write_yaml(frozen_run / "tearsheet.yaml", sheet.to_dict())
    write_yaml(frozen_run / "folds.yaml", {"folds": [asdict(f) for f in fold_rows]})
    run_dir = ARTIFACT_DIR / strategy_name
    run_dir.mkdir(parents=True, exist_ok=True)
    port.to_parquet(run_dir / "returns.parquet")
    pd.concat(weights_chunks).sort_index().to_parquet(run_dir / "weights.parquet")
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id, **manifest}, sort_keys=True))
    oos.to_parquet(run_dir / "oos_scores.parquet")
    write_yaml(run_dir / "tearsheet.yaml", sheet.to_dict())
    write_yaml(run_dir / "folds.yaml", {"folds": [asdict(f) for f in fold_rows]})

    log_run(
        strategy=strategy_name,
        params={
            "threshold": threshold,
            "horizon": horizon,
            "train_years": wf_cfg["train_years"],
            "test_months": wf_cfg["test_months"],
        },
        metrics=sheet.to_dict(),
    )
    print(f"{strategy_name:16}  folds={sheet.n_folds}  ret={sheet.total_return:+.2%}  sharpe={sheet.sharpe:.2f}  "
          f"maxDD={sheet.max_drawdown:.2%}  excess_vs_{bench_sym}={sheet.excess_return:+.2%}")
    return sheet, port, fold_rows


def compare(strategy_names: list[str]) -> pd.DataFrame:
    rows = []
    for name in strategy_names:
        path = ARTIFACT_DIR / name / "tearsheet.yaml"
        if not path.exists():
            continue
        rows.append(load_yaml(path))
    if not rows:
        raise FileNotFoundError("No tear sheets. Run train/backtest first.")
    return pd.DataFrame(rows)
