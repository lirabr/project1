from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from desk.leakage import LeakageError, lint_folds, lint_panel


def _panel(horizon: int, corrupt_tail: bool = False, break_shift: bool = False) -> pd.DataFrame:
    n = 60
    close = pd.Series(100 + np.arange(n, dtype=float))
    fwd = close.shift(-horizon) / close - 1.0
    if corrupt_tail:
        fwd.iloc[-1] = 0.123  # inject lookahead past the edge
    if break_shift:
        fwd = fwd + 0.5  # no longer matches the true forward shift
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * n,
            "date": pd.date_range("2020-01-01", periods=n, freq="D"),
            "Close": close.values,
            "fwd_ret": fwd.values,
        }
    )


def test_clean_panel_passes():
    rep = lint_panel(_panel(5), horizon=5)
    assert rep.ok, rep.violations


def test_tail_lookahead_flagged():
    rep = lint_panel(_panel(5, corrupt_tail=True), horizon=5)
    assert not rep.ok
    assert any("NaN" in v for v in rep.violations)


def test_broken_shift_flagged():
    rep = lint_panel(_panel(5, break_shift=True), horizon=5)
    assert not rep.ok
    assert any("forward close shift" in v for v in rep.violations)


def test_strict_raises():
    with pytest.raises(LeakageError):
        lint_panel(_panel(5, corrupt_tail=True), horizon=5, strict=True)


def test_folds_require_embargo_gap():
    good = [
        (pd.Timestamp("2018-01-01"), pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-06"), pd.Timestamp("2021-04-06")),
    ]
    assert lint_folds(good, embargo_days=5).ok

    no_gap = [
        (pd.Timestamp("2018-01-01"), pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-01"), pd.Timestamp("2021-04-01")),
    ]
    rep = lint_folds(no_gap, embargo_days=5)
    assert not rep.ok
    assert any("embargo" in v or "no gap" in v for v in rep.violations)
