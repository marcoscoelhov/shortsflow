from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GrowthScoreGateResult:
    passed: bool
    decision: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class GrowthScoreGate:
    MIN_GROWTH_SCORE = 0.78
    MIN_AXIS_SCORE = 0.68

    def evaluate(self, quality_summary: dict[str, Any], monetization_report: dict[str, Any]) -> GrowthScoreGateResult:
        script_summary = _dict(quality_summary.get("script"))
        viral = _dict(script_summary.get("viral_intensity"))
        assets = _dict(quality_summary.get("assets"))
        visual = _dict(assets.get("visual_impact"))
        metadata = _dict(quality_summary.get("metadata_ctr"))
        tts = _dict(quality_summary.get("tts"))
        render = _dict(quality_summary.get("render"))
        monetization_hard = [str(item) for item in monetization_report.get("hard_blockers") or []]
        manual_required = [str(item) for item in monetization_report.get("manual_required") or []]
        scores = {
            "script_viral_intensity_score": _float(viral.get("viral_intensity_score"), 0.82 if not viral else 0.0),
            "visual_impact_score": _float(visual.get("visual_impact_score"), 0.82 if not visual else 0.0),
            "metadata_ctr_score": _float(metadata.get("metadata_ctr_score"), 0.82 if not metadata else 0.0),
            "voice_performance_score": _float(tts.get("voice_performance_score"), 0.74 if tts else 0.82),
            "render_reliability_score": 1.0 if render.get("render_gate_pass") is True else 0.0,
            "monetization_clearance_score": 0.0 if monetization_hard else (0.82 if manual_required else 1.0),
        }
        growth_score = (
            scores["script_viral_intensity_score"] * 0.25
            + scores["visual_impact_score"] * 0.24
            + scores["metadata_ctr_score"] * 0.20
            + scores["voice_performance_score"] * 0.12
            + scores["render_reliability_score"] * 0.09
            + scores["monetization_clearance_score"] * 0.10
        )
        reasons: list[str] = []
        ready_script_viral_warning = bool(viral.get("viral_intensity_ready_script_warning")) and scores["script_viral_intensity_score"] >= 0.74
        if viral and not ready_script_viral_warning and (viral.get("viral_intensity_gate_pass") is False or scores["script_viral_intensity_score"] < self.MIN_AXIS_SCORE):
            reasons.append("script_viral_intensity_low")
        if visual and (visual.get("visual_impact_gate_pass") is False or scores["visual_impact_score"] < self.MIN_AXIS_SCORE):
            reasons.append("visual_impact_low")
        if metadata and (metadata.get("metadata_ctr_gate_pass") is False or scores["metadata_ctr_score"] < self.MIN_AXIS_SCORE):
            reasons.append("metadata_ctr_low")
        if any(reason in reasons for reason in ["script_viral_intensity_low", "visual_impact_low", "metadata_ctr_low"]):
            growth_score = min(growth_score, 0.77)
        if scores["voice_performance_score"] < 0.62:
            reasons.append("voice_performance_low")
        if not render.get("render_gate_pass"):
            reasons.append("render_gate_not_passed")
        if monetization_hard:
            reasons.append("monetization_hard_blockers")
        if growth_score < self.MIN_GROWTH_SCORE:
            reasons.append("growth_score_below_threshold")
        reasons = list(dict.fromkeys(reasons))
        passed = not reasons
        if passed:
            decision = "ready_for_growth_review"
        elif any(reason in reasons for reason in ["visual_impact_low", "metadata_ctr_low", "script_viral_intensity_low", "voice_performance_low"]):
            decision = "repair_required"
        else:
            decision = "manual_review_required"
        metrics = {**scores, "growth_score": round(growth_score, 3), "growth_score_gate_pass": passed}
        if ready_script_viral_warning:
            metrics["script_viral_intensity_warning_only"] = True
        return GrowthScoreGateResult(passed, decision, reasons, metrics)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
