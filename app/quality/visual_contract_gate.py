from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils import text_list as _text_list


GENERIC_VISUAL_TEXTS = {
    "imagem forte",
    "visual forte",
    "visual concreto",
    "hook forte",
    "cena impactante",
    "imagem impactante",
}


@dataclass(frozen=True)
class VisualContractGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class VisualContractGate:
    def validate(self, contract: dict[str, Any]) -> VisualContractGateResult:
        reasons: list[str] = []
        if not isinstance(contract, dict) or not contract:
            return VisualContractGateResult(
                passed=False,
                reasons=["missing_visual_contract"],
                metrics={"visual_contract_gate_pass": False},
            )

        hook_frame = contract.get("hook_frame") if isinstance(contract.get("hook_frame"), dict) else {}
        loop_policy = contract.get("loop_policy") if isinstance(contract.get("loop_policy"), dict) else {}
        payoff_frame = contract.get("payoff_frame") if isinstance(contract.get("payoff_frame"), dict) else {}
        beat_progression = contract.get("beat_progression") if isinstance(contract.get("beat_progression"), list) else []

        for key in ("visual_thesis", "visual_domain", "visual_world"):
            if not _has_text(contract.get(key)):
                reasons.append(f"missing_{key}")

        for key in ("promise", "positive_read", "readability_test"):
            if not _has_text(hook_frame.get(key)):
                reasons.append(f"hook_frame_missing_{key}")

        if not _text_list(hook_frame.get("must_show")):
            reasons.append("hook_frame_missing_must_show")
        if not _text_list(hook_frame.get("negative_reads")):
            reasons.append("hook_frame_missing_negative_reads")
        if _is_generic(hook_frame.get("promise")) or _is_generic(hook_frame.get("positive_read")):
            reasons.append("hook_frame_too_generic")

        if not _has_text(loop_policy.get("open_question")):
            reasons.append("loop_policy_missing_open_question")
        if not isinstance(loop_policy.get("forbidden_early_reveal"), list):
            reasons.append("loop_policy_missing_forbidden_early_reveal")

        if not beat_progression:
            reasons.append("missing_beat_progression")
        for index, beat in enumerate(beat_progression):
            if not isinstance(beat, dict):
                reasons.append(f"beat_{index + 1}_invalid")
                continue
            if not _has_text(beat.get("role")):
                reasons.append(f"beat_{index + 1}_missing_role")
            if not _has_text(beat.get("visual_job")):
                reasons.append(f"beat_{index + 1}_missing_visual_job")

        if not _has_text(payoff_frame.get("reveal")):
            reasons.append("payoff_frame_missing_reveal")
        if not _has_text(payoff_frame.get("must_connect_to_hook")):
            reasons.append("payoff_frame_missing_must_connect_to_hook")

        metrics = {
            "visual_contract_gate_pass": not reasons,
            "has_hook_must_show": bool(_text_list(hook_frame.get("must_show"))),
            "has_hook_negative_reads": bool(_text_list(hook_frame.get("negative_reads"))),
            "beat_count": len(beat_progression),
            "has_forbidden_early_reveal": bool(_text_list(loop_policy.get("forbidden_early_reveal"))),
        }
        return VisualContractGateResult(passed=not reasons, reasons=reasons, metrics=metrics)


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_generic(value: Any) -> bool:
    text = " ".join(str(value or "").lower().split())
    return text in GENERIC_VISUAL_TEXTS
