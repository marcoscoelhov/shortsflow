from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Job, ScenePlan, Script, TopicPlan, TopicRequest
from app.pipelines.common import RecoverableStepError, model_payload
from app.pipelines.base import BasePipeline
from app.utils import new_id, read_json, stable_hash, utcnow, word_tokens


class ScenePipeline(BasePipeline):
    def step_scene_plan(self, session: Session, job: Job, attempt: int) -> list[str]:
        self._remove_stale_quality_report(job.job_id, "scene_plan_rejected.json")
        self._remove_stale_quality_report(job.job_id, "scene_plan_raw.json")
        script = session.scalar(select(Script).where(Script.job_id == job.job_id))
        topic_plan = session.scalar(select(TopicPlan).where(TopicPlan.job_id == job.job_id))
        assert script and topic_plan
        request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job.job_id))
        script_artifact = self._script_artifact_payload(job.job_id)
        visual_contract = self._visual_contract_artifact_payload(job.job_id)
        script_dict = {
            "title": script.title,
            "hook": script.hook,
            "body_beats": script.body_beats,
            "ending": script.ending,
            "cta": script.cta,
            "full_narration": script.full_narration,
            "estimated_duration_sec": script.estimated_duration_sec,
            "key_facts": script.key_facts,
            "qa_metrics": script.qa_metrics,
            "retention_map": script_artifact.get("retention_map") if isinstance(script_artifact.get("retention_map"), dict) else {},
            "visual_opening": script_artifact.get("visual_opening") if isinstance(script_artifact.get("visual_opening"), dict) else {},
            "visual_contract": visual_contract,
            "canonical_topic": topic_plan.canonical_topic,
            "angle": topic_plan.angle,
            "hub_viral_prompt_source": request.notes if request else None,
            "downstream_rule": "Scenes, images, subtitles and TTS must derive from full_narration. Do not invent new beats or split tiny punchlines into standalone render scenes.",
        }
        scenes = self.providers.creative.plan_scenes(script_dict, self.settings.scene_target_count)
        self.storage.persist_json(job.job_id, "scene_plan_raw.json", self._serialize_for_json({"scenes": scenes}))
        tokens = word_tokens(script.full_narration)
        scenes = self.normalize_scene_token_coverage(scenes, script.full_narration)
        scenes = self.annotate_scene_retention_roles(scenes, script_dict)
        if not scenes or scenes[0]["token_start"] != 0 or scenes[-1]["token_end"] != len(tokens) - 1:
            fallback_planner = self.scene_fallback_planner()
            if fallback_planner is not None:
                scenes = fallback_planner.plan_scenes(script_dict, self.settings.scene_target_count)
                self.storage.persist_json(job.job_id, "scene_plan_raw.json", self._serialize_for_json({"scenes": scenes}))
                scenes = self.normalize_scene_token_coverage(scenes, script.full_narration)
                scenes = self.annotate_scene_retention_roles(scenes, script_dict)
            if not scenes or scenes[0]["token_start"] != 0 or scenes[-1]["token_end"] != len(tokens) - 1:
                raise RecoverableStepError("scene coverage invalid")
        scenes = [self.normalize_scene_semantics(scene, topic_plan.canonical_topic, visual_contract=visual_contract) for scene in scenes]
        scenes = self.align_scenes_with_visual_contract(scenes, visual_contract)
        scene_gate = self.scene_gate.validate(scenes, self.settings.scene_target_count, visual_contract=visual_contract)
        if not scene_gate.passed:
            fallback_planner = self.scene_fallback_planner()
            if fallback_planner is not None:
                scenes = fallback_planner.plan_scenes(script_dict, self.settings.scene_target_count)
                self.storage.persist_json(job.job_id, "scene_plan_raw.json", self._serialize_for_json({"scenes": scenes}))
                scenes = self.normalize_scene_token_coverage(scenes, script.full_narration)
                scenes = self.annotate_scene_retention_roles(scenes, script_dict)
                scenes = [self.normalize_scene_semantics(scene, topic_plan.canonical_topic, visual_contract=visual_contract) for scene in scenes]
                scenes = self.align_scenes_with_visual_contract(scenes, visual_contract)
                scene_gate = self.scene_gate.validate(scenes, self.settings.scene_target_count, visual_contract=visual_contract)
            if not scene_gate.passed:
                self.storage.persist_json(
                    job.job_id,
                    "scene_plan_rejected.json",
                    {"reasons": scene_gate.reasons, "metrics": scene_gate.metrics, "scenes": scenes},
                )
                raise RecoverableStepError(f"scene plan quality gate failed: {', '.join(scene_gate.reasons[:6])}")
        created_at = utcnow()
        payload = {
            "schema_version": self.settings.schema_version,
            "scene_plan_id": new_id(),
            "job_id": job.job_id,
            "created_at": created_at,
            "content_hash": stable_hash(scenes),
            "scene_count": len(scenes),
            "scenes": scenes,
        }
        session.execute(delete(ScenePlan).where(ScenePlan.job_id == job.job_id))
        session.add(ScenePlan(**model_payload(ScenePlan, payload)))
        self.storage.persist_json(job.job_id, "scene_plan.json", self._serialize_for_json(payload))
        quality_summary = dict(job.quality_summary or {})
        quality_summary["scene_plan"] = {**scene_gate.metrics, "scene_plan_gate_pass": True}
        job.quality_summary = quality_summary
        self._append_event(job.job_id, "scene_plan.generated", "succeeded", quality_summary["scene_plan"])
        return ["scene_plan.json"]

    def _script_artifact_payload(self, job_id: str) -> dict[str, Any]:
        path = self.storage.job_dir(job_id, create=False) / "script.json"
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}

    def _visual_contract_artifact_payload(self, job_id: str) -> dict[str, Any]:
        path = self.storage.job_dir(job_id, create=False) / "visual_contract.json"
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}

    def scene_fallback_planner(self) -> Any:
        if self.settings.strict_minimax_validation:
            return None
        return getattr(self.providers.creative, "scene_provider", None) or getattr(self.providers.creative, "fallback", None)

    def normalize_scene_token_coverage(self, scenes: list[dict[str, Any]], full_narration: str) -> list[dict[str, Any]]:
        if not scenes:
            return scenes
        tokens = word_tokens(full_narration)
        total_tokens = len(tokens)
        if total_tokens <= 0:
            return scenes
        ordered = [dict(scene) for scene in sorted(scenes, key=lambda scene: int(scene.get("order", 0) or 0))]
        weights = [max(1, len(word_tokens(str(scene.get("narration_text") or "")))) for scene in ordered]
        remaining_tokens = total_tokens
        remaining_weight = sum(weights)
        cursor = 0
        normalized: list[dict[str, Any]] = []
        for index, scene in enumerate(ordered):
            scene_id = str(scene.get("scene_id") or f"scene-{index + 1}")
            scenes_left = len(ordered) - index
            weight = weights[index]
            if index == len(ordered) - 1:
                count = remaining_tokens
            else:
                proportional = round(remaining_tokens * (weight / max(remaining_weight, 1)))
                count = max(1, min(proportional, remaining_tokens - (scenes_left - 1)))
            start = cursor
            end = start + count - 1
            exact_text = " ".join(tokens[start : end + 1]).strip()
            normalized.append(
                {
                    **scene,
                    "scene_id": scene_id,
                    "order": index + 1,
                    "token_start": start,
                    "token_end": end,
                    "narration_text": exact_text or str(scene.get("narration_text") or "").strip(),
                }
            )
            cursor = end + 1
            remaining_tokens -= count
            remaining_weight -= weight
        if normalized:
            normalized[0]["token_start"] = 0
            normalized[-1]["token_end"] = total_tokens - 1
            normalized[-1]["narration_text"] = " ".join(tokens[normalized[-1]["token_start"] : total_tokens]).strip()
        return normalized

    def annotate_scene_retention_roles(self, scenes: list[dict[str, Any]], script: dict[str, Any]) -> list[dict[str, Any]]:
        if not scenes:
            return scenes
        normalized: list[dict[str, Any]] = []
        visual_opening = script.get("visual_opening") if isinstance(script.get("visual_opening"), dict) else {}
        hook_text = str(script.get("hook") or "").strip()
        for index, scene in enumerate(scenes):
            updated = dict(scene)
            if index == 0:
                updated.setdefault("retention_role", "visual_hook")
                updated.setdefault("hook_text", hook_text)
                updated.setdefault("visual_opening", visual_opening)
            elif index == len(scenes) - 1:
                updated.setdefault("retention_role", "loop_close")
            normalized.append(updated)
        return normalized

    def normalize_scene_semantics(
        self,
        scene: dict[str, Any],
        canonical_topic: str,
        visual_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        topic_text = canonical_topic.replace("_", " ").strip()
        normalized = dict(scene)
        contract = visual_contract if isinstance(visual_contract, dict) else {}
        normalized["scene_id"] = str(scene.get("scene_id") or normalized.get("scene_id") or "scene-1")
        primary_subject = str(scene.get("primary_subject") or topic_text).replace("_", " ").strip()
        normalized["primary_subject"] = primary_subject or topic_text
        normalized["topic_hint"] = str(scene.get("topic_hint") or topic_text).replace("_", " ").strip() or topic_text
        visual_domain = str(scene.get("visual_domain") or contract.get("visual_domain") or "").strip()
        if visual_domain:
            normalized["visual_domain"] = visual_domain
        visual_world = str(scene.get("visual_world") or contract.get("visual_world") or "").strip()
        if visual_world:
            normalized["visual_world"] = visual_world
        base_queries = [
            query.replace("_", " ").strip()
            for query in scene.get("fallback_queries", [topic_text, f"{topic_text} astronomia", f"{topic_text} espaco"])
        ]
        normalized["fallback_queries"] = self.fallback_query_variants(topic_text, base_queries)
        normalized["image_prompt"] = self.owner.asset_pipeline.image_assets.semantic_english_image_prompt(normalized, topic_text, primary_subject)
        return normalized

    def align_scenes_with_visual_contract(self, scenes: list[dict[str, Any]], visual_contract: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not scenes or not isinstance(visual_contract, dict) or not visual_contract:
            return scenes
        aligned = [dict(scene) for scene in scenes]
        ordered_indexes = sorted(range(len(aligned)), key=lambda index: int(aligned[index].get("order", 0) or 0))
        hook_frame = visual_contract.get("hook_frame") if isinstance(visual_contract.get("hook_frame"), dict) else {}
        payoff_frame = visual_contract.get("payoff_frame") if isinstance(visual_contract.get("payoff_frame"), dict) else {}

        first = aligned[ordered_indexes[0]]
        first["retention_role"] = "visual_hook"
        hook_intent = str(hook_frame.get("recommended_visual_intent") or "").strip()
        if hook_intent:
            first["visual_intent"] = hook_intent.replace(" ", "_")
        hook_requirements = [str(item).strip() for item in hook_frame.get("must_show") or [] if str(item or "").strip()]
        if hook_requirements:
            directive = "Visual contract hook requirements: " + "; ".join(hook_requirements[:3])
            prompt = str(first.get("image_prompt") or "")
            if directive.lower() not in prompt.lower():
                first["image_prompt"] = f"{prompt}, {directive}".strip(", ")
            subject = str(first.get("primary_subject") or "")
            if not any(item.lower() in subject.lower() for item in hook_requirements):
                first["primary_subject"] = f"{subject}; {'; '.join(hook_requirements[:2])}".strip("; ")
        aligned[ordered_indexes[0]] = first

        payoff_intent = str(payoff_frame.get("recommended_visual_intent") or "").strip()
        if payoff_intent:
            payoff_indexes = [
                index
                for index in ordered_indexes
                if str(aligned[index].get("retention_role") or "").strip().lower() in {"turn_or_payoff", "loop_close"}
            ]
            target_index = payoff_indexes[-1] if payoff_indexes else ordered_indexes[-1]
            payoff_scene = aligned[target_index]
            payoff_scene["visual_intent"] = payoff_intent.replace(" ", "_")
            if not str(payoff_scene.get("retention_role") or "").strip():
                payoff_scene["retention_role"] = "loop_close"
            aligned[target_index] = payoff_scene
        return aligned

    def fallback_query_variants(self, topic_text: str, base_queries: list[str]) -> list[str]:
        queries = [query for query in base_queries if query]
        normalized_topic = topic_text.lower()
        if "buraco" in normalized_topic and "negro" in normalized_topic:
            queries.extend(["black hole space", "black hole astronomy", "accretion disk space"])
        queries.extend([topic_text, f"{topic_text} ciencia", f"{topic_text} fotografia"])
        deduped: list[str] = []
        for query in queries:
            if query not in deduped:
                deduped.append(query)
        return deduped
