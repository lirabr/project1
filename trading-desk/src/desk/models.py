from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from desk.features import FEATURE_COLS


class Strategy(Protocol):
    name: str

    def fit(self, train: pd.DataFrame) -> None: ...

    def scores(self, frame: pd.DataFrame) -> pd.Series:
        """Score in [0, 1] used as P(long)."""


@dataclass
class SmaCross:
    """Rule baseline: long when SMA20 > SMA50, encoded via sma_ratio_20_50."""

    name: str = "sma_cross"
    lookback_fast: int = 20
    lookback_slow: int = 50

    def fit(self, train: pd.DataFrame) -> None:
        return None

    def scores(self, frame: pd.DataFrame) -> pd.Series:
        ratio = frame["sma_ratio_20_50"]
        return (ratio > 0).astype(float)


@dataclass
class MomentumVol:
    """Long recent winners only when vol is not exploding."""

    name: str = "momentum_vol"
    mom_col: str = "ret_20"
    vol_col: str = "vol_20"

    def fit(self, train: pd.DataFrame) -> None:
        self._vol_cut = float(train[self.vol_col].median())
        self._mom_cut = float(train[self.mom_col].median())
        self._mom_reference = np.sort(train[self.mom_col].dropna().to_numpy())
        self._vol_reference = np.sort(train[self.vol_col].dropna().to_numpy())

    def scores(self, frame: pd.DataFrame) -> pd.Series:
        if not hasattr(self, "_mom_reference"):
            raise RuntimeError("MomentumVol must be fit before scoring")
        long = (frame[self.mom_col] > self._mom_cut) & (frame[self.vol_col] <= self._vol_cut)
        # Soft score so thresholding still works.
        mom = pd.Series(np.searchsorted(self._mom_reference, frame[self.mom_col], side="right") / len(self._mom_reference), index=frame.index)
        vol_pen = pd.Series(1.0 - np.searchsorted(self._vol_reference, frame[self.vol_col], side="left") / len(self._vol_reference), index=frame.index)
        raw = 0.5 * mom + 0.5 * vol_pen
        return raw.where(long, 0.35)


@dataclass
class HgbTabular:
    name: str = "hgb_tab"

    def __post_init__(self) -> None:
        self.model = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        max_depth=3,
                        learning_rate=0.06,
                        max_iter=120,
                        l2_regularization=0.1,
                        min_samples_leaf=25,
                        random_state=0,
                        early_stopping=False,
                    ),
                ),
            ]
        )
        self._fitted = False

    def fit(self, train: pd.DataFrame) -> None:
        x = train[FEATURE_COLS]
        y = train["y"].astype(int)
        self.model.fit(x, y)
        self._fitted = True

    def scores(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("HgbTabular must be fit before scoring")
        proba = self.model.predict_proba(frame[FEATURE_COLS])
        classes = list(self.model.named_steps["clf"].classes_)
        if 1 not in classes:
            return pd.Series(0.0, index=frame.index)
        return pd.Series(proba[:, classes.index(1)], index=frame.index)


def build_strategy(name: str) -> Strategy:
    catalog: dict[str, type] = {
        "sma_cross": SmaCross,
        "momentum_vol": MomentumVol,
        "hgb_tab": HgbTabular,
    }
    if name not in catalog:
        raise KeyError(f"Unknown strategy {name}. Choose from {list(catalog)}")
    return catalog[name]()


def available_strategies() -> list[str]:
    return ["sma_cross", "momentum_vol", "hgb_tab"]
