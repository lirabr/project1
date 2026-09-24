from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from desk.features import FEATURE_COLS, make_features
from desk.io_utils import write_yaml


def test_full_research_pipeline_and_label_maturity(monkeypatch):
    from desk import io_utils, models, tracking, walkforward

    dates = pd.bdate_range("2018-01-01", periods=1500)
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(.0002, .01, len(dates))))
    bars = pd.DataFrame({"Open": close * .999, "Close": close, "High": close * 1.02,
                         "Low": close * .98, "Volume": rng.integers(1000, 2000, len(dates)),
                         "symbol": "SPY"}, index=dates)
    panel = make_features(bars)
    panel.to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    universe = io_utils.CONFIG_DIR / "test-universe.yaml"
    wf = io_utils.CONFIG_DIR / "test-walkforward.yaml"
    write_yaml(universe, {"equities": ["SPY"], "crypto": [], "benchmark": "SPY"})
    write_yaml(wf, {"train_years": 1, "test_months": 6, "step_months": 6,
                    "embargo_days": 5, "min_train_rows": 100})
    folds = walkforward.make_folds(pd.DatetimeIndex(dates), walkforward.load_yaml(wf))
    fit_count = []

    class CheckedSma(models.SmaCross):
        def fit(self, train):
            cutoff = folds[len(fit_count)][1]
            assert train["label_end"].max() <= cutoff
            assert train["y"].notna().all()
            fit_count.append(len(train))

    monkeypatch.setattr(walkforward, "build_strategy", lambda name: CheckedSma())
    monkeypatch.setattr(tracking, "_try_mlflow", lambda *args, **kwargs: None)
    sheet, returns, results = walkforward.run_walkforward(
        "sma_cross", universe, wf, io_utils.CONFIG_DIR / "costs.yaml"
    )
    assert sheet.n_folds >= 3
    assert len(results) == len(fit_count)
    assert sheet.total_return == pytest.approx(np.prod([1 + fold.total_return for fold in results]) - 1)
    assert np.isfinite(returns.to_numpy()).all()
    scores = pd.read_parquet(io_utils.ARTIFACT_DIR / "sma_cross/oos_scores.parquet")
    assert not scores.duplicated(["symbol", "date"]).any()
    assert (io_utils.ARTIFACT_DIR / "sma_cross/tearsheet.yaml").exists()
    assert sheet.mean_exposure + sheet.mean_cash_weight == pytest.approx(1)
    assert sheet.double_cost_total_return <= sheet.total_return
    assert sheet.benchmarks["cash"] == 0
    assert "SPY_matched_exposure" in sheet.benchmarks
    runs = list((io_utils.ARTIFACT_DIR / "research_runs").iterdir())
    assert len(runs) == 1 and (runs[0] / "manifest.json").exists()
    assert (runs[0] / "weights.parquet").exists()


def test_stale_oos_score_is_not_relabelled_current():
    from desk import io_utils, snapshot

    run = io_utils.ARTIFACT_DIR / "hgb_tab"
    run.mkdir()
    pd.DataFrame({"symbol": ["SPY"], "score": [.9], "date": [pd.Timestamp("2020-01-01")]}).to_parquet(run / "oos_scores.parquet")
    assert snapshot._score_from_oos("SPY", "hgb_tab", pd.Timestamp("2020-01-02")) is None
    assert snapshot._score_from_oos("SPY", "hgb_tab", pd.Timestamp("2020-01-01")) == .9


def test_persistent_graph_resumes_in_new_process(tmp_path):
    pytest.importorskip("langgraph")
    from desk import io_utils

    row = {name: .01 for name in FEATURE_COLS}
    row.update({"symbol": "SPY", "Close": 100., "date": pd.Timestamp.now().normalize(),
                "rsi_14": 55., "ret_20": .03, "sma_ratio_20_50": .01})
    pd.DataFrame([row], index=[row["date"]]).to_parquet(io_utils.FEATURE_DIR / "panel.parquet")
    source = Path(__file__).resolve().parents[1] / "src"
    cfg = io_utils.load_yaml(io_utils.CONFIG_DIR / "desk.yaml")
    cfg["focus"] = ["SPY"]
    write_yaml(io_utils.CONFIG_DIR / "desk.yaml", cfg)
    env = {**os.environ, "DESK_DATA_DIR": str(io_utils.DATA_DIR), "DESK_CONFIG_DIR": str(io_utils.CONFIG_DIR), "PYTHONPATH": str(source)}
    command = [sys.executable, "-m", "desk.cli"]
    first = subprocess.run(command + ["graph", "--thread", "process-restart"], env=env,
                           capture_output=True, text=True, check=True, timeout=30)
    assert "paused for human approval" in first.stdout
    second = subprocess.run(command + ["graph-resume", "--thread", "process-restart", "reject"], env=env,
                            capture_output=True, text=True, check=True, timeout=30)
    assert "finished" in second.stdout
    from desk.memory import book_state, connect

    with connect() as conn:
        assert book_state(conn)["gross"] == 0


def test_default_config_cannot_enable_live():
    from desk import io_utils
    from desk.live import preflight

    risk = io_utils.load_yaml(io_utils.CONFIG_DIR / "risk.paper.yaml")
    live = io_utils.load_yaml(io_utils.CONFIG_DIR / "live.yaml")
    assert risk["allow_live"] is False
    assert risk["require_human_approve"] is True
    assert live["enabled"] is False
    assert io_utils.load_yaml(io_utils.CONFIG_DIR / "desk.yaml")["llm"]["enabled"] is False
    assert preflight(live, risk)
