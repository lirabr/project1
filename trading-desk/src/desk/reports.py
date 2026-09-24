from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from desk.io_utils import ARTIFACT_DIR, load_yaml
from desk.models import available_strategies


def render_report(strategies: list[str], output: Path) -> Path:
    sections = []
    for strategy in strategies:
        if strategy not in available_strategies():
            raise ValueError("Unknown strategy")
        directory = ARTIFACT_DIR / strategy
        sheet = directory / "tearsheet.yaml"
        if not sheet.exists():
            continue
        metrics = load_yaml(sheet)
        sections.append(f"<h2>{html.escape(strategy)}</h2>")
        sections.append(pd.DataFrame([metrics]).to_html(index=False, escape=True))
        manifest = directory / "manifest.json"
        if manifest.exists():
            sections.append("<h3>Provenance</h3><pre>" + html.escape(json.dumps(json.loads(manifest.read_text()), indent=2)) + "</pre>")
        returns = directory / "returns.parquet"
        if returns.exists():
            sections.append("<h3>Latest 30 research intervals</h3>" + pd.read_parquet(returns).tail(30).to_html(escape=True))
    if not sections:
        raise ValueError("No research results; run a backtest first")
    text = ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Trading Desk Research</title>"
            "<body><h1>Trading Desk — Research Evidence</h1>"
            "<p>Read-only historical research. No broker connection or trading controls. "
            "Results are not certification of profitability or execution readiness. "
            "n_trades and hit_rate describe intervals, not completed trades. "
            "total_cost_return is summed cost drag, not dollar fees. "
            "Double-cost results hold signals fixed; they are sensitivity tests, not forecasts.</p>"
            + "\n".join(sections) + "</body></html>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    return output


def paper_statistics(conn) -> dict:
    counts = {f"{r['side']}_{r['status']}": r["n"] for r in conn.execute(
        "SELECT side,status,COUNT(*) AS n FROM desk_orders GROUP BY side,status")}
    values = conn.execute("SELECT COUNT(*) AS fills,COALESCE(SUM(fee),0) AS fees,COALESCE(SUM(realized),0) AS realized_pnl FROM desk_fills").fetchone()
    return {"orders": counts, **dict(values), "execution": "internal_simulator"}
