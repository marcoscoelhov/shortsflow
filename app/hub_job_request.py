from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.job_origin import (
    CREATION_VIA_HUB,
    JOB_ORIGIN_AUTOMATIC_TOPIC,
    JOB_ORIGIN_MANUAL_READY_SCRIPT,
    JOB_ORIGIN_MANUAL_THEME,
    JOB_ORIGIN_MANUAL_TITLE,
)
from app.hub_prompt import build_viral_prompt_note
from app.manual_script import build_ready_script_notes, parse_ready_script
from app.schemas import TopicRequestCreate


@dataclass(frozen=True)
class HubTrendSeed:
    seed_theme: str
    requested_angle: str | None = None
    notes: str | None = None
    report: dict[str, object] | None = None


@dataclass(frozen=True)
class HubJobRequestBuildResult:
    payload: TopicRequestCreate
    trend_report: dict[str, object] | None = None


def normalize_hub_input_mode(input_mode: str) -> str:
    if input_mode == "script":
        return "script"
    if input_mode == "title":
        return "title"
    return "theme"


def selected_angle(custom_angle: str | None, requested_angle: str | None) -> str:
    angle = (custom_angle or "").strip() or (requested_angle or "").strip()
    return "" if angle == "auto" else angle


def compose_hub_notes(
    input_mode: str,
    notes: str | None,
    *,
    retention_optimized_duration_sec: int,
    viral_prompt_template: str,
    learned_retention_guidance: str | None = None,
) -> str:
    normalized_mode = normalize_hub_input_mode(input_mode)
    if normalized_mode == "title":
        mode_note = "Entrada do hub: titulo completo fornecido pelo usuario. Preserve a promessa central, mas reescreva e otimize se necessario."
    elif normalized_mode == "script":
        mode_note = "Entrada do hub: roteiro pronto fornecido pelo usuario. Preserve como fonte de verdade editorial; nao gere outro roteiro."
    else:
        mode_note = "Entrada do hub: tema bruto fornecido pelo usuario. Transforme em pauta e titulo fortes."
    seo_note = (
        "Sempre aplicar copywriting viral e SEO otimizado para YouTube Shorts: promessa clara, "
        "palavra-chave principal no inicio quando natural, curiosidade forte, sem clickbait falso."
    )
    retention_note = (
        f"Duracao alvo padrao do hub: {retention_optimized_duration_sec}s, otimizada para retencao e viralizacao; "
        "roteiro direto, sem enrolacao, com entrega rapida da promessa."
    )
    viral_template_note = build_viral_prompt_note(viral_prompt_template)
    learned_retention_note = None
    if learned_retention_guidance and learned_retention_guidance.strip():
        learned_retention_note = (
            "Aprendizado competitivo aprovado para experimento. Use como diretriz estrutural de retencao, "
            "sem copiar palavras, roteiro literal ou exemplos de Shorts de referencia.\n"
            f"{learned_retention_guidance.strip()}"
        )
    parts = [
        part.strip()
        for part in [notes, f"input_mode={normalized_mode}", mode_note, seo_note, retention_note, learned_retention_note, viral_template_note]
        if part and part.strip()
    ]
    return "\n".join(parts)


def build_hub_job_request(
    *,
    seed_theme: str,
    input_mode: str,
    niche_id: str,
    language: str,
    target_duration_sec: int,
    tone: str,
    cta_style: str,
    notes: str | None,
    requested_angle: str | None,
    custom_angle: str | None,
    ready_script_text: str | None,

    default_niche_id: str,
    retention_optimized_duration_sec: int,
    viral_prompt_template: str,
    trend_seed_resolver: Callable[[str], HubTrendSeed],
    learned_retention_guidance: str | None = None,
    **_legacy_options: object,
) -> HubJobRequestBuildResult:
    normalized_mode = normalize_hub_input_mode(input_mode)
    angle = selected_angle(custom_angle, requested_angle)
    selected_niche = niche_id or default_niche_id
    trend_report: dict[str, object] | None = None

    if normalized_mode == "script":
        ready_script = parse_ready_script(ready_script_text or "")
        selected_seed_theme = str(ready_script.script["title"]).strip()
        combined_notes = build_ready_script_notes(notes, ready_script.raw_text)
        job_origin = JOB_ORIGIN_MANUAL_READY_SCRIPT
        notes_mode = "script"
    elif seed_theme.strip():
        selected_seed_theme = seed_theme.strip()
        combined_notes = "\n\n".join(part for part in [notes] if part)
        job_origin = JOB_ORIGIN_MANUAL_TITLE if normalized_mode == "title" else JOB_ORIGIN_MANUAL_THEME
        notes_mode = normalized_mode
    else:
        trend_seed = trend_seed_resolver(selected_niche)
        selected_seed_theme = trend_seed.seed_theme
        angle = angle or (trend_seed.requested_angle or "")
        combined_notes = "\n\n".join(part for part in [trend_seed.notes, notes] if part)
        trend_report = trend_seed.report
        job_origin = JOB_ORIGIN_AUTOMATIC_TOPIC
        notes_mode = "theme"

    payload = TopicRequestCreate(
        seed_theme=selected_seed_theme,
        niche_id=selected_niche,
        language=language,
        target_duration_sec=target_duration_sec,
        tone=tone,
        cta_style=cta_style,
        notes=compose_hub_notes(
            notes_mode,
            combined_notes,
            retention_optimized_duration_sec=retention_optimized_duration_sec,
            viral_prompt_template=viral_prompt_template,
            learned_retention_guidance=learned_retention_guidance,
        ),
        requested_angle=angle or None,
        job_origin=job_origin,
        creation_via=CREATION_VIA_HUB,
    )
    return HubJobRequestBuildResult(payload=payload, trend_report=trend_report)
