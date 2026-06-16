from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import and_, case, func, or_, select

from app.db import SessionLocal
from app.hub_status import NEEDS_ACTION_JOB_STATUSES
from app.job_origin import (
    creation_via_display,
    creation_via_options,
    job_origin_display,
    job_origin_options,
    resolve_creation_via,
    resolve_job_origin,
)
from app.models import AutomationAttempt, FallbackEvent, Job, PublicationSchedule, RenderOutput, SceneAsset, TopicRequest

HUB_JOBS_PER_PAGE = 4

class HubJobsContext:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    def clamp_page(self, value: int | None) -> int:
        return max(1, int(value or 1))

    def clamp_per_page(self, value: int | None) -> int:
        return max(1, min(100, int(value or HUB_JOBS_PER_PAGE)))

    def query_jobs(
        self,
        status: str | None,
        search: str | None,
        fallback: str | None,
        review: str | None,
        origin: str | None,
        via: str | None,
        page: int = 1,
        per_page: int = HUB_JOBS_PER_PAGE,
    ):
        session = SessionLocal()
        try:
            normalized_page = self.clamp_page(page)
            normalized_per_page = self.clamp_per_page(per_page)
            fallback_count = (
                select(FallbackEvent.job_id, func.count(FallbackEvent.event_id).label("fallback_count"))
                .group_by(FallbackEvent.job_id)
                .subquery()
            )
            final_asset = (
                select(SceneAsset.job_id, func.sum(case((SceneAsset.selected.is_(True), 1), else_=0)).label("asset_count"))
                .group_by(SceneAsset.job_id)
                .subquery()
            )
            automation_attempt = (
                select(AutomationAttempt.job_id, func.max(AutomationAttempt.source).label("automation_source"))
                .group_by(AutomationAttempt.job_id)
                .subquery()
            )
            stmt = (
                select(
                    Job,
                    TopicRequest.seed_theme,
                    TopicRequest.notes,
                    RenderOutput.duration_ms,
                    func.coalesce(fallback_count.c.fallback_count, 0),
                    func.coalesce(final_asset.c.asset_count, 0),
                    PublicationSchedule,
                    automation_attempt.c.automation_source,
                )
                .join(TopicRequest, TopicRequest.job_id == Job.job_id)
                .join(RenderOutput, RenderOutput.job_id == Job.job_id, isouter=True)
                .join(fallback_count, fallback_count.c.job_id == Job.job_id, isouter=True)
                .join(final_asset, final_asset.c.job_id == Job.job_id, isouter=True)
                .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
                .join(automation_attempt, automation_attempt.c.job_id == Job.job_id, isouter=True)
                .order_by(Job.created_at.desc())
            )
            if status:
                now = datetime.now(UTC)
                if status == "unscheduled_approved":
                    stmt = stmt.where(Job.status == "approved_for_publish").where(
                        or_(PublicationSchedule.schedule_id.is_(None), PublicationSchedule.status == "cancelled")
                    )
                elif status == "scheduled_publication":
                    stmt = stmt.where(PublicationSchedule.status.in_(["scheduled", "publishing", "publish_failed"]))
                elif status == "awaiting_confirmation":
                    stmt = stmt.where(PublicationSchedule.status == "scheduled").where(PublicationSchedule.youtube_video_id.is_not(None)).where(
                        PublicationSchedule.scheduled_for_utc <= now
                    )
                elif status == "publication_failed":
                    stmt = stmt.where(PublicationSchedule.status == "publish_failed")
                elif status == "published":
                    stmt = stmt.where(or_(Job.status == "published", PublicationSchedule.status == "published"))
                elif status == "failed":
                    stmt = stmt.where(or_(Job.status == "failed", Job.status.like("%_failed"), PublicationSchedule.status == "publish_failed"))
                elif status == "needs_action":
                    stmt = stmt.where(
                        or_(
                            Job.status.in_(list(NEEDS_ACTION_JOB_STATUSES)),
                            Job.status.like("%_failed"),
                            PublicationSchedule.status == "publish_failed",
                            and_(
                                Job.status == "approved_for_publish",
                                or_(PublicationSchedule.schedule_id.is_(None), PublicationSchedule.status == "cancelled"),
                            ),
                        )
                    )
                else:
                    stmt = stmt.where(Job.status == status)
            if search:
                pattern = f"%{search}%"
                stmt = stmt.where(or_(Job.job_id.like(pattern), TopicRequest.seed_theme.like(pattern), Job.topic_summary.like(pattern)))
            if fallback == "yes":
                stmt = stmt.where(func.coalesce(fallback_count.c.fallback_count, 0) > 0)
            if review:
                stmt = stmt.where(Job.review_state == review)
            raw_rows = session.execute(stmt).all()
            all_rows = []
            for job, seed_theme, notes, duration_ms, fallback_count_value, asset_count, publication_schedule, automation_source in raw_rows:
                origin_display = job_origin_display(resolve_job_origin(job.job_origin, notes, automation_source=automation_source))
                via_display = creation_via_display(
                    resolve_creation_via(job.creation_via, retry_of_job_id=job.retry_of_job_id, notes=notes, automation_source=automation_source)
                )
                if origin and origin_display["value"] != origin:
                    continue
                if via and via_display["value"] != via:
                    continue
                all_rows.append(
                    {
                        "job": job,
                        "seed_theme": seed_theme,
                        "duration_ms": duration_ms,
                        "fallback_count": fallback_count_value,
                        "asset_count": asset_count,
                        "publication_schedule": publication_schedule,
                        "job_origin": origin_display,
                        "creation_via": via_display,
                        "action_summary": self.owner._job_queue_action_summary(job, publication_schedule),
                    }
                )
            total = len(all_rows)
            total_pages = max(1, (total + normalized_per_page - 1) // normalized_per_page)
            normalized_page = min(normalized_page, total_pages)
            offset = (normalized_page - 1) * normalized_per_page
            return {
                "rows": all_rows[offset : offset + normalized_per_page],
                "page": normalized_page,
                "per_page": normalized_per_page,
                "total": total,
                "total_pages": total_pages,
                "has_previous": normalized_page > 1,
                "has_next": normalized_page < total_pages,
            }
        finally:
            session.close()

    def jobs_query_string(self, filters: dict[str, str], page: int, per_page: int) -> str:
        params = {
            "page": page,
            "per_page": per_page,
            **{key: value for key, value in filters.items() if value},
        }
        return urlencode(params)

    def job_list_context(
        self,
        *,
        status: str | None,
        search: str | None,
        fallback: str | None,
        review: str | None,
        origin: str | None,
        via: str | None,
        page: int,
        per_page: int,
    ) -> dict[str, object]:
        filters = {"status": status or "", "search": search or "", "fallback": fallback or "", "review": review or "", "origin": origin or "", "via": via or ""}
        pagination = self.query_jobs(status=status, search=search, fallback=fallback, review=review, origin=origin, via=via, page=page, per_page=per_page)
        pagination["previous_query"] = self.jobs_query_string(filters, max(1, int(pagination["page"]) - 1), int(pagination["per_page"]))
        pagination["next_query"] = self.jobs_query_string(filters, int(pagination["page"]) + 1, int(pagination["per_page"]))
        pagination["current_query"] = self.jobs_query_string(filters, int(pagination["page"]), int(pagination["per_page"]))
        return {
            "rows": pagination["rows"],
            "pagination": pagination,
            "filters": filters,
            "origin_options": job_origin_options(),
            "creation_via_options": creation_via_options(),
        }
