from __future__ import annotations

import pandas as pd

from desk.features import FEATURE_COLS, read_panel
from desk.memory import close_episode, connect, pending_reflections
from desk.trust import update_from_outcome
from desk.vectors import upsert


def _symbol_series(symbol: str) -> pd.DataFrame:
    panel = read_panel()
    sub = panel[panel["symbol"] == symbol].copy()
    if sub.empty:
        return sub
    if "date" in sub.columns:
        sub = sub.sort_values("date")
    return sub


def _latest_close(sub: pd.DataFrame) -> float | None:
    if sub.empty:
        return None
    return float(sub.iloc[-1]["Close"])


def _mae_mfe(sub: pd.DataFrame, entry_px: float, entry_ts: str | None) -> tuple[float | None, float | None, int]:
    """Max adverse / favorable excursion (as returns from entry) over the hold.

    Window starts at the first bar on/after entry_ts (falls back to full series).
    Returns (mae, mfe, holding_bars). MAE <= 0, MFE >= 0 for a long.
    """
    if sub.empty or not entry_px:
        return None, None, 0
    window = sub
    if entry_ts and "date" in sub.columns:
        dates = pd.to_datetime(sub["date"])
        entry_day = pd.to_datetime(entry_ts).tz_localize(None)
        mask = dates.dt.tz_localize(None) >= entry_day
        if not mask.any():
            return None, None, 0
        window = sub[mask]
    closes = window["Close"].astype(float)
    rets = closes / float(entry_px) - 1.0
    return min(0.0, float(rets.min())), max(0.0, float(rets.max())), len(window)


def reflect() -> int:
    conn = connect()
    pending = pending_reflections(conn)
    n = 0
    for row in pending:
        sub = _symbol_series(row["symbol"])
        px = _latest_close(sub)
        if px is None or not row.get("entry_px"):
            continue
        entry = float(row["entry_px"])
        r = px / entry - 1.0
        mae, mfe, holding = _mae_mfe(sub, entry, row.get("ts"))
        if holding == 0:
            continue
        excursion = ""
        if mae is not None and mfe is not None:
            excursion = f" [MAE {mae:+.2%} / MFE {mfe:+.2%} over {holding} bars]"
        if r > 0.01:
            outcome = "win"
            lesson = (
                f"Long {row['symbol']} worked ({r:+.2%}).{excursion} "
                f"Thesis was: {row['thesis'][:160]} Keep sizing small when score is only modest."
            )
        elif r < -0.01:
            outcome = "loss"
            lesson = (
                f"Long {row['symbol']} lost ({r:+.2%}).{excursion} "
                f"Bear brief said: {str(row.get('bear_brief') or '')[:160]} "
                f"Next time require a cleaner regime or half size."
            )
        else:
            outcome = "scratch"
            lesson = f"{row['symbol']} was a scratch ({r:+.2%}).{excursion} Costs dominate this kind of trade."
        close_episode(
            conn,
            int(row["id"]),
            px,
            lesson,
            outcome,
            mae=mae,
            mfe=mfe,
            holding_bars=holding,
        )
        update_from_outcome(outcome, float(row.get("score") or 0.0))
        feat_row = {}
        if not sub.empty:
            last = sub.iloc[-1]
            feat_row = {c: last.get(c) for c in FEATURE_COLS}
        feat_row["symbol"] = row["symbol"]
        upsert(conn, int(row["id"]), row["symbol"], str(row.get("regime") or ""), feat_row, lesson)
        n += 1
        print(f"reflected ep#{row['id']} {row['symbol']} {outcome} {r:+.2%}{excursion}")
    if n == 0:
        print("no submitted episodes ready to reflect")
    return n
