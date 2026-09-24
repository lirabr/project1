from __future__ import annotations

from desk.features import read_panel
from desk.io_utils import CONFIG_DIR, load_yaml
from desk.regime import classify_row


def _is_crypto(symbol: str) -> bool:
    return symbol.endswith("-USD") or "/" in symbol


def pulse(phase3: dict | None = None) -> dict:
    cfg = phase3 or load_yaml(CONFIG_DIR / "phase3.yaml")
    hb = cfg.get("heartbeat") or {}
    symbols = list(hb.get("symbols") or ["BTC-USD", "ETH-USD"])
    shock = float(hb.get("shock_sigma", 2.0))
    vol_z_cut = float(hb.get("volume_z", 2.5))
    panel = read_panel()
    events = []
    fire = False
    for symbol in symbols:
        sub = panel[panel["symbol"] == symbol].copy()
        if sub.empty:
            events.append({"symbol": symbol, "status": "no_data"})
            continue
        if "date" in sub.columns:
            sub = sub.sort_values("date")
        row = sub.iloc[-1]
        ret = float(row.get("ret_1") or 0.0)
        vol = float(row.get("vol_20") or 1e-6)
        vz = float(row.get("volume_z_20") or 0.0)
        sigma = abs(ret) / max(vol, 1e-6)
        regime = classify_row(row, cfg)
        shocked = sigma >= shock or abs(vz) >= vol_z_cut
        fire = fire or shocked
        events.append(
            {
                "symbol": symbol,
                "status": "shock" if shocked else "quiet",
                "ret_1": ret,
                "vol_20": vol,
                "sigma": sigma,
                "volume_z": vz,
                "regime": regime,
                "close": float(row.get("Close") or 0),
            }
        )
    out = {"fire_full_cycle": fire, "events": events}
    print(f"heartbeat fire_full_cycle={fire}")
    for e in events:
        if e.get("status") == "no_data":
            print(f"  {e['symbol']:8} no_data")
            continue
        print(
            f"  {e['symbol']:8} {e['status']:6}  ret1={e['ret_1']:+.2%}  "
            f"{e['sigma']:.2f}σ  vz={e['volume_z']:+.2f}  {e['regime']}"
        )
    if not fire:
        print("council skipped — heartbeat only. run `desk-research cycle` anyway if you want a scheduled pass.")
    return out
