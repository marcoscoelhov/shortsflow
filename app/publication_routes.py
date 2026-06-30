from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.hub_forms import build_performance_metric_payload
from app.orchestrator import FatalStepError
from app.schemas import PublicationSchedulePayload
from app.youtube_api import YouTubeIntegrationError


@dataclass(frozen=True)
class PublicationRouteHandlers:
    toggle_automation: Any
    run_automation_now: Any
    import_ready_scripts: Any
    connect_youtube: Any
    youtube_oauth_callback: Any
    disconnect_youtube: Any
    publication_calendar: Any
    schedule_publication_from_calendar: Any
    update_publish_metadata: Any
    publish_job: Any
    schedule_job_publication: Any
    reopen_job_publication: Any
    record_performance: Any
    sync_job_youtube_analytics: Any
    sync_due_youtube_analytics: Any


def create_publication_router(deps: Any) -> tuple[APIRouter, PublicationRouteHandlers]:
    router = APIRouter()

    @router.post("/automation/toggle")
    def toggle_automation(enabled: bool = Form(default=False), return_to: str | None = Form(default=None)):
        deps.automation_service.set_automation_enabled(enabled)
        return deps.redirect_back(return_to, default="/publication-hub")

    @router.post("/automation/run")
    def run_automation_now(force: bool = Form(default=False), return_to: str | None = Form(default=None)):
        result = deps.automation_service.run_daily_cycle(force=force)
        if result and result.get("status") == "failed":
            return deps.redirect_back(return_to, {"automation_error": result.get("error") or "failed"}, default="/publication-hub")
        return deps.redirect_back(return_to, default="/publication-hub")

    @router.post("/automation/ready-scripts/import")
    async def import_ready_scripts(
        ready_script_batch: str = Form(default=""),
        ready_script_file: UploadFile | None = File(default=None),
        fact_check_confirmed: bool = Form(default=False),
        return_to: str | None = Form(default=None),
    ):
        raw_text = await deps.ready_script_import_text(ready_script_batch, ready_script_file)
        result = deps.automation_service.import_ready_script_batch(raw_text, fact_check_confirmed=True)
        params = {"imported": str(result.imported)}
        if result.errors:
            params["errors"] = str(len(result.errors))
        return deps.redirect_back(return_to, params=params)

    @router.get("/youtube/connect")
    def connect_youtube(request: Request):
        try:
            authorization_url = deps.orchestrator.youtube.authorization_url(deps.effective_youtube_redirect_uri(request))
        except FatalStepError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=authorization_url, status_code=303)

    @router.get("/youtube/oauth/callback")
    def youtube_oauth_callback(
        request: Request,
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
    ):
        if error:
            raise HTTPException(status_code=400, detail=f"youtube oauth error: {error}")
        if not code or not state:
            raise HTTPException(status_code=400, detail="youtube oauth callback missing code/state")
        try:
            deps.orchestrator.youtube.exchange_code(code=code, state=state)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url="/", status_code=303)

    @router.post("/youtube/disconnect")
    def disconnect_youtube():
        deps.orchestrator.youtube.disconnect()
        return RedirectResponse(url="/", status_code=303)

    @router.get("/calendar", response_class=HTMLResponse)
    def publication_calendar(request: Request, month: str | None = Query(default=None)):
        return deps.templates.TemplateResponse(
            request,
            "calendar.html",
            {
                **deps.calendar_context(month),
                "settings": deps.settings,
            },
        )

    @router.post("/calendar/schedule")
    def schedule_publication_from_calendar(
        job_id: str = Form(...),
        scheduled_date: str = Form(...),
        scheduled_time: str = Form(default="15:00"),
        timezone: str = Form(default="America/Sao_Paulo"),
        youtube_visibility: str = Form(default="private"),
        notes: str | None = Form(default=None),
        month: str | None = Form(default=None),
    ):
        try:
            scheduled_day = date.fromisoformat(scheduled_date)
            payload = PublicationSchedulePayload(
                scheduled_for_local=f"{scheduled_day.isoformat()}T{scheduled_time}",
                timezone=timezone,
                youtube_visibility=youtube_visibility,
                notes=notes,
            )
            deps.orchestrator.schedule_publication(job_id, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="scheduled_date must use YYYY-MM-DD") from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except FatalStepError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        target_month = month or scheduled_day.strftime("%Y-%m")
        return RedirectResponse(url=f"/calendar?{urlencode({'month': target_month})}", status_code=303)

    @router.post("/jobs/{job_id}/publish-metadata")
    def update_publish_metadata(
        job_id: str,
        title: str = Form(default=""),
        description: str = Form(default=""),
        hashtags: str = Form(default=""),
    ):
        try:
            deps.orchestrator.update_publish_metadata(
                job_id,
                {
                    "title": title,
                    "description": description,
                    "hashtags": hashtags,
                },
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except FatalStepError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/publish")
    def publish_job(
        request: Request,
        job_id: str,
        youtube_video_id: str | None = Form(default=None),
        youtube_url: str | None = Form(default=None),
    ):
        try:
            deps.orchestrator.publish_job(job_id, youtube_video_id=youtube_video_id, youtube_url=youtube_url)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except FatalStepError as exc:
            redirect_to = f"/jobs/{job_id}?{urlencode({'publish_error': str(exc)})}"
            return RedirectResponse(url=redirect_to, status_code=303)
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/schedule")
    def schedule_job_publication(
        job_id: str,
        action: str = Form(default="schedule"),
        scheduled_for_local: str | None = Form(default=None),
        timezone: str = Form(default="UTC"),
        youtube_visibility: str = Form(default="private"),
        notes: str | None = Form(default=None),
    ):
        try:
            if action == "clear":
                deps.orchestrator.clear_publication_schedule(job_id)
            else:
                payload = PublicationSchedulePayload(
                    scheduled_for_local=scheduled_for_local or "",
                    timezone=timezone,
                    youtube_visibility=youtube_visibility,
                    notes=notes,
                )
                deps.orchestrator.schedule_publication(job_id, payload.model_dump())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except FatalStepError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/reopen-publication")
    def reopen_job_publication(job_id: str):
        try:
            deps.orchestrator.reopen_publication_for_republish(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except FatalStepError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/performance")
    def record_performance(
        job_id: str,
        source: str = Form(default="youtube_studio_manual"),
        retention_percent: str | None = Form(default=None),
        viewed_vs_swiped_away_percent: str | None = Form(default=None),
        rewatch_rate: str | None = Form(default=None),
        likes: str | None = Form(default=None),
        shares: str | None = Form(default=None),
        comments: str | None = Form(default=None),
        rpm_usd: str | None = Form(default=None),
        monetization_status: str | None = Form(default=None),
        notes: str | None = Form(default=None),
    ):
        try:
            payload = build_performance_metric_payload(
                source=source,
                retention_percent=retention_percent,
                viewed_vs_swiped_away_percent=viewed_vs_swiped_away_percent,
                rewatch_rate=rewatch_rate,
                likes=likes,
                shares=shares,
                comments=comments,
                rpm_usd=rpm_usd,
                monetization_status=monetization_status,
                notes=notes,
            )
            deps.orchestrator.record_performance_metrics(job_id, payload.model_dump())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/youtube-analytics/sync")
    def sync_job_youtube_analytics(
        job_id: str,
        days: int = Form(default=28),
        return_to: str | None = Form(default=None),
    ):
        try:
            deps.orchestrator.sync_youtube_analytics_snapshot(job_id, days=days)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except YouTubeIntegrationError as exc:
            return deps.redirect_back(return_to, {"analytics_error": str(exc)}, default=f"/jobs/{job_id}")
        return deps.redirect_back(return_to, {"analytics_synced": "1"}, default=f"/jobs/{job_id}")

    @router.post("/youtube-analytics/sync-due")
    def sync_due_youtube_analytics(
        days: int = Form(default=28),
        limit: int | None = Form(default=None),
        return_to: str | None = Form(default=None),
    ):
        result = deps.orchestrator.sync_due_youtube_analytics_snapshots(days=days, limit=limit)
        if result.get("status") == "skipped":
            return deps.redirect_back(return_to, {"analytics_error": result.get("reason") or "sync_skipped"}, default="/publication-hub")
        return deps.redirect_back(return_to, {"analytics_synced": str(len(result.get("synced") or []))}, default="/publication-hub")

    handlers = PublicationRouteHandlers(
        toggle_automation=toggle_automation,
        run_automation_now=run_automation_now,
        import_ready_scripts=import_ready_scripts,
        connect_youtube=connect_youtube,
        youtube_oauth_callback=youtube_oauth_callback,
        disconnect_youtube=disconnect_youtube,
        publication_calendar=publication_calendar,
        schedule_publication_from_calendar=schedule_publication_from_calendar,
        update_publish_metadata=update_publish_metadata,
        publish_job=publish_job,
        schedule_job_publication=schedule_job_publication,
        reopen_job_publication=reopen_job_publication,
        record_performance=record_performance,
        sync_job_youtube_analytics=sync_job_youtube_analytics,
        sync_due_youtube_analytics=sync_due_youtube_analytics,
    )
    return router, handlers
