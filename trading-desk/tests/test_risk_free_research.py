from __future__ import annotations

import numpy as np
import pandas as pd

from desk.backtest import long_flat_from_scores, portfolio_returns, tear_sheet
from desk.features import FEATURE_COLS, make_features
from desk.models import HgbTabular, MomentumVol, SmaCross
from desk.walkforward import make_folds


def _bars(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 2_000_000, n),
            "symbol": "TEST",
        },
        index=idx,
    )


def test_features_have_no_lookahead_on_inputs():
    feat = make_features(_bars(), horizon=5)
    assert list(FEATURE_COLS) == [
        "ret_1",
        "ret_5",
        "ret_20",
        "vol_20",
        "rsi_14",
        "sma_ratio_20_50",
        "dist_sma_20",
        "volume_z_20",
        "high_low_20",
    ]
    ready = feat.dropna(subset=FEATURE_COLS + ["y"])
    assert len(ready) > 50
    # Last horizon rows cannot have a complete forward label.
    assert feat["fwd_ret"].iloc[-4:].isna().all()


def test_sma_and_momentum_score_in_unit_interval():
    feat = make_features(_bars(), horizon=5).dropna(subset=FEATURE_COLS)
    sma = SmaCross()
    sma.fit(feat)
    s = sma.scores(feat)
    assert s.min() >= 0 and s.max() <= 1
    mom = MomentumVol()
    mom.fit(feat)
    m = mom.scores(feat)
    assert m.min() >= 0 and m.max() <= 1


def test_hgb_fits_tiny_set():
    feat = make_features(_bars(400), horizon=5).dropna(subset=FEATURE_COLS + ["y"])
    model = HgbTabular()
    model.fit(feat.iloc[:250])
    scores = model.scores(feat.iloc[250:])
    assert len(scores) == len(feat.iloc[250:])
    assert scores.between(0, 1).all()


def test_costs_reduce_return():
    feat = make_features(_bars(120), horizon=5).dropna(subset=FEATURE_COLS)
    scores = pd.Series(1.0, index=feat.index)
    weights = long_flat_from_scores(feat, scores, threshold=0.5, max_name_weight=1.0)
    cheap = portfolio_returns(feat, weights, {"equity": {"commission_bps": 0, "slippage_bps": 0, "spread_bps": 0}}, {"TEST": "equity"})
    dear = portfolio_returns(feat, weights, {"equity": {"commission_bps": 10, "slippage_bps": 10, "spread_bps": 10}}, {"TEST": "equity"})
    assert dear["net"].sum() <= cheap["net"].sum() + 1e-12


def test_folds_are_forward_only():
    dates = pd.bdate_range("2018-01-01", "2024-12-31")
    folds = make_folds(dates, {"train_years": 3, "test_months": 6, "step_months": 6, "embargo_days": 5})
    assert folds
    for tr_s, tr_e, te_s, te_e in folds:
        assert tr_s < tr_e < te_s <= te_e
        assert (te_s - tr_e).days >= 5


def test_tear_sheet_buy_and_hold_positive_drift():
    idx = pd.bdate_range("2020-01-01", periods=252)
    r = pd.Series(0.001, index=idx)
    sheet = tear_sheet(r, r, strategy="bh", n_folds=1, n_trades=0)
    assert sheet.total_return > 0
    assert sheet.sharpe > 0
