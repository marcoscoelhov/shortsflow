from __future__ import annotations

from typing import Any

from app.domain_contracts import JOB_STATUS_READY_FOR_UPLOAD


def as_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


def evaluate_autoapproval_score(
    *,
    job_status: str,
    job_origin: str | None,
    monetization_report: dict[str, Any],
    quality_summary: dict[str, Any],
    qa_metrics: dict[str, Any],
    score_threshold: float,
    ready_script_origin: str,
    automatic_topic_origin: str,
) -> dict[str, Any]:
    repetition_report = monetization_report.get("channel_repetition_report") or {}
    manual_confirmations = {str(item) for item in monetization_report.get("manual_confirmations") or []}
    metadata_review = monetization_report.get("metadata_review") or {}
    publish_readiness = monetization_report.get("publish_readiness") or {}
    audit = publish_readiness.get("minimax_audit") or {}
    asset_summary = dict(quality_summary.get("assets") or {})
    ready_script_bank_job = job_origin == ready_script_origin
    automatic_topic_job = job_origin == automatic_topic_origin

    reasons: list[str] = []
    if job_status != JOB_STATUS_READY_FOR_UPLOAD:
        reasons.append("job_not_ready_for_upload")
    if not monetization_report.get("passed"):
        reasons.append("monetization_not_passed")
    repetition_risk = str(repetition_report.get("repetition_risk") or "unknown")
    originality_confirmed = "originality_confirmed" in manual_confirmations

    factual_score = 1.0
    retention_score = as_score(audit.get("retention_score"))
    if retention_score is None:
        candidates = [as_score(qa_metrics.get("hook_score")), as_score(qa_metrics.get("information_density_score"))]
        values = [value for value in candidates if value is not None]
        retention_score = sum(values) / len(values) if values else 0.85
    metadata_score = as_score(audit.get("metadata_score"))
    if metadata_score is None:
        metadata_score = 1.0 if not metadata_review.get("requires_metadata_review") else 0.7
    asset_score = as_score(asset_summary.get("asset_semantic_score_avg"))
    asset_score_missing = asset_score is None
    if asset_score_missing:
        asset_score = 0.0

    if retention_score < 0.75:
        reasons.append("retention_score_below_threshold")
    if metadata_score < 0.75:
        reasons.append("metadata_score_below_threshold")
    if asset_score < 0.80:
        reasons.append("asset_semantic_score_below_threshold")
    if asset_score_missing:
        reasons.append("asset_semantic_score_missing")

    component_scores = [factual_score, retention_score, metadata_score, asset_score]
    composite = sum(component_scores) / len(component_scores)
    score = max(0.0, round(composite, 3))
    if score < score_threshold:
        reasons.append("automation_score_below_threshold")
    diagnostic_reasons: list[str] = []
    if ready_script_bank_job:
        editorial_diagnostic_reasons = {
            "high_narrative_similarity",
            "retention_score_below_threshold",
            "metadata_score_below_threshold",
            "automation_score_below_threshold",
        }
        diagnostic_reasons = [reason for reason in reasons if reason in editorial_diagnostic_reasons]
        reasons = [reason for reason in reasons if reason not in editorial_diagnostic_reasons]
    return {
        "eligible": not reasons,
        "score": score,
        "threshold": score_threshold,
        "reasons": list(dict.fromkeys(reasons)),
        "diagnostic_reasons": list(dict.fromkeys(diagnostic_reasons)),
        "ready_script_bank_policy": (
            "score_diagnostic_only"
            if ready_script_bank_job
            else "score_blocks_automatic_publication"
        ),
        "components": {
            "factual_score": round(factual_score, 3),
            "retention_score": round(retention_score, 3),
            "metadata_score": round(metadata_score, 3),
            "asset_semantic_score": round(asset_score, 3),
            "repetition_risk": repetition_risk,
            "repetition_penalty": 0.0,
            "originality_confirmed": originality_confirmed,
        },
    }
