from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import and_, func, or_, select

from app.db import SessionLocal
from app.growth_metrics import build_growth_score
from app.hub_status import NEEDS_ACTION_JOB_STATUSES
from app.models import ChannelPublication, Job, PublicationSchedule, Script, TopicPlan, TopicRequest, YouTubeAnalyticsSnapshot

class HubPublicationContext:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def orchestrator(self) -> Any:
        return self.owner.orchestrator

    @property
    def automation_service(self) -> Any:
        return self.owner.automation_service

    def effective_youtube_redirect_uri(self, request: Request) -> str:
        return self.settings.youtube_oauth_redirect_uri or f"{str(request.base_url).rstrip('/')}/youtube/oauth/callback"

    def youtube_integration_context(self, request: Request) -> dict[str, object]:
        redirect_uri = self.effective_youtube_redirect_uri(request)
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

    def tiktok_integration_context(self) -> dict[str, object]:
        status = self.orchestrator.tiktok.connection_status()
        return {
            "enabled": status.enabled,
            "token_configured": status.token_configured,
            "ready": status.ready,
            "missing_items": status.missing_items,
            "privacy_level": self.settings.tiktok_privacy_level,
            "retropost_daily_limit": self.settings.tiktok_retropost_daily_limit,
        }

    def dashboard_context(self, request: Request, limit: int = 6) -> dict[str, object]:
        refreshed_at = datetime.now(UTC)
        with SessionLocal() as session:
            ready_to_schedule = self.owner._ready_to_schedule_entries(session, limit=limit)
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
                "title": self.owner._publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self.owner._schedule_display(schedule),
            }
            for schedule, job, topic_request, script in schedule_rows
        ]

        recent_publications = [
            {
                "job_id": job.job_id,
                "title": self.owner._publication_title(job, topic_request, script),
                "seed_theme": topic_request.seed_theme if topic_request else None,
                "job_status": job.status,
                "schedule": self.owner._schedule_display(schedule),
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
            analytics_job_count = session.scalar(select(func.count(func.distinct(YouTubeAnalyticsSnapshot.job_id))).select_from(YouTubeAnalyticsSnapshot)) or 0
            published_with_youtube_id = session.scalar(
                select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.youtube_video_id.is_not(None))
            ) or 0
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
                "title": self.owner._publication_title(job, topic_request, script),
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
        recommendations = self.growth_quick_recommendations(
            top_performers=top_performers,
            jobs_missing_analytics=jobs_missing_analytics,
            reliable_snapshot_count=reliable_snapshot_count,
            low_confidence_count=low_confidence_count,
            stale_snapshot_count=stale_snapshot_count,
            sync_candidates_count=len(sync_candidates),
        )
        analytics_coverage_percent = round((analytics_job_count / published_with_youtube_id) * 100) if published_with_youtube_id else 0
        if reliable_snapshot_count >= 3 and analytics_snapshot_count >= 5:
            decision_status = "base pronta para decisão editorial"
            decision_headline = "Já dá para comparar linhas editoriais."
            decision_body = "Use retenção e volume confiável para repetir temas vencedores e pausar linhas fracas."
        elif len(sync_candidates):
            decision_status = "coleta pendente"
            decision_headline = "A prioridade é coletar Analytics agora."
            decision_body = f"{len(sync_candidates)} publicação(ões) já podem virar evidência. Sem isso, qualquer ranking editorial é chute."
        elif jobs_missing_analytics:
            decision_status = "base incompleta"
            decision_headline = "Faltam vínculos de Analytics antes de decidir pauta."
            decision_body = f"{jobs_missing_analytics} publicação(ões) ainda não têm snapshot salvo no hub."
        else:
            decision_status = "aguardando volume"
            decision_headline = "Acompanhe até a amostra ficar confiável."
            decision_body = "Ainda não há três Jobs com volume mínimo para orientar o próximo lote editorial."
        action_items = [
            {
                "kind": "sync_due",
                "priority": "P1",
                "title": "Coletar Analytics pendente",
                "metric": len(sync_candidates),
                "metric_label": "prontas",
                "body": "Atualiza a base usada para ranking, confiança e recomendações.",
                "enabled": bool(self.settings.performance_collection_enabled and len(sync_candidates)),
                "action_label": "Coletar pendentes",
            },
            {
                "kind": "schedule_backlog",
                "priority": "P1" if unscheduled_approved_count else "OK",
                "title": "Preencher calendário",
                "metric": unscheduled_approved_count,
                "metric_label": "aprovados sem horário",
                "body": "Jobs aprovados ainda não aparecem como publicação futura enquanto não têm horário salvo.",
                "enabled": bool(unscheduled_approved_count),
                "action_label": "Abrir calendário",
                "href": "/calendar",
            },
            {
                "kind": "review_queue",
                "priority": "P2" if awaiting_approval_count else "OK",
                "title": "Liberar ou bloquear revisão",
                "metric": needs_action_count,
                "metric_label": "precisam de ação",
                "body": "Converte Jobs aproveitáveis em agenda ou remove bloqueios antes que a fila perca valor.",
                "enabled": bool(needs_action_count),
                "action_label": "Abrir fila",
                "href": "/jobs?status=needs_action",
            },
        ]
        scoreboard = [
            {
                "label": "Cobertura Analytics",
                "value": f"{analytics_coverage_percent}%",
                "detail": f"{analytics_job_count} de {published_with_youtube_id} publicações com snapshot",
                "state": "bad" if published_with_youtube_id and analytics_coverage_percent < 50 else "ok",
            },
            {
                "label": "Base confiável",
                "value": f"{reliable_snapshot_count}/3",
                "detail": "mínimo para relatório editorial",
                "state": "ok" if reliable_snapshot_count >= 3 else "warn",
            },
            {
                "label": "Agenda futura",
                "value": str(scheduled_count),
                "detail": f"{unscheduled_approved_count} aprovados ainda livres",
                "state": "warn" if unscheduled_approved_count else "ok",
            },
            {
                "label": "Fila de revisão",
                "value": str(awaiting_approval_count),
                "detail": "Jobs esperando aprovação ou correção",
                "state": "warn" if awaiting_approval_count else "ok",
            },
        ]
        return {
            "integration": self.youtube_integration_context(request),
            "tiktok_integration": self.tiktok_integration_context(),
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
                "analytics_job_count": analytics_job_count,
                "published_with_youtube_id": published_with_youtube_id,
                "analytics_coverage_percent": analytics_coverage_percent,
                "jobs_missing_analytics": jobs_missing_analytics,
                "reliable_snapshot_count": reliable_snapshot_count,
                "low_confidence_count": low_confidence_count,
                "stale_snapshot_count": stale_snapshot_count,
                "top_performers": top_performers,
                "recommendations": recommendations,
                "scoreboard": scoreboard,
                "action_items": action_items,
                "decision": {
                    "status": decision_status,
                    "headline": decision_headline,
                    "body": decision_body,
                },
                "last_snapshot_at": next(iter(latest_snapshots.values()), {}).get("fetched_at") if latest_snapshots else None,
                "weekly_report": {
                    "ready": reliable_snapshot_count >= 3 and analytics_snapshot_count >= 5,
                    "minimum_snapshots": 5,
                    "minimum_reliable_jobs": 3,
                    "status_label": "base suficiente" if reliable_snapshot_count >= 3 and analytics_snapshot_count >= 5 else "dados insuficientes",
                },
                "refreshed_at_label": refreshed_at.strftime("%H:%M:%S UTC"),
            },
            "metrics": {
                "unscheduled_approved_count": unscheduled_approved_count,
                "scheduled_count": scheduled_count,
                "publishing_count": publishing_count,
                "failed_count": failed_count,
                "published_count": published_count,
                "awaiting_approval_count": awaiting_approval_count,
                "needs_action_count": needs_action_count,
                "tiktok_scheduled_count": tiktok_scheduled_count,
                "tiktok_published_count": tiktok_published_count,
                "tiktok_failed_count": tiktok_failed_count,
            },
        }

    def growth_quick_recommendations(
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
