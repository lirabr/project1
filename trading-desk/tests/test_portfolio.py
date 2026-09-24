from datetime import UTC, datetime, timedelta

import pytest

from desk.portfolio import Mark, PortfolioTarget, allocate, plan_rebalance

NOW = datetime(2026, 9, 24, 14, tzinfo=UTC)


def target(weights=None):
    return PortfolioTarget(weights or {"A": .2, "B": .2}, NOW.isoformat(),
                           (NOW + timedelta(seconds=1)).isoformat(), "model", "data", "config")


def test_cash_is_not_renormalized_and_target_is_immutable():
    weights = allocate({"A": .8, "B": .9}, .55, .2)
    t = target(weights)
    assert dict(t.weights) == {"A": .2, "B": .2}
    assert t.cash_weight == pytest.approx(.6)
    weights["A"] = 1
    assert t.weights["A"] == .2
    with pytest.raises(TypeError):
        t.weights["A"] = .5
    assert t.target_id == target({"B": .2, "A": .2}).target_id


@pytest.mark.parametrize("weights", [{"A": float("nan")}, {"A": -1}, {"A": 1.1}])
def test_invalid_targets_rejected(weights):
    with pytest.raises(ValueError):
        target(weights)


def test_inverse_vol_and_risk_scale_never_increase_exposure():
    w = allocate({"A": .8, "B": .8}, .5, 1, method="inverse_vol", volatility={"A": .1, "B": .2})
    assert w == pytest.approx({"A": 2 / 3, "B": 1 / 3})
    assert sum(allocate({"A": .8}, .5, .2, exposure_scale=.5).values()) == .1
    assert allocate({"A": .1}, .5, .2) == {"A": 0.0}
    with pytest.raises(ValueError):
        allocate({"A": .8}, .5, 1, method="inverse_vol", volatility={"A": 0})


def test_rebalance_includes_exits_and_sells_first():
    t = target()
    now = NOW + timedelta(seconds=2)
    marks = {s: Mark(100, now.isoformat()) for s in ("A", "B", "OLD")}
    orders = plan_rebalance(t, {"OLD": 5}, 500, marks, now)
    assert [(o.symbol, o.side, o.quantity) for o in orders] == [("OLD", "sell", 5), ("A", "buy", 2), ("B", "buy", 2)]
    assert orders == plan_rebalance(t, {"OLD": 5}, 500, marks, now)
    assert plan_rebalance(t, {"A": 2, "B": 2}, 600, marks, now) == []


def test_missing_stale_future_marks_and_early_execution_rejected():
    t = target()
    for marks, now in [({}, NOW + timedelta(seconds=2)),
                       ({s: Mark(100, (NOW - timedelta(seconds=400)).isoformat()) for s in ("A", "B")}, NOW + timedelta(seconds=2)),
                       ({s: Mark(100, (NOW + timedelta(hours=1)).isoformat()) for s in ("A", "B")}, NOW + timedelta(seconds=2)),
                       ({s: Mark(100, NOW.isoformat()) for s in ("A", "B")}, NOW)]:
        with pytest.raises(ValueError):
            plan_rebalance(t, {}, 1000, marks, now)


def test_expired_target_cannot_be_reauthorized_with_fresh_marks():
    now = NOW + timedelta(days=1)
    marks = {s: Mark(100, now.isoformat()) for s in ("A", "B")}
    with pytest.raises(ValueError, match="expired"):
        plan_rebalance(target(), {}, 1000, marks, now)


def test_research_regime_overlay_is_lagged_and_preserves_cash():
    import pandas as pd

    from desk.backtest import long_flat_from_scores

    dates = pd.date_range("2026-01-01", periods=4)
    panel = pd.DataFrame({"symbol": "A", "date": dates, "ret_20": [-.1, .1, .1, .1],
                          "vol_20": .03}, index=dates)
    weights = long_flat_from_scores(panel, pd.Series(1., index=dates), .5, 1., regime_scales={"risk_off": .5})
    assert weights["A"].tolist() == [0., .5, 1., 0.]
    panel.loc[dates[2]:, "vol_20"] = 10
    changed = long_flat_from_scores(panel, pd.Series(1., index=dates), .5, 1., regime_scales={"risk_off": .5})
    pd.testing.assert_frame_equal(weights.iloc[:2], changed.iloc[:2])


def test_halt_path_is_shared_by_cli_and_paper_gate(tmp_path):
    from desk import io_utils
    from desk.cli import build_parser
    from desk.risk_gate import halt_path

    parser = build_parser()
    args = parser.parse_args(["halt"])
    args.func(args)
    assert halt_path({}) == io_utils.ARTIFACT_DIR / "HALT"
    assert halt_path({}).exists()
    config = tmp_path / "risk.yaml"
    custom = tmp_path / "custom-halt"
    io_utils.write_yaml(config, {"kill_switch_path": str(custom)})
    args = parser.parse_args(["--risk", str(config), "halt"])
    args.func(args)
    assert custom.exists()
