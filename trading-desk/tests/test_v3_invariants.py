from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from desk.backtest import long_flat_from_scores, portfolio_returns, tear_sheet
from desk.contracts import ModelCard, TradeProposal
from desk.features import make_features
from desk.models import MomentumVol
from desk.risk_gate import evaluate


def proposal(**changes):
    values = {"symbol": "AAPL", "side": "long", "urgency": "low", "thesis": "test", "invalidation": "test",
                  "horizon_days": 5, "score": 0.8, "suggested_notional_usd": 1000.0}
    return TradeProposal(**(values | changes))


def risk(prop=None, **changes):
    values = {"book_gross_usd": 1000.0, "book_name_usd": 0.0, "day_pnl_usd": 0.0,
                  "orders_this_cycle": 0, "crypto_weight": 0.0, "is_crypto": False,
                  "cfg": {"max_crypto_weight": 0.3, "kill_switch_path": "data/artifacts/HALT"}}
    return evaluate(prop or proposal(), **(values | changes))


def test_unknown_labels_remain_unknown():
    n = 80
    close = np.linspace(100, 120, n)
    bars = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                             "Close": close, "Volume": np.arange(n) + 100, "symbol": "AAPL"},
                        index=pd.bdate_range("2020-01-01", periods=n))
    features = make_features(bars, horizon=5)
    assert features["y"].tail(5).isna().all()
    assert features["label_end"].tail(5).isna().all()


def test_momentum_scores_do_not_depend_on_future_batch():
    model = MomentumVol()
    model.fit(pd.DataFrame({"ret_20": [-0.02, 0.0, 0.01, 0.05], "vol_20": [0.01, 0.02, 0.03, 0.04]}))
    current = pd.DataFrame({"ret_20": [0.03], "vol_20": [0.01]})
    future = pd.DataFrame({"ret_20": [100.0], "vol_20": [0.00001]})
    assert model.scores(current).iloc[0] == model.scores(pd.concat([current, future])).iloc[0]


def test_next_open_timing_and_terminal_liquidation():
    panel = pd.DataFrame({"symbol": "AAPL", "Open": [100., 100., 110., 110.],
                          "Close": [100., 105., 110., 110.]},
                         index=pd.date_range("2020-01-01", periods=4))
    scores = pd.Series([1., 0., 0., 0.], index=panel.index)
    weights = long_flat_from_scores(panel, scores, .5, 1.)
    returns = portfolio_returns(panel, weights, {"equity": {"commission_bps": 10}}, {"AAPL": "equity"})
    assert returns["gross"].tolist() == pytest.approx([0., .1, 0., 0.])
    assert returns["cost"].sum() == pytest.approx(.002)
    assert weights.iloc[-1].sum() == 0


def test_initial_loss_counts_in_drawdown():
    returns = pd.Series([-.1, 0., 0.], index=pd.date_range("2020-01-01", periods=3))
    assert tear_sheet(returns, None, "test", 1, 1).max_drawdown == pytest.approx(-.1)


def test_projected_crypto_weight_is_clipped():
    decision = risk(proposal(symbol="BTC-USD"), is_crypto=True, crypto_weight=.2)
    assert decision.allow
    assert (200 + decision.clipped_notional_usd) / (1000 + decision.clipped_notional_usd) <= .3 + 1e-9


def test_crypto_cannot_be_first_entire_risk_book():
    assert not risk(proposal(symbol="BTC-USD"), book_gross_usd=0, is_crypto=True).allow


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_notional_cannot_pass(value):
    assert not risk(proposal(suggested_notional_usd=value)).allow


@pytest.mark.parametrize("name", ["book_gross_usd", "book_name_usd", "day_pnl_usd", "crypto_weight"])
def test_nonfinite_portfolio_cannot_pass(name):
    assert not risk(**{name: float("nan")}).allow


def test_auditor_binds_symbol_and_finite_size():
    from desk.auditor import audit_proposal

    card = ModelCard("AAPL", "sma_cross", .8, 100., "2026-01-01", {}, "range")
    assert not audit_proposal(proposal(symbol="MSFT"), card, []).ok
    assert not audit_proposal(proposal(suggested_notional_usd=float("nan")), card, []).ok


def test_trust_does_not_change_model_probability():
    from desk.trust import apply_trust

    score, size, _ = apply_trust(.8, 1000., {"model": 1.8}, "range", False)
    assert score == .8
    assert size <= 1000.


def test_reflection_cannot_use_pre_entry_prices():
    from desk.reflect import _mae_mfe

    data = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=3), "Close": [1., 10., 100.]})
    assert _mae_mfe(data, 100., "2020-01-04T00:00:00Z") == (None, None, 0)


def test_live_preflight_never_claims_execution_readiness(monkeypatch):
    from desk.live import preflight

    monkeypatch.setenv("DESK_LIVE_CONFIRM", "CONFIRM")
    blocks = preflight({"enabled": True, "confirm_phrase": "CONFIRM", "withdraw_disabled_attested": True,
                        "max_live_notional_usd": 250}, {"allow_live": True, "require_human_approve": True})
    assert any("not implemented" in item for item in blocks)


def test_fill_reports_failure_and_deduplicates(tmp_path):
    from desk.memory import apply_fill, book_state, connect

    conn = connect(tmp_path / "fills.sqlite")
    assert apply_fill(conn, "AAPL", 200000, 100., "2020-01-01") is False
    assert apply_fill(conn, "AAPL", 100., 100., "2020-01-01", fill_id="same") is True
    assert apply_fill(conn, "AAPL", 100., 100., "2020-01-01", fill_id="same") is True
    assert book_state(conn)["gross"] == 100.
    assert book_state(conn)["cash"] == 99900.


def test_overlapping_folds_are_rejected():
    from desk.walkforward import make_folds

    with pytest.raises(ValueError):
        make_folds(pd.bdate_range("2018-01-01", "2024-12-31"),
                   {"train_years": 3, "test_months": 6, "step_months": 3, "embargo_days": 5})


def test_adjacent_folds_do_not_share_test_dates():
    from desk.walkforward import make_folds

    folds = make_folds(pd.bdate_range("2018-01-01", "2024-12-31"),
                       {"train_years": 3, "test_months": 6, "step_months": 6, "embargo_days": 5})
    assert all(left[3] < right[2] for left, right in itertools.pairwise(folds))
