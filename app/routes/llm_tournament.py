from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.llm_tournament import latest_llm_tournament_decision_summary


def create_llm_tournament_router(settings: Settings, templates: Jinja2Templates) -> APIRouter:
    """Expose the optional LLM tournament surface without coupling it to app.main."""

    router = APIRouter()
    output_root = (settings.data_dir / "llm_tournament").resolve()

    def resolve_artifact_path(uri: str | None) -> Path | None:
        if not uri:
            return None
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
                    output_root / source,
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
                resolved.relative_to(output_root)
            except ValueError:
                continue
            return resolved
        return None

    def artifact_url(uri: str | None) -> str:
        path = resolve_artifact_path(uri)
        if not path:
            return "#"
        relative_path = path.relative_to(output_root)
        return f"/llm-tournament/file?path={quote(relative_path.as_posix())}"

    def read_json(uri: str | None) -> Any | None:
        path = resolve_artifact_path(uri)
        if not path:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def pretty_json(payload: Any | None) -> str | None:
        if payload is None:
            return None
        try:
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return None

    templates.env.globals["llm_tournament_artifact_url"] = artifact_url

    @router.get("/llm-tournament", response_class=HTMLResponse)
    def llm_tournament_page(request: Request):
        tournament = latest_llm_tournament_decision_summary()
        paths = tournament.get("paths") if isinstance(tournament, dict) and isinstance(tournament.get("paths"), dict) else {}
        decision_report = read_json(paths.get("decision_report_json"))
        if isinstance(decision_report, dict):
            committee_packet_path = decision_report.get("source_committee_packet_path")
        else:
            committee_packet_path = paths.get("committee_packet")
        committee_packet = read_json(committee_packet_path)
        latest_textual_path = tournament.get("latest_textual_path") if isinstance(tournament, dict) else None
        latest_textual = read_json(latest_textual_path or paths.get("latest_textual"))
        artifact_entries = [
            {
                "label": key.replace("_", " ").replace("-", " ").title(),
                "path": str(value),
                "url": artifact_url(str(value)),
            }
            for key, value in paths.items()
            if key != "run_dir" and value
        ]
        return templates.TemplateResponse(
            request,
            "llm_tournament.html",
            {
                "settings": settings,
                "tournament": tournament,
                "tournament_artifacts": artifact_entries,
                "tournament_decision_report": decision_report,
                "tournament_decision_report_pretty": pretty_json(decision_report),
                "tournament_committee_packet": committee_packet,
                "tournament_committee_packet_pretty": pretty_json(committee_packet),
                "tournament_latest_textual": latest_textual,
                "tournament_latest_textual_pretty": pretty_json(latest_textual),
            },
        )

    @router.get("/llm-tournament/file")
    def llm_tournament_file(path: str | None = Query(default=None)):
        artifact_path = resolve_artifact_path(path)
        if not artifact_path:
            raise HTTPException(status_code=404, detail="artifact not found")
        return PlainTextResponse(artifact_path.read_text(encoding="utf-8"))

    return router
