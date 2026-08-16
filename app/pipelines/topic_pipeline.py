from __future__ import annotations

from datetime import timedelta
import json
import math
import unicodedata
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.editorial.research_brief import build_research_brief
from app.editorial.topic_mode import resolve_editorial_mode
from app.automation_topics import COSMOS_CURIOSITY_POOL, WINNER_SEED_MIN_SCORE, has_recognizable_hook_object, select_cosmos_topics
from app.job_origin import JOB_ORIGIN_AUTOMATIC_TOPIC
from app.models import Job, PerformanceMetric, Script, TopicPlan, TopicRegistry, TopicRequest
from app.niche_classification import classify_niche_contract
from app.pipelines.base import BasePipeline
from app.pipelines.common import RecoverableStepError, model_payload
from app.providers.errors import ProviderFailure
from app.utils import cosineish_similarity, jaccard_bigrams, new_id, stable_hash, utcnow


def _identity_key(value: Any) -> str:
    """Normaliza caso, acentos e espaços para comparação exata de identidade."""
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _raw_topic_draft_schema_reason(raw: dict[str, Any]) -> str | None:
    """Valida o draft cru ANTES da normalização, que fabricaria defaults."""
    for field in ("canonical_topic", "angle", "hook_promise"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            return "topic_draft_schema_invalid"
    title_candidates = raw.get("title_candidates")
    if (
        not isinstance(title_candidates, list)
        or not 3 <= len(title_candidates) <= 5
        or any(not isinstance(item, str) or not item.strip() for item in title_candidates)
    ):
        return "topic_draft_schema_invalid"
    for field in ("entities", "search_terms"):
        value = raw.get(field)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            return "topic_draft_schema_invalid"
    metrics = raw.get("quality_metrics")
    if not isinstance(metrics, dict):
        return "topic_draft_schema_invalid"
    score = metrics.get("viral_potential_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "topic_draft_schema_invalid"
    if not 0.0 <= float(score) <= 1.0:
        return "topic_draft_schema_invalid"
    reason = metrics.get("viral_potential_reason")
    if not isinstance(reason, str) or not reason.strip():
        return "topic_draft_schema_invalid"
    return None


class TopicPipeline(BasePipeline):
    def step_topic_plan(self, session: Session, job: Job, attempt: int) -> list[str]:
        request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job.job_id))
        assert request
        history = self.recent_topic_history(session, request.niche_id)
        topic_drafts: dict[str, Any] | None = None
        if job.job_origin == JOB_ORIGIN_AUTOMATIC_TOPIC:
            plan, topic_metrics, topic_drafts = self.generate_automatic_topic_drafts(
                request=request,
                history=history,
                attempt=attempt,
                job_id=job.job_id,
            )
        else:
            plan, topic_metrics = self.generate_topic_plan_with_repair(
                request=request,
                history=history,
                attempt=attempt,
            )
        created_at = utcnow()
        payload = {
            "schema_version": self.settings.schema_version,
            "topic_id": new_id(),
            "job_id": job.job_id,
            "created_at": created_at,
            "content_hash": stable_hash(plan),
            **plan,
            "quality_metrics": {
                **plan["quality_metrics"],
                **topic_metrics,
            },
        }
        session.execute(delete(TopicPlan).where(TopicPlan.job_id == job.job_id))
        session.add(TopicPlan(**model_payload(TopicPlan, payload)))
        self.storage.persist_json(job.job_id, "topic_plan.json", self._serialize_for_json(payload))
        self.storage.persist_json(job.job_id, "research_brief.json", self._serialize_for_json(payload.get("research_brief") or {}))
        if topic_drafts is not None:
            self.storage.persist_json(job.job_id, "topic_drafts.json", self._serialize_for_json(topic_drafts))
        topic_telemetry_file = self._persist_repair_telemetry(
            job.job_id,
            "topic_plan",
            {
                "job_id": job.job_id,
                "attempt": attempt,
                "final_passed": payload["quality_metrics"].get("topic_uniqueness_pass", False),
                "repair_attempts": payload["quality_metrics"].get("topic_repair_loop_attempt", 1),
                "attempts": payload["quality_metrics"].get("topic_repair_attempts_log", []),
            },
        )
        job.topic_summary = f"{plan['canonical_topic']} | {plan['angle']}"
        self._append_event(job.job_id, "topic.generated", "succeeded", payload["quality_metrics"])
        artifacts = ["topic_plan.json", "research_brief.json", topic_telemetry_file]
        if topic_drafts is not None:
            artifacts.append("topic_drafts.json")
        return artifacts

    def generate_automatic_topic_drafts(
        self,
        request: TopicRequest,
        history: list[dict[str, Any]],
        attempt: int,
        job_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        candidates = self._automatic_topic_candidates(request, history)
        if not candidates:
            raise RecoverableStepError("automatic topic requires at least one eligible cosmos candidate")
        try:
            batch = self.providers.creative.plan_topic_batch(
                candidates,
                10,
                attempt,
                history,
                tone=request.tone,
                notes=request.notes,
            )
        except ProviderFailure as exc:
            audit = {
                "draft_count": 0,
                "drafts": [],
                "selected_index": None,
                "failure_reason": "provider_batch_generation_failed",
                "provider_error": str(exc)[:500],
            }
            self.storage.persist_json(job_id, "topic_drafts.json", self._serialize_for_json(audit))
            raise RecoverableStepError("automatic topic batch generation failed before judge/script/assets") from exc

        raw_drafts = batch.get("drafts") if isinstance(batch, dict) else None
        if not isinstance(raw_drafts, list) or len(raw_drafts) != 10:
            draft_count = len(raw_drafts) if isinstance(raw_drafts, list) else 0
            audit = {
                "draft_count": draft_count,
                "drafts": raw_drafts if isinstance(raw_drafts, list) else [],
                "selected_index": None,
                "failure_reason": "topic_batch_draft_count_invalid",
            }
            self.storage.persist_json(job_id, "topic_drafts.json", self._serialize_for_json(audit))
            raise RecoverableStepError("automatic topic batch must contain exactly 10 drafts before judge/script/assets")

        summaries: list[dict[str, Any]] = []
        plans: list[dict[str, Any]] = []
        draft_surfaces: list[str] = []
        hook_surfaces: list[str] = []
        seen_identity_keys: set[str] = set()
        history_identity_keys = {
            _identity_key(row.get("canonical_topic"))
            for row in history
            if str(row.get("canonical_topic") or "").strip()
        }
        for index, raw_plan in enumerate(raw_drafts):
            if not isinstance(raw_plan, dict):
                summaries.append(
                    {"index": index, "valid": False, "rejection_reason": "topic_draft_schema_invalid"}
                )
                continue
            schema_reason = _raw_topic_draft_schema_reason(raw_plan)
            if schema_reason is not None:
                summaries.append(
                    {"index": index, "valid": False, "rejection_reason": schema_reason}
                )
                continue
            plan = self.normalize_topic_plan_payload(raw_plan, request)
            metrics = self._topic_uniqueness_metrics(plan, history)
            score, score_reason = self._normalized_viral_potential(plan)
            candidate_surface = f"{plan['canonical_topic']} {plan['angle']}"
            hook_surface = plan["hook_promise"]
            identity_keys = {_identity_key(plan["canonical_topic"])}
            identity_keys.update(
                _identity_key(entity) for entity in (plan.get("entities") or []) if str(entity or "").strip()
            )
            rejection_reason: str | None = None
            if score is None:
                rejection_reason = "viral_potential_score_invalid"
            elif not score_reason:
                rejection_reason = "viral_potential_reason_missing"
            elif not isinstance(plan.get("niche_contract"), dict) or plan["niche_contract"].get("niche") != "astronomia":
                rejection_reason = "automatic_topic_niche_contract_failed"
            elif not has_recognizable_hook_object(f"{plan['canonical_topic']} {plan['hook_promise']}"):
                rejection_reason = "recognizable_hook_object_missing"
            elif identity_keys & history_identity_keys:
                rejection_reason = "topic_too_similar_to_history"
            elif identity_keys & seen_identity_keys:
                rejection_reason = "topic_draft_not_distinct"
            elif not metrics["topic_uniqueness_pass"]:
                rejection_reason = "topic_too_similar_to_history"
            elif any(cosineish_similarity(candidate_surface, surface) >= 0.82 for surface in draft_surfaces) or any(
                jaccard_bigrams(hook_surface, surface) >= 0.88 for surface in hook_surfaces
            ):
                rejection_reason = "topic_draft_not_distinct"

            quality_metrics = plan["quality_metrics"]
            if score is not None:
                quality_metrics["viral_potential_score"] = score
            if score_reason:
                quality_metrics["viral_potential_reason"] = score_reason
            summary = {
                "index": index,
                **plan,
                "viral_potential_score": score,
                "viral_potential_reason": score_reason,
                "source_provider": quality_metrics.get("source_provider"),
                "fallback_used": bool(quality_metrics.get("fallback_used", False)),
                "fallback_reason": quality_metrics.get("fallback_reason"),
                "fallback_stage": quality_metrics.get("fallback_stage"),
                "valid": rejection_reason is None,
                "rejection_reason": rejection_reason,
            }
            summaries.append(summary)
            if rejection_reason is None:
                plans.append(plan)
                draft_surfaces.append(candidate_surface)
                hook_surfaces.append(hook_surface)
                seen_identity_keys.update(identity_keys)

        if len(plans) != 10 or any(not summary.get("valid") for summary in summaries):
            audit = {
                "draft_count": 10,
                "drafts": summaries,
                "selected_index": None,
                "failure_reason": "invalid_or_repeating_topic_drafts",
            }
            self.storage.persist_json(job_id, "topic_drafts.json", self._serialize_for_json(audit))
            raise RecoverableStepError("automatic topic batch contains an invalid or repeating draft before judge/script/assets")

        try:
            judge_result = self.providers.creative.select_topic_draft(plans)
        except ProviderFailure as exc:
            audit = {
                "draft_count": 10,
                "drafts": summaries,
                "selected_index": None,
                "failure_reason": "independent_topic_draft_judge_failed",
                "judge_error": str(exc)[:500],
            }
            self.storage.persist_json(job_id, "topic_drafts.json", self._serialize_for_json(audit))
            raise RecoverableStepError("independent topic draft judge failed before script/assets") from exc

        selection, failure_reason = self._validate_topic_draft_selection(judge_result)
        if selection is None:
            audit = {
                "draft_count": 10,
                "drafts": summaries,
                "selected_index": None,
                "failure_reason": failure_reason,
                "judge_result": judge_result,
            }
            self.storage.persist_json(job_id, "topic_drafts.json", self._serialize_for_json(audit))
            raise RecoverableStepError("topic draft judge selection malformed before script/assets")

        selected_index = selection["selected_index"]
        selected_plan = plans[selected_index]
        selected_metrics = self._topic_uniqueness_metrics(selected_plan, history)
        selected_judge_score = selection["ranking"][0]["viral_potential_score"]
        selected_plan["quality_metrics"] = {
            **selected_plan["quality_metrics"],
            "topic_draft_selected_index": selected_index,
            "topic_draft_selected_topic": selected_plan["canonical_topic"],
            "topic_draft_selected_judge_score": selected_judge_score,
            "topic_draft_selected_reason": selection["selected_reason"],
            "topic_draft_judge_confidence": selection["confidence"],
            "topic_draft_judge_provider": selection["provider"],
            "topic_draft_judge_model": selection["model"],
            "topic_draft_judge_provider_role": selection["judge_provider_role"],
        }
        selected_metrics = {
            **selected_metrics,
            "topic_draft_selected_index": selected_index,
            "topic_draft_selected_topic": selected_plan["canonical_topic"],
            "topic_draft_selected_judge_score": selected_judge_score,
            "topic_draft_selected_reason": selection["selected_reason"],
            "topic_draft_judge_confidence": selection["confidence"],
            "topic_draft_judge_provider": selection["provider"],
            "topic_draft_judge_model": selection["model"],
            "topic_draft_judge_provider_role": selection["judge_provider_role"],
            "topic_repair_loop_attempt": 1,
            "topic_repair_attempts_log": summaries,
        }
        audit = {
            "draft_count": 10,
            "drafts": summaries,
            "selected_index": selected_index,
            "selected_topic": selected_plan["canonical_topic"],
            "selected_reason": selection["selected_reason"],
            "selected_judge_score": selected_judge_score,
            "ranking": selection["ranking"],
            "confidence": selection["confidence"],
            "judge_provider": selection["provider"],
            "judge_model": selection["model"],
            "judge_provider_role": selection["judge_provider_role"],
        }
        return selected_plan, selected_metrics, audit

    def _validate_topic_draft_selection(self, result: Any) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(result, dict):
            return None, "judge_result_not_object"
        selected_index = result.get("selected_index")
        if isinstance(selected_index, bool) or not isinstance(selected_index, int) or not 0 <= selected_index <= 9:
            return None, "selected_index_invalid"
        selected_reason = str(result.get("selected_reason") or "").strip()
        if not selected_reason:
            return None, "selected_reason_missing"
        ranking = result.get("ranking")
        if not isinstance(ranking, list) or len(ranking) != 10:
            return None, "ranking_count_invalid"
        normalized_ranking: list[dict[str, Any]] = []
        indices: list[int] = []
        for entry in ranking:
            if not isinstance(entry, dict):
                return None, "ranking_entry_invalid"
            index = entry.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 9:
                return None, "ranking_indices_invalid"
            score = entry.get("viral_potential_score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                return None, "ranking_score_invalid"
            score = float(score)
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                return None, "ranking_score_invalid"
            reason = str(entry.get("reason") or "").strip()
            if not reason:
                return None, "ranking_reason_missing"
            indices.append(index)
            normalized_ranking.append({"index": index, "viral_potential_score": round(score, 4), "reason": reason})
        if set(indices) != set(range(10)) or len(indices) != len(set(indices)):
            return None, "ranking_indices_invalid"
        scores = [entry["viral_potential_score"] for entry in normalized_ranking]
        if any(left < right for left, right in zip(scores, scores[1:], strict=False)):
            return None, "ranking_not_descending"
        if normalized_ranking[0]["index"] != selected_index:
            return None, "selected_index_ranking_mismatch"
        confidence = result.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None, "judge_confidence_invalid"
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return None, "judge_confidence_invalid"
        return {
            "selected_index": selected_index,
            "selected_reason": selected_reason,
            "ranking": normalized_ranking,
            "confidence": round(confidence, 4),
            "provider": str(result.get("provider") or "").strip(),
            "model": str(result.get("model") or "").strip(),
            "judge_provider_role": str(result.get("judge_provider_role") or "").strip(),
        }, None

    def _automatic_topic_candidates(self, request: TopicRequest, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prefix = "automatic_topic_candidates_json="
        for line in str(request.notes or "").splitlines():
            if not line.startswith(prefix):
                continue
            try:
                payload = json.loads(line.removeprefix(prefix))
            except json.JSONDecodeError as exc:
                raise RecoverableStepError("automatic topic candidate context is malformed") from exc
            if not isinstance(payload, list):
                return []
            candidates = [item for item in payload if isinstance(item, dict) and str(item.get("topic") or "").strip()]
            if len({str(item["topic"]).strip().casefold() for item in candidates}) != len(candidates):
                return []
            return candidates
        recent_topics = [f"{row.get('canonical_topic') or ''} {row.get('title') or ''}".strip() for row in history]
        available_count = sum(seed.base_score >= WINNER_SEED_MIN_SCORE for seed in COSMOS_CURIOSITY_POOL)
        return [
            {
                "topic": candidate.topic,
                "requested_angle": candidate.requested_angle,
                "hook_seed": candidate.hook_seed,
                "visual_seed": candidate.visual_seed,
                "seed_score": candidate.score,
            }
            for candidate in select_cosmos_topics(recent_topics, count=available_count)
        ]

    def _normalized_viral_potential(self, plan: dict[str, Any]) -> tuple[float | None, str]:
        metrics = plan.get("quality_metrics") if isinstance(plan.get("quality_metrics"), dict) else {}
        raw_score = metrics.get("viral_potential_score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            return None, ""
        score = float(raw_score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            return None, ""
        reason = str(metrics.get("viral_potential_reason") or "").strip()[:240]
        return round(score, 4), reason

    def _topic_uniqueness_metrics(self, plan: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
        candidate_topic_surface = f"{plan['canonical_topic']} {plan['angle']}"
        topic_similarity = max(
            [cosineish_similarity(candidate_topic_surface, f"{row['canonical_topic']} {row['title']}") for row in history],
            default=0.0,
        )
        hook_similarity = max(
            [jaccard_bigrams(plan["hook_promise"], row["hook"]) for row in history],
            default=0.0,
        )
        return {
            "topic_uniqueness_pass": topic_similarity < 0.82 and hook_similarity < 0.88,
            "topic_similarity_max": round(topic_similarity, 3),
            "hook_similarity_max": round(hook_similarity, 3),
        }

    def recent_topic_history(self, session: Session, niche_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = session.scalars(
            select(TopicRegistry)
            .where(
                TopicRegistry.approved.is_(True),
                TopicRegistry.created_at >= utcnow() - timedelta(days=90),
            )
            .order_by(TopicRegistry.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {"canonical_topic": row.canonical_topic, "hook": row.hook, "title": row.title}
            for row in rows
        ]

    def channel_learning_brief(self, session: Session, niche_id: str, limit: int = 30) -> dict[str, Any]:
        rows = session.execute(
            select(PerformanceMetric, TopicPlan, Script)
            .join(Job, Job.job_id == PerformanceMetric.job_id)
            .join(TopicPlan, TopicPlan.job_id == Job.job_id, isouter=True)
            .join(Script, Script.job_id == Job.job_id, isouter=True)
            .where(Job.niche_id == niche_id)
            .order_by(PerformanceMetric.created_at.desc())
            .limit(limit)
        ).all()
        samples = [
            {
                "job_id": metric.job_id,
                "retention_percent": metric.retention_percent,
                "viewed_vs_swiped_away_percent": metric.viewed_vs_swiped_away_percent,
                "rewatch_rate": metric.rewatch_rate,
                "rpm_usd": metric.rpm_usd,
                "monetization_status": metric.monetization_status,
                "canonical_topic": topic_plan.canonical_topic if topic_plan else None,
                "angle": topic_plan.angle if topic_plan else None,
                "hook": script.hook if script else None,
                "title": script.title if script else None,
            }
            for metric, topic_plan, script in rows
        ]
        if not samples:
            return {"sample_count": 0, "instruction": "No channel performance metrics recorded yet."}
        strong = [
            sample
            for sample in samples
            if (sample.get("retention_percent") or 0) >= 80
            or (sample.get("viewed_vs_swiped_away_percent") or 0) >= 70
            or (sample.get("rewatch_rate") or 0) >= 1.15
        ]
        weak = [
            sample
            for sample in samples
            if (sample.get("retention_percent") is not None and sample["retention_percent"] < 55)
            or (sample.get("viewed_vs_swiped_away_percent") is not None and sample["viewed_vs_swiped_away_percent"] < 50)
        ]
        return {
            "sample_count": len(samples),
            "strong_patterns": strong[:5],
            "weak_patterns": weak[:5],
            "instruction": "Prefer hooks, topics and pacing similar to strong_patterns; avoid weak_patterns unless the new angle is clearly different.",
        }

    def generate_topic_plan_with_repair(
        self,
        request: TopicRequest,
        history: list[dict[str, Any]],
        attempt: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        topic_attempts = max(1, self.settings.llm_topic_repair_attempts + 1)
        notes_suffix = ""
        last_metrics: dict[str, Any] | None = None
        last_plan: dict[str, Any] | None = None
        attempts_log: list[dict[str, Any]] = []
        for repair_attempt in range(1, topic_attempts + 1):
            plan = self.providers.creative.plan_topic(
                request.seed_theme,
                attempt,
                history,
                request.requested_angle,
                tone=request.tone,
                notes="\n\n".join(part for part in [request.notes, notes_suffix] if part),
            )
            plan = self.normalize_topic_plan_payload(plan, request)
            last_plan = plan
            candidate_topic_surface = f"{plan['canonical_topic']} {plan['angle']}"
            topic_similarity = max(
                [cosineish_similarity(candidate_topic_surface, f"{row['canonical_topic']} {row['title']}") for row in history],
                default=0.0,
            )
            hook_similarity = max(
                [jaccard_bigrams(plan["hook_promise"], row["hook"]) for row in history],
                default=0.0,
            )
            last_metrics = {
                "topic_uniqueness_pass": topic_similarity < 0.82 and hook_similarity < 0.88,
                "topic_similarity_max": round(topic_similarity, 3),
                "hook_similarity_max": round(hook_similarity, 3),
                "topic_repair_loop_attempt": repair_attempt,
            }
            attempts_log.append(
                {
                    "repair_attempt": repair_attempt,
                    "canonical_topic": plan["canonical_topic"],
                    "angle": plan["angle"],
                    "hook_promise": plan["hook_promise"],
                    "topic_similarity_max": round(topic_similarity, 3),
                    "hook_similarity_max": round(hook_similarity, 3),
                    "passed": last_metrics["topic_uniqueness_pass"],
                    "reason_codes": [] if last_metrics["topic_uniqueness_pass"] else ["topic_too_similar_to_history"],
                }
            )
            if last_metrics["topic_uniqueness_pass"]:
                if repair_attempt > 1:
                    last_metrics["topic_repair_used"] = True
                last_metrics["topic_repair_attempts_log"] = attempts_log
                return plan, last_metrics
            notes_suffix = (
                "REPAIR TOPIC FOR UNIQUENESS:\n"
                f"- previous canonical_topic: {plan['canonical_topic']}\n"
                f"- previous angle: {plan['angle']}\n"
                f"- previous hook_promise: {plan['hook_promise']}\n"
                f"- similarity thresholds exceeded: topic={topic_similarity:.3f}, hook={hook_similarity:.3f}\n"
                "- choose a distinctly different angle, hook promise and title set while preserving the seed theme.\n"
                "- avoid repeating recently approved topic surfaces or hooks."
            )
        assert last_plan is not None and last_metrics is not None
        last_metrics["topic_repair_attempts_log"] = attempts_log
        raise RecoverableStepError(
            f"topic too similar to approved history (topic_similarity={last_metrics['topic_similarity_max']}, hook_similarity={last_metrics['hook_similarity_max']})"
        )

    def normalize_topic_plan_payload(self, plan: dict[str, Any], request: TopicRequest) -> dict[str, Any]:
        aliases = {
            "canonical_topic": ("canonical_topic", "tema_canonico", "topico_canonico", "tema_principal", "topico_principal", "topic", "tema", "title"),
            "angle": ("angle", "angulo", "recorte", "abordagem", "requested_angle"),
            "hook_promise": ("hook_promise", "promessa_hook", "promessa_do_hook", "gancho", "hook"),
            "title_candidates": ("title_candidates", "titulos", "candidatos_titulo", "candidatos_de_titulo"),
            "entities": ("entities", "entidades", "elementos", "assuntos"),
            "search_terms": ("search_terms", "termos_busca", "termos_de_busca", "palavras_chave", "keywords"),
            "quality_metrics": ("quality_metrics", "metricas_qualidade", "metricas"),
        }
        normalized: dict[str, Any] = {}
        for target, names in aliases.items():
            for name in names:
                value = plan.get(name)
                if value not in (None, "", []):
                    normalized[target] = value
                    break

        canonical_topic = str(normalized.get("canonical_topic") or request.seed_theme).strip() or request.seed_theme
        angle = str(
            normalized.get("angle")
            or request.requested_angle
            or f"o detalhe mais contraintuitivo de {canonical_topic}"
        ).strip()
        hook_promise = str(
            normalized.get("hook_promise")
            or f"por que {canonical_topic} muda quando voce entende o mecanismo"
        ).strip()

        title_candidates = normalized.get("title_candidates")
        if isinstance(title_candidates, str):
            title_candidates = [title_candidates]
        if not isinstance(title_candidates, list) or not title_candidates:
            title_candidates = [f"{canonical_topic.capitalize()}: o detalhe que quase ninguem percebe"]

        entities = normalized.get("entities")
        if isinstance(entities, str):
            entities = [entities]
        if not isinstance(entities, list) or not entities:
            entities = [canonical_topic]

        search_terms = normalized.get("search_terms")
        if isinstance(search_terms, str):
            search_terms = [search_terms]
        if not isinstance(search_terms, list) or not search_terms:
            search_terms = [canonical_topic, f"{canonical_topic} curiosidades", f"{canonical_topic} explicacao"]

        quality_metrics = normalized.get("quality_metrics")
        if not isinstance(quality_metrics, dict):
            quality_metrics = {}
        if "topic_repair_used" not in quality_metrics:
            required = {"canonical_topic", "angle", "hook_promise", "title_candidates", "entities", "search_terms", "quality_metrics"}
            quality_metrics = {
                **quality_metrics,
                "topic_repair_used": any(key not in plan or plan.get(key) in (None, "", []) for key in required),
            }
        request_notes = str(getattr(request, "notes", "") or "")
        fallback_niche = str(getattr(request, "niche_id", "general") or "general")
        niche_policy_notes = "\n".join(
            line
            for line in request_notes.splitlines()
            if line.startswith("automatic_topic_policy=") or line.startswith("automation_source=")
        )
        niche_contract = classify_niche_contract(
            request.seed_theme,
            request.requested_angle,
            canonical_topic,
            angle,
            hook_promise,
            " ".join(str(entity) for entity in entities if str(entity).strip()),
            niche_policy_notes,
            fallback_niche=fallback_niche,
        )
        quality_metrics = {
            **quality_metrics,
            "editorial_mode": resolve_editorial_mode(
                {
                    "canonical_topic": canonical_topic,
                    "angle": angle,
                    "hook_promise": hook_promise,
                    "quality_metrics": quality_metrics,
                },
                request,
            ),
            **niche_contract.as_quality_metrics(),
        }

        normalized_plan = {
            **plan,
            "canonical_topic": canonical_topic,
            "angle": angle,
            "hook_promise": hook_promise,
            "title_candidates": [str(title).strip() for title in title_candidates if str(title).strip()][:5],
            "entities": [str(entity).strip() for entity in entities if str(entity).strip()],
            "search_terms": [str(term).strip() for term in search_terms if str(term).strip()],
            "quality_metrics": quality_metrics,
            "niche_contract": niche_contract.as_contract(),
        }
        return {
            **normalized_plan,
            "research_brief": build_research_brief(normalized_plan, request),
        }

    def upsert_topic_registry(self, session: Session, job_id: str, approved: bool) -> None:
        topic_plan = session.scalar(select(TopicPlan).where(TopicPlan.job_id == job_id))
        script = session.scalar(select(Script).where(Script.job_id == job_id))
        if not topic_plan or not script:
            return
        existing = session.scalar(select(TopicRegistry).where(TopicRegistry.job_id == job_id))
        if existing:
            existing.approved = approved
            existing.title = script.title
            existing.hook = script.hook
            existing.entities = topic_plan.entities
            return
        session.add(
            TopicRegistry(
                registry_id=new_id(),
                job_id=job_id,
                canonical_topic=topic_plan.canonical_topic,
                title=script.title,
                hook=script.hook,
                entities=topic_plan.entities,
                approved=approved,
                created_at=utcnow(),
            )
        )
