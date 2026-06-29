from __future__ import annotations

from typing import Any

from app.domain_contracts import (
    JOB_STATUS_APPROVED_FOR_PUBLISH,
    JOB_STATUS_BLOCKED_FOR_MONETIZATION,
    JOB_STATUS_MONETIZATION_REVIEW,
    JOB_STATUS_READY_FOR_UPLOAD,
    JOB_STATUS_SCENE_PLAN_QUALITY_FAILED,
    JOB_STATUS_SCRIPT_QUALITY_FAILED,
    JOB_STATUS_SUBTITLE_QUALITY_FAILED,
    SCENE_PLAN_REPAIR_REASONS,
    SUBTITLE_REPAIR_REASONS,
    TEXTUAL_REPAIR_REASONS,
    VISUAL_REVIEW_REQUIREMENTS,
)


def visual_review_can_be_attempted(report: dict[str, Any]) -> bool:
    manual_required = {str(item) for item in report.get("manual_required") or []}
    return not report.get("hard_blockers") and bool(manual_required & VISUAL_REVIEW_REQUIREMENTS)


def only_safe_visual_review_remains(report: dict[str, Any]) -> bool:
    manual_required = {str(item) for item in report.get("manual_required") or []}
    return visual_review_can_be_attempted(report) and manual_required.issubset(VISUAL_REVIEW_REQUIREMENTS)


def classify_failure(status: str, failure_reason: str | None, monetization_report: dict[str, Any]) -> dict[str, Any]:
    evidence = " ".join(
        [
            str(failure_reason or ""),
            " ".join(str(item) for item in monetization_report.get("hard_blockers") or []),
            " ".join(str(item) for item in monetization_report.get("manual_required") or []),
            " ".join(str(item) for item in (monetization_report.get("publish_readiness") or {}).get("reasons") or []),
        ]
    ).lower()
    matched_reasons: list[str] = []
    for reason in sorted(TEXTUAL_REPAIR_REASONS | SCENE_PLAN_REPAIR_REASONS | SUBTITLE_REPAIR_REASONS):
        if reason in evidence:
            matched_reasons.append(reason)

    hard_blockers = [str(item) for item in monetization_report.get("hard_blockers") or []]
    if hard_blockers and any(reason in TEXTUAL_REPAIR_REASONS for reason in matched_reasons):
        return {
            "classification": "textual_repairable",
            "matched_reasons": matched_reasons,
            "retry_from_step": "script",
        }
    if status == JOB_STATUS_BLOCKED_FOR_MONETIZATION or hard_blockers:
        return {
            "classification": "hard_blocker",
            "matched_reasons": matched_reasons or hard_blockers,
            "retry_from_step": None,
        }
    if status == JOB_STATUS_MONETIZATION_REVIEW and visual_review_can_be_attempted(monetization_report):
        manual_required = {str(item) for item in monetization_report.get("manual_required") or []}
        return {
            "classification": "visual_review_repairable"
            if manual_required.issubset(VISUAL_REVIEW_REQUIREMENTS)
            else "visual_review_partial_repairable",
            "matched_reasons": list(monetization_report.get("manual_required") or []),
            "retry_from_step": None,
        }
    if status == JOB_STATUS_SCRIPT_QUALITY_FAILED and any(reason in TEXTUAL_REPAIR_REASONS for reason in matched_reasons):
        return {
            "classification": "textual_repairable",
            "matched_reasons": matched_reasons,
            "retry_from_step": "script",
        }
    if status == JOB_STATUS_SCENE_PLAN_QUALITY_FAILED and any(reason in SCENE_PLAN_REPAIR_REASONS for reason in matched_reasons):
        return {
            "classification": "scene_plan_repairable",
            "matched_reasons": matched_reasons,
            "retry_from_step": "scene_plan",
        }
    if status == JOB_STATUS_SUBTITLE_QUALITY_FAILED and any(reason in SUBTITLE_REPAIR_REASONS for reason in matched_reasons):
        return {
            "classification": "subtitle_repairable",
            "matched_reasons": matched_reasons,
            "retry_from_step": "subtitle_alignment",
        }
    if status in {JOB_STATUS_READY_FOR_UPLOAD, JOB_STATUS_APPROVED_FOR_PUBLISH}:
        return {"classification": "publishable", "matched_reasons": [], "retry_from_step": None}
    return {"classification": "unclassified_failure", "matched_reasons": matched_reasons, "retry_from_step": None}
