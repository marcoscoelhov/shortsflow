from __future__ import annotations

from typing import Any

JOB_ORIGIN_READY_SCRIPT_BANK = "ready_script_bank"
JOB_ORIGIN_MANUAL_READY_SCRIPT = "manual_ready_script"
JOB_ORIGIN_AUTOMATIC_TOPIC = "automatic_topic"
JOB_ORIGIN_MANUAL_THEME = "manual_theme"
JOB_ORIGIN_MANUAL_TITLE = "manual_title"
JOB_ORIGIN_UNKNOWN = "unknown"

CREATION_VIA_HUB = "hub"
CREATION_VIA_DAILY_CYCLE = "daily_cycle"
CREATION_VIA_CLI = "cli"
CREATION_VIA_API = "api"
CREATION_VIA_RECREATION = "recreation"
CREATION_VIA_UNKNOWN = "unknown"

JOB_ORIGIN_LABELS = {
    JOB_ORIGIN_READY_SCRIPT_BANK: "Banco",
    JOB_ORIGIN_MANUAL_READY_SCRIPT: "Roteiro manual",
    JOB_ORIGIN_AUTOMATIC_TOPIC: "Auto",
    JOB_ORIGIN_MANUAL_THEME: "Tema manual",
    JOB_ORIGIN_MANUAL_TITLE: "Título manual",
    JOB_ORIGIN_UNKNOWN: "Origem incerta",
}

JOB_ORIGIN_DESCRIPTIONS = {
    JOB_ORIGIN_READY_SCRIPT_BANK: "Banco de Roteiros Prontos",
    JOB_ORIGIN_MANUAL_READY_SCRIPT: "Roteiro Pronto manual",
    JOB_ORIGIN_AUTOMATIC_TOPIC: "Tema Automático",
    JOB_ORIGIN_MANUAL_THEME: "Tema manual",
    JOB_ORIGIN_MANUAL_TITLE: "Título manual",
    JOB_ORIGIN_UNKNOWN: "Origem incerta",
}

CREATION_VIA_LABELS = {
    CREATION_VIA_HUB: "Hub",
    CREATION_VIA_DAILY_CYCLE: "Ciclo diário",
    CREATION_VIA_CLI: "CLI",
    CREATION_VIA_API: "API",
    CREATION_VIA_RECREATION: "Recriação",
    CREATION_VIA_UNKNOWN: "Via incerta",
}

CREATION_VIA_DESCRIPTIONS = {
    CREATION_VIA_HUB: "Criado pelo Hub de Revisão",
    CREATION_VIA_DAILY_CYCLE: "Criado pelo Ciclo Diário de Automação",
    CREATION_VIA_CLI: "Criado por comando local",
    CREATION_VIA_API: "Criado por chamada direta de API",
    CREATION_VIA_RECREATION: "Criado como recriação de outro Job de Video",
    CREATION_VIA_UNKNOWN: "Via de criação incerta",
}

JOB_ORIGIN_VALUES = set(JOB_ORIGIN_LABELS)
CREATION_VIA_VALUES = set(CREATION_VIA_LABELS)


def normalize_job_origin(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in JOB_ORIGIN_VALUES else JOB_ORIGIN_UNKNOWN


def normalize_creation_via(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in CREATION_VIA_VALUES else CREATION_VIA_UNKNOWN


def infer_job_origin_from_notes(notes: str | None, *, automation_source: str | None = None) -> str:
    normalized_source = str(automation_source or "").strip()
    if normalized_source == JOB_ORIGIN_READY_SCRIPT_BANK:
        return JOB_ORIGIN_READY_SCRIPT_BANK
    if normalized_source == JOB_ORIGIN_AUTOMATIC_TOPIC:
        return JOB_ORIGIN_AUTOMATIC_TOPIC

    text = str(notes or "").lower()
    if "automation_source=automatic_topic" in text:
        return JOB_ORIGIN_AUTOMATIC_TOPIC
    if "input_mode=script" in text:
        return JOB_ORIGIN_MANUAL_READY_SCRIPT
    if "input_mode=title" in text:
        return JOB_ORIGIN_MANUAL_TITLE
    if "trend_research=" in text:
        return JOB_ORIGIN_AUTOMATIC_TOPIC
    if "input_mode=theme" in text:
        return JOB_ORIGIN_MANUAL_THEME
    return JOB_ORIGIN_UNKNOWN


def infer_creation_via(*, retry_of_job_id: str | None = None, notes: str | None = None, automation_source: str | None = None) -> str:
    if retry_of_job_id:
        return CREATION_VIA_RECREATION
    normalized_source = str(automation_source or "").strip()
    if normalized_source in {JOB_ORIGIN_READY_SCRIPT_BANK, JOB_ORIGIN_AUTOMATIC_TOPIC}:
        return CREATION_VIA_DAILY_CYCLE
    if "entrada do hub:" in str(notes or "").lower():
        return CREATION_VIA_HUB
    return CREATION_VIA_UNKNOWN


def resolve_job_origin(stored: Any, notes: str | None = None, *, automation_source: str | None = None) -> str:
    normalized = normalize_job_origin(stored)
    if normalized != JOB_ORIGIN_UNKNOWN:
        return normalized
    return infer_job_origin_from_notes(notes, automation_source=automation_source)


def resolve_creation_via(
    stored: Any,
    *,
    retry_of_job_id: str | None = None,
    notes: str | None = None,
    automation_source: str | None = None,
) -> str:
    normalized = normalize_creation_via(stored)
    if normalized != CREATION_VIA_UNKNOWN:
        return normalized
    return infer_creation_via(retry_of_job_id=retry_of_job_id, notes=notes, automation_source=automation_source)


def job_origin_display(value: Any) -> dict[str, str]:
    normalized = normalize_job_origin(value)
    return {
        "value": normalized,
        "label": JOB_ORIGIN_LABELS[normalized],
        "description": JOB_ORIGIN_DESCRIPTIONS[normalized],
    }


def creation_via_display(value: Any) -> dict[str, str]:
    normalized = normalize_creation_via(value)
    return {
        "value": normalized,
        "label": CREATION_VIA_LABELS[normalized],
        "description": CREATION_VIA_DESCRIPTIONS[normalized],
    }


def job_origin_options() -> list[dict[str, str]]:
    return [job_origin_display(value) for value in JOB_ORIGIN_LABELS]


def creation_via_options() -> list[dict[str, str]]:
    return [creation_via_display(value) for value in CREATION_VIA_LABELS]


def build_job_origin_artifact(
    *,
    job_id: str,
    job_origin: str,
    creation_via: str,
    inferred: bool,
    created_at: Any,
) -> dict[str, Any]:
    origin = job_origin_display(job_origin)
    via = creation_via_display(creation_via)
    return {
        "job_id": job_id,
        "job_origin": origin["value"],
        "job_origin_label": origin["label"],
        "job_origin_description": origin["description"],
        "creation_via": via["value"],
        "creation_via_label": via["label"],
        "creation_via_description": via["description"],
        "inferred": inferred,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }
