from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from app.db import session_scope
from app.models import Job, PublicationSchedule
from app.pipelines.common import FatalStepError
from app.publication_schedule_state import update_publication_schedule_content_hash
from app.utils import iso_now, new_id, path_from_uri, utcnow
from app.youtube_api import YouTubeIntegrationError


class YouTubePublicationOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def youtube(self) -> Any:
        return self.owner.youtube

    def first_comment_text(self, title: str | None) -> str:
        clean_title = str(title or "").strip().rstrip(".!?")
        if clean_title:
            return f"Sobre {clean_title}: qual detalhe mais te surpreendeu?"
        return "Qual detalhe desse vídeo mais te surpreendeu?"

    def post_first_public_comment(self, job_id: str, *, video_id: str | None, title: str | None) -> dict[str, Any] | None:
        normalized_video_id = str(video_id or "").strip()
        if not normalized_video_id:
            return None
        text = self.first_comment_text(title)
        try:
            response = self.youtube.post_top_level_comment(video_id=normalized_video_id, text=text)
        except YouTubeIntegrationError as exc:
            self.owner._append_event(job_id, "youtube.first_comment_failed", "failed", {"error": str(exc), "video_id": normalized_video_id})
            return None
        payload = {"video_id": normalized_video_id, "text": text, "response": response}
        self.owner._append_event(job_id, "youtube.first_comment_posted", "succeeded", payload)
        return payload

    def api_mode_enabled(self) -> bool:
        return bool(self.settings.youtube_api_enabled and self.settings.youtube_publish_mode == "api")

    def ensure_api_ready(self) -> None:
        status = self.youtube.connection_status()
        blockers = [
            item
            for item in status.missing_items
            if item
            not in {"SHORTSFLOW_YOUTUBE_PUBLISH_MODE != api", "SHORTSFLOW_YOUTUBE_API_ENABLED=false"}
        ]
        if blockers:
            raise FatalStepError("integração YouTube indisponível: " + ", ".join(blockers))

    def upload_publish_package(self, package: dict[str, Any], visibility: str) -> dict[str, Any]:
        video_uri = str(package.get("video_uri") or "").strip()
        if not video_uri:
            raise FatalStepError("publish package missing video_uri")
        try:
            upload = self.youtube.upload_video(
                video_path=path_from_uri(video_uri),
                title=str(package.get("title") or "") or "Short",
                description=str(package.get("description") or ""),
                tags=list(package.get("hashtags") or []),
                privacy_status=visibility,
                altered_or_synthetic=bool(package.get("altered_or_synthetic")),
            )
        except YouTubeIntegrationError as exc:
            raise FatalStepError(str(exc)) from exc
        return {
            "mode": "api",
            "api_enabled": True,
            "video_id": str(upload.get("id") or "").strip() or None,
            "url": upload.get("youtube_url"),
            "published_at": iso_now(),
            "response": upload,
            "target_visibility": visibility,
            "actual_visibility": ((upload.get("status") or {}).get("privacyStatus") if isinstance(upload.get("status"), dict) else None),
        }

    def schedule_publish_package(self, package: dict[str, Any], scheduled_for_utc: datetime, visibility: str) -> dict[str, Any]:
        video_uri = str(package.get("video_uri") or "").strip()
        if not video_uri:
            raise FatalStepError("publish package missing video_uri")
        try:
            upload = self.youtube.upload_video(
                video_path=path_from_uri(video_uri),
                title=str(package.get("title") or "") or "Short",
                description=str(package.get("description") or ""),
                tags=list(package.get("hashtags") or []),
                privacy_status=visibility,
                altered_or_synthetic=bool(package.get("altered_or_synthetic")),
                publish_at=scheduled_for_utc,
            )
        except YouTubeIntegrationError as exc:
            raise FatalStepError(str(exc)) from exc
        return {
            "mode": "api",
            "api_enabled": True,
            "video_id": str(upload.get("id") or "").strip() or None,
            "url": upload.get("youtube_url"),
            "scheduled_for_utc": scheduled_for_utc.isoformat(),
            "response": upload,
            "target_visibility": visibility,
            "actual_visibility": ((upload.get("status") or {}).get("privacyStatus") if isinstance(upload.get("status"), dict) else None),
            "native_youtube_schedule": True,
        }

    def reschedule_video(self, youtube_video_id: str, scheduled_for_utc: datetime) -> dict[str, Any]:
        try:
            response = self.youtube.schedule_published_video(video_id=youtube_video_id, publish_at=scheduled_for_utc)
        except YouTubeIntegrationError as exc:
            raise FatalStepError(str(exc)) from exc
        return {
            "mode": "api",
            "api_enabled": True,
            "video_id": youtube_video_id,
            "url": response.get("youtube_url"),
            "scheduled_for_utc": scheduled_for_utc.isoformat(),
            "response": response,
            "target_visibility": "public",
            "actual_visibility": ((response.get("status") or {}).get("privacyStatus") if isinstance(response.get("status"), dict) else None),
            "native_youtube_schedule": True,
        }

    def clear_video_schedule(self, youtube_video_id: str) -> dict[str, Any]:
        try:
            response = self.youtube.clear_scheduled_publish(video_id=youtube_video_id)
        except YouTubeIntegrationError as exc:
            raise FatalStepError(str(exc)) from exc
        return {
            "mode": "api",
            "api_enabled": True,
            "video_id": youtube_video_id,
            "url": response.get("youtube_url"),
            "response": response,
            "native_youtube_schedule": True,
        }

    def sync_native_scheduled_publications(self) -> int:
        if not self.api_mode_enabled():
            return 0
        now = utcnow()
        with session_scope() as session:
            rows = session.execute(
                select(PublicationSchedule.job_id, PublicationSchedule.youtube_video_id)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .where(PublicationSchedule.status == "scheduled")
                .where(PublicationSchedule.youtube_video_id.is_not(None))
                .where(PublicationSchedule.scheduled_for_utc <= now)
                .where(Job.status == "approved_for_publish")
                .order_by(PublicationSchedule.scheduled_for_utc)
            ).all()
        synced = 0
        for job_id, youtube_video_id in rows:
            try:
                payload = self.youtube.fetch_video(str(youtube_video_id or ""))
            except YouTubeIntegrationError:
                continue
            status = dict(payload.get("status") or {})
            privacy_status = str(status.get("privacyStatus") or "").strip().lower()
            if privacy_status != "public":
                continue
            publish_package = self.owner._read_job_json(str(job_id), "publish_package.json")
            first_comment_payload = self.post_first_public_comment(
                str(job_id),
                video_id=str(youtube_video_id or ""),
                title=str(publish_package.get("title") or ""),
            )
            published_at = utcnow()
            with session_scope() as session:
                job = session.get(Job, job_id)
                schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
                if not job or not schedule or schedule.status != "scheduled":
                    continue
                schedule.status = "published"
                schedule.published_at = published_at
                schedule.youtube_video_id = str(youtube_video_id or "").strip() or None
                schedule.youtube_url = payload.get("youtube_url")
                update_publication_schedule_content_hash(schedule, include_publish_result=True)
                self.owner._persist_publication_schedule_artifact(job, schedule)
                job.status = "published"
                job.review_state = "published"
                quality_summary = dict(job.quality_summary or {})
                quality_summary["youtube_publish"] = {
                    "status": "published",
                    "last_attempt_at": iso_now(),
                    "mode": "api",
                    "video_id": schedule.youtube_video_id,
                    "youtube_url": schedule.youtube_url,
                }
                quality_summary["youtube"] = payload
                if first_comment_payload:
                    quality_summary["youtube_first_comment"] = first_comment_payload
                job.quality_summary = quality_summary
                self.owner._update_publication_artifact_index(job)
                self.owner._ensure_tiktok_publication_for_schedule(session, job, schedule, source="youtube_schedule")
                self.owner._refresh_retention_state(session, job, schedule)
            self.owner._append_publication_attempt(
                job_id,
                {
                    "attempt_id": new_id(),
                    "trigger": "youtube_schedule_sync",
                    "started_at": iso_now(),
                    "finished_at": iso_now(),
                    "status": "published",
                    "mode": "api",
                    "target_visibility": "public",
                    "youtube_video_id": youtube_video_id,
                    "youtube_url": payload.get("youtube_url"),
                },
            )
            self.owner._append_event(job_id, "youtube.schedule.synced", "succeeded", {"video_id": youtube_video_id, "url": payload.get("youtube_url")})
            synced += 1
        return synced

    def claim_due_publication_schedule(self) -> str | None:
        if not self.api_mode_enabled():
            return None
        now = utcnow()
        with session_scope() as session:
            claimable_job_id = (
                select(PublicationSchedule.job_id)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .where(PublicationSchedule.status == "scheduled")
                .where(PublicationSchedule.youtube_video_id.is_(None))
                .where(PublicationSchedule.scheduled_for_utc <= now)
                .where(Job.status == "approved_for_publish")
                .order_by(PublicationSchedule.scheduled_for_utc)
                .limit(1)
                .scalar_subquery()
            )
            claim = (
                update(PublicationSchedule)
                .where(PublicationSchedule.job_id == claimable_job_id)
                .where(PublicationSchedule.status == "scheduled")
                .values(status="publishing", updated_at=utcnow())
                .returning(PublicationSchedule.job_id)
            )
            claimed_job_id = session.execute(claim).scalar_one_or_none()
            if not claimed_job_id:
                return None
            job = session.get(Job, claimed_job_id)
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == claimed_job_id))
            if job and schedule:
                self.owner._persist_publication_schedule_artifact(job, schedule)
            return claimed_job_id
