from __future__ import annotations

from dataclasses import dataclass

from app.domain_contracts import (
    REASON_ASSET_VISUAL_REVIEW_REQUIRED,
    REASON_INVENTED_SOURCE_FACT_IDS,
    REASON_UNSUPPORTED_CLAIM,
    REASON_VISUAL_REVIEW_REQUIRED,
)

FACTUAL_OR_RIGHTS_MARKERS = {
    REASON_UNSUPPORTED_CLAIM,
    REASON_INVENTED_SOURCE_FACT_IDS,
    "rights",
    "copyright",
    "youtube_policy",
    "policy_risk",
    "factual",
}

CORRECTABLE_MARKERS = {
    REASON_VISUAL_REVIEW_REQUIRED,
    REASON_ASSET_VISUAL_REVIEW_REQUIRED,
    "metadata",
    "text publish audit missing",
    "image_semantics_score_below_threshold",
    "topic quality metrics incomplete",
    "duration",
    "render failed",
    "asset",
    "tts",
    "subtitle",
    "monetization_readiness_gate",
    "premium_publish_score_below_threshold",
}


@dataclass(frozen=True)
class RecoveryGateDecision:
    classification: str
    reasons: list[str]
    risk: str


def classify_recovery_gate(evidence_text: str, *, duplicate_risk: bool) -> RecoveryGateDecision:
    normalized = str(evidence_text or "").lower()
    if duplicate_risk:
        return RecoveryGateDecision("needs_checkpoint", ["duplicate_or_already_published_risk"], "medium")
    if any(marker in normalized for marker in FACTUAL_OR_RIGHTS_MARKERS):
        return RecoveryGateDecision("needs_checkpoint", ["factual_or_rights_risk"], "high")
    if any(marker in normalized for marker in CORRECTABLE_MARKERS):
        return RecoveryGateDecision("correctable", ["correctable_gate_or_score_blocker"], "medium")
    return RecoveryGateDecision("continue", [], "low")
