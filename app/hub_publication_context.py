from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.backlog_recovery import BacklogRecoveryService
from app.config import Settings
from app.db import SessionLocal
from app.domain_contracts import JOB_STATUS_APPROVED_FOR_PUBLISH
from app.hub_status import NEEDS_ACTION_JOB_STATUSES
from app.models import (
    Job,
    PublicationSchedule,
    Script,
    TopicRequest,
)

if TYPE_CHECKING:
    from app.automation import AutomationService
    from app.orchestrator import JobOrchestrator


class HubPublicationContext:
    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: JobOrchestrator,
        automation_service: AutomationService,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.automation_service = automation_service

    def effective_youtube_redirect_uri(self, request: Request) -> str:
        return self.settings.youtube_oauth_redirect_uri or f"{str(request.base_url).rstrip('/')}/youtube/oauth/callback"

    def youtube_integration_context(self, request: Request) -> dict[str, object]:
        redirect_uri = self.effective_youtube_redirect_uri(request)
        status = self.orchestrator.youtube.connection_status(redirect_uri)
        missing_items = list(status.missing_items)
        if not self.settings.youtube_channel_id:
            missing_items.append("SHORTSFLOW_YOUTUBE_CHANNEL_ID ainda não está configurado.")
        if self.settings.youtube_publish_mode == "manual":
            stage = "manual_only"
            headline = "Agenda local ativa. A publicação continua manual no YouTube Studio."
        elif self.settings.youtube_api_enabled and status.connected and not missing_items:
            stage = "api_ready"
            headline = "OAuth conectado e worker pronto para publicar automaticamente nos horários programados."
        else:
            stage = "config_partial"
            headline = "A integração real existe, mas ainda falta fechar configuração ou conexão OAuth."
        return {
            "stage": stage,
            "headline": headline,
            "publish_mode": self.settings.youtube_publish_mode,
            "api_enabled": self.settings.youtube_api_enabled,
            "channel_id": self.settings.youtube_channel_id,
            "connected": status.connected,
            "publish_connected": status.publish_connected,
            "analytics_connected": status.analytics_connected,
            "analytics_missing_items": status.analytics_missing_items or [],
            "reporting_connected": status.reporting_connected,
            "reporting_missing_items": status.reporting_missing_items or [],
            "client_configured": status.client_configured,
            "dependencies_available": status.dependencies_available,
            "redirect_uri": redirect_uri,
            "granted_scopes": status.granted_scopes,
            "connected_at": status.connected_at,
            "token_expires_at": status.token_expires_at,
            "missing_items": missing_items,
        }

    def maintenance_summary(self, *, future_scheduled_count: int, needs_action_count: int) -> dict[str, object]:
        try:
            backlog = BacklogRecoveryService(self.settings, self.orchestrator).scan(limit=50)
            summary = backlog.to_dict()["summary"]
        except Exception:  # noqa: BLE001
            summary = {}
        checkpoint_count = int(summary.get("needs_checkpoint") or 0)
        near_publishable_count = int(summary.get("near_publishable") or 0)
        minimum = int(getattr(self.settings, "watchdog_min_future_coverage_days", 3))
        action = "ok"
        action_label = "Nada urgente"
        action_body = "Agenda e revisão não indicam ação imediata."
        if future_scheduled_count < minimum:
            action = "recover_schedule"
            action_label = "Rodar recovery seguro"
            action_body = "Cobertura futura abaixo do mínimo; tente recuperar backlog sem publicar checkpoints."
        elif checkpoint_count:
            action = "review_checkpoints"
            action_label = "Revisar checkpoint humano"
            action_body = "Há jobs bloqueados por duplicidade ou bloqueio técnico; precisam de decisão humana."
        elif near_publishable_count:
            action = "recover_near_publishable"
            action_label = "Recuperar jobs próximos"
            action_body = "Há jobs perto de publicação que podem passar por reparo seguro."
        return {
            "future_scheduled_count": future_scheduled_count,
            "minimum_future_scheduled_count": minimum,
            "needs_action_count": needs_action_count,
            "checkpoint_count": checkpoint_count,
            "near_publishable_count": near_publishable_count,
            "recommended_action": action,
            "recommended_action_label": action_label,
            "recommended_action_body": action_body,
        }

    def schedule_display(self, schedule: PublicationSchedule | None) -> dict[str, str | None] | None:
        if schedule is None:
            return None
        scheduled_for_utc = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
        published_at = schedule.published_at if schedule.published_at and schedule.published_at.tzinfo else (
            schedule.published_at.replace(tzinfo=UTC) if schedule.published_at else None
        )
        local_dt = scheduled_for_utc.astimezone(ZoneInfo(schedule.timezone))
        published_local = published_at.astimezone(ZoneInfo(schedule.timezone)) if published_at else None
        return {
            "status": schedule.status,
            "scheduled_for_utc": scheduled_for_utc.isoformat(),
            "scheduled_for_local": local_dt.isoformat(),
            "scheduled_for_local_form": local_dt.strftime("%Y-%m-%dT%H:%M"),
            "local_date": local_dt.date().isoformat(),
            "local_time": local_dt.strftime("%H:%M"),
            "timezone": schedule.timezone,
            "youtube_visibility": schedule.youtube_visibility,
            "notes": schedule.notes,
            "published_at": published_local.isoformat() if published_local else None,
            "published_local_label": published_local.strftime("%d/%m/%Y %H:%M") if published_local else None,
            "youtube_video_id": schedule.youtube_video_id,
            "youtube_url": schedule.youtube_url,
        }

    def publication_title(self, job: Job, topic_request: TopicRequest | None, script: Script | None) -> str:
        return (
            (script.title if script else None)
            or job.topic_summary
            or (topic_request.seed_theme if topic_request else None)
            or job.job_id
        )

    def ready_to_schedule_entries(self, session: Session, limit: int | None = None) -> list[dict[str, object]]:
        stmt = (
            select(Job, TopicRequest, Script, PublicationSchedule)
            .join(TopicRequest, TopicRequest.job_id == Job.job_id)
            .join(Script, Script.job_id == Job.job_id, isouter=True)
            .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
            .where(Job.status == JOB_STATUS_APPROVED_FOR_PUBLISH)
            .where(or_(PublicationSchedule.schedule_id.is_(None), PublicationSchedule.status == "cancelled"))
            .order_by(Job.created_at.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()
        return [
            {
                "job_id": job.job_id,
                "title": self.publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "job_status": job.status,
                "schedule": self.schedule_display(schedule) if schedule else None,
            }
            for job, topic_request, script, schedule in rows
        ]

    def dashboard_context(self, request: Request, limit: int = 6) -> dict[str, object]:
        refreshed_at = datetime.now(UTC)
        with SessionLocal() as session:
            ready_to_schedule = self.ready_to_schedule_entries(session, limit)
            schedule_rows = session.execute(
                select(PublicationSchedule, Job, TopicRequest, Script)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .join(TopicRequest, TopicRequest.job_id == PublicationSchedule.job_id)
                .join(Script, Script.job_id == PublicationSchedule.job_id, isouter=True)
                .where(PublicationSchedule.status.in_(["scheduled", "publishing", "publish_failed"]))
                .order_by(PublicationSchedule.scheduled_for_utc.asc())
                .limit(limit)
            ).all()
            published_rows = session.execute(
                select(PublicationSchedule, Job, TopicRequest, Script)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .join(TopicRequest, TopicRequest.job_id == PublicationSchedule.job_id)
                .join(Script, Script.job_id == PublicationSchedule.job_id, isouter=True)
                .where(PublicationSchedule.status == "published")
                .order_by(PublicationSchedule.published_at.desc(), PublicationSchedule.updated_at.desc())
                .limit(limit)
            ).all()
            awaiting_approval_count = session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.status.in_(["monetization_review", "ready_for_upload"]))
            ) or 0
            needs_action_count = session.scalar(
                select(func.count(func.distinct(Job.job_id)))
                .select_from(Job)
                .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
                .where(
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
            ) or 0
            unscheduled_approved_count = session.scalar(
                select(func.count())
                .select_from(Job)
                .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
                .where(Job.status == "approved_for_publish")
                .where(or_(PublicationSchedule.schedule_id.is_(None), PublicationSchedule.status == "cancelled"))
            ) or 0
            scheduled_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "scheduled")
            ) or 0
            future_scheduled_count = session.scalar(
                select(func.count())
                .select_from(PublicationSchedule)
                .where(PublicationSchedule.status.in_(["scheduled", "publishing"]))
                .where(PublicationSchedule.scheduled_for_utc > refreshed_at)
            ) or 0
            publishing_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "publishing")
            ) or 0
            failed_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "publish_failed")
            ) or 0
            published_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "published")
            ) or 0

        upcoming_schedule = [
            {
                "job_id": job.job_id,
                "title": self.publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self.schedule_display(schedule),
            }
            for schedule, job, topic_request, script in schedule_rows
        ]

        recent_publications = [
            {
                "job_id": job.job_id,
                "title": self.publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self.schedule_display(schedule),
            }
            for schedule, job, topic_request, script in published_rows
        ]
        return {
            "integration": self.youtube_integration_context(request),
            "automation": self.automation_service.dashboard_context(),
            "maintenance": self.maintenance_summary(future_scheduled_count=int(future_scheduled_count), needs_action_count=int(needs_action_count)),
            "ready_to_schedule": ready_to_schedule,
            "upcoming_schedule": upcoming_schedule,
            "recent_publications": recent_publications,
            "refreshed_at_label": refreshed_at.strftime("%H:%M:%S UTC"),
            "metrics": {
                "unscheduled_approved_count": unscheduled_approved_count,
                "scheduled_count": scheduled_count,
                "publishing_count": publishing_count,
                "failed_count": failed_count,
                "published_count": published_count,
                "awaiting_approval_count": awaiting_approval_count,
                "needs_action_count": needs_action_count,
            },
        }
