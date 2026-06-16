from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.utils import utcnow


RETENTION_HARD_FAILURE_STATUSES = {
    "failed",
    "script_quality_failed",
    "visual_contract_quality_failed",
    "scene_plan_quality_failed",
    "asset_quality_failed",
    "subtitle_quality_failed",
    "render_quality_failed",
}
RETENTION_RECOVERABLE_STATUSES = {
    "monetization_review",
    "blocked_for_monetization",
    "rejected",
}
RETENTION_EXCLUDED_JOB_STATUSES = {
    "queued",
    "running",
    "published",
    "cancelled",
}
RETENTION_EXCLUDED_SCHEDULE_STATUSES = {
    "publishing",
    "published",
}


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def retention_classification(job: Any, schedule: Any | None) -> str | None:
    schedule_status = str(schedule.status or "") if schedule else ""
    if job.status in RETENTION_EXCLUDED_JOB_STATUSES or schedule_status in RETENTION_EXCLUDED_SCHEDULE_STATUSES:
        return None
    if schedule_status == "scheduled":
        return "publishable"
    if schedule_status == "publish_failed":
        return "recoverable"
    if job.status in {"ready_for_upload", "approved_for_publish"}:
        return "publishable"
    if job.status in RETENTION_HARD_FAILURE_STATUSES:
        return "hard_failure"
    if job.status in RETENTION_RECOVERABLE_STATUSES:
        return "recoverable"
    return None


def retention_base_timestamp(job: Any, schedule: Any | None) -> datetime:
    timestamps = [as_utc(job.updated_at) or as_utc(job.created_at) or utcnow()]
    if schedule and schedule.updated_at:
        timestamps.append(as_utc(schedule.updated_at) or utcnow())
    return max(timestamps)


def retention_ttl(settings: Any, classification: str) -> timedelta:
    if classification == "hard_failure":
        return timedelta(hours=settings.artifact_ttl_hard_failure_hours)
    if classification == "recoverable":
        return timedelta(hours=settings.artifact_ttl_recoverable_hours)
    return timedelta(hours=settings.artifact_ttl_publishable_hours)


def retention_metadata(
    settings: Any,
    job: Any,
    schedule: Any | None,
    *,
    now: datetime,
    cleaned: bool = False,
    cleaned_at: str | None = None,
    cleanup_reason: str | None = None,
) -> dict[str, Any] | None:
    classification = retention_classification(job, schedule)
    if not classification:
        return None
    base_timestamp = retention_base_timestamp(job, schedule)
    expires_at = base_timestamp + retention_ttl(settings, classification)
    return {
        "classification": classification,
        "base_timestamp": base_timestamp.isoformat(),
        "expires_at": expires_at.isoformat(),
        "last_evaluated_at": now.isoformat(),
        "cleaned": cleaned,
        "cleaned_at": cleaned_at,
        "cleanup_reason": cleanup_reason,
    }


def set_retention_metadata(job: Any, metadata: dict[str, Any] | None) -> None:
    quality_summary = dict(job.quality_summary or {})
    if metadata is None:
        quality_summary.pop("retention", None)
    else:
        quality_summary["retention"] = metadata
    job.quality_summary = quality_summary


def retention_sweep_statuses() -> tuple[str, ...]:
    return tuple(
        RETENTION_HARD_FAILURE_STATUSES
        | RETENTION_RECOVERABLE_STATUSES
        | {"ready_for_upload", "approved_for_publish"}
    )
