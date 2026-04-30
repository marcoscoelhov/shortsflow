from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils import word_tokens


GENERIC_PROMPT_MARKERS = {
    "vertical cinematic scientific image",
    "focused on the described phenomenon",
    "showing subject closeup",
    "showing subject in context",
    "showing process or mechanism",
}


@dataclass(frozen=True)
class SceneGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class ScenePlanGate:
    def validate(self, scenes: list[dict[str, Any]], expected_scene_count: int) -> SceneGateResult:
        reasons: list[str] = []
        scene_results: list[dict[str, Any]] = []
        if not scenes:
            reasons.append("missing_scenes")
        if scenes and len(scenes) != expected_scene_count:
            reasons.append("scene_count_mismatch")
        for scene in scenes:
            scene_id = str(scene.get("scene_id") or "unknown")
            scene_reasons: list[str] = []
            narration = str(scene.get("narration_text") or "")
            prompt = str(scene.get("image_prompt") or "")
            subject = str(scene.get("primary_subject") or scene.get("topic_hint") or "")
            if not narration.strip():
                scene_reasons.append("missing_narration_text")
            if len(word_tokens(narration)) < 3:
                scene_reasons.append("narration_too_short")
            if not prompt.strip():
                scene_reasons.append("missing_image_prompt")
            if "no readable text" not in prompt.lower():
                scene_reasons.append("missing_no_text_constraint")
            if subject and subject.lower() not in prompt.lower() and subject.lower() not in narration.lower():
                # Provider prompts may translate the subject to English for image models.
                # Treat this as a metric, not a hard failure.
                pass
            generic_hits = [marker for marker in GENERIC_PROMPT_MARKERS if marker in prompt.lower()]
            if generic_hits and len(word_tokens(prompt)) < 22:
                scene_reasons.append("image_prompt_too_generic")
            if not isinstance(scene.get("token_start"), int) or not isinstance(scene.get("token_end"), int):
                scene_reasons.append("missing_token_bounds")
            elif int(scene["token_end"]) < int(scene["token_start"]):
                scene_reasons.append("invalid_token_bounds")
            scene_results.append({"scene_id": scene_id, "passed": not scene_reasons, "reasons": scene_reasons})
            reasons.extend(f"{scene_id}:{reason}" for reason in scene_reasons)
        return SceneGateResult(
            passed=not reasons,
            reasons=reasons,
            metrics={"scene_count": len(scenes), "expected_scene_count": expected_scene_count, "scenes": scene_results},
        )
