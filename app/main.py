from __future__ import annotations

import logging
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
import secrets
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.automation import AutomationService
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.domain_contracts import ARTIFACT_TREND_RESEARCH
from app.http_limits import content_length_exceeds, read_request_body_limited, replay_request_body
from app.hub_forms import build_review_action_payload
from app.hub_job_request import HubTrendSeed, build_hub_job_request
from app.hub_prompt import (
    DEFAULT_VIRAL_PROMPT_TEMPLATE,
    hub_settings_path,
    load_viral_prompt_template,
    save_viral_prompt_template,
)

from app.models import Job, Script, TopicPlan, TopicRequest
from app.operational_settings import (
    apply_operational_settings,
    build_operational_settings_context,
    clear_operational_settings,
    parse_operational_form_values,
    save_operational_settings,
)
from app.orchestrator import FatalStepError, RecoverableStepError, orchestrator
from app.ready_script_import import MAX_READY_SCRIPT_IMPORT_BODY_BYTES, MAX_READY_SCRIPT_IMPORT_CHARS, ready_script_import_text
from app.hub_context import COMMON_SCHEDULE_TIMEZONES, HubContext
from app.publication_routes import create_publication_router
from app.routes.health import router as health_router
from pydantic import ValidationError

from app.topic_scout import TopicScout
from app.utils import path_from_uri, utcnow
from app.web_redirects import redirect_back as _redirect_back


settings = get_settings()
logger = logging.getLogger(__name__)
automation_service = AutomationService(orchestrator)



def _generate_premium_finish_background(job_id: str) -> None:
    try:
        orchestrator.generate_premium_finishing(job_id)
    except Exception as exc:  # noqa: BLE001
        orchestrator.record_premium_finishing_failure(job_id, str(exc))


def _log_render_startup_preflight() -> None:
    if str(settings.render_primary_backend).lower() != "remotion":
        return
    status = orchestrator.premium_finishing.renderer.preflight_environment()
    if status["ready"]:
        logger.info("remotion preflight passed project_dir=%s", status["project_dir"])
        return
    logger.warning("remotion preflight failed missing_items=%s", "; ".join(str(item) for item in status["missing_items"]))


def _request_path_with_query(request: Request) -> str:
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def _shared_template_context(request: Request) -> dict[str, object]:
    return {
        "settings": settings,
        "operational_settings": build_operational_settings_context(settings),
        "automation": automation_service.dashboard_context(),
        "viral_prompt_template": load_viral_prompt_template(hub_settings_path(settings.data_dir)),
        "return_to": _request_path_with_query(request),
        "hub_defaults": {
            "niche_id": HUB_DEFAULT_NICHE,
            "seed_theme": "",
            "suggested_seed_theme": _default_seed_theme(),
            "target_duration_sec": HUB_RETENTION_OPTIMIZED_DURATION_SEC,
        },
    }


templates = Jinja2Templates(directory=str(settings.templates_dir), context_processors=[_shared_template_context])

HUB_DEFAULT_NICHE = "curiosidades"
HUB_RETENTION_OPTIMIZED_DURATION_SEC = 45
HUB_RANDOM_THEME_POOL = [
    "Por que o pão fica duro e a bolacha fica mole?",
    "Por que o espelho embaça no banho?",
    "Por que a roupa preta esquenta mais no sol?",
    "Por que sentimos o celular vibrar sem ele vibrar?",
    "Por que o cheiro de chuva aparece antes da chuva?",
    "Por que gelo estala dentro do copo?",
    "Por que algumas músicas grudam na cabeça?",
    "Por que bocejo parece contagioso?",
    "Por que a tela do celular parece pior no sol?",
    "Por que a água gelada sua por fora do copo?",
]
HUB_JOBS_PER_PAGE = 4


hub_context = HubContext(settings, orchestrator, automation_service)
_job_status_label = hub_context._job_status_label
_schedule_status_label = hub_context._schedule_status_label
_job_flow_stage = hub_context._job_flow_stage
_job_next_action = hub_context._job_next_action
_publication_operational_status = hub_context._publication_operational_status
_job_progress_snapshot = hub_context._job_progress_snapshot
_failure_diagnosis = hub_context._failure_diagnosis
_job_origin_display = hub_context._job_origin_display
_creation_via_display = hub_context._creation_via_display
_job_action_guide = hub_context._job_action_guide
_job_list_context = hub_context._job_list_context
_schedule_display = hub_context._schedule_display
_ready_to_schedule_entries = hub_context._ready_to_schedule_entries
_effective_youtube_redirect_uri = hub_context._effective_youtube_redirect_uri
_youtube_integration_context = hub_context._youtube_integration_context
_tiktok_integration_context = hub_context._tiktok_integration_context
_publication_dashboard_context = hub_context._publication_dashboard_context
_calendar_context = hub_context._calendar_context
_resolve_job_id = hub_context._resolve_job_id


def artifact_url(uri: str | None) -> str:
    if not uri:
        return "#"
    if uri.startswith("file://"):
        try:
            path = path_from_uri(uri).resolve()
            relative_path = path.relative_to(settings.artifacts_dir.resolve())
        except (OSError, ValueError):
            return "#"
        if not path.exists():
            return "#"
        return f"/artifacts/{quote(relative_path.as_posix())}"
    return uri


templates.env.globals["artifact_url"] = artifact_url
templates.env.globals["job_status_label"] = _job_status_label
templates.env.globals["schedule_status_label"] = _schedule_status_label
templates.env.globals["job_flow_stage"] = _job_flow_stage
templates.env.globals["job_next_action"] = _job_next_action
templates.env.globals["publication_operational_status"] = _publication_operational_status
templates.env.globals["job_progress_snapshot"] = _job_progress_snapshot
templates.env.globals["failure_diagnosis"] = _failure_diagnosis
templates.env.globals["job_origin_display"] = _job_origin_display
templates.env.globals["creation_via_display"] = _creation_via_display


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    apply_operational_settings(settings)
    _log_render_startup_preflight()
    orchestrator.start_worker()
    yield
    orchestrator.stop_worker()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.mount("/artifacts", StaticFiles(directory=str(settings.artifacts_dir)), name="artifacts")
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")


def _authorized_request(request: Request) -> bool:
    if not settings.hub_auth_token:
        return True
    supplied = request.headers.get("x-shortsflow-hub-token")
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()
    if not supplied:
        supplied = request.cookies.get("shortsflow_hub_token")
    return bool(supplied) and secrets.compare_digest(str(supplied), str(settings.hub_auth_token))


def _hub_login_response(status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ShortsFlow Hub</title></head><body style="font-family:system-ui;margin:3rem;max-width:32rem"><h1>ShortsFlow Hub</h1><p>Informe o token do Hub.</p><form method="post" action="/auth"><input name="token" type="password" autocomplete="current-password" autofocus style="width:100%;padding:.75rem"><button type="submit" style="margin-top:1rem;padding:.75rem 1rem">Entrar</button></form></body></html>""",
        status_code=status_code,
    )


@app.middleware("http")
async def require_hub_auth(request: Request, call_next):
    if request.url.path.startswith("/healthz") or request.url.path.startswith("/static") or request.url.path == "/auth":
        return await call_next(request)
    if request.method != "OPTIONS" and not _authorized_request(request):
        if request.method in {"GET", "HEAD"} and request.url.path == "/":
            return _hub_login_response()
        return PlainTextResponse("unauthorized", status_code=401)
    if request.method == "POST" and request.url.path == "/automation/ready-scripts/import":
        if content_length_exceeds(request, MAX_READY_SCRIPT_IMPORT_BODY_BYTES):
            return PlainTextResponse("payload too large", status_code=413)
        body = await read_request_body_limited(request, MAX_READY_SCRIPT_IMPORT_BODY_BYTES)
        if body is None:
            return PlainTextResponse("payload too large", status_code=413)
        replay_request_body(request, body)
        return await call_next(request)
    return await call_next(request)


@app.post("/auth")
async def authenticate_hub(token: str = Form(default="")):
    if not settings.hub_auth_token or secrets.compare_digest(str(token), str(settings.hub_auth_token)):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("shortsflow_hub_token", str(token), httponly=True, samesite="lax")
        return response
    return _hub_login_response(status_code=401)


































def _default_seed_theme() -> str:
    with SessionLocal() as session:
        recent_themes = session.scalars(
            select(TopicRequest.seed_theme)
            .where(TopicRequest.niche_id == HUB_DEFAULT_NICHE)
            .order_by(TopicRequest.created_at.desc())
            .limit(30)
        ).all()
    recent = {theme.strip().lower() for theme in recent_themes if theme and theme.strip()}
    candidates = [theme for theme in HUB_RANDOM_THEME_POOL if theme.lower() not in recent]
    return random.choice(candidates or HUB_RANDOM_THEME_POOL)


def _trend_seed_theme(niche_id: str) -> tuple[str, str | None, str | None, dict[str, object] | None]:
    with SessionLocal() as session:
        recent_themes = session.scalars(
            select(TopicRequest.seed_theme)
            .where(TopicRequest.niche_id == (niche_id or HUB_DEFAULT_NICHE))
            .order_by(TopicRequest.created_at.desc())
            .limit(40)
        ).all()
    scout_result = TopicScout().find_topic(niche_id, recent_topics=recent_themes)
    if scout_result is None:
        fallback_theme = _default_seed_theme()
        return (
            fallback_theme,
            None,
            "trend_research=unavailable\ntrend_source=fallback_pool\ntrend_status=no_topic_scout_candidate",
            {
                "trend_research": "unavailable",
                "source": "fallback_pool",
                "status": "no_topic_scout_candidate",
                "fallback_seed_theme": fallback_theme,
            },
        )
    trend = scout_result.candidate
    report = trend.as_report()
    report.update({"topic_scout": "enabled", "considered_count": scout_result.considered_count, "rejected_recent_count": scout_result.rejected_recent_count})
    return trend.topic, trend.requested_angle, trend.as_notes(), report


class _PublicationRouteDeps:
    @property
    def settings(self):
        return settings

    @property
    def templates(self):
        return templates

    @property
    def orchestrator(self):
        return orchestrator

    @property
    def automation_service(self):
        return automation_service

    @staticmethod
    def redirect_back(return_to, params=None, *, default="/"):
        return _redirect_back(return_to, params=params, default=default)

    @staticmethod
    async def ready_script_import_text(ready_script_batch, ready_script_file):
        return await ready_script_import_text(ready_script_batch, ready_script_file)

    @staticmethod
    def effective_youtube_redirect_uri(request: Request) -> str:
        return _effective_youtube_redirect_uri(request)

    @staticmethod
    def calendar_context(month: str | None):
        return _calendar_context(month)


publication_router, _publication_route_handlers = create_publication_router(_PublicationRouteDeps())
app.include_router(publication_router)
toggle_automation = _publication_route_handlers.toggle_automation
run_automation_now = _publication_route_handlers.run_automation_now
import_ready_scripts = _publication_route_handlers.import_ready_scripts
connect_youtube = _publication_route_handlers.connect_youtube
youtube_oauth_callback = _publication_route_handlers.youtube_oauth_callback
disconnect_youtube = _publication_route_handlers.disconnect_youtube
publication_calendar = _publication_route_handlers.publication_calendar
schedule_publication_from_calendar = _publication_route_handlers.schedule_publication_from_calendar
update_publish_metadata = _publication_route_handlers.update_publish_metadata
publish_job = _publication_route_handlers.publish_job
schedule_job_publication = _publication_route_handlers.schedule_job_publication
reopen_job_publication = _publication_route_handlers.reopen_job_publication
record_performance = _publication_route_handlers.record_performance
sync_job_youtube_analytics = _publication_route_handlers.sync_job_youtube_analytics
sync_due_youtube_analytics = _publication_route_handlers.sync_due_youtube_analytics


def _jobs_listing_page_context(request: Request, *, deleted_job: str | None, list_context: dict[str, object]) -> dict[str, object]:
    publication_context = _publication_dashboard_context(request, limit=4)
    return {
        **list_context,
        "workflow_summary": publication_context["metrics"],
        "youtube_integration": publication_context["integration"],
        "automation": publication_context["automation"],
        "hub_defaults": {
            "niche_id": HUB_DEFAULT_NICHE,
            "seed_theme": "",
            "suggested_seed_theme": _default_seed_theme(),
            "target_duration_sec": HUB_RETENTION_OPTIMIZED_DURATION_SEC,
        },
        "viral_prompt_template": load_viral_prompt_template(hub_settings_path(settings.data_dir)),
        "calendar_url": "/calendar",
        "settings": settings,
        "deleted_job": deleted_job,
    }


@app.get("/", response_class=HTMLResponse)
def jobs_page(
    request: Request,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    fallback: str | None = Query(default=None),
    review: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    via: str | None = Query(default=None),
    page: int = Query(default=1),
    per_page: int = Query(default=HUB_JOBS_PER_PAGE),
    deleted_job: str | None = Query(default=None),
):
    list_context = _job_list_context(status=status, search=search, fallback=fallback, review=review, origin=origin, via=via, page=page, per_page=per_page)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        _jobs_listing_page_context(request, deleted_job=deleted_job, list_context=list_context),
    )


@app.post("/hub/prompt")
def update_hub_prompt(
    viral_prompt_template: str | None = Form(default=None),
    action: str = Form(default="save"),
    return_to: str | None = Form(default=None),
):
    if action == "reset":
        save_viral_prompt_template(hub_settings_path(settings.data_dir), DEFAULT_VIRAL_PROMPT_TEMPLATE)
    else:
        save_viral_prompt_template(hub_settings_path(settings.data_dir), viral_prompt_template)
    return _redirect_back(return_to)


@app.post("/operations/settings")
async def update_operational_settings(request: Request):
    form = await request.form()
    return_to = str(form.get("return_to") or "")
    action = str(form.get("action") or "save")
    try:
        if action == "reset":
            clear_operational_settings(settings)
        else:
            save_operational_settings(settings, parse_operational_form_values(dict(form)))
    except (ValueError, ValidationError) as exc:
        return _redirect_back(return_to, {"settings_error": str(exc)}, default="/#publication-hub")
    return _redirect_back(return_to, {"settings_saved": "1"}, default="/#publication-hub")


@app.get("/jobs", response_class=HTMLResponse)
def jobs_route(
    request: Request,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    fallback: str | None = Query(default=None),
    review: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    via: str | None = Query(default=None),
    page: int = Query(default=1),
    per_page: int = Query(default=HUB_JOBS_PER_PAGE),
    deleted_job: str | None = Query(default=None),
):
    list_context = _job_list_context(status=status, search=search, fallback=fallback, review=review, origin=origin, via=via, page=page, per_page=per_page)
    if request.headers.get("hx-request", "").lower() != "true":
        return templates.TemplateResponse(
            request,
            "jobs.html",
            _jobs_listing_page_context(request, deleted_job=deleted_job, list_context=list_context),
        )
    return templates.TemplateResponse(
        request,
        "jobs_table.html",
        list_context,
    )


@app.get("/publication-hub", response_class=HTMLResponse)
def publication_dashboard_page(request: Request):
    return templates.TemplateResponse(
        request,
        "growth.html",
        {
            **_publication_dashboard_context(request),
            "growth_return_to": "/publication-hub",
            "show_maintenance": True,
            "settings": settings,
        },
    )


@app.get("/publication-hub/fragment", response_class=HTMLResponse)
def publication_dashboard_fragment(request: Request):
    return templates.TemplateResponse(
        request,
        "publication_dashboard.html",
        {
            **_publication_dashboard_context(request),
            "growth_return_to": "/publication-hub",
            "settings": settings,
        },
    )


@app.get("/library", response_class=HTMLResponse)
def ready_script_library(request: Request):
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "settings": settings,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
def operational_settings_page(request: Request):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
        },
    )


@app.post("/jobs")
def create_job(
    seed_theme: str = Form(default=""),
    input_mode: str = Form(default="theme"),
    niche_id: str = Form(default=HUB_DEFAULT_NICHE),
    language: str = Form(default="pt-BR"),
    target_duration_sec: int = Form(default=HUB_RETENTION_OPTIMIZED_DURATION_SEC),
    tone: str = Form(default="intrigante_direto"),
    cta_style: str = Form(default="none"),
    notes: str | None = Form(default=None),
    requested_angle: str | None = Form(default=None),
    custom_angle: str | None = Form(default=None),
    ready_script_text: str | None = Form(default=None),
    ready_script_fact_check_confirmed: bool = Form(default=False),
):
    def resolve_trend_seed(selected_niche: str) -> HubTrendSeed:
        trend_theme, trend_angle, trend_notes, trend_report = _trend_seed_theme(selected_niche)
        return HubTrendSeed(
            seed_theme=trend_theme,
            requested_angle=trend_angle,
            notes=trend_notes,
            report=trend_report,
        )

    try:
        selected_niche = niche_id or HUB_DEFAULT_NICHE
        result = build_hub_job_request(
            seed_theme=seed_theme,
            input_mode=input_mode,
            niche_id=selected_niche,
            language=language,
            target_duration_sec=target_duration_sec,
            tone=tone,
            cta_style=cta_style,
            notes=notes,
            requested_angle=requested_angle,
            custom_angle=custom_angle,
            ready_script_text=ready_script_text,
            ready_script_fact_check_confirmed=ready_script_fact_check_confirmed,
            default_niche_id=HUB_DEFAULT_NICHE,
            retention_optimized_duration_sec=HUB_RETENTION_OPTIMIZED_DURATION_SEC,
            viral_prompt_template=load_viral_prompt_template(hub_settings_path(settings.data_dir)),
            trend_seed_resolver=resolve_trend_seed,
        )
        job_id = orchestrator.create_job(result.payload.model_dump())
        if result.trend_report is not None:
            orchestrator.storage.persist_json(job_id, ARTIFACT_TREND_RESEARCH, result.trend_report)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": error["loc"],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/api/jobs/{job_id}")
def job_json(job_id: str):
    with SessionLocal() as session:
        resolved_job_id = _resolve_job_id(session, job_id)
        details = orchestrator.get_job_details(session, resolved_job_id)
        return {
            "job": {
                "job_id": details["job"].job_id,
                "status": details["job"].status,
                "current_step": details["job"].current_step,
                "quality_summary": details["job"].quality_summary,
            },
            "topic_request": {
                "seed_theme": details["topic_request"].seed_theme if details["topic_request"] else None,
            },
            "render": {
                "video_uri": details["render"].video_uri if details["render"] else None,
                "duration_ms": details["render"].duration_ms if details["render"] else None,
            },
            "progress": details["progress"],
            "premium_finishing": details.get("premium_finishing") or {},
        }


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str):
    with SessionLocal() as session:
        try:
            resolved_job_id = _resolve_job_id(session, job_id)
            details = orchestrator.get_job_details(session, resolved_job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
    youtube_integration = _youtube_integration_context(request)
    publication_schedule_display = _schedule_display(details.get("publication_schedule"))
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "details": details,
            "settings": settings,
            "publication_schedule_display": publication_schedule_display,
            "common_schedule_timezones": COMMON_SCHEDULE_TIMEZONES,
            "youtube_integration": youtube_integration,
            "review_error": request.query_params.get("review_error"),
            "publish_error": request.query_params.get("publish_error"),
            "reprocess_error": request.query_params.get("reprocess_error"),
            "premium_error": request.query_params.get("premium_error"),
            "action_guide": _job_action_guide(
                details["job"],
                details.get("monetization_report"),
                publication_schedule_display,
                youtube_integration,
            ),
        },
    )


@app.post("/jobs/{job_id}/delete")
def delete_job(job_id: str):
    try:
        with SessionLocal() as session:
            resolved_job_id = _resolve_job_id(session, job_id)
        orchestrator.delete_job(resolved_job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'review_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/?{urlencode({'deleted_job': resolved_job_id[:8]})}", status_code=303)


@app.post("/jobs/{job_id}/premium-finish")
def generate_premium_finish(job_id: str, background_tasks: BackgroundTasks):
    try:
        with SessionLocal() as session:
            resolved_job_id = _resolve_job_id(session, job_id)
        orchestrator.request_premium_finishing(resolved_job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'premium_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    background_tasks.add_task(_generate_premium_finish_background, resolved_job_id)
    return RedirectResponse(url=f"/jobs/{resolved_job_id}?premium_started=1", status_code=303)


@app.post("/jobs/{job_id}/reprocess")
def reprocess_job_from_step(job_id: str, from_step: str = Form(default="tts")):
    try:
        orchestrator.reprocess_job_from_step(job_id, from_step)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except (FatalStepError, ValueError) as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'reprocess_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/scenes/{scene_id}/regenerate")
def regenerate_scene(job_id: str, scene_id: str, operator_instruction: str | None = Form(default=None)):
    try:
        orchestrator.regenerate_scene_and_rerender(job_id, scene_id, operator_instruction=operator_instruction)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except (FatalStepError, RecoverableStepError, ValueError) as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'reprocess_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/review")
def review_job(
    job_id: str,
    reviewer_identity: str = Form(default="tailscale:local-reviewer"),
    action: str = Form(...),
    reason_codes: list[str] | None = Form(default=None),
    confirmation_codes: list[str] | None = Form(default=None),
    rights_confirmed: bool = Form(default=False),
    ai_disclosure_confirmed: bool = Form(default=False),
    fact_review_confirmed: bool = Form(default=False),
    metadata_confirmed: bool = Form(default=False),
    originality_confirmed: bool = Form(default=False),
    notes: str | None = Form(default=None),
):
    try:
        payload = build_review_action_payload(
            reviewer_identity=reviewer_identity,
            action=action,
            reason_codes=reason_codes,
            confirmation_codes=confirmation_codes,
            rights_confirmed=rights_confirmed,
            ai_disclosure_confirmed=ai_disclosure_confirmed,
            fact_review_confirmed=fact_review_confirmed,
            metadata_confirmed=metadata_confirmed,
            originality_confirmed=originality_confirmed,
            notes=notes,
        )
        new_job_id = orchestrator.review_job(payload.model_dump(), job_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except FatalStepError as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'review_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    redirect_to = f"/jobs/{new_job_id}" if new_job_id else f"/jobs/{job_id}"
    return RedirectResponse(url=redirect_to, status_code=303)


@app.post("/jobs/{job_id}/premium-approve")
def approve_premium_for_publish(job_id: str, reviewer_identity: str = Form(default="tailscale:local-reviewer")):
    try:
        orchestrator.approve_premium_for_publish(job_id, reviewer_identity=reviewer_identity)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'review_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
