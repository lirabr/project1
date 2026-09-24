# Desk policy v1

Status: approved
Updated: 2026-09-22

## Evidence
- Prefer Phase 1 registered scores over a fresh LLM opinion.
- Retrieve at least 3 analogous episodes when they exist.
- Cite memory ids in the thesis when a lesson is used.

## Sizing
- Long/flat only.
- Scale notional with (score - min_score) and with model trust.
- If bear trust > model trust + 0.3, cut suggested size in half.
- Never raise a cap that the risk gate owns.

## Regime
- Stand aside on `risk_off` unless score >= 0.70 and model trust >= 1.1.
- In `trend_up_volatile`, default urgency is low.
- Crypto shocks (heartbeat) do not by themselves create equity longs.

## Change control
- Policy edits are proposed, not applied.
- A human must run `desk-research policy-approve`.
- Live trading is out of scope for this policy version.
