from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.channel_publication import refresh_channel_publication_hash, tiktok_caption
from app.db import session_scope
from app.models import ChannelPublication, Job, PublicationSchedule
from app.pipelines.common import FatalStepError
from app.tiktok_api import TikTokIntegrationError
from app.utils import new_id, path_from_uri, utcnow


class TikTokPublicationOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def tiktok(self) -> Any:
        return self.owner.tiktok

    @property
    def monetization_pipeline(self) -> Any:
        return self.owner.monetization_pipeline

    def auto_publish_enabled(self) -> bool:
        return bool(self.settings.tiktok_auto_publish_enabled)

    def ensure_publication_for_schedule(
        self,
        session: Session,
        job: Job,
        schedule: PublicationSchedule,
        *,
        source: str,
        scheduled_for_utc: datetime | None = None,
    ) -> ChannelPublication | None:
        if not self.auto_publish_enabled():
            return None
        if schedule.status not in {"scheduled", "published"}:
            return None
        existing = session.scalar(
            select(ChannelPublication).where(
                ChannelPublication.job_id == job.job_id,
                ChannelPublication.channel == "tiktok",
            )
        )
        if existing:
            return existing
        target_utc = scheduled_for_utc or schedule.scheduled_for_utc
        target_utc = target_utc if target_utc.tzinfo else target_utc.replace(tzinfo=UTC)
        publication = ChannelPublication(
            publication_id=new_id(),
            job_id=job.job_id,
            channel="tiktok",
            schema_version=self.settings.schema_version,
            content_hash="",
            scheduled_for_utc=target_utc,
            timezone=schedule.timezone,
            status="scheduled",
            source=source,
            privacy_level=self.settings.tiktok_privacy_level,
        )
        refresh_channel_publication_hash(publication)
        session.add(publication)
        session.flush()
        self.owner._persist_channel_publication_artifact(job, publication)
        self.owner._append_event(
            job.job_id,
            "tiktok.publication_scheduled",
            "succeeded",
            {"publication_id": publication.publication_id, "source": source, "scheduled_for_utc": target_utc.isoformat()},
        )
        return publication

    def retropost_day_bounds(self) -> tuple[datetime, datetime]:
        local_tz = ZoneInfo(self.settings.automation_daily_timezone)
        local_today = utcnow().astimezone(local_tz).date()
        start = datetime.combine(local_today, datetime.min.time(), tzinfo=local_tz).astimezone(UTC)
        end = start + timedelta(days=1)
        return start, end

    def sync_crosspost_queue(self) -> int:
        if not self.auto_publish_enabled():
            return 0
        queued = 0
        now = utcnow()
        start, end = self.retropost_day_bounds()
        with session_scope() as session:
            scheduled_rows = session.execute(
                select(Job, PublicationSchedule)
                .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id)
                .where(PublicationSchedule.status == "scheduled")
                .where(
                    ~select(ChannelPublication.publication_id)
                    .where(ChannelPublication.job_id == Job.job_id)
                    .where(ChannelPublication.channel == "tiktok")
                    .exists()
                )
                .order_by(PublicationSchedule.scheduled_for_utc)
            ).all()
            for job, schedule in scheduled_rows:
                if self.ensure_publication_for_schedule(session, job, schedule, source="youtube_schedule"):
                    queued += 1

            retropost_limit = max(0, int(self.settings.tiktok_retropost_daily_limit))
            retroposts_today = session.scalar(
                select(func.count())
                .select_from(ChannelPublication)
                .where(ChannelPublication.channel == "tiktok")
                .where(ChannelPublication.source == "retropost")
                .where(ChannelPublication.created_at >= start)
                .where(ChannelPublication.created_at < end)
            ) or 0
            remaining = max(0, retropost_limit - int(retroposts_today))
            if remaining:
                published_rows = session.execute(
                    select(Job, PublicationSchedule)
                    .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id)
                    .where(PublicationSchedule.status == "published")
                    .where(
                        ~select(ChannelPublication.publication_id)
                        .where(ChannelPublication.job_id == Job.job_id)
                        .where(ChannelPublication.channel == "tiktok")
                        .exists()
                    )
                    .order_by(PublicationSchedule.published_at.asc(), PublicationSchedule.updated_at.asc())
                    .limit(remaining)
                ).all()
                for job, schedule in published_rows:
                    if self.ensure_publication_for_schedule(session, job, schedule, source="retropost", scheduled_for_utc=now):
                        queued += 1
        return queued

    def claim_due_publication(self) -> str | None:
        if not self.auto_publish_enabled():
            return None
        now = utcnow()
        with session_scope() as session:
            claimable_id = (
                select(ChannelPublication.publication_id)
                .where(ChannelPublication.channel == "tiktok")
                .where(ChannelPublication.status == "scheduled")
                .where(ChannelPublication.scheduled_for_utc <= now)
                .order_by(ChannelPublication.scheduled_for_utc)
                .limit(1)
                .scalar_subquery()
            )
            claim = (
                update(ChannelPublication)
                .where(ChannelPublication.publication_id == claimable_id)
                .where(ChannelPublication.status == "scheduled")
                .values(status="publishing", updated_at=utcnow(), last_attempt_at=utcnow())
                .returning(ChannelPublication.publication_id)
            )
            publication_id = session.execute(claim).scalar_one_or_none()
            if not publication_id:
                return None
            publication = session.get(ChannelPublication, publication_id)
            job = session.get(Job, publication.job_id) if publication else None
            if job and publication:
                refresh_channel_publication_hash(publication)
                self.owner._persist_channel_publication_artifact(job, publication)
            return publication_id

    def publish_channel_publication(self, publication_id: str) -> None:
        with session_scope() as session:
            publication = session.get(ChannelPublication, publication_id)
            if not publication:
                raise KeyError(publication_id)
            job = session.get(Job, publication.job_id)
            if not job:
                raise KeyError(publication.job_id)
            job_id = job.job_id
            gate_result = self.owner._run_premium_publish_gate(session, job, context="tiktok_publish")
            if not gate_result.passed:
                message = self.owner._block_job_for_premium_publish_gate(job, gate_result)
                publication.status = "publish_failed"
                publication.last_error = message
                publication.channel_metadata = {"error": message}
                publication.last_attempt_at = utcnow()
                refresh_channel_publication_hash(publication)
                self.owner._persist_channel_publication_artifact(job, publication)
                self.owner._refresh_retention_state(session, job)
                session.commit()
                raise FatalStepError(message)
            package = self.monetization_pipeline.build_publish_package(session, job)
            video_uri = str(package.get("video_uri") or "")
            video_path = path_from_uri(video_uri)
            privacy_level = publication.privacy_level or self.settings.tiktok_privacy_level
            publication.attempt_count = int(publication.attempt_count or 0) + 1
            publication.last_attempt_at = utcnow()
        try:
            result = self.tiktok.direct_post_video(
                video_path=video_path,
                title=tiktok_caption(package),
                privacy_level=privacy_level,
                is_aigc=bool(package.get("altered_or_synthetic")),
                disable_comment=bool(self.settings.tiktok_disable_comment),
                disable_duet=bool(self.settings.tiktok_disable_duet),
                disable_stitch=bool(self.settings.tiktok_disable_stitch),
            )
        except (TikTokIntegrationError, httpx.HTTPError, OSError, FatalStepError) as exc:
            with session_scope() as session:
                publication = session.get(ChannelPublication, publication_id)
                job = session.get(Job, publication.job_id) if publication else None
                if publication:
                    publication.status = "publish_failed"
                    publication.last_error = str(exc)
                    publication.channel_metadata = {"error": str(exc)}
                    refresh_channel_publication_hash(publication)
                    if job:
                        self.owner._persist_channel_publication_artifact(job, publication)
            self.owner._append_event(job_id, "tiktok.publish_failed", "failed", {"publication_id": publication_id, "error": str(exc)})
            return
        with session_scope() as session:
            publication = session.get(ChannelPublication, publication_id)
            job = session.get(Job, publication.job_id) if publication else None
            if not publication:
                return
            publication.status = "processing"
            publication.external_id = str(result.get("publish_id") or "").strip() or None
            publication.last_error = None
            publication.channel_metadata = self.owner._serialize_for_json(result)
            refresh_channel_publication_hash(publication)
            if job:
                self.owner._persist_channel_publication_artifact(job, publication)
        self.owner._append_event(job_id, "tiktok.publish_started", "succeeded", {"publication_id": publication_id, "publish_id": result.get("publish_id")})

    def sync_publication_statuses(self) -> int:
        if not self.auto_publish_enabled() or not self.settings.tiktok_access_token:
            return 0
        with session_scope() as session:
            rows = session.execute(
                select(ChannelPublication.publication_id, ChannelPublication.external_id)
                .where(ChannelPublication.channel == "tiktok")
                .where(ChannelPublication.status == "processing")
                .where(ChannelPublication.external_id.is_not(None))
                .order_by(ChannelPublication.updated_at)
                .limit(10)
            ).all()
        synced = 0
        for publication_id, publish_id in rows:
            try:
                payload = self.tiktok.fetch_post_status(str(publish_id or ""))
            except (TikTokIntegrationError, httpx.HTTPError):
                continue
            status = str(payload.get("status") or "").upper()
            public_ids = payload.get("publicaly_available_post_id") or payload.get("publicly_available_post_id") or []
            final_status: str | None = None
            if status == "FAILED":
                final_status = "publish_failed"
            elif public_ids or status in {"PUBLISH_COMPLETE", "PUBLICLY_AVAILABLE", "SUCCESS"}:
                final_status = "published"
            if final_status is None:
                continue
            with session_scope() as session:
                publication = session.get(ChannelPublication, publication_id)
                job = session.get(Job, publication.job_id) if publication else None
                if not publication:
                    continue
                publication.status = final_status
                publication.channel_metadata = self.owner._serialize_for_json(payload)
                if final_status == "published":
                    publication.published_at = utcnow()
                    publication.external_url = None
                    publication.last_error = None
                else:
                    publication.last_error = str(payload.get("fail_reason") or "TikTok publication failed")
                refresh_channel_publication_hash(publication)
                if job:
                    self.owner._persist_channel_publication_artifact(job, publication)
            synced += 1
        return synced
