from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifact_retention import retention_metadata, retention_sweep_statuses, set_retention_metadata
from app.db import session_scope
from app.models import Job, PublicationSchedule
from app.utils import iso_now, utcnow


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class RetentionOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def storage(self) -> Any:
        return self.owner.storage

    def cleanup_snapshot(
        self,
        job: Job,
        schedule: PublicationSchedule | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        snapshots = {
            "monetization_report": self.owner._read_job_json(job.job_id, "monetization_report.json"),
            "publish_package": self.owner._read_job_json(job.job_id, "publish_package.json"),
            "publish_result": self.owner._read_job_json(job.job_id, "publish_result.json"),
            "publication_attempts": self.owner._read_job_json(job.job_id, "youtube_publish_attempts.json").get("attempts", []),
        }
        if schedule:
            snapshots["publication_schedule"] = self.owner._publication_schedule_payload(schedule)
        return {
            "schema_version": self.settings.schema_version,
            "job_id": job.job_id,
            "cleaned_at": metadata.get("cleaned_at"),
            "classification": metadata.get("classification"),
            "expires_at": metadata.get("expires_at"),
            "cleanup_reason": metadata.get("cleanup_reason"),
            "snapshots": snapshots,
        }

    def cleanup_expired_job_artifacts(self, job_id: str) -> bool:
        if not self.settings.artifact_retention_enabled:
            return False
        now = utcnow()
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                return False
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            current_retention = dict((job.quality_summary or {}).get("retention") or {})
            if current_retention.get("cleaned"):
                return False
            metadata = current_retention or retention_metadata(self.settings, job, schedule, now=now)
            set_retention_metadata(job, metadata)
            if not metadata:
                return False
            expires_at = _as_utc(datetime.fromisoformat(str(metadata["expires_at"]))) or now
            if expires_at > now:
                return False
            cleaned_at = iso_now()
            metadata = {
                **metadata,
                "cleaned": True,
                "cleaned_at": cleaned_at,
                "cleanup_reason": "ttl_expired",
                "last_evaluated_at": cleaned_at,
            }
            snapshot = self.cleanup_snapshot(job, schedule, metadata)
            self.storage.remove_job_artifacts(job_id)
            self.storage.persist_json(job_id, "retention_cleanup.json", self.owner._serialize_for_json(snapshot))
            set_retention_metadata(job, metadata)
            job.artifact_index = {"retention_cleanup": "retention_cleanup.json"}
        self.owner._append_event(job_id, "job.artifacts.cleaned", "succeeded", {"reason": "ttl_expired"})
        return True

    def refresh_state(self, session: Session, job: Job, schedule: PublicationSchedule | None = None) -> None:
        if not self.settings.artifact_retention_enabled:
            return
        schedule = schedule if schedule is not None else session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job.job_id))
        current_retention = dict((job.quality_summary or {}).get("retention") or {})
        metadata = retention_metadata(self.settings, job, schedule, now=utcnow())
        if current_retention.get("cleaned"):
            set_retention_metadata(
                job,
                {
                    **current_retention,
                    "last_evaluated_at": iso_now(),
                },
            )
            return
        set_retention_metadata(job, metadata)

    def run_sweep(self) -> int:
        if not self.settings.artifact_retention_enabled:
            return 0
        with session_scope() as session:
            rows = set(
                session.execute(
                    select(Job.job_id).where(
                        Job.status.in_(retention_sweep_statuses())
                    )
                ).scalars().all()
            )
            rows.update(
                session.execute(
                    select(PublicationSchedule.job_id).where(PublicationSchedule.status.in_(("scheduled", "publish_failed")))
                ).scalars().all()
            )
            for job_id in rows:
                job = session.get(Job, job_id)
                if job:
                    self.refresh_state(session, job)
        cleaned = 0
        for job_id in rows:
            if self.cleanup_expired_job_artifacts(job_id):
                cleaned += 1
        self.owner._last_retention_sweep_at = time.monotonic()
        return cleaned
