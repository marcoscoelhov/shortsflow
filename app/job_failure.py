from __future__ import annotations

from typing import Any


QUALITY_FAILURE_STATUS_BY_STEP = {
    "script": "script_quality_failed",
    "scene_plan": "scene_plan_quality_failed",
    "asset_generation": "asset_quality_failed",
    "subtitle_alignment": "subtitle_quality_failed",
    "render": "render_quality_failed",
}


def failure_status_for_step(step_name: str, message: str) -> str:
    if "quality gate" not in message and "gate failed" not in message:
        return "failed"
    if "visual contract" in message:
        return "visual_contract_quality_failed"
    return QUALITY_FAILURE_STATUS_BY_STEP.get(step_name, "failed")


def build_failure_diagnosis(
    *,
    job_id: str,
    status: str,
    step_name: str,
    message: str,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts = artifacts or {}
    evidence = [f"{step_name}: {message}"]
    reason_codes = _extract_reason_codes(message)
    evidence.extend(reason_codes)

    fact_pack = _as_dict(artifacts.get("fact_pack"))
    script_debug = _as_dict(artifacts.get("script_generation_debug"))
    text_audit = _as_dict(artifacts.get("text_publish_audit"))
    visual_gate = _as_dict(artifacts.get("visual_contract_gate"))
    rejected_script = _as_dict(artifacts.get("script_rejected"))

    fact_status = str(fact_pack.get("status") or "").strip()
    fact_count = len(fact_pack.get("facts") or []) if isinstance(fact_pack.get("facts"), list) else 0
    source_count = len(fact_pack.get("sources") or []) if isinstance(fact_pack.get("sources"), list) else 0
    fallback_reason = _first_text(
        script_debug.get("fallback_reason"),
        _as_dict(text_audit.get("audit")).get("fallback_reason"),
    )
    script_provider = str(script_debug.get("script_provider") or "").strip()
    debug_phase = str(script_debug.get("phase") or "").strip()

    provider_evidence = _provider_evidence(fallback_reason, script_provider)
    if provider_evidence:
        evidence.append(provider_evidence)
    if fact_status:
        evidence.append(f"fact_pack={fact_status}; facts={fact_count}; sources={source_count}")
    if debug_phase:
        evidence.append(f"script_debug_phase={debug_phase}")

    if "visual contract" in message.lower() or "hook_frame_missing_promise" in reason_codes:
        gate_reasons = [str(item) for item in visual_gate.get("reasons") or [] if str(item)]
        if gate_reasons:
            evidence.append(f"visual_contract_gate={', '.join(gate_reasons[:6])}")
        return _diagnosis(
            job_id=job_id,
            status=status,
            step_name=step_name,
            code=gate_reasons[0] if gate_reasons else "visual_contract_invalid",
            title="Contrato visual incompleto",
            cause="O roteiro passou a auditoria textual, mas o provider devolveu um contrato visual sem a promessa do primeiro frame. Sem essa promessa, o gerador de cenas não sabe qual leitura visual precisa provar no hook.",
            action="Regere a partir de Roteiro. Se repetir, ajuste o prompt/normalização do contrato visual para exigir hook_frame.promise antes de avançar para cenas.",
            reason_codes=reason_codes or gate_reasons,
            evidence=evidence,
        )

    if step_name == "script" and "text publish audit failed" in message.lower():
        audit = _as_dict(text_audit.get("audit"))
        audit_reasons = [str(item) for item in audit.get("reasons") or reason_codes if str(item)]
        audit_suggestions = audit.get("suggestions")
        if audit_suggestions:
            evidence.append(f"audit_suggestions={_compact(audit_suggestions)}")

        if fact_status != "verified" and {"unsupported_claim", "invented_source_fact_ids"} & set(audit_reasons):
            return _diagnosis(
                job_id=job_id,
                status=status,
                step_name=step_name,
                code="script_audit_without_verified_facts",
                title="Roteiro sem base factual verificável",
                cause="A auditoria textual encontrou claims que exigiam fonte, mas o fact pack do job não trouxe fatos verificáveis suficientes. O roteiro ficou dependente de afirmações conservadoras ou de fallback de LLM, então o gate bloqueou a publicação.",
                action="Troque o tema por algo verificável, use Roteiro Pronto com fatos confirmados ou melhore a busca de fontes antes de reprocessar a etapa de roteiro.",
                reason_codes=audit_reasons,
                evidence=evidence,
            )

        if {"off_topic", "low_factual_integrity", "invented_source_fact_ids"} & set(audit_reasons):
            script = _as_dict(rejected_script.get("script") if isinstance(rejected_script.get("script"), dict) else rejected_script)
            title = str(script.get("title") or "").strip()
            hook = str(script.get("hook") or "").strip()
            if title:
                evidence.append(f"rejected_script_title={title}")
            if hook:
                evidence.append(f"rejected_script_hook={hook}")
            fallback_clause = (
                " Um artefato legado indica que o antigo caminho determinístico de fallback gerou roteiro desalinhado ao tema salvo."
                if script_provider == "verified_fact_pack_deterministic"
                else ""
            )
            return _diagnosis(
                job_id=job_id,
                status=status,
                step_name=step_name,
                code="script_off_topic_after_repair",
                title="Roteiro saiu do tema do job",
                cause="O roteiro rejeitado não ficou alinhado ao tema e ao pacote factual do job." + fallback_clause,
                action="Reprocesse a etapa de roteiro depois de corrigir o reparo LLM ou o fact pack que gerou conteúdo fora do tema; não avance esse job para mídia.",
                reason_codes=audit_reasons,
                evidence=evidence,
            )

        return _diagnosis(
            job_id=job_id,
            status=status,
            step_name=step_name,
            code=audit_reasons[0] if audit_reasons else "text_publish_audit_failed",
            title="Auditoria textual reprovou o roteiro",
            cause="O roteiro foi gerado, mas a auditoria textual bloqueou a etapa antes de cenas, áudio e render.",
            action="Leia os códigos da auditoria, corrija roteiro/fact pack e reprocesse a partir de Roteiro.",
            reason_codes=audit_reasons,
            evidence=evidence,
        )

    return _diagnosis(
        job_id=job_id,
        status=status,
        step_name=step_name,
        code=reason_codes[0] if reason_codes else "pipeline_failure",
        title="Falha no pipeline",
        cause=f"A etapa {step_name} falhou antes de o job chegar à revisão/publicação.",
        action="Leia as evidências, corrija a causa principal e reprocesse a etapa afetada.",
        reason_codes=reason_codes,
        evidence=evidence,
    )


def _diagnosis(
    *,
    job_id: str,
    status: str,
    step_name: str,
    code: str,
    title: str,
    cause: str,
    action: str,
    reason_codes: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    compact_evidence = [item for item in dict.fromkeys(str(item).strip() for item in evidence) if item]
    return {
        "visible": True,
        "job_id": job_id,
        "status": status,
        "step": step_name,
        "code": code,
        "title": title,
        "cause": cause,
        "action": action,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "evidence": compact_evidence[:12],
        "problem_items": [],
    }


def _extract_reason_codes(message: str) -> list[str]:
    if ":" in message:
        tail = message.rsplit(":", 1)[-1]
    else:
        tail = message
    codes = []
    for part in tail.split(","):
        code = part.strip()
        if code and " " not in code and len(code) <= 80:
            codes.append(code)
    return codes


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _provider_evidence(fallback_reason: str, script_provider: str) -> str:
    parts = []
    if script_provider:
        parts.append(f"script_provider={script_provider}")
    if fallback_reason:
        normalized = " ".join(fallback_reason.split())
        if "insufficient_quota" in normalized or "429" in normalized:
            normalized = "OpenAI retornou 429 insufficient_quota; o job usou fallback"
        parts.append(f"provider_fallback={normalized}")
    return "; ".join(parts)


def _compact(value: Any) -> str:
    if isinstance(value, list):
        text = " | ".join(str(item) for item in value[:3])
    else:
        text = str(value)
    return " ".join(text.split())[:500]
