from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone-aware timestamps are required")
    return result


def finite(value: float, minimum: float = 0) -> float:
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError("Invalid finite nonnegative number")
    return value


@dataclass(frozen=True)
class PortfolioTarget:
    weights: Mapping[str, float]
    as_of: str
    execute_after: str
    model_version: str
    data_version: str
    config_version: str
    evidence_ids: tuple[str, ...] = ()
    expires_at: str = ""

    def __post_init__(self):
        weights = {str(s): finite(w) for s, w in sorted(self.weights.items())}
        if any(not s for s in weights) or sum(weights.values()) > 1 + 1e-10:
            raise ValueError("Invalid long-only weights")
        if timestamp(self.execute_after) <= timestamp(self.as_of):
            raise ValueError("Execution must follow the decision timestamp")
        expiry = timestamp(self.expires_at) if self.expires_at else min(timestamp(self.as_of) + timedelta(days=1), timestamp(self.execute_after) + timedelta(minutes=5))
        if not timestamp(self.execute_after) < expiry <= timestamp(self.as_of) + timedelta(days=1):
            raise ValueError("Target expiry must follow execution and be within one day of the decision")
        object.__setattr__(self, "expires_at", expiry.isoformat())
        if not all((self.model_version, self.data_version, self.config_version)):
            raise ValueError("Target lineage is required")
        object.__setattr__(self, "weights", MappingProxyType(weights))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1 - sum(self.weights.values()))

    def to_dict(self) -> dict:
        return {"weights": dict(self.weights), "cash_weight": self.cash_weight, "as_of": self.as_of,
                "execute_after": self.execute_after, "model_version": self.model_version,
                "data_version": self.data_version, "config_version": self.config_version,
                "evidence_ids": list(self.evidence_ids), "expires_at": self.expires_at}

    @property
    def target_id(self) -> str:
        return digest(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict) -> PortfolioTarget:
        payload = dict(value)
        cash = payload.pop("cash_weight", None)
        target = cls(**payload)
        if cash is not None and (not math.isfinite(float(cash)) or abs(cash - target.cash_weight) > 1e-10):
            raise ValueError("Cash allocation mismatch")
        return target


@dataclass(frozen=True)
class Mark:
    price: float
    as_of: str

    def validate(self, now: datetime, max_age_seconds: float = 300) -> float:
        price = finite(self.price)
        age = (now - timestamp(self.as_of)).total_seconds()
        if price <= 0 or not 0 <= age <= finite(max_age_seconds):
            raise ValueError("Missing, stale, future or invalid mark")
        return price


@dataclass(frozen=True)
class PlannedOrder:
    order_id: str
    target_id: str
    symbol: str
    side: str
    quantity: float
    reference_price: float


def allocate(scores: Mapping[str, float], threshold: float, max_name_weight: float,
             *, method: str = "equal", volatility: Mapping[str, float] | None = None,
             exposure_scale: float = 1.0, risk_scales: Mapping[str, float] | None = None) -> dict[str, float]:
    if not all(0 <= finite(v) <= 1 for v in (threshold, max_name_weight, exposure_scale)):
        raise ValueError("Allocation bounds must be in [0, 1]")
    if method not in {"equal", "inverse_vol"}:
        raise ValueError(f"Unknown allocator: {method}")
    if any(not 0 <= finite(score) <= 1 for score in scores.values()):
        raise ValueError("Scores must be in [0, 1]")
    selected = sorted(s for s, score in scores.items() if score >= threshold)
    raw = {}
    for symbol in selected:
        vol = finite((volatility or {}).get(symbol, 0)) if method == "inverse_vol" else 1
        if vol <= 0:
            raise ValueError(f"Missing positive volatility for {symbol}")
        raw[symbol] = 1 / vol
    total = sum(raw.values())
    risk_scales = risk_scales or {}
    if any(not 0 <= finite(scale) <= 1 for scale in risk_scales.values()):
        raise ValueError("Risk scales can only reduce exposure")
    return {s: min(max_name_weight, raw.get(s, 0) / total) * exposure_scale * risk_scales.get(s, 1) if total else 0.0
            for s in sorted(scores)}


def regime_scale(features: Mapping, scales: Mapping[str, float] | None = None) -> float:
    from desk.regime import REGIME_LABELS, classify_row

    scales = scales or {}
    if set(scales) - set(REGIME_LABELS) or any(not 0 <= finite(v) <= 1 for v in scales.values()):
        raise ValueError("Invalid regime exposure reduction")
    return float(scales.get(classify_row(features), 1))


def plan_rebalance(target: PortfolioTarget, quantities: Mapping[str, float], cash: float,
                   marks: Mapping[str, Mark], now: datetime, *, max_age_seconds: float = 300,
                   min_notional: float = 1) -> list[PlannedOrder]:
    if not timestamp(target.execute_after) <= now < timestamp(target.expires_at):
        raise ValueError("Target is not executable yet or has expired")
    finite(min_notional)
    symbols = set(quantities) | set(target.weights)
    if symbols - marks.keys():
        raise ValueError(f"Missing marks: {sorted(symbols - marks.keys())}")
    prices = {s: marks[s].validate(now, max_age_seconds) for s in symbols}
    equity = finite(cash) + sum(finite(q) * prices[s] for s, q in quantities.items())
    if equity <= 0:
        raise ValueError("Positive equity is required")
    orders = []
    for symbol in sorted(symbols):
        delta = target.weights.get(symbol, 0) * equity - quantities.get(symbol, 0) * prices[symbol]
        if abs(delta) < max(min_notional, 1e-8):
            continue
        side = "buy" if delta > 0 else "sell"
        quantity = abs(delta) / prices[symbol]
        order_id = digest([target.target_id, symbol, side, quantity, prices[symbol]])
        orders.append(PlannedOrder(order_id, target.target_id, symbol, side, quantity, prices[symbol]))
    return sorted(orders, key=lambda o: (o.side != "sell", o.symbol))
