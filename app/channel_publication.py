from __future__ import annotations

from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

from app.utils import stable_hash


def channel_publication_payload(publication: Any, *, schema_version: str) -> dict[str, Any]:
    scheduled_for_utc = publication.scheduled_for_utc if publication.scheduled_for_utc.tzinfo else publication.scheduled_for_utc.replace(tzinfo=UTC)
    published_at = publication.published_at if publication.published_at and publication.published_at.tzinfo else (
        publication.published_at.replace(tzinfo=UTC) if publication.published_at else None
    )
    local_dt = scheduled_for_utc.astimezone(ZoneInfo(publication.timezone))
    return {
        "schema_version": schema_version,
        "publication_id": publication.publication_id,
        "job_id": publication.job_id,
        "channel": publication.channel,
        "status": publication.status,
        "source": publication.source,
        "scheduled_for_utc": scheduled_for_utc.isoformat(),
        "scheduled_for_local": local_dt.isoformat(),
        "local_date": local_dt.date().isoformat(),
        "local_time": local_dt.strftime("%H:%M"),
        "timezone": publication.timezone,
        "privacy_level": publication.privacy_level,
        "external_id": publication.external_id,
        "external_url": publication.external_url,
        "published_at": published_at.isoformat() if published_at else None,
        "attempt_count": publication.attempt_count,
        "last_attempt_at": publication.last_attempt_at.isoformat() if publication.last_attempt_at else None,
        "last_error": publication.last_error,
        "channel_metadata": publication.channel_metadata or {},
    }


def refresh_channel_publication_hash(publication: Any) -> None:
    publication.content_hash = stable_hash(
        {
            "job_id": publication.job_id,
            "channel": publication.channel,
            "status": publication.status,
            "source": publication.source,
            "scheduled_for_utc": publication.scheduled_for_utc.isoformat(),
            "timezone": publication.timezone,
            "privacy_level": publication.privacy_level,
            "external_id": publication.external_id,
            "external_url": publication.external_url,
            "published_at": publication.published_at.isoformat() if publication.published_at else None,
            "attempt_count": publication.attempt_count,
            "last_error": publication.last_error,
        }
    )


def tiktok_caption(package: dict[str, Any]) -> str:
    title = str(package.get("title") or "").strip()
    hashtags = [str(tag).strip() for tag in list(package.get("hashtags") or []) if str(tag).strip()]
    suffix = " ".join(tag if tag.startswith("#") else f"#{tag}" for tag in hashtags[:8])
    caption = " ".join(part for part in [title, suffix] if part)
    return caption[:2200]
