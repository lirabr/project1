from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from desk.io_utils import ARTIFACT_DIR, CONFIG_DIR

POLICY_PATH = CONFIG_DIR / "policy.md"
PENDING_PATH = ARTIFACT_DIR / "policy_pending.md"
HISTORY_DIR = ARTIFACT_DIR / "policy_history"


def read_policy() -> str:
    return POLICY_PATH.read_text() if POLICY_PATH.exists() else ""


def stand_aside(regime: str, score: float, model_trust: float) -> bool:
    text = read_policy().lower()
    if ("stand aside on `risk_off`" in text or "stand aside on risk_off" in text) and "risk_off" in regime:
        return not (score >= 0.70 and model_trust >= 1.1)
    return False


def propose(note: str) -> Path:
    current = read_policy()
    stamp = datetime.now(UTC).isoformat()
    proposed = current.rstrip() + f"\n\n## Changelog\n- {stamp}: {note}\n"
    pending = (
        f"# Desk policy PENDING\n\nProposed: {stamp}\n"
        f"Reason: {note}\n\nEdit the proposed section if you want, then run policy-approve.\n\n"
        f"--- current ---\n{current}\n"
        "--- proposed change (edit this file, then policy-approve) ---\n"
        f"{proposed}"
    )
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(pending)
    return PENDING_PATH


def approve() -> Path:
    if not PENDING_PATH.exists():
        raise FileNotFoundError("No pending policy. Run policy-propose first.")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if POLICY_PATH.exists():
        (HISTORY_DIR / f"policy_{stamp}.md").write_text(POLICY_PATH.read_text())
    text = PENDING_PATH.read_text()
    marker = "--- proposed change (edit this file, then policy-approve) ---"
    new = text.split(marker, 1)[-1].strip() if marker in text else text
    if new.startswith("# Desk policy PENDING"):
        raise RuntimeError("Pending file still looks unedited. Change the proposed section first.")
    POLICY_PATH.write_text(new + "\n")
    PENDING_PATH.unlink()
    return POLICY_PATH
