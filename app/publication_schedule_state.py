from __future__ import annotations

from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

from app.models import PublicationSchedule
from app.utils import stable_hash


def publication_schedule_payload(schedule: PublicationSchedule, *, schema_version: str) -> dict[str, Any]:
    scheduled_for_utc = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
    published_at = schedule.published_at if schedule.published_at and schedule.published_at.tzinfo else (
        schedule.published_at.replace(tzinfo=UTC) if schedule.published_at else None
    )
    local_dt = scheduled_for_utc.astimezone(ZoneInfo(schedule.timezone))
    return {
        "schema_version": schema_version,
        "job_id": schedule.job_id,
        "schedule_id": schedule.schedule_id,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
        "status": schedule.status,
        "scheduled_for_utc": scheduled_for_utc.isoformat(),
        "scheduled_for_local": local_dt.isoformat(),
        "local_date": local_dt.date().isoformat(),
        "local_time": local_dt.strftime("%H:%M"),
        "timezone": schedule.timezone,
        "youtube_visibility": schedule.youtube_visibility,
        "notes": schedule.notes,
        "published_at": published_at.isoformat() if published_at else None,
        "youtube_video_id": schedule.youtube_video_id,
        "youtube_url": schedule.youtube_url,
    }


def update_publication_schedule_content_hash(schedule: PublicationSchedule, *, include_publish_result: bool = False) -> None:
    payload: dict[str, Any] = {
        "job_id": schedule.job_id,
        "scheduled_for_utc": schedule.scheduled_for_utc.isoformat(),
        "timezone": schedule.timezone,
        "youtube_visibility": schedule.youtube_visibility,
        "status": schedule.status,
        "notes": schedule.notes,
    }
    if include_publish_result:
        payload.update(
            {
                "published_at": schedule.published_at.isoformat() if schedule.published_at else None,
                "youtube_video_id": schedule.youtube_video_id,
                "youtube_url": schedule.youtube_url,
            }
        )
    schedule.content_hash = stable_hash(payload)
