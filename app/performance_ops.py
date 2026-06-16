from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db import session_scope
from app.growth_metrics import optional_float_value, optional_int_value
from app.models import Job, PerformanceMetric, PublicationSchedule, YouTubeAnalyticsSnapshot
from app.pipelines.common import model_payload
from app.utils import new_id, stable_hash, utcnow
from app.youtube_api import YouTubeIntegrationError


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class PerformanceOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

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
    def monetization_pipeline(self) -> Any:
        return self.owner.monetization_pipeline

    def _serialize_for_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.owner._serialize_for_json(payload)

    def _append_event(self, job_id: str, event_name: str, status: str, payload: dict[str, Any]) -> None:
        self.owner._append_event(job_id, event_name, status, payload)

    def record_performance_metrics(self, job_id: str, payload: dict[str, Any]) -> None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            metric_payload = {
                "metric_id": new_id(),
                "job_id": job_id,
                "schema_version": self.settings.schema_version,
                "created_at": utcnow(),
                **payload,
            }
            metric_payload["content_hash"] = stable_hash({key: value for key, value in metric_payload.items() if key != "created_at"})
            session.add(PerformanceMetric(**model_payload(PerformanceMetric, metric_payload)))
            session.flush()
            metrics = session.scalars(
                select(PerformanceMetric).where(PerformanceMetric.job_id == job_id).order_by(PerformanceMetric.created_at.desc())
            ).all()
            report = self.monetization_pipeline.build_job_performance_report(metrics)
            self.storage.persist_json(job_id, "performance_metrics.json", self._serialize_for_json(report))
            artifact_index = dict(job.artifact_index or {})
            artifact_index["performance_metrics"] = "performance_metrics.json"
            job.artifact_index = artifact_index
            quality_summary = dict(job.quality_summary or {})
            quality_summary["performance"] = report["latest"] or {}
            job.quality_summary = quality_summary
        self._append_event(job_id, "youtube.performance_recorded", "succeeded", payload)

    def sync_youtube_analytics_snapshot(self, job_id: str, *, days: int = 28) -> dict[str, Any]:
        days = max(1, min(int(days), 90))
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days - 1)
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            schedule = session.scalars(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id)).first()
            youtube_video_id = str(schedule.youtube_video_id or "").strip() if schedule else ""
            if not youtube_video_id:
                raise YouTubeIntegrationError("Job ainda não tem video_id do YouTube vinculado")
        snapshot_payload = self.youtube.fetch_video_analytics_snapshot(video_id=youtube_video_id, start_date=start_date, end_date=end_date)
        fetched_at = datetime.fromisoformat(str(snapshot_payload["fetched_at"]))
        snapshot_id = new_id()
        snapshot_record = {
            "snapshot_id": snapshot_id,
            "job_id": job_id,
            "schema_version": self.settings.schema_version,
            "created_at": utcnow(),
            "fetched_at": fetched_at,
            "youtube_video_id": youtube_video_id,
            "start_date": snapshot_payload["start_date"],
            "end_date": snapshot_payload["end_date"],
            "summary_metrics": snapshot_payload.get("summary_metrics") or {},
            "daily_rows": snapshot_payload.get("daily_rows") or [],
            "raw_response": snapshot_payload.get("raw_response") or {},
        }
        snapshot_record["content_hash"] = stable_hash({key: value for key, value in snapshot_record.items() if key not in {"created_at", "fetched_at"}})
        summary = dict(snapshot_record["summary_metrics"])
        metric_payload = {
            "source": "youtube_analytics_api",
            "retention_percent": optional_float_value(summary.get("averageViewPercentage")),
            "likes": optional_int_value(summary.get("likes")),
            "shares": optional_int_value(summary.get("shares")),
            "comments": optional_int_value(summary.get("comments")),
            "notes": f"Snapshot YouTube Analytics {snapshot_record['start_date']} a {snapshot_record['end_date']}",
        }
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            session.add(YouTubeAnalyticsSnapshot(**model_payload(YouTubeAnalyticsSnapshot, snapshot_record)))
            metric_record = {
                "metric_id": new_id(),
                "job_id": job_id,
                "schema_version": self.settings.schema_version,
                "created_at": utcnow(),
                **metric_payload,
            }
            metric_record["content_hash"] = stable_hash({key: value for key, value in metric_record.items() if key != "created_at"})
            session.add(PerformanceMetric(**model_payload(PerformanceMetric, metric_record)))
            session.flush()
            metrics = session.scalars(
                select(PerformanceMetric).where(PerformanceMetric.job_id == job_id).order_by(PerformanceMetric.created_at.desc())
            ).all()
            performance_report = self.monetization_pipeline.build_job_performance_report(metrics)
            report_payload = {
                "schema_version": self.settings.schema_version,
                "snapshot": self._serialize_for_json(snapshot_payload),
                "performance_report": self._serialize_for_json(performance_report),
            }
            self.storage.persist_json(job_id, "youtube_analytics_snapshot.json", report_payload)
            artifact_index = dict(job.artifact_index or {})
            artifact_index["youtube_analytics_snapshot"] = "youtube_analytics_snapshot.json"
            artifact_index["performance_metrics"] = "performance_metrics.json"
            job.artifact_index = artifact_index
            self.storage.persist_json(job_id, "performance_metrics.json", self._serialize_for_json(performance_report))
            quality_summary = dict(job.quality_summary or {})
            quality_summary["youtube_analytics"] = {
                "snapshot_id": snapshot_id,
                "start_date": snapshot_record["start_date"],
                "end_date": snapshot_record["end_date"],
                "summary_metrics": summary,
            }
            quality_summary["performance"] = performance_report["latest"] or {}
            job.quality_summary = quality_summary
        self._append_event(job_id, "youtube.analytics_snapshot_synced", "succeeded", {"days": days, "youtube_video_id": youtube_video_id})
        return self._serialize_for_json(snapshot_payload)

    def youtube_analytics_sync_candidates(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        now_utc = as_utc(now or utcnow()) or utcnow()
        active_window_days = int(self.settings.performance_sync_active_window_days)
        archive_window_days = int(self.settings.performance_sync_archive_window_days)
        batch_limit = int(limit or self.settings.performance_sync_batch_limit)
        candidates: list[dict[str, Any]] = []
        with session_scope() as session:
            schedules = session.scalars(
                select(PublicationSchedule)
                .where(PublicationSchedule.status == "published")
                .where(PublicationSchedule.youtube_video_id.is_not(None))
                .order_by(PublicationSchedule.published_at.desc(), PublicationSchedule.updated_at.desc())
            ).all()
            for schedule in schedules:
                youtube_video_id = str(schedule.youtube_video_id or "").strip()
                if not youtube_video_id:
                    continue
                published_at = as_utc(schedule.published_at) or as_utc(schedule.scheduled_for_utc) or as_utc(schedule.created_at) or now_utc
                age_days = max(0, (now_utc - published_at).days)
                if age_days > archive_window_days:
                    continue
                if age_days <= active_window_days:
                    stale_after = timedelta(hours=24)
                    cadence = "daily"
                else:
                    stale_after = timedelta(days=7)
                    cadence = "weekly"
                latest_snapshot = session.scalars(
                    select(YouTubeAnalyticsSnapshot)
                    .where(YouTubeAnalyticsSnapshot.job_id == schedule.job_id)
                    .order_by(YouTubeAnalyticsSnapshot.fetched_at.desc())
                    .limit(1)
                ).first()
                latest_fetched_at = as_utc(latest_snapshot.fetched_at) if latest_snapshot else None
                if latest_fetched_at and now_utc - latest_fetched_at < stale_after:
                    continue
                candidates.append(
                    {
                        "job_id": schedule.job_id,
                        "youtube_video_id": youtube_video_id,
                        "published_at": published_at.isoformat(),
                        "age_days": age_days,
                        "cadence": cadence,
                        "latest_snapshot_at": latest_fetched_at.isoformat() if latest_fetched_at else None,
                        "reason": "no_snapshot" if latest_fetched_at is None else "stale_snapshot",
                    }
                )
                if len(candidates) >= batch_limit:
                    break
        return candidates

    def sync_due_youtube_analytics_snapshots(self, *, days: int = 28, limit: int | None = None) -> dict[str, Any]:
        if not self.settings.performance_collection_enabled:
            return {
                "status": "skipped",
                "reason": "performance_collection_disabled",
                "synced": [],
                "failed": [],
                "candidates": [],
            }
        status = self.youtube.connection_status(None)
        if not status.analytics_connected:
            return {
                "status": "skipped",
                "reason": "youtube_analytics_not_connected",
                "missing_items": status.analytics_missing_items or status.missing_items,
                "synced": [],
                "failed": [],
                "candidates": [],
            }
        candidates = self.youtube_analytics_sync_candidates(limit=limit)
        synced: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for candidate in candidates:
            job_id = str(candidate["job_id"])
            try:
                self.sync_youtube_analytics_snapshot(job_id, days=days)
            except Exception as exc:  # keep one bad video from stopping the daily collection batch
                failed.append({"job_id": job_id, "error": str(exc), "reason": candidate.get("reason")})
                continue
            synced.append({"job_id": job_id, "reason": candidate.get("reason"), "cadence": candidate.get("cadence")})
        return {
            "status": "completed" if not failed else "partial",
            "synced": synced,
            "failed": failed,
            "candidates": candidates,
        }
