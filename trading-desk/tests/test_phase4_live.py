from __future__ import annotations

from desk.audit import append_audit
from desk.contracts import RiskDecision, TradeProposal
from desk.live import live_size_ok, preflight, route_live_intent


def _prop() -> TradeProposal:
    return TradeProposal(
        symbol="AAPL",
        side="long",
        urgency="low",
        thesis="tiny live test",
        invalidation="x",
        horizon_days=5,
        score=0.7,
        suggested_notional_usd=1000,
    )


def test_preflight_blocks_by_default():
    blockers = preflight(
        {"enabled": False, "confirm_phrase": "X", "withdraw_disabled_attested": False, "max_live_notional_usd": 250},
        {"allow_live": False, "require_human_approve": True},
    )
    assert any("enabled=false" in b for b in blockers)
    assert any("allow_live=false" in b for b in blockers)


def test_crypto_blocked_when_equities_only():
    ok, _reason, clipped = live_size_ok(_prop(), {"max_live_notional_usd": 250, "equities_only": True}, is_crypto=True)
    assert ok is False
    assert clipped == 0


def test_live_clips_to_tiny_cap():
    ok, _, clipped = live_size_ok(_prop(), {"max_live_notional_usd": 250, "equities_only": True}, is_crypto=False)
    assert ok is True
    assert clipped == 250


def test_route_never_calls_broker(tmp_path, monkeypatch):
    from desk import live as live_mod

    monkeypatch.setattr(live_mod, "load_live_cfg", lambda path=None: {
        "enabled": True,
        "confirm_phrase": "I_UNDERSTAND_TINY_LIVE",
        "withdraw_disabled_attested": True,
        "max_live_notional_usd": 250,
        "equities_only": True,
        "audit_copy_path": str(tmp_path / "copy.jsonl"),
    })
    monkeypatch.setenv("DESK_LIVE_CONFIRM", "I_UNDERSTAND_TINY_LIVE")
    # still blocked because risk allow_live comes from real file unless we patch preflight
    event = route_live_intent(
        _prop(),
        RiskDecision(allow=True, reason="passed", clipped_notional_usd=250, gates={}),
        is_crypto=False,
        submit=True,
    )
    assert event["broker_called"] is False
    assert event["status"] in {"blocked_or_dry", "authorized_but_not_sent"}


def test_audit_writes_hash(tmp_path):
    p = append_audit({"kind": "test"}, path=tmp_path / "a.jsonl", copy_path=tmp_path / "b.jsonl")
    text = p.read_text()
    assert "sha256" in text
    assert (tmp_path / "b.jsonl").exists()
