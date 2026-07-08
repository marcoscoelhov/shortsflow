from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.channel_publication import refresh_channel_publication_hash
from app.db import session_scope
from app.models import ChannelPublication, Job, PublicationSchedule
from app.pipelines.common import FatalStepError
from app.publication_schedule_state import update_publication_schedule_content_hash
from app.schemas import PublicationSchedulePayload
from app.utils import iso_now, new_id, utcnow


class PublicationWorkflowOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def monetization_pipeline(self) -> Any:
        return self.owner.monetization_pipeline

    def publish_job(
        self,
        job_id: str,
        youtube_video_id: str | None = None,
        youtube_url: str | None = None,
        *,
        trigger: str = "manual",
    ) -> None:
        attempt_id = new_id()
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            if job.status != "approved_for_publish":
                raise FatalStepError("job must be approved_for_publish before publishing")
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            monetization_report = self.owner._read_job_json(job.job_id, "monetization_report.json")
            monetization_summary = dict((job.quality_summary or {}).get("monetization") or {})
            if monetization_summary.get("passed") is True and not monetization_report.get("passed"):
                monetization_report = self.owner._sync_monetization_report_from_quality_summary(job) or monetization_report
            if monetization_report and not monetization_report.get("passed"):
                raise FatalStepError("job has not passed monetization readiness gate")
            if self.owner._youtube_api_mode_enabled():
                self.owner._ensure_youtube_api_ready()
            elif not (str(youtube_video_id or "").strip() or str(youtube_url or "").strip()):
                raise FatalStepError("manual publish requires youtube_video_id or youtube_url")
            gate_result = self.owner._run_premium_publish_gate(session, job, context=f"publish_{trigger}")
            if not gate_result.passed:
                message = self.owner._block_job_for_premium_publish_gate(job, gate_result)
                self.owner._refresh_retention_state(session, job, schedule)
                session.commit()
                raise FatalStepError(message)
            package = self.monetization_pipeline.build_publish_package(session, job)
            published_at = utcnow()
            if schedule is None:
                schedule = PublicationSchedule(
                    schedule_id=new_id(),
                    job_id=job_id,
                    schema_version=self.settings.schema_version,
                    content_hash="",
                    created_at=published_at,
                    scheduled_for_utc=published_at,
                    timezone="UTC",
                    youtube_visibility="private",
                    status="scheduled" if self.owner._youtube_api_mode_enabled() else "published",
                )
                session.add(schedule)
            if self.owner._youtube_api_mode_enabled():
                schedule.status = "publishing"
                self.owner._persist_publication_schedule_artifact(job, schedule)
            package_snapshot = self.owner._serialize_for_json(package)
            visibility = schedule.youtube_visibility or "private"
            notes = schedule.notes

        started_at = iso_now()
        attempt_payload = {
            "attempt_id": attempt_id,
            "trigger": trigger,
            "started_at": started_at,
            "status": "started",
            "mode": "api" if self.owner._youtube_api_mode_enabled() else "manual",
            "target_visibility": visibility,
            "notes": notes,
        }
        self.owner._append_publication_attempt(job_id, attempt_payload)

        try:
            first_comment_payload = None
            if self.owner._youtube_api_mode_enabled():
                youtube_payload = self.owner._upload_publish_package(package_snapshot, visibility)
                youtube_video_id = youtube_payload.get("video_id")
                youtube_url = youtube_payload.get("url")
                if str(visibility).lower() == "public" and str(youtube_payload.get("actual_visibility") or "").lower() == "public":
                    first_comment_payload = self.owner.youtube_ops.post_first_public_comment(
                        job_id,
                        video_id=str(youtube_video_id or ""),
                        title=str(package_snapshot.get("title") or ""),
                    )
            else:
                youtube_payload = {
                    "mode": self.settings.youtube_publish_mode,
                    "api_enabled": self.settings.youtube_api_enabled,
                    "video_id": str(youtube_video_id or "").strip() or None,
                    "url": str(youtube_url or "").strip() or None,
                    "published_at": iso_now(),
                }
                first_comment_payload = None
        except Exception as exc:
            with session_scope() as session:
                job = session.get(Job, job_id)
                if not job:
                    raise
                schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
                if schedule is not None:
                    schedule.status = "publish_failed"
                    update_publication_schedule_content_hash(schedule)
                    self.owner._persist_publication_schedule_artifact(job, schedule)
                quality_summary = dict(job.quality_summary or {})
                quality_summary["youtube_publish"] = {
                    "status": "publish_failed",
                    "last_error": str(exc),
                    "last_attempt_at": iso_now(),
                }
                job.quality_summary = quality_summary
                self.owner._update_publication_artifact_index(job)
                self.owner._refresh_retention_state(session, job, schedule)
            self.owner._append_publication_attempt(
                job_id,
                {
                    "attempt_id": attempt_id,
                    "trigger": trigger,
                    "started_at": started_at,
                    "finished_at": iso_now(),
                    "status": "failed",
                    "mode": "api" if self.owner._youtube_api_mode_enabled() else "manual",
                    "target_visibility": visibility,
                    "error": str(exc),
                },
            )
            self.owner._append_event(job_id, "youtube.publish_failed", "failed", {"error": str(exc), "trigger": trigger})
            if isinstance(exc, FatalStepError):
                raise
            raise FatalStepError(str(exc)) from exc

        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            published_at = utcnow()
            if schedule is None:
                schedule = PublicationSchedule(
                    schedule_id=new_id(),
                    job_id=job_id,
                    schema_version=self.settings.schema_version,
                    content_hash="",
                    created_at=published_at,
                    scheduled_for_utc=published_at,
                    timezone="UTC",
                    youtube_visibility=visibility,
                    status="published",
                )
                session.add(schedule)
            schedule.status = "published"
            schedule.published_at = published_at
            schedule.youtube_video_id = str(youtube_video_id or "").strip() or None
            schedule.youtube_url = str(youtube_url or "").strip() or None
            update_publication_schedule_content_hash(schedule, include_publish_result=True)
            self.owner._persist_publication_schedule_artifact(job, schedule)
            package_snapshot["status"] = "published"
            package_snapshot["published_at"] = published_at.isoformat()
            package_snapshot["youtube_video_id"] = schedule.youtube_video_id
            package_snapshot["youtube_url"] = schedule.youtube_url
            package_snapshot["publication_schedule"] = self.owner._publication_schedule_payload(schedule)
            package_snapshot["youtube"] = youtube_payload
            if first_comment_payload:
                package_snapshot["youtube_first_comment"] = first_comment_payload
            self.storage.persist_json(job.job_id, "publish_result.json", self.owner._serialize_for_json(package_snapshot))
            job.status = "published"
            job.review_state = "published"
            quality_summary = dict(job.quality_summary or {})
            quality_summary["youtube"] = youtube_payload
            quality_summary["youtube_publish"] = {
                "status": "published",
                "last_attempt_at": iso_now(),
                "mode": youtube_payload.get("mode"),
                "video_id": schedule.youtube_video_id,
                "youtube_url": schedule.youtube_url,
            }
            job.quality_summary = quality_summary
            self.owner._update_publication_artifact_index(job)
            self.owner._ensure_tiktok_publication_for_schedule(session, job, schedule, source="youtube_publish")
            self.owner._refresh_retention_state(session, job, schedule)
        self.owner._append_publication_attempt(
            job_id,
            {
                "attempt_id": attempt_id,
                "trigger": trigger,
                "started_at": started_at,
                "finished_at": iso_now(),
                "status": "published",
                "mode": youtube_payload.get("mode"),
                "target_visibility": visibility,
                "youtube_video_id": youtube_video_id,
                "youtube_url": youtube_url,
            },
        )
        self.owner._append_event(job_id, "youtube.published", "succeeded", {"video_id": youtube_video_id, "url": youtube_url, "trigger": trigger})

    def update_publish_metadata(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            overrides = self.monetization_pipeline.normalize_publish_metadata_overrides(
                payload.get("title"),
                payload.get("description"),
                payload.get("hashtags"),
            )
            persisted = {
                "schema_version": self.settings.schema_version,
                "job_id": job_id,
                "updated_at": iso_now(),
                **overrides,
            }
            self.storage.persist_json(job_id, "publish_metadata_overrides.json", self.owner._serialize_for_json(persisted))
            package = self.monetization_pipeline.build_publish_package(session, job)
            self.storage.persist_json(job_id, "publish_package.json", self.owner._serialize_for_json(package))
            self.owner._refresh_retention_state(session, job)
            self.owner._update_publication_artifact_index(job)
        self.owner._append_event(
            job_id,
            "publish.metadata.updated",
            "succeeded",
            {
                "title": package.get("title"),
                "hashtags": package.get("hashtags"),
            },
        )
        return package

    def schedule_publication(self, job_id: str, payload: dict[str, Any]) -> None:
        validated = PublicationSchedulePayload(**payload)
        scheduled_for_utc = self.owner._scheduled_local_to_utc(validated.scheduled_for_local, validated.timezone)
        if scheduled_for_utc <= utcnow():
            raise FatalStepError("scheduled publish time must be in the future")
        youtube_schedule_payload: dict[str, Any] | None = None
        youtube_video_id: str | None = None
        youtube_url: str | None = None
        had_existing_youtube_video = False
        if self.owner._youtube_api_mode_enabled():
            self.owner._ensure_youtube_api_ready()
            if validated.youtube_visibility != "public":
                raise FatalStepError("native YouTube scheduling currently requires visibility public")
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            if job.status != "approved_for_publish":
                raise FatalStepError("job must be approved_for_publish before entering the publication schedule")
            gate_result = self.owner._run_premium_publish_gate(session, job, context="schedule_publication")
            if not gate_result.passed:
                message = self.owner._block_job_for_premium_publish_gate(job, gate_result)
                self.owner._refresh_retention_state(session, job)
                session.commit()
                raise FatalStepError(message)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            package = self.monetization_pipeline.build_publish_package(session, job) if self.owner._youtube_api_mode_enabled() and (schedule is None or not schedule.youtube_video_id) else None
            if schedule is not None:
                youtube_video_id = str(schedule.youtube_video_id or "").strip() or None
                youtube_url = str(schedule.youtube_url or "").strip() or None
                had_existing_youtube_video = youtube_video_id is not None
        if self.owner._youtube_api_mode_enabled():
            if youtube_video_id:
                youtube_schedule_payload = self.owner._reschedule_youtube_video(youtube_video_id, scheduled_for_utc)
            else:
                assert package is not None
                youtube_schedule_payload = self.owner._schedule_publish_package_on_youtube(
                    package,
                    scheduled_for_utc,
                    validated.youtube_visibility,
                )
                youtube_video_id = str(youtube_schedule_payload.get("video_id") or "").strip() or None
                youtube_url = str(youtube_schedule_payload.get("url") or "").strip() or None
            attempt_started_at = iso_now()
            self.owner._append_publication_attempt(
                job_id,
                {
                    "attempt_id": new_id(),
                    "trigger": "schedule_update" if had_existing_youtube_video else "schedule_upload",
                    "started_at": attempt_started_at,
                    "finished_at": attempt_started_at,
                    "status": "scheduled",
                    "mode": "api",
                    "target_visibility": validated.youtube_visibility,
                    "scheduled_for_utc": scheduled_for_utc.isoformat(),
                    "youtube_video_id": youtube_video_id,
                    "youtube_url": youtube_url,
                    "native_youtube_schedule": True,
                },
            )
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            if schedule is None:
                schedule = PublicationSchedule(
                    schedule_id=new_id(),
                    job_id=job_id,
                    schema_version=self.settings.schema_version,
                    content_hash="",
                    created_at=utcnow(),
                    scheduled_for_utc=scheduled_for_utc,
                    timezone=validated.timezone,
                    youtube_visibility=validated.youtube_visibility,
                    status="scheduled",
                    notes=validated.notes,
                )
                session.add(schedule)
            else:
                schedule.scheduled_for_utc = scheduled_for_utc
                schedule.timezone = validated.timezone
                schedule.youtube_visibility = validated.youtube_visibility
                schedule.status = "scheduled"
                schedule.notes = validated.notes
                schedule.published_at = None
            if self.owner._youtube_api_mode_enabled():
                schedule.youtube_video_id = youtube_video_id
                schedule.youtube_url = youtube_url
            else:
                schedule.youtube_video_id = None
                schedule.youtube_url = None
            update_publication_schedule_content_hash(schedule)
            self.owner._persist_publication_schedule_artifact(job, schedule)
            if self.owner._youtube_api_mode_enabled():
                quality_summary = dict(job.quality_summary or {})
                quality_summary["youtube_publish"] = {
                    "status": "scheduled",
                    "last_attempt_at": iso_now(),
                    "mode": "api",
                    "video_id": schedule.youtube_video_id,
                    "youtube_url": schedule.youtube_url,
                    "scheduled_for_utc": schedule.scheduled_for_utc.isoformat(),
                    "native_youtube_schedule": True,
                }
                if youtube_schedule_payload is not None:
                    quality_summary["youtube"] = youtube_schedule_payload
                job.quality_summary = quality_summary
                self.owner._update_publication_artifact_index(job)
            self.owner._ensure_tiktok_publication_for_schedule(session, job, schedule, source="youtube_schedule")
            self.owner._refresh_retention_state(session, job, schedule)
        self.owner._append_event(
            job_id,
            "youtube.schedule.updated",
            "succeeded",
            {
                "scheduled_for_utc": scheduled_for_utc.isoformat(),
                "timezone": validated.timezone,
                "youtube_visibility": validated.youtube_visibility,
                "native_youtube_schedule": self.owner._youtube_api_mode_enabled(),
                "youtube_video_id": youtube_video_id,
                "youtube_url": youtube_url,
            },
        )

    def clear_publication_schedule(self, job_id: str) -> None:
        youtube_video_id: str | None = None
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            if schedule is None:
                return
            if schedule.status == "published":
                raise FatalStepError("published job schedule cannot be cleared")
            if self.owner._youtube_api_mode_enabled():
                youtube_video_id = str(schedule.youtube_video_id or "").strip() or None
        if self.owner._youtube_api_mode_enabled() and youtube_video_id:
            self.owner._clear_youtube_video_schedule(youtube_video_id)
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            if schedule is None:
                return
            schedule.status = "cancelled"
            update_publication_schedule_content_hash(schedule)
            self.owner._persist_publication_schedule_artifact(job, schedule)
            channel_publication = session.scalar(
                select(ChannelPublication).where(ChannelPublication.job_id == job_id, ChannelPublication.channel == "tiktok")
            )
            if channel_publication and channel_publication.status in {"scheduled", "publishing", "processing", "publish_failed"}:
                channel_publication.status = "cancelled"
                channel_publication.last_error = None
                refresh_channel_publication_hash(channel_publication)
                self.owner._persist_channel_publication_artifact(job, channel_publication)
            self.owner._refresh_retention_state(session, job, schedule)
        self.owner._append_event(job_id, "youtube.schedule.cleared", "succeeded", {"youtube_video_id": youtube_video_id})

    def reopen_publication_for_republish(self, job_id: str) -> None:
        reopened_at = iso_now()
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            if job.status != "published":
                raise FatalStepError("only published jobs can be reopened for republication")
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            if schedule is None or schedule.status != "published":
                raise FatalStepError("published job is missing a published schedule record")
            previous_video_id = schedule.youtube_video_id
            previous_youtube_url = schedule.youtube_url
            schedule.status = "cancelled"
            schedule.published_at = None
            schedule.youtube_video_id = None
            schedule.youtube_url = None
            update_publication_schedule_content_hash(schedule)
            self.owner._persist_publication_schedule_artifact(job, schedule)
            job.status = "approved_for_publish"
            job.review_state = "approved"
            quality_summary = dict(job.quality_summary or {})
            quality_summary["youtube_publish"] = {
                "status": "reopened_for_republish",
                "last_reopened_at": reopened_at,
                "previous_video_id": previous_video_id,
                "previous_youtube_url": previous_youtube_url,
            }
            job.quality_summary = quality_summary
            self.owner._update_publication_artifact_index(job)
            self.owner._refresh_retention_state(session, job, schedule)
        self.owner._append_publication_attempt(
            job_id,
            {
                "attempt_id": new_id(),
                "trigger": "reopen_for_republish",
                "started_at": reopened_at,
                "finished_at": reopened_at,
                "status": "reopened_for_republish",
            },
        )
        self.owner._append_event(job_id, "youtube.reopened_for_republish", "succeeded", {"status": "approved_for_publish"})
