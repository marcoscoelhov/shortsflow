#!/usr/bin/env python3
"""Smoke E2E do automatic_topic com nicho astronomia.

Executa 3 variações astronômicas em ambiente isolado com providers mock explícitos,
atravessando: seleção de tema automatic_topic -> niche contract -> viral contract ->
roteiro/gates -> assets/TTS/render -> monetization readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SmokeCase:
    label: str
    topic: str
    expected_subniche: str
    requested_angle: str
    hook_seed: str
    visual_seed: str
    tags: tuple[str, ...]


SMOKE_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        label="planeta_contraintuitivo",
        topic="Por que Vênus é mais quente que Mercúrio?",
        expected_subniche="planetas",
        requested_angle="Explicar o paradoxo visual: Mercúrio fica mais perto do Sol, mas Vênus prende calor com uma atmosfera espessa. Linguagem conservadora, sem números precisos.",
        hook_seed="O planeta mais quente não é o mais perto do Sol.",
        visual_seed="Vênus brilhando coberto por nuvens densas, Mercúrio perto do Sol, comparação cinematográfica sem texto",
        tags=("venus", "mercurio", "planetas", "atmosfera"),
    ),
    SmokeCase(
        label="universo_cosmologia",
        topic="Por que buracos negros parecem engolir luz?",
        expected_subniche="buracos_negros",
        requested_angle="Usar metáfora visual segura: perto de um buraco negro, a gravidade curva caminhos da luz de modo extremo. Evitar números e certezas exageradas.",
        hook_seed="Existe um lugar onde até a luz perde a saída.",
        visual_seed="buraco negro com disco de acreção brilhante curvando luz, espaço escuro cinematográfico, sem texto",
        tags=("buraco negro", "luz", "gravidade", "universo"),
    ),
    SmokeCase(
        label="observacao_espacial",
        topic="Por que estrelas parecem piscar no céu?",
        expected_subniche="estrelas",
        requested_angle="Explicar a observação da cintilação: a atmosfera da Terra distorce a luz das estrelas, criando o pisca-pisca visto a olho nu.",
        hook_seed="A estrela não pisca sozinha: o ar mexe na luz.",
        visual_seed="estrela tremulando no céu noturno através de camadas de ar quente, atmosfera terrestre sutil, realismo",
        tags=("estrelas", "atmosfera", "observacao", "ceu"),
    ),
)

VIRAL_PROMPT = """Smoke real automatic_topic astronomia.
Obrigatório para passar no gate:
- abrir com paradoxo espacial específico, nunca com 'você sabia'
- usar loop aberto em até duas frases
- manter linguagem conservadora quando fact_pack estiver desligado
Retenção:
- cada beat precisa aumentar surpresa visual
- payoff no último terço deve recontextualizar o hook
SEO:
- título começa com planeta, universo, estrela ou fenômeno espacial quando natural
Tom:
- pt-BR direto, intrigante, sem aula morna
Proibido:
- banco de roteiros prontos
- fallback determinístico local
"""

TERMINAL_STATUSES = {
    "ready_for_upload",
    "monetization_review",
    "blocked_for_monetization",
    "script_quality_failed",
    "visual_contract_quality_failed",
    "scene_plan_quality_failed",
    "asset_quality_failed",
    "subtitle_quality_failed",
    "render_quality_failed",
    "failed",
}


def _configure_environment(data_dir: Path) -> None:
    os.environ["SHORTSFLOW_DATA_DIR"] = str(data_dir)
    os.environ["SHORTSFLOW_DATABASE_URL"] = f"sqlite:///{data_dir / 'smoke.db'}"
    os.environ["SHORTSFLOW_USE_MOCK_PROVIDERS"] = "true"
    os.environ["SHORTSFLOW_RENDER_PRIMARY_BACKEND"] = "ffmpeg"
    os.environ["SHORTSFLOW_BACKGROUND_MUSIC_ENABLED"] = "false"
    os.environ["SHORTSFLOW_FACT_PACK_ENABLED"] = "false"
    os.environ["SHORTSFLOW_NICHE_ID"] = "curiosidades"
    os.environ["SHORTSFLOW_SCENE_TARGET_COUNT"] = "5"
    os.environ["SHORTSFLOW_ASSET_GENERATION_PARALLELISM"] = "2"
    os.environ["SHORTSFLOW_YOUTUBE_PUBLISH_MODE"] = "manual"
    os.environ["SHORTSFLOW_YOUTUBE_API_ENABLED"] = "false"
    os.environ["SHORTSFLOW_TIKTOK_AUTO_PUBLISH_ENABLED"] = "false"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke E2E automatic_topic astronomia")
    parser.add_argument(
        "--data-dir",
        default="data-kanban/automatic_topic_smoke",
        help="Diretório isolado para DB e artifacts do smoke.",
    )
    parser.add_argument("--keep-data", action="store_true", help="Não limpa data-dir antes da execução.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    data_dir = (repo_root / args.data_dir).resolve()
    if data_dir.exists() and not args.keep_data:
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _configure_environment(data_dir)

    from app.automation import AutomationService
    from app.db import SessionLocal, init_db
    from app.hub_prompt import hub_settings_path, save_viral_prompt_template
    from app.job_origin import JOB_ORIGIN_AUTOMATIC_TOPIC
    from app.models import Job
    from app.orchestrator import JobOrchestrator
    from app.trends import TrendCandidate

    init_db()
    orchestrator = JobOrchestrator()
    service = AutomationService(orchestrator)
    save_viral_prompt_template(hub_settings_path(orchestrator.settings.data_dir), VIRAL_PROMPT)

    results: list[dict[str, Any]] = []
    approved_count = 0

    for index, case in enumerate(SMOKE_CASES, start=1):
        candidate = TrendCandidate(
            topic=case.topic,
            requested_angle=case.requested_angle,
            source="cosmos_curiosity_pool",
            source_url="local://cosmos-curiosity-pool/smoke-e2e",
            score=0.99,
            raw_title=case.topic,
            familiarity_score=0.95,
            source_title=case.topic,
            hook_seed=case.hook_seed,
            visual_seed=case.visual_seed,
            why=["smoke_e2e", case.label, *case.tags],
        )
        service._cosmos_automation_topic = lambda _recent_topics, selected=candidate: selected  # type: ignore[method-assign]
        payload = service._automatic_topic_payload()
        reason = service._automatic_topic_payload_rejection_reason(payload)
        if reason:
            _fail(f"{case.label}: payload automatic_topic rejeitado antes do job: {reason}")
        if payload.get("job_origin") != JOB_ORIGIN_AUTOMATIC_TOPIC:
            _fail(f"{case.label}: job_origin inesperado no payload: {payload.get('job_origin')!r}")
        payload_notes = str(payload.get("notes") or "")
        if "ready_script" in payload_notes.lower() or "[[shortsflow_ready_script_begin]]" in payload_notes.lower():
            _fail(f"{case.label}: payload contaminado por ready_script_bank")
        if "Prompt viral customizado do hub" not in payload_notes or "source=hub_settings" not in payload_notes:
            _fail(f"{case.label}: payload não contém prompt viral do Hub")

        job_id = orchestrator.create_job(payload)
        status = orchestrator.process_job(job_id)
        if status not in TERMINAL_STATUSES:
            _fail(f"{case.label}: status terminal inesperado: {status}")

        artifact_dir = data_dir / "artifacts" / job_id
        request = _read_json(artifact_dir / "request.json")
        job_origin = _read_json(artifact_dir / "job_origin.json")
        topic_plan = _read_json(artifact_dir / "topic_plan.json") if (artifact_dir / "topic_plan.json").exists() else {}
        structured_contract = _read_json(artifact_dir / "structured_viral_contract.json") if (artifact_dir / "structured_viral_contract.json").exists() else {}
        monetization = _read_json(artifact_dir / "monetization_report.json") if (artifact_dir / "monetization_report.json").exists() else {}
        render_output = _read_json(artifact_dir / "render_output.json") if (artifact_dir / "render_output.json").exists() else {}
        script_artifact_path = artifact_dir / ("script.json" if (artifact_dir / "script.json").exists() else "script_rejected.json")
        script_artifact = _read_json(script_artifact_path) if script_artifact_path.exists() else {}

        with SessionLocal() as session:
            job = session.get(Job, job_id)
            failure_reason = job.failure_reason if job else None
            quality_summary = job.quality_summary if job else {}
            db_job_origin = job.job_origin if job else None
            db_creation_via = job.creation_via if job else None

        notes = str(request.get("notes") or "")
        quality_metrics = topic_plan.get("quality_metrics") if isinstance(topic_plan, dict) else {}
        quality_metrics = quality_metrics if isinstance(quality_metrics, dict) else {}
        niche_contract = (((structured_contract.get("topic") or {}).get("niche_contract")) if isinstance(structured_contract, dict) else {}) or {}
        viral_prompt = structured_contract.get("viral_prompt") if isinstance(structured_contract, dict) else {}
        gate_decisions_raw = structured_contract.get("gate_decisions") if isinstance(structured_contract, dict) else {}
        gate_decisions = gate_decisions_raw if isinstance(gate_decisions_raw, dict) else {}
        script_payload_raw = script_artifact.get("script") if isinstance(script_artifact, dict) else {}
        script_payload = script_payload_raw if isinstance(script_payload_raw, dict) else script_artifact
        script_payload = script_payload if isinstance(script_payload, dict) else {}
        script_qa_metrics = script_payload.get("qa_metrics") if isinstance(script_payload, dict) else {}
        script_qa_metrics = script_qa_metrics if isinstance(script_qa_metrics, dict) else {}
        rejected_gate_metrics = script_artifact.get("gate_metrics") if isinstance(script_artifact, dict) else {}
        rejected_gate_metrics = rejected_gate_metrics if isinstance(rejected_gate_metrics, dict) else {}
        gate_evidence = sorted(gate_decisions.keys())
        if not gate_evidence and "script_quality_gate_pass" in rejected_gate_metrics:
            gate_evidence = ["script_quality_rejected"]
        final_video_uri = render_output.get("video_uri")
        final_video_path = Path(final_video_uri.removeprefix("file://")) if isinstance(final_video_uri, str) and final_video_uri.startswith("file://") else None

        if db_job_origin != JOB_ORIGIN_AUTOMATIC_TOPIC:
            _fail(f"{case.label}: DB job_origin não é automatic_topic: {db_job_origin!r}")
        if db_creation_via != "daily_cycle":
            _fail(f"{case.label}: DB creation_via não é daily_cycle: {db_creation_via!r}")
        if job_origin.get("job_origin") != JOB_ORIGIN_AUTOMATIC_TOPIC:
            _fail(f"{case.label}: artifact job_origin não é automatic_topic: {job_origin}")
        if job_origin.get("creation_via") != "daily_cycle":
            _fail(f"{case.label}: artifact creation_via não é daily_cycle: {job_origin}")
        if request.get("job_origin") and request.get("job_origin") != JOB_ORIGIN_AUTOMATIC_TOPIC:
            _fail(f"{case.label}: request job_origin incompatível: {request.get('job_origin')!r}")
        if "automation_source=automatic_topic" not in notes:
            _fail(f"{case.label}: request sem automation_source=automatic_topic")
        if "automatic_topic_policy=cosmos_astronomia_universo_first" not in notes:
            _fail(f"{case.label}: request sem policy cosmos")
        if "ready_script" in notes.lower() or "[[shortsflow_ready_script_begin]]" in notes.lower():
            _fail(f"{case.label}: artifact request contaminado por ready_script_bank")
        if quality_metrics.get("topic_niche") != "astronomia":
            _fail(f"{case.label}: topic_niche não é astronomia: {quality_metrics.get('topic_niche')!r}")
        if quality_metrics.get("topic_subniche") != case.expected_subniche:
            _fail(f"{case.label}: topic_subniche incorreto: {quality_metrics.get('topic_subniche')!r}; esperado {case.expected_subniche!r}")
        if niche_contract.get("niche") != "astronomia":
            _fail(f"{case.label}: structured niche_contract não é astronomia: {niche_contract}")
        if niche_contract.get("subniche") != case.expected_subniche:
            _fail(f"{case.label}: structured subniche incorreto: {niche_contract.get('subniche')!r}; esperado {case.expected_subniche!r}")
        if viral_prompt.get("source") != "hub_settings" or "paradoxo espacial" not in str(viral_prompt.get("prompt") or ""):
            _fail(f"{case.label}: structured viral_prompt não preservou Hub/settings: {viral_prompt}")
        if not gate_evidence:
            _fail(f"{case.label}: artifact sem evidência de decisão de gate")
        if "script_quality" not in gate_decisions and "script_quality_rejected" not in gate_evidence:
            _fail(f"{case.label}: artifacts não preservaram decisão de script_quality: {gate_decisions}")
        if script_qa_metrics.get("script_generation_fallback_used") is not False:
            _fail(f"{case.label}: script indicou fallback de geração: {script_qa_metrics}")

        if status == "ready_for_upload":
            approved_count += 1
            if not final_video_path or not final_video_path.exists():
                _fail(f"{case.label}: ready_for_upload sem render final existente: {final_video_uri}")
            destination = "ready_for_upload"
            reason_code = None
        else:
            destination = status
            reason_code = None
            failure_diagnosis = quality_summary.get("failure_diagnosis") if isinstance(quality_summary, dict) else None
            if isinstance(failure_diagnosis, dict):
                reason_code = failure_diagnosis.get("primary_reason") or failure_diagnosis.get("summary")
            reason_code = reason_code or failure_reason or "gate_or_generation_rejected"

        result = {
            "case": case.label,
            "job_id": job_id,
            "topic": payload.get("seed_theme"),
            "status": status,
            "destination": destination,
            "reason_code": reason_code,
            "artifact_dir": str(artifact_dir),
            "final_video": str(final_video_path) if final_video_path else None,
            "source": job_origin.get("job_origin"),
            "creation_via": job_origin.get("creation_via"),
            "niche": quality_metrics.get("topic_niche"),
            "subniche": quality_metrics.get("topic_subniche"),
            "viral_prompt_source": viral_prompt.get("source"),
            "gate_decisions": gate_evidence,
            "monetization_final_status": monetization.get("final_status"),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    if approved_count < 1:
        _fail("Nenhum caso chegou a ready_for_upload; ver resultados acima para blocker técnico reproduzível.")

    summary = {
        "data_dir": str(data_dir),
        "cases": len(results),
        "ready_for_upload_count": approved_count,
        "results": results,
    }
    summary_path = data_dir / "automatic_topic_smoke_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    print(f"summary_path={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE_FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
