from __future__ import annotations

from pathlib import Path
from typing import Any

from app.quality.render_gate import RenderGate, RenderGateResult


ALLOWED_COMPONENT_POLICY = "free_only"
ALLOWED_TRANSITIONS = {"cold_open", "evidence_cut", "payoff_reveal", "soft_cut"}
ALLOWED_MOTIONS = {"stable_hold", "subtle_push", "slow_drift", "payoff_pulse"}
ALLOWED_OVERLAYS = {"hook_tag", "payoff_tag", "evidence_marker"}
MAX_SCALE_DELTA = 0.18
MAX_TRANSLATION_DELTA = 60


class PremiumFinishingGate:
    def __init__(self, render_gate: RenderGate | None = None) -> None:
        self.render_gate = render_gate or RenderGate()

    def validate(self, video_path: Path, expected_duration_ms: int, edit_plan: dict[str, Any]) -> RenderGateResult:
        base = self.render_gate.validate(video_path, expected_duration_ms)
        reasons = list(base.reasons)
        metrics = dict(base.metrics)
        plan_report = self._validate_plan(edit_plan)
        reasons.extend(plan_report["reasons"])
        metrics["premium_finishing_gate"] = {
            "plan_checked": True,
            "scene_count": plan_report["scene_count"],
            "caption_count": plan_report["caption_count"],
            "component_policy": plan_report["component_policy"],
        }
        return RenderGateResult(passed=not reasons, reasons=reasons, metrics=metrics)

    def _validate_plan(self, edit_plan: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        scenes = edit_plan.get("scenes") if isinstance(edit_plan.get("scenes"), list) else []
        caption_track = edit_plan.get("caption_track") if isinstance(edit_plan.get("caption_track"), dict) else {}
        captions = caption_track.get("items") if isinstance(caption_track.get("items"), list) else []
        style = edit_plan.get("style") if isinstance(edit_plan.get("style"), dict) else {}
        component_policy = str(style.get("component_policy") or "")
        if component_policy != ALLOWED_COMPONENT_POLICY:
            reasons.append("paid_or_unknown_component_policy")
        if not scenes:
            reasons.append("missing_premium_scenes")
        if not captions:
            reasons.append("missing_premium_captions")
        if caption_track.get("max_lines") != 1:
            reasons.append("premium_captions_not_one_line")
        for scene in scenes:
            scene_id = str(scene.get("scene_id") or "scene")
            transition = scene.get("transition") if isinstance(scene.get("transition"), dict) else {}
            motion = scene.get("motion") if isinstance(scene.get("motion"), dict) else {}
            if transition.get("kind") not in ALLOWED_TRANSITIONS:
                reasons.append(f"{scene_id}:unsupported_transition")
            if motion.get("kind") not in ALLOWED_MOTIONS:
                reasons.append(f"{scene_id}:unsupported_motion")
            start_scale = _float_value(motion.get("start_scale"), 1.0)
            end_scale = _float_value(motion.get("end_scale"), start_scale)
            x_delta = abs(_float_value(motion.get("x_delta"), 0.0))
            y_delta = abs(_float_value(motion.get("y_delta"), 0.0))
            if abs(end_scale - start_scale) > MAX_SCALE_DELTA or x_delta > MAX_TRANSLATION_DELTA or y_delta > MAX_TRANSLATION_DELTA:
                reasons.append(f"{scene_id}:excessive_motion")
            for overlay in scene.get("overlays") or []:
                if not isinstance(overlay, dict) or overlay.get("kind") not in ALLOWED_OVERLAYS:
                    reasons.append(f"{scene_id}:unsupported_overlay")
        for caption in captions:
            text = str(caption.get("text") or "")
            if "\n" in text:
                reasons.append("premium_caption_has_line_break")
            if len(text) > 74:
                reasons.append("premium_caption_too_long")
        return {
            "reasons": reasons,
            "scene_count": len(scenes),
            "caption_count": len(captions),
            "component_policy": component_policy,
        }


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
