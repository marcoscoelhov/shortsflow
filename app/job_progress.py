from __future__ import annotations

from typing import Any


PIPELINE_STEP_NAMES = [
    "input_gate",
    "topic_plan",
    "script",
    "scene_plan",
    "asset_generation",
    "tts",
    "subtitle_alignment",
    "background_music",
    "render",
    "monetization_readiness_gate",
    "publish_to_review_hub",
]

PROGRESS_STEP_LABELS = {
    "input_gate": "Entrada",
    "topic_plan": "Pauta",
    "script": "Roteiro",
    "scene_plan": "Cenas",
    "asset_generation": "Imagens",
    "tts": "Narração",
    "subtitle_alignment": "Legendas",
    "background_music": "Trilha",
    "render": "Render",
    "monetization_readiness_gate": "Monetização",
    "publish_to_review_hub": "Revisão",
}
PROGRESS_COMPLETE_STATUSES = {
    "monetization_review",
    "blocked_for_monetization",
    "ready_for_upload",
    "approved_for_publish",
    "published",
    "approved",
    "rejected",
}
PROGRESS_FAILED_STATUSES = {
    "failed",
    "script_quality_failed",
    "visual_contract_quality_failed",
    "scene_plan_quality_failed",
    "asset_quality_failed",
    "subtitle_quality_failed",
    "render_quality_failed",
    "cancelled",
}


def progress_step_label(step_name: str) -> str:
    return PROGRESS_STEP_LABELS.get(step_name, step_name.replace("_", " ").title())


def build_job_progress(
    job: Any,
    *,
    step_names: list[str] | None = None,
    performance_timeline: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_step_names = list(step_names or PIPELINE_STEP_NAMES)
    total_steps = len(resolved_step_names)
    timeline_steps = list((performance_timeline or {}).get("steps") or [])
    has_timeline_steps = bool(timeline_steps)
    latest_by_step: dict[str, dict[str, Any]] = {}
    for row in timeline_steps:
        if not isinstance(row, dict):
            continue
        step_name = str(row.get("step_name") or "")
        if step_name:
            latest_by_step[step_name] = row

    job_status = str(job.status or "")
    current_step = str(job.current_step or "")
    complete = job_status in PROGRESS_COMPLETE_STATUSES
    failed = job_status in PROGRESS_FAILED_STATUSES or job_status.endswith("_failed")
    running = job_status == "running"
    queued = job_status == "queued"
    current_index = resolved_step_names.index(current_step) if current_step in resolved_step_names else -1
    completed_count = 0
    progress_steps: list[dict[str, Any]] = []

    for index, step_name in enumerate(resolved_step_names, start=1):
        execution = latest_by_step.get(step_name, {})
        execution_status = str(execution.get("status") or "")
        step_status = "pending"
        if complete:
            step_status = "completed"
        elif execution_status == "succeeded":
            step_status = "completed"
        elif execution_status == "failed" or (failed and current_step == step_name):
            step_status = "failed"
        elif not has_timeline_steps and current_index >= 0 and index - 1 < current_index:
            step_status = "completed"
        elif running and current_step == step_name:
            step_status = "running"

        if step_status == "completed":
            completed_count += 1
        progress_steps.append(
            {
                "name": step_name,
                "label": progress_step_label(step_name),
                "index": index,
                "status": step_status,
                "attempt": execution.get("attempt"),
                "duration_ms": execution.get("duration_ms"),
                "started_at": execution.get("started_at"),
                "finished_at": execution.get("finished_at"),
            }
        )

    current_name = current_step if current_step in resolved_step_names else ""
    if not current_name:
        next_pending = next((step for step in progress_steps if step["status"] in {"running", "failed", "pending"}), None)
        current_name = str(next_pending["name"]) if next_pending else resolved_step_names[-1]
    current_label = progress_step_label(current_name)

    if complete:
        percent = 100
        state = "completed"
        summary = "Pipeline concluído; o job está pronto para revisão, aprovação ou publicação."
    elif queued:
        percent = 0
        state = "queued"
        summary = "Aguardando o worker iniciar o pipeline."
        current_label = "Fila"
    elif failed:
        percent = round((completed_count / total_steps) * 100) if total_steps else 0
        state = "failed"
        summary = f"Falhou em {current_label}; abra os dados técnicos para ver o erro."
    elif running:
        partial = 0.35 if current_name else 0
        percent = min(99, round(((completed_count + partial) / total_steps) * 100)) if total_steps else 0
        state = "running"
        summary = f"Rodando {current_label}; a página atualiza automaticamente."
    else:
        percent = min(100, round((completed_count / total_steps) * 100)) if total_steps else 0
        state = "waiting"
        summary = "Sem execução ativa no momento."

    last_event = events[-1] if events else None
    return {
        "state": state,
        "percent": percent,
        "completed_steps": completed_count,
        "total_steps": total_steps,
        "current_step": current_name,
        "current_label": current_label,
        "summary": summary,
        "steps": progress_steps,
        "last_event": last_event,
    }
