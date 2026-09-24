from __future__ import annotations

from datetime import UTC, datetime

from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR, load_yaml, write_yaml

TRUST_PATH = ARTIFACT_DIR / "trust.yaml"


def _bounds(cfg: dict) -> tuple[float, float, dict]:
    t = (cfg or {}).get("trust") or {}
    start = {"model": 1.0, "bull": 1.0, "bear": 1.0}
    start.update(t.get("start") or {})
    return float(t.get("min", 0.35)), float(t.get("max", 1.8)), start


def load_trust(phase3: dict | None = None) -> dict[str, float]:
    _, _, start = _bounds(phase3 or _phase3())
    if TRUST_PATH.exists():
        data = load_yaml(TRUST_PATH)
        weights = data.get("weights") or start
        return {k: float(weights.get(k, start[k])) for k in start}
    return dict(start)


def save_trust(weights: dict[str, float], note: str = "") -> None:
    write_yaml(
        TRUST_PATH,
        {"updated": datetime.now(UTC).isoformat(), "note": note, "weights": weights},
    )


def _phase3() -> dict:
    path = CONFIG_DIR / "phase3.yaml"
    return load_yaml(path) if path.exists() else {}


def update_from_outcome(outcome: str, score: float, phase3: dict | None = None) -> dict[str, float]:
    cfg = phase3 or _phase3()
    lo, hi, _ = _bounds(cfg)
    step_win = float((cfg.get("trust") or {}).get("step_win", 0.05))
    step_loss = float((cfg.get("trust") or {}).get("step_loss", 0.08))
    w = load_trust(cfg)
    if outcome == "win":
        w["model"] += step_win
        w["bull"] += step_win if score >= 0.6 else 0.0
        w["bear"] -= step_win / 2
    elif outcome == "loss":
        w["model"] -= step_loss
        w["bull"] -= step_loss
        w["bear"] += step_loss
    elif outcome == "scratch":
        w["model"] -= step_win / 2
    for k in w:
        w[k] = min(hi, max(lo, w[k]))
    save_trust(w, note=f"outcome={outcome} score={score:.2f}")
    return w


def apply_trust(score: float, notional: float, weights: dict[str, float], regime: str, policy_stand_aside: bool) -> tuple[float, float, str]:
    """Returns (adjusted_score, adjusted_notional, note)."""
    model = weights.get("model", 1.0)
    bull = weights.get("bull", 1.0)
    bear = weights.get("bear", 1.0)
    adj = score
    note = f"trust model={model:.2f} bull={bull:.2f} bear={bear:.2f}"
    size = notional * max(0.0, min(1.0, model))
    if bear > model + 0.3:
        size *= 0.5
        note += " bear-dominant → half size"
    if policy_stand_aside:
        adj = min(adj, 0.49)
        size = 0.0
        note += f" stand-aside regime={regime}"
    return float(adj), float(size), note
