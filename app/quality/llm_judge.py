from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

EDITORIAL_SOFT_REASONS = {
    "weak_loop_closure",
    "ending_not_connected_to_hook",
    "generic_hook_opening",
    "generic_loop_ending",
    "hook_first_word_weak",
    "hook_not_scroll_stopping",
    "viral_intensity_below_threshold",
    "curiosity_gap_low",
    "escalation_low",
    "payoff_surprise_low",
    "share_trigger_low",
    "didactic_tone_detected",
    "weak_ending",
    "weak_factual_precision_excess",
    "potentially_misleading_generalization",
    "low_retention",
    "title_click_tension_low",
    "metadata_ctr_below_threshold",
    "opening_frame_not_scroll_stopping",
    "generic_stock_visual_penalty",
    "visual_impact_below_threshold",
    "semantic_match_below_threshold",
    "asset_visual_gate_failed",
}

HARD_REASON_PREFIXES = (
    "missing_",
    "factual_",
    "foreign_",
    "non_latin_",
    "markup_",
    "placeholder_",
    "invented_",
    "unsupported_",
    "overconfident_",
)


@dataclass(frozen=True)
class LlmJudgeResult:
    passed: bool
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)
    provider: str = "none"
    gate_kind: str = ""
    skipped: bool = False
    notes: str = ""


class LlmQualityJudge:
    MIN_OVERRIDE_CONFIDENCE = 0.72

    def __init__(
        self,
        *,
        enabled: bool,
        timeout_sec: float,
        gray_zone_low: float,
        gray_zone_high: float,
        judge_callable: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
    ) -> None:
        self.enabled = enabled
        self.timeout_sec = timeout_sec
        self.gray_zone_low = gray_zone_low
        self.gray_zone_high = gray_zone_high
        self._judge_callable = judge_callable

    def may_consider_override(self, local_reasons: list[str]) -> bool:
        return self.enabled and self._judge_callable is not None and self.can_override_local_failure(local_reasons)

    def can_override_local_failure(self, local_reasons: list[str]) -> bool:
        if not local_reasons:
            return False
        normalized = [str(reason) for reason in local_reasons]
        if any(reason.startswith(HARD_REASON_PREFIXES) for reason in normalized):
            return False
        if any(":" in reason for reason in normalized):
            base_reasons = {reason.split(":", 1)[0] for reason in normalized}
        else:
            base_reasons = set(normalized)
        return base_reasons.issubset(EDITORIAL_SOFT_REASONS) or any(
            reason in EDITORIAL_SOFT_REASONS for reason in normalized
        )

    def should_override(self, *, local_passed: bool, local_reasons: list[str], judge: LlmJudgeResult) -> bool:
        if local_passed or judge.skipped or not judge.passed:
            return False
        if judge.confidence < self.MIN_OVERRIDE_CONFIDENCE:
            return False
        return self.can_override_local_failure(local_reasons)

    def in_growth_gray_zone(self, growth_score: float) -> bool:
        return self.gray_zone_low <= growth_score < self.gray_zone_high

    def judge_editorial(self, payload: dict[str, Any]) -> LlmJudgeResult:
        return self._invoke("editorial", payload)

    def judge_metadata_ctr(self, payload: dict[str, Any]) -> LlmJudgeResult:
        return self._invoke("metadata_ctr", payload)

    def judge_visual_assets(self, payload: dict[str, Any]) -> LlmJudgeResult:
        return self._invoke("visual_assets", payload)

    def judge_growth_score(self, payload: dict[str, Any]) -> LlmJudgeResult:
        return self._invoke("growth_score", payload)

    def _invoke(self, gate_kind: str, payload: dict[str, Any]) -> LlmJudgeResult:
        if not self.enabled or self._judge_callable is None:
            return LlmJudgeResult(False, skipped=True, gate_kind=gate_kind)
        try:
            raw = self._judge_callable(gate_kind, payload)
        except Exception as exc:  # noqa: BLE001
            return LlmJudgeResult(
                False,
                reasons=[f"llm_judge_error:{type(exc).__name__}"],
                gate_kind=gate_kind,
                notes=str(exc),
            )
        return _normalize_judge_result(gate_kind, raw)

    def merge_editorial_metrics(self, metrics: dict[str, Any], judge: LlmJudgeResult, *, local_reasons: list[str]) -> dict[str, Any]:
        merged = dict(metrics)
        merged["llm_judge_gate_kind"] = judge.gate_kind
        merged["llm_judge_passed"] = judge.passed
        merged["llm_judge_confidence"] = judge.confidence
        merged["llm_judge_reasons"] = judge.reasons
        merged["llm_judge_scores"] = judge.scores
        merged["llm_judge_provider"] = judge.provider
        if self.should_override(local_passed=False, local_reasons=local_reasons, judge=judge):
            merged["llm_judge_override"] = True
            merged["llm_judge_overridden_reasons"] = list(local_reasons)
            if judge.gate_kind == "editorial":
                merged["viral_intensity_gate_pass"] = True
                merged["viral_intensity_hard_block"] = False
                merged["script_quality_gate_pass"] = True
        return merged


def _normalize_judge_result(gate_kind: str, raw: Any) -> LlmJudgeResult:
    if not isinstance(raw, dict):
        return LlmJudgeResult(False, reasons=["llm_judge_invalid_response"], gate_kind=gate_kind)
    reasons = [str(item) for item in raw.get("reasons") or [] if str(item).strip()]
    scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    confidence = _float(raw.get("confidence"), 0.0)
    passed = bool(raw.get("passed")) and confidence >= 0.55
    return LlmJudgeResult(
        passed=passed,
        confidence=confidence,
        reasons=reasons,
        scores=scores,
        provider=str(raw.get("provider") or "llm_judge"),
        gate_kind=gate_kind,
        notes=str(raw.get("notes") or ""),
    )


def build_editorial_judge_payload(
    *,
    script: dict[str, Any],
    local_reasons: list[str],
    local_metrics: dict[str, Any] | None = None,
    gate_name: str,
    structured_viral_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "local_reasons": local_reasons,
        "local_metrics": local_metrics or {},
        "structured_viral_contract": structured_viral_contract or {},
        "script": {
            "title": script.get("title"),
            "hook": script.get("hook"),
            "loop": script.get("loop"),
            "body_beats": script.get("body_beats"),
            "payoff": script.get("payoff"),
            "ending": script.get("ending"),
            "full_narration": script.get("full_narration"),
            "qa_metrics": script.get("qa_metrics"),
        },
    }


def build_metadata_judge_payload(
    *,
    topic_plan: dict[str, Any] | Any,
    script: dict[str, Any] | Any,
    hashtags: list[str],
    local_reasons: list[str],
    local_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "topic_plan": _as_dict(topic_plan),
        "script": _as_dict(script),
        "hashtags": hashtags,
        "local_reasons": local_reasons,
        "local_metrics": local_metrics,
    }


def build_visual_judge_payload(
    *,
    scenes: list[dict[str, Any]],
    selected_assets: list[dict[str, Any]],
    visual_contract: dict[str, Any] | None,
    local_reasons: list[str],
    local_metrics: dict[str, Any],
) -> dict[str, Any]:
    assets_by_scene = {str(asset.get("scene_id") or ""): asset for asset in selected_assets}
    scene_rows = []
    for scene in scenes:
        scene_id = str(scene.get("scene_id") or "")
        asset = assets_by_scene.get(scene_id, {})
        scene_rows.append(
            {
                "scene_id": scene_id,
                "order": scene.get("order"),
                "retention_role": scene.get("retention_role"),
                "visual_intent": scene.get("visual_intent"),
                "primary_subject": scene.get("primary_subject"),
                "narration_text": scene.get("narration_text"),
                "image_prompt": scene.get("image_prompt"),
                "semantic_match": asset.get("semantic_match"),
                "total_score": asset.get("total_score"),
                "provider": asset.get("provider"),
                "prompt_snapshot": asset.get("prompt_snapshot"),
            }
        )
    return {
        "scenes": scene_rows,
        "visual_contract_summary": {
            "visual_thesis": (visual_contract or {}).get("visual_thesis"),
            "visual_domain": (visual_contract or {}).get("visual_domain"),
            "hook_must_show": ((visual_contract or {}).get("hook_frame") or {}).get("must_show"),
        },
        "local_reasons": local_reasons,
        "local_metrics": local_metrics,
    }


def build_growth_judge_payload(
    *,
    quality_summary: dict[str, Any],
    local_reasons: list[str],
    local_metrics: dict[str, Any],
    monetization_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "quality_summary": quality_summary,
        "local_reasons": local_reasons,
        "local_metrics": local_metrics,
        "monetization_context": monetization_context,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {
        "title": getattr(value, "title", None),
        "hook": getattr(value, "hook", None),
        "ending": getattr(value, "ending", None),
        "full_narration": getattr(value, "full_narration", None),
        "canonical_topic": getattr(value, "canonical_topic", None),
        "angle": getattr(value, "angle", None),
    }


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default