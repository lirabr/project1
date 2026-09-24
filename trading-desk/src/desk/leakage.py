"""Leakage / lookahead linter.

The architecture promises a skeptic step that hunts leakage before a research
run is accepted. This module makes that runnable and testable without a network
or an LLM. It asserts the invariants that silently produce fantasy Sharpe:

1. The last ``horizon`` forward-return labels must be NaN (no peeking past the
   edge of the panel).
2. The label is strictly forward (close-to-close over ``horizon``), so a row's
   ``fwd_ret`` must equal the realized shift and never reference the same bar.
3. Walk-forward folds must satisfy ``train_end < test_start`` with an embargo,
   so a training label cannot overlap the test window.

Each check returns a list of human-readable violations. An empty list means the
check passed. ``lint_panel`` / ``lint_folds`` raise ``LeakageError`` when strict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


class LeakageError(AssertionError):
    """Raised when a leakage invariant is violated in strict mode."""


@dataclass
class LintReport:
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations

    def raise_if_bad(self) -> LintReport:
        if self.violations:
            raise LeakageError("; ".join(self.violations))
        return self


def lint_panel(panel: pd.DataFrame, horizon: int, *, strict: bool = False) -> LintReport:
    """Check per-symbol forward-label invariants on a feature panel."""
    violations: list[str] = []
    if "fwd_ret" not in panel.columns:
        violations.append("panel has no 'fwd_ret' column")
        report = LintReport(violations)
        return report.raise_if_bad() if strict else report
    if "symbol" not in panel.columns:
        violations.append("panel has no 'symbol' column")

    group_key = "symbol" if "symbol" in panel.columns else None
    groups = panel.groupby(group_key) if group_key else [("__all__", panel)]
    for name, g in groups:
        g = g.sort_values("date") if "date" in g.columns else g
        tail = g["fwd_ret"].tail(horizon)
        n_valid = int(tail.notna().sum())
        if n_valid > 0:
            violations.append(
                f"{name}: last {horizon} fwd_ret rows should be NaN, found {n_valid} non-NaN "
                "(lookahead past panel edge)"
            )
        # Reconstruct the label from Close and compare where both are defined.
        if "Close" in g.columns:
            recon = g["Close"].shift(-horizon) / g["Close"] - 1.0
            both = g["fwd_ret"].notna() & recon.notna()
            if both.any():
                diff = (g["fwd_ret"][both] - recon[both]).abs().max()
                if not math.isnan(diff) and diff > 1e-9:
                    violations.append(
                        f"{name}: fwd_ret does not match forward close shift (max diff {diff:.2e})"
                    )

    report = LintReport(violations)
    return report.raise_if_bad() if strict else report


def lint_folds(
    folds: list[tuple[Any, Any, Any, Any]],
    embargo_days: int,
    *,
    strict: bool = False,
) -> LintReport:
    """Check that every walk-forward fold trains strictly before it tests.

    ``folds`` is a list of ``(train_start, train_end, test_start, test_end)``.
    """
    violations: list[str] = []
    for i, fold in enumerate(folds):
        train_start, train_end, test_start, test_end = (pd.Timestamp(x) for x in fold)
        if not (train_start < train_end):
            violations.append(f"fold {i}: train_start >= train_end")
        if not (train_end < test_start):
            violations.append(f"fold {i}: train_end >= test_start (no gap)")
        else:
            gap = (test_start - train_end).days
            if gap < embargo_days:
                violations.append(
                    f"fold {i}: embargo gap {gap}d < required {embargo_days}d"
                )
        if not (test_start < test_end):
            violations.append(f"fold {i}: test_start >= test_end")
    report = LintReport(violations)
    return report.raise_if_bad() if strict else report
