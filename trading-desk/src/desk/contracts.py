from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Side = Literal["long", "flat", "short"]
AssetClass = Literal["equity", "crypto"]


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: AssetClass


@dataclass
class TearSheet:
    strategy: str
    n_folds: int
    n_trades: int
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    hit_rate: float
    turnover: float
    total_return: float
    bench_total_return: float
    excess_return: float
    notes: list[str] = field(default_factory=list)
    mean_exposure: float = 0.0
    mean_cash_weight: float = 1.0
    total_cost_return: float = 0.0
    double_cost_total_return: float = 0.0
    fold_return_std: float = 0.0
    benchmarks: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelCard:
    symbol: str
    strategy: str
    score: float
    last_close: float
    as_of: str
    features: dict[str, float]
    note: str
    model_version: str = "unversioned"
    data_version: str = "unversioned"
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TradeProposal:
    symbol: str
    side: Side
    urgency: Literal["low", "normal", "high"]
    thesis: str
    invalidation: str
    horizon_days: int
    score: float
    suggested_notional_usd: float
    cited_memory_ids: list[int] = field(default_factory=list)
    bull_brief: str = ""
    bear_brief: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    target_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskDecision:
    allow: bool
    reason: str
    clipped_notional_usd: float
    gates: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Episode:
    id: int | None
    ts: str
    symbol: str
    side: Side
    thesis: str
    lesson: str
    realized_r: float | None
    outcome: str
    regime: str
    strategy: str


@dataclass
class FoldResult:
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int
    total_return: float
    sharpe: float
    max_drawdown: float
