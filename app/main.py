from __future__ import annotations

import json
import random
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.automation import AutomationService
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.http_limits import content_length_exceeds, read_request_body_limited, replay_request_body
from app.hub_forms import build_performance_metric_payload, build_review_action_payload
from app.hub_job_request import HubTrendSeed, build_hub_job_request
from app.hub_prompt import (
    DEFAULT_VIRAL_PROMPT_TEMPLATE,
    hub_settings_path,
    load_viral_prompt_template,
    save_viral_prompt_template,
    sanitize_viral_prompt_template,
)
from app.llm_tournament import latest_llm_tournament_decision_summary
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
from app.routes.health import router as health_router
from pydantic import ValidationError

from app.schemas import PublicationSchedulePayload
from app.topic_scout import TopicScout
from app.utils import path_from_uri
from app.web_redirects import redirect_back as _redirect_back
from app.youtube_api import YouTubeIntegrationError


settings = get_settings()
automation_service = AutomationService(orchestrator)
LLM_TOURNAMENT_OUTPUT_ROOT = (settings.data_dir / "llm_tournament").resolve()


def _generate_premium_finish_background(job_id: str) -> None:
    try:
        orchestrator.generate_premium_finishing(job_id)
    except Exception as exc:  # noqa: BLE001
        orchestrator.record_premium_finishing_failure(job_id, str(exc))


def _request_path_with_query(request: Request) -> str:
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def _shared_template_context(request: Request) -> dict[str, object]:
    return {
        "settings": settings,
        "operational_settings": build_operational_settings_context(settings),
        "automation": automation_service.dashboard_context(),
        "viral_prompt_template": _viral_prompt_template(),
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
HUB_RETENTION_OPTIMIZED_DURATION_SEC = 50
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


def _resolve_llm_tournament_artifact_path(uri: str | None) -> Path | None:
    if not uri:
        return None
    base = LLM_TOURNAMENT_OUTPUT_ROOT
    source = Path(uri)
    candidates: list[Path] = []
    if source.is_absolute():
        candidates.append(source)
    else:
        candidates.extend(
            (
                source,
                Path.cwd() / source,
                settings.data_dir / source,
                settings.data_dir / "llm_tournament" / source,
            )
        )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        try:
            resolved.relative_to(base)
        except ValueError:
            continue
        return resolved
    return None


def _llm_tournament_artifact_url(uri: str | None) -> str:
    path = _resolve_llm_tournament_artifact_path(uri)
    if not path:
        return "#"
    relative_path = path.relative_to(LLM_TOURNAMENT_OUTPUT_ROOT)
    return f"/llm-tournament/file?path={quote(relative_path.as_posix())}"


def _read_llm_tournament_json(uri: str | None) -> Any | None:
    path = _resolve_llm_tournament_artifact_path(uri)
    if not path:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pretty_json(payload: Any | None) -> str | None:
    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return None


templates.env.globals["artifact_url"] = artifact_url
templates.env.globals["llm_tournament_artifact_url"] = _llm_tournament_artifact_url
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
    supplied = request.headers.get("x-yts-hub-token")
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()
    if not supplied and request.method in {"GET", "HEAD"}:
        supplied = request.cookies.get("yts_hub_token")
    return supplied == settings.hub_auth_token


@app.middleware("http")
async def require_hub_auth(request: Request, call_next):
    if request.url.path.startswith("/healthz") or request.url.path.startswith("/static"):
        return await call_next(request)
    if request.method != "OPTIONS" and not _authorized_request(request):
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


































def _hub_settings_path():
    return hub_settings_path(settings.data_dir)


def _sanitize_viral_prompt_template(template: str | None) -> str:
    return sanitize_viral_prompt_template(template)


def _viral_prompt_template() -> str:
    return load_viral_prompt_template(_hub_settings_path())


def _save_viral_prompt_template(template: str | None) -> None:
    save_viral_prompt_template(_hub_settings_path(), template)


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
    publication_context = _publication_dashboard_context(request, limit=4)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
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
            "viral_prompt_template": _viral_prompt_template(),
            "calendar_url": "/calendar",
            "settings": settings,
            "deleted_job": deleted_job,
        },
    )


@app.post("/hub/prompt")
def update_hub_prompt(
    viral_prompt_template: str | None = Form(default=None),
    action: str = Form(default="save"),
    return_to: str | None = Form(default=None),
):
    if action == "reset":
        _save_viral_prompt_template(DEFAULT_VIRAL_PROMPT_TEMPLATE)
    else:
        _save_viral_prompt_template(viral_prompt_template)
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
        publication_context = _publication_dashboard_context(request, limit=4)
        return templates.TemplateResponse(
            request,
            "jobs.html",
            {
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
                "viral_prompt_template": _viral_prompt_template(),
                "calendar_url": "/calendar",
                "settings": settings,
                "deleted_job": deleted_job,
            },
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


@app.get("/llm-tournament", response_class=HTMLResponse)
def llm_tournament_page(request: Request):
    tournament = latest_llm_tournament_decision_summary()
    decision_report = _read_llm_tournament_json(
        (tournament.get("paths") or {}).get("decision_report_json")
        if isinstance(tournament, dict) and isinstance(tournament.get("paths"), dict)
        else None
    )
    committee_packet_path: str | None = None
    if isinstance(decision_report, dict):
        committee_packet_path = decision_report.get("source_committee_packet_path")
    elif isinstance(tournament, dict):
        committee_packet_path = (tournament.get("paths") or {}).get("committee_packet")
    committee_packet = _read_llm_tournament_json(committee_packet_path)
    latest_textual_path = None
    if isinstance(tournament, dict):
        latest_textual_path = tournament.get("latest_textual_path") or (tournament.get("paths") or {}).get("latest_textual")
    latest_textual = _read_llm_tournament_json(latest_textual_path)
    artifact_entries: list[dict[str, str | None]] = []
    raw_paths = tournament.get("paths") if isinstance(tournament, dict) else None
    if isinstance(raw_paths, dict):
        for key, value in raw_paths.items():
            if key == "run_dir" or not value:
                continue
            artifact_entries.append(
                {
                    "label": key.replace("_", " ").replace("-", " ").title(),
                    "path": str(value),
                    "url": _llm_tournament_artifact_url(str(value)),
                }
            )
    return templates.TemplateResponse(
        request,
        "llm_tournament.html",
        {
            "settings": settings,
            "tournament": tournament,
            "tournament_artifacts": artifact_entries,
            "tournament_decision_report": decision_report,
            "tournament_decision_report_pretty": _pretty_json(decision_report),
            "tournament_committee_packet": committee_packet,
            "tournament_committee_packet_pretty": _pretty_json(committee_packet),
            "tournament_latest_textual": latest_textual,
            "tournament_latest_textual_pretty": _pretty_json(latest_textual),
        },
    )


@app.get("/llm-tournament/file")
def llm_tournament_file(path: str | None = Query(default=None)):
    artifact_path = _resolve_llm_tournament_artifact_path(path)
    if not artifact_path:
        raise HTTPException(status_code=404, detail="artifact not found")
    return PlainTextResponse(artifact_path.read_text(encoding="utf-8"))


@app.post("/automation/toggle")
def toggle_automation(enabled: bool = Form(default=False), return_to: str | None = Form(default=None)):
    automation_service.set_automation_enabled(enabled)
    return _redirect_back(return_to, default="/publication-hub")


@app.post("/automation/run")
def run_automation_now(force: bool = Form(default=False), return_to: str | None = Form(default=None)):
    result = automation_service.run_daily_cycle(force=force)
    if result and result.get("status") == "failed":
        return _redirect_back(return_to, {"automation_error": result.get("error") or "failed"}, default="/publication-hub")
    return _redirect_back(return_to, default="/publication-hub")


@app.post("/automation/ready-scripts/import")
async def import_ready_scripts(
    ready_script_batch: str = Form(default=""),
    ready_script_file: UploadFile | None = File(default=None),
    fact_check_confirmed: bool = Form(default=False),
    return_to: str | None = Form(default=None),
):
    if not fact_check_confirmed:
        raise HTTPException(status_code=422, detail="fact_check_confirmed is required for automation-ready script batches")
    raw_text = await ready_script_import_text(ready_script_batch, ready_script_file)
    result = automation_service.import_ready_script_batch(raw_text, fact_check_confirmed=fact_check_confirmed)
    params = {"imported": str(result.imported)}
    if result.errors:
        params["errors"] = str(len(result.errors))
    return _redirect_back(return_to, params=params)


@app.get("/youtube/connect")
def connect_youtube(request: Request):
    try:
        authorization_url = orchestrator.youtube.authorization_url(_effective_youtube_redirect_uri(request))
    except FatalStepError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=authorization_url, status_code=303)


@app.get("/youtube/oauth/callback")
def youtube_oauth_callback(request: Request, code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None)):
    if error:
        raise HTTPException(status_code=400, detail=f"youtube oauth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="youtube oauth callback missing code/state")
    try:
        orchestrator.youtube.exchange_code(code=code, state=state)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url="/", status_code=303)


@app.post("/youtube/disconnect")
def disconnect_youtube():
    orchestrator.youtube.disconnect()
    return RedirectResponse(url="/", status_code=303)


@app.get("/calendar", response_class=HTMLResponse)
def publication_calendar(request: Request, month: str | None = Query(default=None)):
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            **_calendar_context(month),
            "settings": settings,
        },
    )


@app.post("/calendar/schedule")
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
        orchestrator.schedule_publication(job_id, payload.model_dump())
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
        result = build_hub_job_request(
            seed_theme=seed_theme,
            input_mode=input_mode,
            niche_id=niche_id,
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
            viral_prompt_template=_viral_prompt_template(),
            trend_seed_resolver=resolve_trend_seed,
        )
        job_id = orchestrator.create_job(result.payload.model_dump())
        if result.trend_report is not None:
            orchestrator.storage.persist_json(job_id, "trend_research.json", result.trend_report)
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


@app.post("/jobs/{job_id}/publish-metadata")
def update_publish_metadata(
    job_id: str,
    title: str = Form(default=""),
    description: str = Form(default=""),
    hashtags: str = Form(default=""),
):
    try:
        orchestrator.update_publish_metadata(
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


@app.post("/jobs/{job_id}/publish")
def publish_job(
    request: Request,
    job_id: str,
    youtube_video_id: str | None = Form(default=None),
    youtube_url: str | None = Form(default=None),
):
    try:
        orchestrator.publish_job(job_id, youtube_video_id=youtube_video_id, youtube_url=youtube_url)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        redirect_to = f"/jobs/{job_id}?{urlencode({'publish_error': str(exc)})}"
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/schedule")
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
            orchestrator.clear_publication_schedule(job_id)
        else:
            payload = PublicationSchedulePayload(
                scheduled_for_local=scheduled_for_local or "",
                timezone=timezone,
                youtube_visibility=youtube_visibility,
                notes=notes,
            )
            orchestrator.schedule_publication(job_id, payload.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/reopen-publication")
def reopen_job_publication(job_id: str):
    try:
        orchestrator.reopen_publication_for_republish(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except FatalStepError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/performance")
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
        orchestrator.record_performance_metrics(job_id, payload.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/youtube-analytics/sync")
def sync_job_youtube_analytics(
    job_id: str,
    days: int = Form(default=28),
    return_to: str | None = Form(default=None),
):
    try:
        orchestrator.sync_youtube_analytics_snapshot(job_id, days=days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except YouTubeIntegrationError as exc:
        return _redirect_back(return_to, {"analytics_error": str(exc)}, default=f"/jobs/{job_id}")
    return _redirect_back(return_to, {"analytics_synced": "1"}, default=f"/jobs/{job_id}")


@app.post("/youtube-analytics/sync-due")
def sync_due_youtube_analytics(
    days: int = Form(default=28),
    limit: int | None = Form(default=None),
    return_to: str | None = Form(default=None),
):
    result = orchestrator.sync_due_youtube_analytics_snapshots(days=days, limit=limit)
    if result.get("status") == "skipped":
        return _redirect_back(return_to, {"analytics_error": result.get("reason") or "sync_skipped"}, default="/publication-hub")
    return _redirect_back(return_to, {"analytics_synced": str(len(result.get("synced") or []))}, default="/publication-hub")
