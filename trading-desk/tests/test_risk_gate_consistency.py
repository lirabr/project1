from __future__ import annotations

from desk.contracts import TradeProposal
from desk.risk_gate import evaluate

CFG = {
    "allow_live": False,
    "max_notional_per_name_usd": 500,
    "max_gross_exposure_usd": 10000,
    "max_daily_loss_usd": 250,
    "max_orders_per_cycle": 4,
    "max_crypto_weight": 0.3,
    "min_score": 0.55,
    "allowed_sides": ["long", "flat"],
    "kill_switch_path": "data/artifacts/NO_HALT_XYZ",
}


def _prop(**kw) -> TradeProposal:
    base = {
        "symbol": "AAPL", "side": "long", "urgency": "low", "thesis": "t", "invalidation": "x",
        "horizon_days": 5, "score": 0.7, "suggested_notional_usd": 1000,
    }
    base.update(kw)
    return TradeProposal(**base)  # type: ignore[arg-type]


def _call(prop, **kw):
    args = {
        "book_gross_usd": 0, "book_name_usd": 0, "day_pnl_usd": 0, "orders_this_cycle": 0,
        "crypto_weight": 0, "is_crypto": False, "live": False, "cfg": CFG,
    }
    args.update(kw)
    return evaluate(prop, **args)


def test_flat_is_never_allowed_and_reason_is_consistent():
    d = _call(_prop(side="flat", score=0.0, suggested_notional_usd=0.0))
    assert d.allow is False
    assert d.reason == "flat / no order"
    assert d.clipped_notional_usd == 0.0


def test_allow_never_has_reject_reason():
    d = _call(_prop(suggested_notional_usd=1000))
    assert d.allow is True
    assert d.reason == "passed"
    assert d.clipped_notional_usd == 500  # clipped to name cap


def test_oversize_is_clipped_not_rejected():
    d = _call(_prop(suggested_notional_usd=999999))
    assert d.allow is True
    assert d.clipped_notional_usd == 500


def test_no_size_room_rejects():
    d = _call(_prop(), book_name_usd=500)  # name cap fully used
    assert d.allow is False
    assert d.reason == "no remaining size room"


def test_crypto_cap_blocks_when_over_weight():
    d = _call(_prop(symbol="BTC-USD"), is_crypto=True, crypto_weight=0.9)
    assert d.allow is False
    assert d.reason == "crypto weight cap"


def test_low_score_rejects_before_size():
    d = _call(_prop(score=0.10))
    assert d.allow is False
    assert d.reason.startswith("score")
