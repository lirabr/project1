from __future__ import annotations

import numpy as np
import pandas as pd

from desk.contracts import TearSheet
from desk.portfolio import allocate, regime_scale


def _ann_factor(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 252.0
    delta = (index.max() - index.min()).days
    if delta <= 0:
        return 252.0
    bars_per_year = len(index) * 365.25 / delta
    return max(bars_per_year, 52.0)


def total_cost_bps(cost_cfg: dict, asset_class: str) -> float:
    block = cost_cfg.get(asset_class, cost_cfg.get("equity", {}))
    return float(block.get("commission_bps", 0) + block.get("slippage_bps", 0) + 0.5 * block.get("spread_bps", 0))


def apply_costs(turnover: pd.Series, cost_bps: float) -> pd.Series:
    return turnover.abs() * (cost_bps / 1e4)


def long_flat_from_scores(
    panel: pd.DataFrame,
    scores: pd.Series,
    threshold: float,
    max_name_weight: float,
    *,
    allocation_method: str = "equal",
    exposure_scale: float = 1.0,
    regime_scales: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Next-open fill, long/flat, equal-weight across names that fire that day,
    clipped to max_name_weight.
    """
    df = panel.copy()
    if "date" not in df.columns:
        df["date"] = pd.to_datetime(df.index)
    score_vals = scores
    if len(score_vals) != len(df):
        score_vals = pd.Series(scores.to_numpy(), index=df.index)
    df["score"] = np.asarray(score_vals)
    df["raw_signal"] = ((df["score"] >= threshold) & df.get("in_universe", True)).astype(float)

    # Signal at close t → position from open t+1 to open t+2.
    df["signal"] = df.groupby("symbol", group_keys=False)["raw_signal"].shift(1).fillna(0.0)

    pivoted = df.pivot_table(index="date", columns="symbol", values="signal", aggfunc="last").fillna(0.0)
    df["allocation_scale"] = df.apply(lambda row: regime_scale(row, regime_scales), axis=1)
    df["allocation_scale"] = df.groupby("symbol")["allocation_scale"].shift(1).fillna(1.)
    scales = df.pivot_table(index="date", columns="symbol", values="allocation_scale", aggfunc="last")
    volatility = None
    if allocation_method == "inverse_vol":
        df["lagged_vol"] = df.groupby("symbol")["vol_20"].shift(1)
        volatility = df.pivot_table(index="date", columns="symbol", values="lagged_vol", aggfunc="last")
    weights = pd.DataFrame([allocate(row.to_dict(), .5, max_name_weight, method=allocation_method,
                                     volatility=volatility.loc[date].to_dict() if volatility is not None and date in volatility.index else {},
                                     exposure_scale=exposure_scale, risk_scales=scales.loc[date].to_dict()) for date, row in pivoted.iterrows()],
                           index=pivoted.index, columns=pivoted.columns)
    # If clip reduced exposure, leave the residual in cash (do not renormalize up).
    if not weights.empty:
        weights.iloc[-1] = 0.0
    return weights


def portfolio_returns(
    panel: pd.DataFrame,
    weights: pd.DataFrame,
    cost_cfg: dict,
    asset_class_map: dict[str, str],
) -> pd.DataFrame:
    frame = panel.copy()
    if "date" not in frame.columns:
        frame["date"] = pd.to_datetime(frame.index)
    close = frame.pivot_table(index="date", columns="symbol", values="Open", aggfunc="last")
    if close.isna().any().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any().any():
        raise ValueError("Missing or invalid opens: use one complete trading calendar per run")
    # Next-open approximation: use next close-to-close after the shift already applied
    # plus an explicit one-bar delay already in weights. Asset return is close-to-close.
    asset_ret = (close.shift(-1) / close - 1.0).fillna(0.0)
    aligned = asset_ret.reindex(weights.index).fillna(0.0)
    w = weights.reindex(aligned.index).fillna(0.0)
    prev_w = w.shift(1).fillna(0.0)
    turnover = (w - prev_w).abs().sum(axis=1)

    # Cost per name using that name's asset class.
    cost = pd.Series(0.0, index=w.index)
    for sym in w.columns:
        cls = asset_class_map.get(sym, "equity")
        bps = total_cost_bps(cost_cfg, cls)
        cost = cost + (w[sym] - prev_w[sym]).abs() * (bps / 1e4)

    gross = (w * aligned).sum(axis=1)
    net = gross - cost
    out = pd.DataFrame({"gross": gross, "net": net, "cost": cost, "turnover": turnover,
                        "exposure": w.sum(axis=1), "cash_weight": 1 - w.sum(axis=1)})
    return out


def tear_sheet(
    returns: pd.Series,
    bench: pd.Series | None,
    strategy: str,
    n_folds: int,
    n_trades: int,
    extra_notes: list[str] | None = None,
) -> TearSheet:
    r = returns.dropna()
    if r.empty:
        raise ValueError("No returns to score")
    ann = _ann_factor(r.index)
    equity = (1 + r).cumprod()
    total = float(equity.iloc[-1] - 1)
    years = max((r.index.max() - r.index.min()).days / 365.25, 1 / 252)
    cagr = float((1 + total) ** (1 / years) - 1) if total > -1 else -1.0
    vol = float(r.std(ddof=1) * np.sqrt(ann)) if len(r) > 2 else float("nan")
    sharpe = float(r.mean() * ann / vol) if vol and vol > 0 else 0.0
    downside = r[r < 0]
    dvol = float(downside.std(ddof=1) * np.sqrt(ann)) if len(downside) > 2 else vol
    sortino = float(r.mean() * ann / dvol) if dvol and dvol > 0 else 0.0
    peak = equity.cummax().clip(lower=1.0)
    dd = equity / peak - 1.0
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    hit = float((r > 0).mean())
    turnover = float("nan")
    bench_total = 0.0
    if bench is not None and not bench.empty:
        b = bench.reindex(r.index).fillna(0.0)
        bench_total = float((1 + b).prod() - 1)
    notes = extra_notes or []
    return TearSheet(
        strategy=strategy,
        n_folds=n_folds,
        n_trades=n_trades,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        calmar=calmar,
        hit_rate=hit,
        turnover=turnover,
        total_return=total,
        bench_total_return=bench_total,
        excess_return=total - bench_total,
        notes=notes,
    )


def buy_and_hold_returns(panel: pd.DataFrame, symbol: str) -> pd.Series:
    sub = panel.loc[panel["symbol"] == symbol].copy()
    if "date" in sub.columns:
        sub = sub.drop_duplicates("date").set_index("date")
    else:
        sub = sub[~sub.index.duplicated(keep="last")].sort_index()
    if sub.empty:
        raise ValueError(f"Missing benchmark {symbol}")
    return (sub["Open"].shift(-1) / sub["Open"] - 1.0).fillna(0.0)
