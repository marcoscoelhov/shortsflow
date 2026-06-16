from __future__ import annotations

import time
from typing import Any
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.editorial.retention import enrich_plan_for_script_generation
from app.editorial.visual_contract import normalize_visual_contract_payload
from app.job_origin import JOB_ORIGIN_READY_SCRIPT_BANK
from app.manual_script import extract_ready_script_from_notes
from app.models import Job, Script, TopicPlan, TopicRequest
from app.pipelines.common import FatalStepError, RecoverableStepError, model_payload
from app.pipelines.base import BasePipeline
from app.pipelines.script_audit import ScriptAuditDomain
from app.pipelines.script_fact_pack import ScriptFactPackDomain
from app.pipelines.script_metrics import normalize_script_metrics
from app.pipelines.script_repair import ScriptRepairDomain
from app.utils import new_id, stable_hash, utcnow


class ScriptPipeline(BasePipeline):
    def step_script(self, session: Session, job: Job, attempt: int) -> list[str]:
        step_started = time.monotonic()
        stage_timings_ms: dict[str, float] = {}
        self._remove_stale_quality_report(job.job_id, "script_rejected.json")
        self._remove_stale_quality_report(job.job_id, "script_generation_debug.json")
        self._remove_stale_quality_report(job.job_id, "visual_contract.json")
        self._remove_stale_quality_report(job.job_id, "visual_contract_gate.json")
        topic_plan = session.scalar(select(TopicPlan).where(TopicPlan.job_id == job.job_id))
        request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job.job_id))
        assert topic_plan and request
        editorial_mode = self._editorial_mode(topic_plan, request)
        research_brief = self._build_research_brief(topic_plan, request)
        plan_dict = {
            "canonical_topic": topic_plan.canonical_topic,
            "angle": topic_plan.angle,
            "hook_promise": topic_plan.hook_promise,
            "title_candidates": topic_plan.title_candidates,
            "tone": request.tone or "intrigante_direto",
            "requested_angle": request.requested_angle,
            "hub_notes": request.notes,
            "original_input": request.seed_theme,
            "editorial_mode": editorial_mode,
            "research_brief": research_brief,
        }
        plan_dict = enrich_plan_for_script_generation(
            plan_dict,
            target_duration_sec=job.target_duration_sec,
            recent_history=self._recent_topic_history(session, request.niche_id),
        )
        plan_dict["channel_learning_brief"] = self._channel_learning_brief(session, request.niche_id)
        ready_script = extract_ready_script_from_notes(request.notes)
        if ready_script is not None:
            plan_dict["ready_script_mode"] = True
            plan_dict["ready_script_fact_check_confirmed"] = ready_script.fact_check_confirmed
            self.storage.persist_json(
                job.job_id,
                "ready_script_input.json",
                {
                    "schema_version": self.settings.schema_version,
                    "job_id": job.job_id,
                    "created_at": utcnow().isoformat(),
                    "fact_check_confirmed": ready_script.fact_check_confirmed,
                    "raw_text": ready_script.raw_text,
                    "hashtags": ready_script.hashtags,
                },
            )
        fact_started = time.monotonic()
        if ready_script is not None:
            fact_pack = ready_script.fact_pack
        else:
            fact_pack = self._build_fact_pack(topic_plan, request, research_brief)
        stage_timings_ms["fact_pack_ms"] = round((time.monotonic() - fact_started) * 1000, 1)
        plan_dict["fact_pack"] = fact_pack
        self.storage.persist_json(job.job_id, "fact_pack.json", self._serialize_for_json(fact_pack))
        if self._requires_verified_fact_pack(topic_plan, request, fact_pack):
            error = FatalStepError("script quality gate failed: fact_pack_missing_for_factual_topic")
            self._persist_script_generation_debug(
                job_id=job.job_id,
                attempt=attempt,
                plan_dict=plan_dict,
                fact_pack=fact_pack,
                phase="fact_pack_failed",
                elapsed_ms=0.0,
                stage_timings_ms={
                    **stage_timings_ms,
                    "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
                },
                error=error,
            )
            raise error
        structured_contract_file: str | None = None
        if ready_script is None:
            structured_contract = self._structured_viral_contract(plan_dict, job.target_duration_sec)
            plan_dict["structured_viral_contract"] = structured_contract
            self.storage.persist_json(job.job_id, "structured_viral_contract.json", self._serialize_for_json(structured_contract))
            structured_contract_file = "structured_viral_contract.json"
        generation_started = time.monotonic()
        if ready_script is not None:
            script = ready_script.script
            generation_elapsed_ms = 0.0
        else:
            try:
                script = self.providers.creative.generate_script(plan_dict)
            except Exception as exc:  # noqa: BLE001
                self._persist_script_generation_debug(
                    job_id=job.job_id,
                    attempt=attempt,
                    plan_dict=plan_dict,
                    fact_pack=fact_pack,
                    phase="generation",
                    elapsed_ms=round((time.monotonic() - generation_started) * 1000, 1),
                    stage_timings_ms={
                        **stage_timings_ms,
                        "generation_ms": round((time.monotonic() - generation_started) * 1000, 1),
                        "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
                    },
                    error=exc,
                )
                raise
            generation_elapsed_ms = round((time.monotonic() - generation_started) * 1000, 1)
        stage_timings_ms["generation_ms"] = generation_elapsed_ms
        validation_started = time.monotonic()
        try:
            script, metrics = self._validate_or_repair_script(script, plan_dict, job.target_duration_sec, request.cta_style or "none", job.job_id)
            script, viral_metrics, viral_repair_file = self._validate_or_repair_viral_intensity(
                script,
                plan_dict=plan_dict,
                ready_script_mode=ready_script is not None,
                ready_script_bank_mode=job.job_origin == JOB_ORIGIN_READY_SCRIPT_BANK,
                job_id=job.job_id,
            )
            metrics = {**metrics, "viral_intensity": viral_metrics}
        except Exception as exc:  # noqa: BLE001
            self._persist_script_generation_debug(
                job_id=job.job_id,
                attempt=attempt,
                plan_dict=plan_dict,
                fact_pack=fact_pack,
                phase="validation",
                elapsed_ms=generation_elapsed_ms,
                script=script,
                stage_timings_ms={
                    **stage_timings_ms,
                    "validation_ms": round((time.monotonic() - validation_started) * 1000, 1),
                    "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
                },
                error=exc,
            )
            raise
        stage_timings_ms["validation_ms"] = round((time.monotonic() - validation_started) * 1000, 1)
        audit_started = time.monotonic()
        audit_topic_context = {
            key: plan_dict.get(key)
            for key in ("canonical_topic", "angle", "hook_promise", "original_input", "editorial_mode")
        }
        text_audit = self._text_publish_audit(job.job_id, script, fact_pack, audit_topic_context)
        audit_repair_file: str | None = None
        if text_audit.get("passed") is False:
            script, metrics, text_audit, audit_repair_file = self._repair_after_text_audit(
                job_id=job.job_id,
                script=script,
                metrics=metrics,
                audit=text_audit,
                plan_dict=plan_dict,
                target_duration_sec=job.target_duration_sec,
                cta_style=request.cta_style or "none",
                topic_context=audit_topic_context,
            )
        stage_timings_ms["text_publish_audit_ms"] = round((time.monotonic() - audit_started) * 1000, 1)
        if text_audit.get("passed") is False:
            audit_reasons = [str(reason) for reason in text_audit.get("reasons") or ["text_publish_audit_failed"]]
            self._persist_script_generation_debug(
                job_id=job.job_id,
                attempt=attempt,
                plan_dict=plan_dict,
                fact_pack=fact_pack,
                phase="audit_failed",
                elapsed_ms=generation_elapsed_ms,
                script=script,
                metrics={**metrics, "text_publish_audit": text_audit},
                stage_timings_ms={
                    **stage_timings_ms,
                    "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
                },
            )
            self._persist_script_rejection(job.job_id, script, metrics, audit_reasons)
            raise RecoverableStepError(f"text publish audit failed: {', '.join(audit_reasons)}")
        visual_contract_started = time.monotonic()
        try:
            visual_contract, visual_contract_metrics = self._generate_and_validate_visual_contract(job.job_id, script)
        except Exception as exc:  # noqa: BLE001
            stage_timings_ms["visual_contract_ms"] = round((time.monotonic() - visual_contract_started) * 1000, 1)
            self._persist_script_generation_debug(
                job_id=job.job_id,
                attempt=attempt,
                plan_dict=plan_dict,
                fact_pack=fact_pack,
                phase="visual_contract_failed",
                elapsed_ms=generation_elapsed_ms,
                script=script,
                metrics=metrics,
                stage_timings_ms={
                    **stage_timings_ms,
                    "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
                },
                error=exc,
            )
            if isinstance(exc, RecoverableStepError):
                raise
            raise RecoverableStepError(f"visual contract generation failed: {exc}") from exc
        stage_timings_ms["visual_contract_ms"] = round((time.monotonic() - visual_contract_started) * 1000, 1)
        metrics = {**metrics, "visual_contract": visual_contract_metrics}
        self._persist_script_generation_debug(
            job_id=job.job_id,
            attempt=attempt,
            plan_dict=plan_dict,
            fact_pack=fact_pack,
            phase="completed",
            elapsed_ms=generation_elapsed_ms,
            script=script,
            metrics=metrics,
            stage_timings_ms={
                **stage_timings_ms,
                "total_step_ms": round((time.monotonic() - step_started) * 1000, 1),
            },
        )
        script = self._attach_editorial_source(script, plan_dict)
        editorial_source = "ready_script" if ready_script is not None else "hub_viral_prompt"
        metrics = {**metrics, "editorial_source": editorial_source, "downstream_source_of_truth": "script_full_narration"}
        created_at = utcnow()
        payload = {
            "schema_version": self.settings.schema_version,
            "script_id": new_id(),
            "job_id": job.job_id,
            "created_at": created_at,
            "content_hash": stable_hash(script),
            **script,
        }
        session.execute(delete(Script).where(Script.job_id == job.job_id))
        session.add(Script(**model_payload(Script, payload)))
        self.storage.persist_json(job.job_id, "script.json", self._serialize_for_json(payload))
        self.storage.persist_json(job.job_id, "visual_contract.json", self._serialize_for_json(visual_contract))
        script_telemetry_file = self._persist_repair_telemetry(
            job.job_id,
            "script",
            {
                "job_id": job.job_id,
                "attempt": attempt,
                "final_passed": metrics.get("script_quality_gate_pass", False) and metrics.get("fact_pack_consistency_pass", False),
                "attempts": metrics.get("script_repair_attempts_log", []),
            },
        )
        quality_summary = dict(job.quality_summary or {})
        quality_summary["script"] = metrics
        job.quality_summary = quality_summary
        self._append_event(job.job_id, "script.generated", "succeeded", metrics)
        artifacts = ["fact_pack.json", "script.json", "script_generation_debug.json", "text_publish_audit.json", script_telemetry_file]
        if audit_repair_file is not None:
            artifacts.append(audit_repair_file)
        if viral_repair_file is not None:
            artifacts.append(viral_repair_file)
        artifacts.append("visual_contract.json")
        if ready_script is not None:
            artifacts.append("ready_script_input.json")
        if structured_contract_file is not None:
            artifacts.append(structured_contract_file)
        return artifacts

    def _validate_viral_intensity(self, script: dict[str, Any], *, ready_script_mode: bool) -> dict[str, Any]:
        result = self.viral_intensity_gate.validate(script)
        return self._viral_intensity_metrics(result, ready_script_mode=ready_script_mode)

    def _validate_or_repair_viral_intensity(
        self,
        script: dict[str, Any],
        *,
        plan_dict: dict[str, Any],
        ready_script_mode: bool,
        job_id: str,
        ready_script_bank_mode: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        result = self.viral_intensity_gate.validate(script)
        if result.passed:
            return script, self._viral_intensity_metrics(result, ready_script_mode=ready_script_mode), None
        if ready_script_bank_mode:
            metrics = self._viral_intensity_metrics(result, ready_script_mode=ready_script_mode, raise_on_fail=False)
            metrics["ready_script_bank_policy"] = "viral_intensity_diagnostic_only"
            return script, metrics, None
        if ready_script_mode:
            metrics = self._viral_intensity_metrics(result, ready_script_mode=ready_script_mode, raise_on_fail=False)
            self._persist_script_rejection(job_id, script, {"viral_intensity": metrics}, ["script_viral_intensity_low"])
            raise RecoverableStepError(f"viral intensity gate failed: {', '.join(result.reasons[:6])}")
        repair_reasons = [str(reason) for reason in result.reasons]
        try:
            candidate = self.providers.creative.repair_script(script, repair_reasons, plan_dict)
        except Exception as exc:  # noqa: BLE001
            raise RecoverableStepError(f"viral intensity gate failed: {', '.join(repair_reasons[:6])}") from exc
        repaired_result = self.viral_intensity_gate.validate(candidate)
        if not repaired_result.passed:
            raise RecoverableStepError(f"viral intensity gate failed: {', '.join(repaired_result.reasons[:6])}")
        repaired_metrics = self._viral_intensity_metrics(repaired_result, ready_script_mode=False)
        repaired_metrics["viral_intensity_repair_attempted"] = True
        repaired_metrics["viral_intensity_original_reasons"] = repair_reasons
        repair_payload = {
            "job_id": job_id,
            "original_reasons": repair_reasons,
            "repaired_passed": repaired_result.passed,
            "repaired_reasons": repaired_result.reasons,
            "metrics": repaired_metrics,
        }
        if hasattr(self, "storage"):
            try:
                self.storage.persist_json(job_id, "viral_intensity_repair.json", self._serialize_for_json(repair_payload))
            except Exception:  # noqa: BLE001
                pass
        return candidate, repaired_metrics, "viral_intensity_repair.json"

    def _viral_intensity_metrics(self, result: Any, *, ready_script_mode: bool, raise_on_fail: bool = True) -> dict[str, Any]:
        metrics = dict(result.metrics)
        metrics["viral_intensity_reasons"] = result.reasons
        metrics["viral_intensity_hard_block"] = bool(not result.passed)
        if ready_script_mode and not result.passed:
            metrics["viral_intensity_ready_script_blocked"] = True
        if not result.passed and raise_on_fail:
            raise RecoverableStepError(f"viral intensity gate failed: {', '.join(result.reasons[:6])}")
        return metrics

    def _repair_after_text_audit(
        self,
        *,
        job_id: str,
        script: dict[str, Any],
        metrics: dict[str, Any],
        audit: dict[str, Any],
        plan_dict: dict[str, Any],
        target_duration_sec: int,
        cta_style: str,
        topic_context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str | None]:
        reasons = list(dict.fromkeys(str(reason) for reason in audit.get("reasons") or []))
        repairable_reasons = {"invented_source_fact_ids", "off_topic", "unsupported_claim", "weak_ending"}
        if not reasons or not set(reasons).issubset(repairable_reasons):
            return script, metrics, audit, None

        try:
            candidate = self.providers.creative.repair_script(script, reasons, plan_dict)
            repaired_script, repaired_metrics = self._validate_or_repair_script(
                candidate,
                plan_dict,
                target_duration_sec,
                cta_style,
                job_id,
            )
            repaired_audit = self._text_publish_audit(job_id, repaired_script, plan_dict.get("fact_pack") or {}, topic_context)
        except Exception as exc:  # noqa: BLE001
            repaired_script = script
            repaired_metrics = metrics
            repaired_audit = {
                "passed": False,
                "reasons": reasons,
                "provider": "post_audit_repair",
                "repair_error": f"{type(exc).__name__}: {exc}",
            }

        artifact_name = "text_publish_audit_repair.json"
        self.storage.persist_json(
            job_id,
            artifact_name,
            {
                "schema_version": self.settings.schema_version,
                "job_id": job_id,
                "created_at": utcnow().isoformat(),
                "initial_audit": self._serialize_for_json(audit),
                "final_audit": self._serialize_for_json(repaired_audit),
                "repair_reasons": reasons,
                "revalidated_locally": repaired_audit.get("repair_error") is None,
            },
        )
        if repaired_audit.get("passed") is not True:
            return script, metrics, repaired_audit, artifact_name
        repaired_metrics = {
            **repaired_metrics,
            "text_audit_repair_used": True,
            "text_audit_repair_initial_reasons": reasons,
        }
        repaired_script["qa_metrics"] = repaired_metrics
        return repaired_script, repaired_metrics, repaired_audit, artifact_name

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self.fact_pack_domain = ScriptFactPackDomain(self)
        self.audit_domain = ScriptAuditDomain(self)
        self.repair_domain = ScriptRepairDomain(self)

    def _structured_viral_contract(self, plan_dict: dict[str, Any], target_duration_sec: int) -> dict[str, Any]:
        return {
            "schema_version": self.settings.schema_version,
            "contract_name": "Pauta Viral Estruturada",
            "source": "hub_viral_prompt",
            "topic": {
                "canonical_topic": plan_dict.get("canonical_topic"),
                "angle": plan_dict.get("angle"),
                "hook_promise": plan_dict.get("hook_promise"),
                "original_input": plan_dict.get("original_input"),
                "requested_angle": plan_dict.get("requested_angle"),
                "editorial_mode": plan_dict.get("editorial_mode"),
            },
            "target_duration_sec": target_duration_sec,
            "word_count_range": [80, 120],
            "max_words_per_sentence": 15,
            "field_order": ["title", "hook", "loop", "beats", "payoff", "closing", "hashtags"],
            "fields": {
                "title": {
                    "source_label": "Título",
                    "internal_target": "title",
                    "rule": "45-75 caracteres, palavra-chave no início quando natural, promessa específica e verificável",
                },
                "hook": {
                    "source_label": "Hook",
                    "internal_target": "hook",
                    "rule": "0-2s, primeira palavra forte, contraste, paradoxo ou fato impossível-mas-verdadeiro",
                },
                "loop": {
                    "source_label": "Loop",
                    "internal_target": "retention_map.proof_or_tension",
                    "rule": "pergunta mental de tensão respondida apenas no payoff",
                },
                "beats": {
                    "source_label": "Beats",
                    "internal_target": "body_beats",
                    "rule": "3-5 frases em escalada: fato, implicação, consequência, imagem visual e virada",
                },
                "payoff": {
                    "source_label": "Payoff",
                    "internal_target": "last_body_beat_or_turn_or_payoff",
                    "rule": "revelação mais surpreendente no último terço, prova o hook e fecha o loop",
                },
                "closing": {
                    "source_label": "Fechamento",
                    "internal_target": "ending",
                    "rule": "recontextualiza o hook com frase curta que provoca replay mental",
                },
                "hashtags": {
                    "source_label": "Hashtags",
                    "internal_target": "publish_package.hashtags",
                    "rule": "5 tags mix pt-BR/en com alcance amplo e nicho de curiosidades; não entram na narração",
                },
            },
            "prohibited_openings": ["você sabia", "voce sabia", "já imaginou", "ja imaginou", "nesse vídeo", "nesse video"],
            "output_rule": "O provider retorna JSON interno do app, mas deve satisfazer semanticamente estes campos.",
        }

    def _generate_and_validate_visual_contract(self, job_id: str, script: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        self._remove_stale_quality_report(job_id, "visual_contract_gate.json")
        raw_contract = self.providers.creative.generate_visual_contract(script)
        raw_dict = raw_contract if isinstance(raw_contract, dict) else {}
        contract = normalize_visual_contract_payload(
            raw_contract,
            script=script,
            schema_version=self.settings.schema_version,
            source_provider=str(raw_dict.get("source_provider") or raw_dict.get("provider") or ""),
        )
        gate = self.visual_contract_gate.validate(contract)
        metrics = gate.metrics
        if not gate.passed:
            self.storage.persist_json(
                job_id,
                "visual_contract_gate.json",
                {"reasons": gate.reasons, "metrics": gate.metrics, "visual_contract": contract},
            )
            raise RecoverableStepError(f"visual contract quality gate failed: {', '.join(gate.reasons[:6])}")
        return contract, metrics

    def _requires_verified_fact_pack(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._requires_verified_fact_pack(*args, **kwargs)

    def _editorial_mode(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._editorial_mode(*args, **kwargs)

    def _topic_requires_verified_fact_pack(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._topic_requires_verified_fact_pack(*args, **kwargs)

    def _build_research_brief(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._build_research_brief(*args, **kwargs)

    def _build_fact_pack(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._build_fact_pack(*args, **kwargs)

    def _query_supports_research_brief(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._query_supports_research_brief(*args, **kwargs)

    def _fact_topic_tokens(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_topic_tokens(*args, **kwargs)

    def _query_matches_primary_fact_topic(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._query_matches_primary_fact_topic(*args, **kwargs)

    def _fact_pack_matches_topic(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_pack_matches_topic(*args, **kwargs)

    def _fact_query_priority(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_query_priority(*args, **kwargs)

    def _is_weak_fact_query(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._is_weak_fact_query(*args, **kwargs)

    def _fact_pack_queries(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_pack_queries(*args, **kwargs)

    def _should_include_standalone_fact_concept(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._should_include_standalone_fact_concept(*args, **kwargs)

    def _fact_query_source_texts(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_query_source_texts(*args, **kwargs)

    def _clean_fact_query(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._clean_fact_query(*args, **kwargs)

    def _extract_fact_entity(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._extract_fact_entity(*args, **kwargs)

    def _fact_query_concepts(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_query_concepts(*args, **kwargs)

    def _normalize_fact_text(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._normalize_fact_text(*args, **kwargs)

    def _fact_result_is_relevant(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_result_is_relevant(*args, **kwargs)

    def _fact_sentence_is_useful(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._fact_sentence_is_useful(*args, **kwargs)

    def _scientific_article_fact_pack(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._scientific_article_fact_pack(*args, **kwargs)

    def _openalex_abstract_text(self, *args: Any, **kwargs: Any) -> Any:
        return self.fact_pack_domain._openalex_abstract_text(*args, **kwargs)

    def _text_publish_audit(self, *args: Any, **kwargs: Any) -> Any:
        return self.audit_domain._text_publish_audit(*args, **kwargs)

    def _normalize_text_publish_audit(self, *args: Any, **kwargs: Any) -> Any:
        return self.audit_domain._normalize_text_publish_audit(*args, **kwargs)

    def _call_with_timeout(self, *args: Any, **kwargs: Any) -> Any:
        return self.audit_domain._call_with_timeout(*args, **kwargs)

    def _fact_pack_consistency_reasons(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._fact_pack_consistency_reasons(*args, **kwargs)

    def _apply_cta_policy(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._apply_cta_policy(*args, **kwargs)

    def _attach_editorial_source(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._attach_editorial_source(*args, **kwargs)

    def _postprocess_script_for_quality(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._postprocess_script_for_quality(*args, **kwargs)

    def _restore_script_from_retention_map(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._restore_script_from_retention_map(*args, **kwargs)

    def _repair_common_script_text_issues(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._repair_common_script_text_issues(*args, **kwargs)

    def _normalize_script_visible_text(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._normalize_script_visible_text(*args, **kwargs)

    def _normalize_script_narration_fields(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._normalize_script_narration_fields(*args, **kwargs)

    def _split_long_script_sentences(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._split_long_script_sentences(*args, **kwargs)

    def _should_force_conservative_fact_rewrite(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._should_force_conservative_fact_rewrite(*args, **kwargs)

    def _should_repair_loop(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._should_repair_loop(*args, **kwargs)

    def _rewrite_script_conservatively(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._rewrite_script_conservatively(*args, **kwargs)

    def _fact_backed_pt_br_sentence(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._fact_backed_pt_br_sentence(*args, **kwargs)

    def _soften_risky_sentence(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._soften_risky_sentence(*args, **kwargs)

    def _repair_script_loop_closure(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._repair_script_loop_closure(*args, **kwargs)

    def _loop_closure_sentence(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._loop_closure_sentence(*args, **kwargs)

    def _script_anchor_phrase(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._script_anchor_phrase(*args, **kwargs)

    def _attach_claim_trace(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._attach_claim_trace(*args, **kwargs)

    def _normalize_claim_trace(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._normalize_claim_trace(*args, **kwargs)

    def _validate_or_repair_script(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._validate_or_repair_script(*args, **kwargs)

    def _validate_ready_script_without_repair(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._validate_ready_script_without_repair(*args, **kwargs)

    def _ready_script_declared_fact_check_accepts(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._ready_script_declared_fact_check_accepts(*args, **kwargs)

    def _claim_trace_metrics(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._claim_trace_metrics(*args, **kwargs)

    def _persist_script_rejection(self, *args: Any, **kwargs: Any) -> Any:
        return self.repair_domain._persist_script_rejection(*args, **kwargs)








    def _persist_script_generation_debug(
        self,
        job_id: str,
        attempt: int,
        plan_dict: dict[str, Any],
        fact_pack: dict[str, Any],
        phase: str,
        elapsed_ms: float,
        script: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        stage_timings_ms: dict[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        payload = {
            "job_id": job_id,
            "attempt": attempt,
            "phase": phase,
            "elapsed_ms": elapsed_ms,
            "strict_minimax_validation": self.settings.strict_minimax_validation,
            "llm_primary_provider": self.settings.llm_primary_provider,
            "llm_fallback_provider": self.settings.llm_fallback_provider,
            "llm_script_draft_provider": self.settings.llm_script_draft_provider,
            "llm_enable_fallback": self.settings.llm_enable_fallback,
            "real_run_allow_mock_fallback": self.settings.real_run_allow_mock_fallback,
            "llm_script_draft_timeout_sec": self.settings.llm_script_draft_timeout_sec,
            "minimax_script_timeout_sec": self.settings.minimax_script_timeout_sec,
            "fact_pack_status": fact_pack.get("status"),
            "fact_count": len(fact_pack.get("facts") or []),
            "stage_timings_ms": stage_timings_ms or {},
            "canonical_topic": plan_dict.get("canonical_topic"),
            "angle": plan_dict.get("angle"),
            "requested_angle": plan_dict.get("requested_angle"),
            "source_fact_ids": list((script or {}).get("source_fact_ids") or []),
            "claim_trace": self._serialize_for_json({"claim_trace": (script or {}).get("claim_trace") or []})["claim_trace"],
            "script_title": (script or {}).get("title"),
            "script_hook": (script or {}).get("hook"),
            "script_snapshot": self._serialize_for_json(
                {
                    "title": (script or {}).get("title"),
                    "hook": (script or {}).get("hook"),
                    "body_beats": (script or {}).get("body_beats"),
                    "ending": (script or {}).get("ending"),
                    "full_narration": (script or {}).get("full_narration"),
                    "key_facts": (script or {}).get("key_facts"),
                }
            ),
            "script_language": (script or {}).get("language"),
            "script_estimated_duration_sec": (script or {}).get("estimated_duration_sec"),
            "script_provider": ((script or {}).get("qa_metrics") or {}).get("generation_provider")
            or ((script or {}).get("qa_metrics") or {}).get("source_provider"),
            "script_provider_role": ((script or {}).get("qa_metrics") or {}).get("generation_provider_role"),
            "qa_metrics": self._serialize_for_json(metrics or {}),
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error) if error else None,
        }
        self.storage.persist_json(job_id, "script_generation_debug.json", self._serialize_for_json(payload))
