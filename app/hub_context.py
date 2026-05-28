from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from sqlalchemy import case, func, or_, select

from app.db import SessionLocal
from app.job_origin import (
    creation_via_display,
    creation_via_options,
    job_origin_display,
    job_origin_options,
    resolve_creation_via,
    resolve_job_origin,
)
from app.models import AutomationAttempt, ChannelPublication, FallbackEvent, Job, PublicationSchedule, RenderOutput, SceneAsset, Script, TopicPlan, TopicRequest, YouTubeAnalyticsSnapshot
from app.publication_ops import build_growth_score

COMMON_SCHEDULE_TIMEZONES = [
    "UTC",
    "America/Sao_Paulo",
    "America/New_York",
    "Europe/London",
]

JOB_STATUS_LABELS = {
    "queued": "Na fila",
    "running": "Gerando vídeo",
    "script_quality_failed": "Falhou no roteiro",
    "visual_contract_quality_failed": "Falhou no contrato visual",
    "scene_plan_quality_failed": "Falhou nas cenas",
    "asset_quality_failed": "Falhou nos assets",
    "subtitle_quality_failed": "Falhou nas legendas",
    "render_quality_failed": "Falhou no render",
    "monetization_review": "Precisa revisão",
    "blocked_for_monetization": "Bloqueado para publicar",
    "ready_for_upload": "Pronto para aprovar",
    "approved_for_publish": "Aprovado para publicar",
    "unscheduled_approved": "Aprovado sem agenda",
    "scheduled_publication": "Programado",
    "awaiting_confirmation": "Aguardando confirmação",
    "publication_failed": "Falha de publicação",
    "published": "Publicado",
    "approved": "Aprovado",
    "rejected": "Rejeitado",
    "failed": "Falhou",
}

SCHEDULE_STATUS_LABELS = {
    "scheduled": "Programado",
    "publishing": "Publicando",
    "publish_failed": "Falhou no upload",
    "published": "Publicado",
    "cancelled": "Programação limpa",
}

HUB_JOBS_PER_PAGE = 4

class HubContext:
    def __init__(self, settings: Any, orchestrator: Any, automation_service: Any) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.automation_service = automation_service

    def _job_status_label(self, status: str | None) -> str:
        return JOB_STATUS_LABELS.get(str(status or ""), str(status or "-"))

    def _schedule_status_label(self, status: str | None) -> str:
        return SCHEDULE_STATUS_LABELS.get(str(status or ""), str(status or "-"))

    def _job_flow_stage(self, job_status: str | None, schedule_status: str | None = None) -> str:
        normalized = str(job_status or "")
        if schedule_status == "published" or normalized == "published":
            return "Publicado"
        if schedule_status == "awaiting_confirmation":
            return "Confirmação"
        if schedule_status in {"scheduled", "publishing", "publish_failed"} or normalized == "approved_for_publish":
            return "Programação"
        if normalized in {"monetization_review", "ready_for_upload"}:
            return "Aprovação"
        if normalized in {"queued", "running"}:
            return "Geração"
        if normalized in {"blocked_for_monetization", "rejected"}:
            return "Bloqueado"
        if normalized.endswith("_failed") or normalized == "failed":
            return "Falhou"
        return "Geração"

    def _job_next_action(self, job_status: str | None, schedule_status: str | None = None) -> str:
        normalized = str(job_status or "")
        if schedule_status == "published" or normalized == "published":
            return "Registrar métricas do vídeo e seguir para o próximo."
        if schedule_status == "awaiting_confirmation":
            return "Aguardar confirmação real do YouTube antes de marcar como publicado."
        if schedule_status == "publish_failed":
            return "Abrir o job, revisar o erro e repetir a publicação."
        if schedule_status == "publishing":
            return "Aguardar o upload terminar e conferir o resultado."
        if schedule_status == "scheduled":
            return "Conferir data e hora; o worker publica quando o horário vencer."
        if normalized in {"monetization_review", "ready_for_upload"}:
            return "Abrir o job, revisar checklist e clicar em Aprovar."
        if normalized == "approved_for_publish":
            return "Definir data no bloco Agenda ou clicar em Publicar agora."
        if normalized == "blocked_for_monetization":
            return "Rejeitar ou recriar o job após corrigir os bloqueios."
        if normalized == "rejected":
            return "Criar novo job completo ou ajustar o tema."
        if normalized.endswith("_failed") or normalized == "failed":
            return "Abrir o job, ler o erro e tentar novamente."
        if normalized == "running":
            return "Aguardar a geração terminar."
        return "Aguardar a próxima etapa automática."

    def _publication_operational_status(self, job: Job, schedule: PublicationSchedule | None = None) -> dict[str, str]:
        schedule_status = str(schedule.status or "") if schedule else ""
        scheduled_for_utc = None
        if schedule and schedule.scheduled_for_utc:
            scheduled_for_utc = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
        if schedule_status == "published" or job.status == "published":
            status = "published"
        elif schedule_status == "publish_failed":
            status = "publish_failed"
        elif schedule_status == "publishing":
            status = "publishing"
        elif schedule_status == "scheduled" and scheduled_for_utc and scheduled_for_utc <= datetime.now(UTC) and schedule.youtube_video_id:
            status = "awaiting_confirmation"
        elif schedule_status == "scheduled":
            status = "scheduled_publication"
        elif job.status == "approved_for_publish":
            status = "unscheduled_approved"
        else:
            status = str(job.status or "")
        schedule_for_helper = status if status in {"published", "publish_failed", "publishing", "scheduled", "awaiting_confirmation"} else None
        if status == "scheduled_publication":
            schedule_for_helper = "scheduled"
        return {
            "status": status,
            "class_name": status,
            "label": self._job_status_label(status) if status not in SCHEDULE_STATUS_LABELS else self._schedule_status_label(status),
            "stage": self._job_flow_stage(job.status, schedule_for_helper),
            "next_action": self._job_next_action(job.status, schedule_for_helper),
        }

    def _job_progress_snapshot(self, job: Job) -> dict[str, object]:
        return self.orchestrator.build_job_progress(job)

    def _job_origin_display(
        self,
        job: Job,
        topic_request: TopicRequest | None = None,
        automation_source: str | None = None,
    ) -> dict[str, str]:
        return job_origin_display(resolve_job_origin(job.job_origin, topic_request.notes if topic_request else None, automation_source=automation_source))

    def _creation_via_display(
        self,
        job: Job,
        topic_request: TopicRequest | None = None,
        automation_source: str | None = None,
    ) -> dict[str, str]:
        return creation_via_display(
            resolve_creation_via(
                job.creation_via,
                retry_of_job_id=job.retry_of_job_id,
                notes=topic_request.notes if topic_request else None,
                automation_source=automation_source,
            )
        )

    def _job_action_guide(
        self,
        job: Job,
        monetization_report: dict[str, object] | None,
        schedule_display: dict[str, str | None] | None,
        youtube_integration: dict[str, object],
    ) -> dict[str, str]:
        job_status = str(job.status or "")
        schedule_status = str((schedule_display or {}).get("status") or "")
        if schedule_status == "published" or job_status == "published":
            return {
                "step": "4. Publicado",
                "title": "Upload concluído",
                "body": "O vídeo já foi publicado. Use a seção de performance para registrar os números do YouTube Studio.",
            }
        if schedule_status == "publish_failed":
            return {
                "step": "4. Repetir publicação",
                "title": "Upload falhou",
                "body": "Revise a tentativa de publicação logo abaixo e dispare um novo upload quando o erro estiver claro.",
            }
        if schedule_status == "scheduled":
            return {
                "step": "3. Programado",
                "title": "O vídeo já está na agenda",
                "body": "Confira data, hora e visibilidade. Se quiser postar imediatamente, use o botão de publicar agora.",
            }
        if job_status == "approved_for_publish":
            publish_mode = str(youtube_integration.get("publish_mode") or "manual")
            helper = "No modo api, o worker publica no horário salvo." if publish_mode == "api" else "No modo manual, o hub só registra o que você publicou no Studio."
            return {
                "step": "3. Programar ou publicar",
                "title": "A aprovação terminou",
                "body": f"Agora o vídeo já pode entrar na agenda. Preencha data, hora e visibilidade no bloco Agenda. {helper}",
            }
        if job_status in {"monetization_review", "ready_for_upload"}:
            hard_blockers = list((monetization_report or {}).get("hard_blockers") or [])
            manual_required = list((monetization_report or {}).get("manual_required") or [])
            if hard_blockers:
                return {
                    "step": "2. Corrigir antes de aprovar",
                    "title": "Ainda não dá para aprovar",
                    "body": "O relatório de monetização encontrou bloqueios. Revise os bloqueios e rejeite ou regenere o job.",
                }
            if manual_required:
                return {
                    "step": "2. Aprovar vídeo",
                    "title": "Falta revisão humana",
                    "body": "Marque as confirmações exigidas na seção Review e clique em Aprovar. A agenda só libera depois disso.",
                }
            return {
                "step": "2. Aprovar vídeo",
                "title": "Pronto para aprovação",
                "body": "O vídeo já passou nos gates automáticos. Revise rápido o conteúdo e clique em Aprovar para liberar a agenda.",
            }
        if job_status in {"queued", "running"}:
            return {
                "step": "1. Gerando vídeo",
                "title": "A geração ainda está em andamento",
                "body": "Espere o pipeline terminar. Quando o status virar revisão, a ação principal passa a ser aprovar o vídeo.",
            }
        if job_status in {"blocked_for_monetization", "rejected"} or job_status.endswith("_failed") or job_status == "failed":
            return {
                "step": "1. Corrigir",
                "title": "Este job não chegou à publicação",
                "body": "Use Reject ou Criar novo job completo depois de revisar a causa principal na página.",
            }
        return {
            "step": "Fluxo",
            "title": "Acompanhe o próximo passo",
            "body": self._job_next_action(job_status, schedule_status or None),
        }

    def _clamp_page(self, value: int | None) -> int:
        return max(1, int(value or 1))

    def _clamp_per_page(self, value: int | None) -> int:
        return max(1, min(100, int(value or HUB_JOBS_PER_PAGE)))

    def _query_jobs(
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
            normalized_page = self._clamp_page(page)
            normalized_per_page = self._clamp_per_page(per_page)
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

    def _jobs_query_string(self, filters: dict[str, str], page: int, per_page: int) -> str:
        params = {
            "page": page,
            "per_page": per_page,
            **{key: value for key, value in filters.items() if value},
        }
        return urlencode(params)

    def _job_list_context(
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
        pagination = self._query_jobs(status=status, search=search, fallback=fallback, review=review, origin=origin, via=via, page=page, per_page=per_page)
        pagination["previous_query"] = self._jobs_query_string(filters, max(1, int(pagination["page"]) - 1), int(pagination["per_page"]))
        pagination["next_query"] = self._jobs_query_string(filters, int(pagination["page"]) + 1, int(pagination["per_page"]))
        pagination["current_query"] = self._jobs_query_string(filters, int(pagination["page"]), int(pagination["per_page"]))
        return {
            "rows": pagination["rows"],
            "pagination": pagination,
            "filters": filters,
            "origin_options": job_origin_options(),
            "creation_via_options": creation_via_options(),
        }

    def _schedule_display(self, schedule: PublicationSchedule | None) -> dict[str, str | None] | None:
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

    def _publication_title(self, job: Job, topic_request: TopicRequest | None, script: Script | None) -> str:
        return (
            (script.title if script else None)
            or job.topic_summary
            or (topic_request.seed_theme if topic_request else None)
            or job.job_id
        )

    def _ready_to_schedule_entries(self, session, limit: int | None = None) -> list[dict[str, object]]:
        stmt = (
            select(Job, TopicRequest, Script, PublicationSchedule)
            .join(TopicRequest, TopicRequest.job_id == Job.job_id)
            .join(Script, Script.job_id == Job.job_id, isouter=True)
            .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
            .where(Job.status == "approved_for_publish")
            .where(or_(PublicationSchedule.schedule_id.is_(None), PublicationSchedule.status == "cancelled"))
            .order_by(Job.created_at.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()
        return [
            {
                "job_id": job.job_id,
                "title": self._publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "job_status": job.status,
                "schedule": self._schedule_display(schedule) if schedule else None,
            }
            for job, topic_request, script, schedule in rows
        ]

    def _effective_youtube_redirect_uri(self, request: Request) -> str:
        return self.settings.youtube_oauth_redirect_uri or f"{str(request.base_url).rstrip('/')}/youtube/oauth/callback"

    def _youtube_integration_context(self, request: Request) -> dict[str, object]:
        redirect_uri = self._effective_youtube_redirect_uri(request)
        status = self.orchestrator.youtube.connection_status(redirect_uri)
        missing_items = list(status.missing_items)
        if not self.settings.youtube_channel_id:
            missing_items.append("YTS_YOUTUBE_CHANNEL_ID ainda não está configurado.")
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
            "client_configured": status.client_configured,
            "dependencies_available": status.dependencies_available,
            "redirect_uri": redirect_uri,
            "granted_scopes": status.granted_scopes,
            "connected_at": status.connected_at,
            "token_expires_at": status.token_expires_at,
            "missing_items": missing_items,
        }

    def _tiktok_integration_context(self) -> dict[str, object]:
        status = self.orchestrator.tiktok.connection_status()
        return {
            "enabled": status.enabled,
            "token_configured": status.token_configured,
            "ready": status.ready,
            "missing_items": status.missing_items,
            "privacy_level": self.settings.tiktok_privacy_level,
            "retropost_daily_limit": self.settings.tiktok_retropost_daily_limit,
        }

    def _publication_dashboard_context(self, request: Request, limit: int = 6) -> dict[str, object]:
        with SessionLocal() as session:
            ready_to_schedule = self._ready_to_schedule_entries(session, limit=limit)
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
            publishing_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "publishing")
            ) or 0
            failed_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "publish_failed")
            ) or 0
            published_count = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.status == "published")
            ) or 0
            tiktok_scheduled_count = session.scalar(
                select(func.count())
                .select_from(ChannelPublication)
                .where(ChannelPublication.channel == "tiktok")
                .where(ChannelPublication.status.in_(["scheduled", "publishing", "processing"]))
            ) or 0
            tiktok_published_count = session.scalar(
                select(func.count()).select_from(ChannelPublication).where(ChannelPublication.channel == "tiktok").where(ChannelPublication.status == "published")
            ) or 0
            tiktok_failed_count = session.scalar(
                select(func.count()).select_from(ChannelPublication).where(ChannelPublication.channel == "tiktok").where(ChannelPublication.status == "publish_failed")
            ) or 0

        upcoming_schedule = [
            {
                "job_id": job.job_id,
                "title": self._publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self._schedule_display(schedule),
            }
            for schedule, job, topic_request, script in schedule_rows
        ]

        recent_publications = [
            {
                "job_id": job.job_id,
                "title": self._publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self._schedule_display(schedule),
            }
            for schedule, job, topic_request, script in published_rows
        ]
        with SessionLocal() as session:
            analytics_rows = session.execute(
                select(YouTubeAnalyticsSnapshot, Job, TopicRequest, Script, TopicPlan)
                .join(Job, Job.job_id == YouTubeAnalyticsSnapshot.job_id)
                .join(TopicRequest, TopicRequest.job_id == Job.job_id, isouter=True)
                .join(Script, Script.job_id == Job.job_id, isouter=True)
                .join(TopicPlan, TopicPlan.job_id == Job.job_id, isouter=True)
                .order_by(YouTubeAnalyticsSnapshot.fetched_at.desc())
                .limit(100)
            ).all()
            analytics_snapshot_count = session.scalar(select(func.count()).select_from(YouTubeAnalyticsSnapshot)) or 0
            jobs_missing_analytics = session.scalar(
                select(func.count())
                .select_from(PublicationSchedule)
                .where(PublicationSchedule.youtube_video_id.is_not(None))
                .where(~PublicationSchedule.job_id.in_(select(YouTubeAnalyticsSnapshot.job_id)))
            ) or 0
        latest_snapshots: dict[str, dict[str, object]] = {}
        for snapshot, job, topic_request, script, topic_plan in analytics_rows:
            if job.job_id in latest_snapshots:
                continue
            summary = dict(snapshot.summary_metrics or {})
            score = build_growth_score(summary, fetched_at=snapshot.fetched_at)
            latest_snapshots[job.job_id] = {
                "job_id": job.job_id,
                "title": self._publication_title(job, topic_request, script),
                "canonical_topic": topic_plan.canonical_topic if topic_plan else topic_request.seed_theme if topic_request else None,
                "hook": script.hook if script else None,
                "fetched_at": snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
                "start_date": snapshot.start_date,
                "end_date": snapshot.end_date,
                "youtube_video_id": snapshot.youtube_video_id,
                "score": score["score"],
                "confidence": score["confidence"],
                "confidence_label": score["confidence_label"],
                "stale": score["stale"],
                "views": score["views"],
                "retention_percent": score["retention_percent"],
                "average_view_duration": score["average_view_duration"],
                "shares": score["shares"],
                "subscribers_gained": score["subscribers_gained"],
                "likes": score["likes"],
                "comments": score["comments"],
                "_sort_key": score["sort_key"],
            }
        top_performers = sorted(
            latest_snapshots.values(),
            key=lambda item: item.get("_sort_key") or (-1, 0, 0, 0, 0),
            reverse=True,
        )[:5]
        for item in top_performers:
            item.pop("_sort_key", None)
        all_snapshot_items = list(latest_snapshots.values())
        reliable_snapshot_count = sum(1 for item in all_snapshot_items if item.get("confidence") == "confiavel")
        low_confidence_count = sum(1 for item in all_snapshot_items if item.get("confidence") != "confiavel")
        stale_snapshot_count = sum(1 for item in all_snapshot_items if item.get("stale"))
        try:
            sync_candidates = self.orchestrator.youtube_analytics_sync_candidates()
        except Exception:
            sync_candidates = []
        recommendations = self._growth_quick_recommendations(
            top_performers=top_performers,
            jobs_missing_analytics=jobs_missing_analytics,
            reliable_snapshot_count=reliable_snapshot_count,
            low_confidence_count=low_confidence_count,
            stale_snapshot_count=stale_snapshot_count,
            sync_candidates_count=len(sync_candidates),
        )
        return {
            "integration": self._youtube_integration_context(request),
            "tiktok_integration": self._tiktok_integration_context(),
            "automation": self.automation_service.dashboard_context(),
            "ready_to_schedule": ready_to_schedule,
            "upcoming_schedule": upcoming_schedule,
            "recent_publications": recent_publications,
            "growth": {
                "window_days": 28,
                "volume_minimum": 100,
                "active_window_days": self.settings.performance_sync_active_window_days,
                "archive_window_days": self.settings.performance_sync_archive_window_days,
                "collection_enabled": self.settings.performance_collection_enabled,
                "sync_candidates_count": len(sync_candidates),
                "snapshot_count": analytics_snapshot_count,
                "jobs_missing_analytics": jobs_missing_analytics,
                "reliable_snapshot_count": reliable_snapshot_count,
                "low_confidence_count": low_confidence_count,
                "stale_snapshot_count": stale_snapshot_count,
                "top_performers": top_performers,
                "recommendations": recommendations,
                "last_snapshot_at": next(iter(latest_snapshots.values()), {}).get("fetched_at") if latest_snapshots else None,
                "weekly_report": {
                    "ready": reliable_snapshot_count >= 3 and analytics_snapshot_count >= 5,
                    "minimum_snapshots": 5,
                    "minimum_reliable_jobs": 3,
                    "status_label": "base suficiente" if reliable_snapshot_count >= 3 and analytics_snapshot_count >= 5 else "dados insuficientes",
                },
            },
            "metrics": {
                "unscheduled_approved_count": unscheduled_approved_count,
                "scheduled_count": scheduled_count,
                "publishing_count": publishing_count,
                "failed_count": failed_count,
                "published_count": published_count,
                "awaiting_approval_count": awaiting_approval_count,
                "tiktok_scheduled_count": tiktok_scheduled_count,
                "tiktok_published_count": tiktok_published_count,
                "tiktok_failed_count": tiktok_failed_count,
            },
        }

    def _metric_number(self, value: object, *, as_int: bool = False) -> int | float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if as_int:
            return int(number)
        return round(number, 2)

    def _growth_quick_recommendations(
        self,
        *,
        top_performers: list[dict[str, object]],
        jobs_missing_analytics: int,
        reliable_snapshot_count: int,
        low_confidence_count: int,
        stale_snapshot_count: int,
        sync_candidates_count: int,
    ) -> list[dict[str, object]]:
        recommendations: list[dict[str, object]] = []
        if sync_candidates_count:
            recommendations.append(
                {
                    "title": "Atualizar coleta pendente",
                    "body": f"{sync_candidates_count} publicação(ões) já podem receber novo snapshot de performance.",
                    "impact": "Base mais fresca para ranking e recomendações.",
                    "action_label": "Rodar coleta",
                    "action_kind": "manual_sync_batch",
                }
            )
        if jobs_missing_analytics:
            recommendations.append(
                {
                    "title": "Fechar vínculos sem Analytics",
                    "body": f"{jobs_missing_analytics} publicação(ões) ainda não têm snapshot salvo.",
                    "impact": "Aumenta cobertura antes do relatório semanal.",
                    "action_label": "Ver pendências",
                    "action_kind": "review_missing_analytics",
                }
            )
        best = top_performers[0] if top_performers else None
        if best and best.get("confidence") == "confiavel":
            recommendations.append(
                {
                    "title": "Criar variação da linha vencedora",
                    "body": str(best.get("canonical_topic") or best.get("title") or "linha com melhor retenção"),
                    "impact": f"Score {best.get('score') or '-'} com amostra confiável.",
                    "action_label": "Abrir referência",
                    "action_kind": "open_job",
                    "job_id": best.get("job_id"),
                }
            )
        elif best:
            recommendations.append(
                {
                    "title": "Aguardar volume antes de repetir",
                    "body": str(best.get("canonical_topic") or best.get("title") or "linha ainda sem amostra suficiente"),
                    "impact": "Evita tratar poucos views como padrão vencedor.",
                    "action_label": "Acompanhar",
                    "action_kind": "open_job",
                    "job_id": best.get("job_id"),
                }
            )
        if reliable_snapshot_count < 3:
            recommendations.append(
                {
                    "title": "Coletar mais base confiável",
                    "body": f"{reliable_snapshot_count} de 3 Jobs confiáveis para liberar relatório semanal.",
                    "impact": "Reduz chance de diagnóstico por amostra fraca.",
                    "action_label": "Continuar coleta",
                    "action_kind": "collect_more",
                }
            )
        if low_confidence_count and len(recommendations) < 5:
            recommendations.append(
                {
                    "title": "Separar baixa confiança",
                    "body": f"{low_confidence_count} snapshot(s) abaixo do volume mínimo de 100 views.",
                    "impact": "Mantém views baixos fora do ranking decisivo.",
                    "action_label": "Ver ranking",
                    "action_kind": "review_low_confidence",
                }
            )
        if stale_snapshot_count and len(recommendations) < 5:
            recommendations.append(
                {
                    "title": "Revisar snapshots desatualizados",
                    "body": f"{stale_snapshot_count} leitura(s) têm mais de 48h.",
                    "impact": "Evita decidir com dado antigo dentro da janela ativa.",
                    "action_label": "Atualizar",
                    "action_kind": "manual_sync_batch",
                }
            )
        return recommendations[:5]

    def _parse_calendar_month(self, month: str | None) -> date:
        normalized = str(month or "").strip()
        if not normalized:
            now = datetime.now(UTC)
            return date(now.year, now.month, 1)
        try:
            parsed = datetime.strptime(normalized, "%Y-%m")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="month must use YYYY-MM") from exc
        return date(parsed.year, parsed.month, 1)

    def _shift_month(self, month_start: date, delta: int) -> date:
        month_index = month_start.month - 1 + delta
        year = month_start.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, 1)

    def _calendar_context(self, month: str | None) -> dict[str, object]:
        month_start = self._parse_calendar_month(month)
        previous_month = self._shift_month(month_start, -1)
        next_month = self._shift_month(month_start, 1)
        month_names_pt_br = [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        month_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
        with SessionLocal() as session:
            ready_to_schedule = self._ready_to_schedule_entries(session)
            schedule_rows = session.execute(
                select(PublicationSchedule, Job, TopicRequest, Script)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .join(TopicRequest, TopicRequest.job_id == PublicationSchedule.job_id)
                .join(Script, Script.job_id == PublicationSchedule.job_id, isouter=True)
                .where(PublicationSchedule.status.in_(["scheduled", "publishing", "publish_failed", "published"]))
                .order_by(PublicationSchedule.scheduled_for_utc)
            ).all()

        entries_by_day: dict[date, list[dict[str, object]]] = {}
        scheduled_count = 0
        published_count = 0
        for schedule, job, topic_request, script in schedule_rows:
            scheduled_for_utc = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
            local_dt = scheduled_for_utc.astimezone(ZoneInfo(schedule.timezone))
            local_day = local_dt.date()
            if local_day.year != month_start.year or local_day.month != month_start.month:
                continue
            title = script.title if script else (job.topic_summary or topic_request.seed_theme)
            entry = {
                "job_id": job.job_id,
                "title": title,
                "seed_theme": topic_request.seed_theme,
                "job_status": job.status,
                "review_state": job.review_state,
                "schedule_status": schedule.status,
                "local_time": local_dt.strftime("%H:%M"),
                "timezone": schedule.timezone,
                "youtube_visibility": schedule.youtube_visibility,
                "youtube_url": schedule.youtube_url,
            }
            entries_by_day.setdefault(local_day, []).append(entry)
            if schedule.status == "scheduled":
                scheduled_count += 1
            if schedule.status == "published":
                published_count += 1

        weeks: list[list[dict[str, object]]] = []
        for week in month_weeks:
            week_cells = []
            for day in week:
                week_cells.append(
                    {
                        "date": day,
                        "iso_date": day.isoformat(),
                        "day_number": day.day,
                        "is_current_month": day.month == month_start.month,
                        "entries": entries_by_day.get(day, []),
                    }
                )
            weeks.append(week_cells)

        return {
            "month_value": month_start.strftime("%Y-%m"),
            "month_label": f"{month_names_pt_br[month_start.month - 1]} {month_start.year}",
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "weeks": weeks,
            "scheduled_count": scheduled_count,
            "published_count": published_count,
            "ready_to_schedule": ready_to_schedule,
            "common_schedule_timezones": COMMON_SCHEDULE_TIMEZONES,
            "default_schedule_timezone": "America/Sao_Paulo",
            "default_schedule_time": "15:00",
            "default_youtube_visibility": "public" if self.settings.youtube_publish_mode == "api" else "private",
        }

    def _resolve_job_id(self, session, job_id: str) -> str:
        if session.get(Job, job_id):
            return job_id
        matches = session.scalars(select(Job.job_id).where(Job.job_id.like(f"{job_id}%")).order_by(Job.created_at.desc()).limit(2)).all()
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="job id prefix is ambiguous")
        raise KeyError(job_id)
