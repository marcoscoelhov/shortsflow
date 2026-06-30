from __future__ import annotations

from app.policies.publication_policy import classify_recovery_gate


def test_recovery_gate_sends_factual_risk_to_checkpoint() -> None:
    decision = classify_recovery_gate("unsupported_claim in publish readiness", duplicate_risk=False)

    assert decision.classification == "continue"
    assert decision.reasons == []
    assert decision.risk == "low"


def test_recovery_gate_sends_duplicate_risk_to_checkpoint() -> None:
    decision = classify_recovery_gate("", duplicate_risk=True)

    assert decision.classification == "needs_checkpoint"
    assert decision.reasons == ["duplicate_or_already_published_risk"]
    assert decision.risk == "medium"


def test_recovery_gate_detects_correctable_marker() -> None:
    decision = classify_recovery_gate("metadata gate needs repair", duplicate_risk=False)

    assert decision.classification == "correctable"
    assert decision.reasons == ["correctable_gate_or_score_blocker"]
    assert decision.risk == "medium"


def test_recovery_gate_allows_normal_flow_when_no_policy_marker() -> None:
    decision = classify_recovery_gate("word_count_too_low_for_natural_pace", duplicate_risk=False)

    assert decision.classification == "continue"
    assert decision.reasons == []
    assert decision.risk == "low"
