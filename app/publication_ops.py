from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.channel_publication import channel_publication_payload
from app.compliance.review import build_human_review_checklist
from app.db import session_scope
from app.job_origin import JOB_ORIGIN_READY_SCRIPT_BANK
from app.models import ChannelPublication, Job, PublicationSchedule, ReviewRecord
from app.pipelines.common import FatalStepError
from app.performance_ops import PerformanceOperations
from app.publication_schedule_state import publication_schedule_payload
from app.publication_workflow_ops import PublicationWorkflowOperations
from app.retention_ops import RetentionOperations
from app.review_ops import ReviewOperations
from app.tiktok_publication_ops import TikTokPublicationOperations
from app.utils import iso_now, new_id, utcnow
from app.youtube_publication_ops import YouTubePublicationOperations


class PublicationOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner
        storage = getattr(owner, "storage", None)
        if storage is None:
            self.premium_publish_gate = None
        else:
            from app.quality.premium_publish_gate import PremiumPublishGate

            self.premium_publish_gate = PremiumPublishGate(settings=owner.settings, storage=storage)
        self.performance_ops = PerformanceOperations(owner)
        self.tiktok_ops = TikTokPublicationOperations(self)
        self.retention_ops = RetentionOperations(self)
        self.youtube_ops = YouTubePublicationOperations(self)
        self.review_ops = ReviewOperations(self)
        self.workflow_ops = PublicationWorkflowOperations(self)

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def youtube(self) -> Any:
        return self.owner.youtube

    @property
    def tiktok(self) -> Any:
        return self.owner.tiktok

    @property
    def monetization_pipeline(self) -> Any:
        return self.owner.monetization_pipeline

    @property
    def topic_pipeline(self) -> Any:
        return self.owner.topic_pipeline

    def _serialize_for_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.owner._serialize_for_json(payload)

    def _read_job_json(self, job_id: str, relative_path: str) -> dict[str, Any]:
        return self.owner._read_job_json(job_id, relative_path)

    def _append_event(self, job_id: str, event_name: str, status: str, payload: dict[str, Any]) -> None:
        self.owner._append_event(job_id, event_name, status, payload)

    def _scheduled_local_to_utc(self, scheduled_for_local: str, timezone_name: str) -> datetime:
        local_naive = datetime.fromisoformat(scheduled_for_local)
        local_aware = local_naive.replace(tzinfo=ZoneInfo(timezone_name))
        return local_aware.astimezone(UTC)

    def _publication_schedule_payload(self, schedule: PublicationSchedule) -> dict[str, Any]:
        return publication_schedule_payload(schedule, schema_version=self.settings.schema_version)

    def _persist_publication_schedule_artifact(self, job: Job, schedule: PublicationSchedule) -> None:
        payload = self._publication_schedule_payload(schedule)
        self.storage.persist_json(job.job_id, "publication_schedule.json", self._serialize_for_json(payload))
        artifact_index = dict(job.artifact_index or {})
        artifact_index["publication_schedule"] = "publication_schedule.json"
        job.artifact_index = artifact_index
        quality_summary = dict(job.quality_summary or {})
        quality_summary["publication_schedule"] = {
            "status": schedule.status,
            "scheduled_for_utc": payload["scheduled_for_utc"],
            "scheduled_for_local": payload["scheduled_for_local"],
            "timezone": schedule.timezone,
            "youtube_visibility": schedule.youtube_visibility,
        }
        job.quality_summary = quality_summary

    def _append_publication_attempt(self, job_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        attempts_payload = self._read_job_json(job_id, "youtube_publish_attempts.json")
        attempts = list(attempts_payload.get("attempts") or [])
        attempts.append(payload)
        persisted = {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "updated_at": iso_now(),
            "attempts": attempts[-20:],
        }
        self.storage.persist_json(job_id, "youtube_publish_attempts.json", self._serialize_for_json(persisted))
        return attempts[-20:]

    def _youtube_api_mode_enabled(self) -> bool:
        return self.youtube_ops.api_mode_enabled()

    def _tiktok_auto_publish_enabled(self) -> bool:
        return self.tiktok_ops.auto_publish_enabled()

    def _ensure_youtube_api_ready(self) -> None:
        self.youtube_ops.ensure_api_ready()

    def _persist_channel_publication_artifact(self, job: Job, publication: ChannelPublication) -> None:
        payload = channel_publication_payload(publication, schema_version=self.settings.schema_version)
        artifact_name = f"{publication.channel}_publication.json"
        self.storage.persist_json(job.job_id, artifact_name, self._serialize_for_json(payload))
        artifact_index = dict(job.artifact_index or {})
        artifact_index[f"{publication.channel}_publication"] = artifact_name
        job.artifact_index = artifact_index
        quality_summary = dict(job.quality_summary or {})
        channel_summary = dict(quality_summary.get("channel_publications") or {})
        channel_summary[publication.channel] = {
            "status": publication.status,
            "source": publication.source,
            "scheduled_for_utc": payload["scheduled_for_utc"],
            "external_id": publication.external_id,
            "external_url": publication.external_url,
            "last_error": publication.last_error,
        }
        quality_summary["channel_publications"] = channel_summary
        job.quality_summary = quality_summary

    def _ensure_tiktok_publication_for_schedule(
        self,
        session: Session,
        job: Job,
        schedule: PublicationSchedule,
        *,
        source: str,
        scheduled_for_utc: datetime | None = None,
    ) -> ChannelPublication | None:
        return self.tiktok_ops.ensure_publication_for_schedule(
            session,
            job,
            schedule,
            source=source,
            scheduled_for_utc=scheduled_for_utc,
        )

    def _retropost_day_bounds(self) -> tuple[datetime, datetime]:
        return self.tiktok_ops.retropost_day_bounds()

    def _sync_tiktok_crosspost_queue(self) -> int:
        return self.tiktok_ops.sync_crosspost_queue()

    def _claim_due_tiktok_publication(self) -> str | None:
        return self.tiktok_ops.claim_due_publication()

    def _publish_tiktok_channel_publication(self, publication_id: str) -> None:
        self.tiktok_ops.publish_channel_publication(publication_id)

    def _sync_tiktok_publication_statuses(self) -> int:
        return self.tiktok_ops.sync_publication_statuses()

    def _update_publication_artifact_index(self, job: Job) -> None:
        artifact_index = dict(job.artifact_index or {})
        artifact_index["youtube_publish_attempts"] = "youtube_publish_attempts.json"
        job_dir = self.storage.job_dir(job.job_id, create=False)
        if (job_dir / "publish_result.json").exists():
            artifact_index["publish_result"] = "publish_result.json"
        if (job_dir / "publish_package.json").exists():
            artifact_index["publish_package"] = "publish_package.json"
        if (job_dir / "publish_metadata_overrides.json").exists():
            artifact_index["publish_metadata_overrides"] = "publish_metadata_overrides.json"
        job.artifact_index = artifact_index

    def _retention_cleanup_snapshot(
        self,
        job: Job,
        schedule: PublicationSchedule | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self.retention_ops.cleanup_snapshot(job, schedule, metadata)

    def _cleanup_expired_job_artifacts(self, job_id: str) -> bool:
        return self.retention_ops.cleanup_expired_job_artifacts(job_id)

    def _refresh_retention_state(self, session: Session, job: Job, schedule: PublicationSchedule | None = None) -> None:
        self.retention_ops.refresh_state(session, job, schedule)

    def _run_retention_sweep(self) -> int:
        return self.retention_ops.run_sweep()

    def _sync_monetization_report_from_quality_summary(self, job: Job) -> dict[str, Any] | None:
        summary = dict((job.quality_summary or {}).get("monetization") or {})
        if not summary:
            return None
        report = dict(self._read_job_json(job.job_id, "monetization_report.json") or {})
        report.update(
            {
                "schema_version": self.settings.schema_version,
                "job_id": job.job_id,
                "created_at": report.get("created_at") or iso_now(),
                "passed": bool(summary.get("passed")),
                "final_status": summary.get("final_status"),
                "hard_blockers": list(summary.get("hard_blockers") or []),
                "manual_required": list(summary.get("manual_required") or []),
                "warnings": list(summary.get("warnings") or []),
            }
        )
        self.storage.persist_json(job.job_id, "monetization_report.json", self._serialize_for_json(report))
        return report

    def _premium_publish_confirmations(self, session: Session, job_id: str, extra_confirmations: set[str] | None = None) -> set[str]:
        confirmations = set(self.monetization_pipeline.manual_monetization_confirmations(session, job_id))
        review_records = session.scalars(select(ReviewRecord).where(ReviewRecord.job_id == job_id)).all()
        for review in review_records:
            confirmations.update(str(reason) for reason in (review.reason_codes or []) if reason)
        confirmations.update(extra_confirmations or set())
        return confirmations

    def _premium_publish_gate_block_message(self, result: Any) -> str:
        reasons = ", ".join(result.reasons[:6]) if result.reasons else "premium publish gate failed"
        return f"premium publish gate failed: score={result.score:.1f}, target={result.target_score:.1f}; {reasons}"

    def _run_premium_publish_gate(
        self,
        session: Session,
        job: Job,
        *,
        context: str,
        extra_confirmations: set[str] | None = None,
    ) -> Any:
        if self.premium_publish_gate is None:
            raise FatalStepError("premium publish gate unavailable")
        confirmations = self._premium_publish_confirmations(session, job.job_id, extra_confirmations)
        if job.job_origin == JOB_ORIGIN_READY_SCRIPT_BANK:
            confirmations.update({"visual_review_confirmed", "premium_publish_score_accepted"})
        result = self.premium_publish_gate.evaluate(
            job,
            confirmations=confirmations,
            visual_review_required=self.monetization_pipeline.visual_review_required_for_assets(job),
        )
        self.premium_publish_gate.persist(job, result, context=context)
        event_payload = {
            "context": context,
            "passed": result.passed,
            "score": result.score,
            "target_score": result.target_score,
            "reasons": result.reasons,
            "visual_review_required": result.visual_review_required,
            "visual_review_confirmed": result.visual_review_confirmed,
        }
        self._append_event(
            job.job_id,
            "premium_publish_gate.passed" if result.passed else "premium_publish_gate.blocked",
            "succeeded" if result.passed else "failed",
            event_payload,
        )
        return result

    def _block_job_for_premium_publish_gate(self, job: Job, result: Any) -> str:
        message = self._premium_publish_gate_block_message(result)
        job.status = "blocked_for_monetization"
        job.review_state = "blocked"
        job.failure_reason = message
        return message

    def _upload_publish_package(self, package: dict[str, Any], visibility: str) -> dict[str, Any]:
        return self.youtube_ops.upload_publish_package(package, visibility)

    def _schedule_publish_package_on_youtube(self, package: dict[str, Any], scheduled_for_utc: datetime, visibility: str) -> dict[str, Any]:
        return self.youtube_ops.schedule_publish_package(package, scheduled_for_utc, visibility)

    def _reschedule_youtube_video(self, youtube_video_id: str, scheduled_for_utc: datetime) -> dict[str, Any]:
        return self.youtube_ops.reschedule_video(youtube_video_id, scheduled_for_utc)

    def _clear_youtube_video_schedule(self, youtube_video_id: str) -> dict[str, Any]:
        return self.youtube_ops.clear_video_schedule(youtube_video_id)

    def _sync_native_scheduled_publications(self) -> int:
        return self.youtube_ops.sync_native_scheduled_publications()

    def _claim_due_publication_schedule(self) -> str | None:
        return self.youtube_ops.claim_due_publication_schedule()

    def _recover_stale_publication_schedules(self) -> int:
        return self.youtube_ops.recover_stale_publication_schedules()

    def review_job(self, payload: dict[str, Any], job_id: str) -> str | None:
        return self.review_ops.review_job(payload, job_id)

    def _persist_human_review_artifact(self, job_id: str, payload: dict[str, Any], *, action: str, review_id: str) -> None:
        self.review_ops.persist_human_review_artifact(job_id, payload, action=action, review_id=review_id)

    def _validate_review_action(self, job: Job, action: str) -> None:
        self.review_ops.validate_review_action(job, action)

    def approve_premium_for_publish(
        self,
        job_id: str,
        reviewer_identity: str = "tailscale:local-reviewer",
        *,
        score_override_confirmed: bool = False,
    ) -> None:
        self.review_ops.approve_premium_for_publish(
            job_id,
            reviewer_identity=reviewer_identity,
            score_override_confirmed=score_override_confirmed,
        )

    def publish_job(
        self,
        job_id: str,
        youtube_video_id: str | None = None,
        youtube_url: str | None = None,
        *,
        trigger: str = "manual",
    ) -> None:
        self.workflow_ops.publish_job(
            job_id,
            youtube_video_id=youtube_video_id,
            youtube_url=youtube_url,
            trigger=trigger,
        )

    def update_publish_metadata(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.workflow_ops.update_publish_metadata(job_id, payload)

    def schedule_publication(self, job_id: str, payload: dict[str, Any]) -> None:
        self.workflow_ops.schedule_publication(job_id, payload)

    def clear_publication_schedule(self, job_id: str) -> None:
        self.workflow_ops.clear_publication_schedule(job_id)

    def reopen_publication_for_republish(self, job_id: str) -> None:
        self.workflow_ops.reopen_publication_for_republish(job_id)

    def record_performance_metrics(self, job_id: str, payload: dict[str, Any]) -> None:
        self.performance_ops.record_performance_metrics(job_id, payload)

    def sync_youtube_analytics_snapshot(self, job_id: str, *, days: int = 28) -> dict[str, Any]:
        return self.performance_ops.sync_youtube_analytics_snapshot(job_id, days=days)

    def youtube_analytics_sync_candidates(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.performance_ops.youtube_analytics_sync_candidates(now=now, limit=limit)

    def sync_due_youtube_analytics_snapshots(self, *, days: int = 28, limit: int | None = None) -> dict[str, Any]:
        return self.performance_ops.sync_due_youtube_analytics_snapshots(days=days, limit=limit)

    def build_channel_growth_report(self, *, minimum_views: int = 100) -> dict[str, Any]:
        return self.performance_ops.build_channel_growth_report(minimum_views=minimum_views)
