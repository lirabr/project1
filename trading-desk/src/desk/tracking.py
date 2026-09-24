from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from desk.io_utils import ARTIFACT_DIR, load_yaml, write_yaml

RUNS_PATH = ARTIFACT_DIR / "runs.yaml"
REGISTRY_PATH = ARTIFACT_DIR / "registry.yaml"


def _try_mlflow(strategy: str, params: dict[str, Any], metrics: dict[str, Any]) -> None:
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_tracking_uri(str(ARTIFACT_DIR / "mlruns"))
    mlflow.set_experiment("trading-desk-phase1")
    with mlflow.start_run(run_name=strategy):
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in metrics.items():
            if isinstance(v, (int, float)) and math.isfinite(v):
                mlflow.log_metric(k, float(v))


def log_run(strategy: str, params: dict[str, Any], metrics: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"runs": []}
    if RUNS_PATH.exists():
        payload = load_yaml(RUNS_PATH)
        payload.setdefault("runs", [])
    payload["runs"].append(
        {
            "ts": datetime.now(UTC).isoformat(),
            "strategy": strategy,
            "params": params,
            "metrics": {k: metrics[k] for k in ("cagr", "sharpe", "max_drawdown", "total_return", "excess_return", "n_folds") if k in metrics},
        }
    )
    write_yaml(RUNS_PATH, payload)
    _try_mlflow(strategy, params, metrics)


def promote(strategy: str, stage: str = "candidate") -> None:
    allowed = {"dev", "candidate", "paper", "retired"}
    if stage not in allowed:
        raise ValueError(f"stage must be one of {allowed}")
    sheet = ARTIFACT_DIR / strategy / "tearsheet.yaml"
    if not sheet.exists():
        raise FileNotFoundError(f"No tear sheet for {strategy}. Run backtest first.")
    metrics = load_yaml(sheet)
    registry = {"models": {}}
    if REGISTRY_PATH.exists():
        registry = load_yaml(REGISTRY_PATH)
        registry.setdefault("models", {})
    registry["models"][strategy] = {
        "stage": stage,
        "promoted_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "path": str(sheet),
    }
    write_yaml(REGISTRY_PATH, registry)
    print(f"promoted {strategy} → {stage}")
