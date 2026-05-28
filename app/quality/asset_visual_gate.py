from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings


HOOK_MIN_SEMANTIC_SCORE = 0.80
HOOK_MIN_TOTAL_SCORE = 0.75
NEGATION_TOKENS = {"no", "not", "without", "sem", "nao", "nunca", "avoid", "evitar"}
PAYOFF_ROLES = {"turn_or_payoff", "loop_close"}


@dataclass(frozen=True)
class AssetVisualGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class AssetVisualGate:
    def validate(
        self,
        selected_assets: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        visual_contract: dict[str, Any] | None = None,
    ) -> AssetVisualGateResult:
        if not visual_contract:
            return AssetVisualGateResult(
                passed=True,
                metrics={"asset_visual_gate_pass": True, "checked": False, "reason": "missing_visual_contract"},
            )
        if not scenes:
            return AssetVisualGateResult(
                passed=False,
                reasons=["missing_scenes"],
                metrics={"asset_visual_gate_pass": False, "checked": True, "scenes": []},
            )

        settings = get_settings()
        hook_semantic_threshold = max(float(settings.asset_semantic_threshold), HOOK_MIN_SEMANTIC_SCORE)
        hook_total_threshold = max(float(settings.asset_total_threshold), HOOK_MIN_TOTAL_SCORE)
        assets_by_scene_id = {str(asset.get("scene_id") or ""): asset for asset in selected_assets}
        ordered_scenes = sorted(scenes, key=lambda scene: int(scene.get("order", 0) or 0))
        payoff_start_order = self._payoff_start_order(ordered_scenes)
        hook_scene = ordered_scenes[0]
        hook_scene_id = str(hook_scene.get("scene_id") or "scene-1")
        hook_asset = assets_by_scene_id.get(hook_scene_id, {})
        hook_frame = visual_contract.get("hook_frame") if isinstance(visual_contract.get("hook_frame"), dict) else {}
        loop_policy = visual_contract.get("loop_policy") if isinstance(visual_contract.get("loop_policy"), dict) else {}
        payoff_frame = visual_contract.get("payoff_frame") if isinstance(visual_contract.get("payoff_frame"), dict) else {}

        reasons: list[str] = []
        scene_reports: list[dict[str, Any]] = []
        hook_reasons = self._validate_hook_asset(
            hook_scene,
            hook_asset,
            hook_frame,
            semantic_threshold=hook_semantic_threshold,
            total_threshold=hook_total_threshold,
        )
        reasons.extend(f"{hook_scene_id}:{reason}" for reason in hook_reasons)

        forbidden_terms = _text_list(loop_policy.get("forbidden_early_reveal"))
        for scene in ordered_scenes:
            scene_id = str(scene.get("scene_id") or "unknown")
            asset = assets_by_scene_id.get(scene_id, {})
            scene_reasons: list[str] = []
            if scene_id == hook_scene_id:
                scene_reasons.extend(hook_reasons)
            if forbidden_terms and int(scene.get("order", 0) or 0) < payoff_start_order:
                early_corpus = _asset_scene_corpus(scene, asset)
                if any(_contains_unnegated_term(early_corpus, item) for item in forbidden_terms):
                    scene_reasons.append("forbidden_early_reveal_visible_in_asset_prompt")
                    reasons.append(f"{scene_id}:forbidden_early_reveal_visible_in_asset_prompt")
            scene_reports.append(
                {
                    "scene_id": scene_id,
                    "role": str(scene.get("retention_role") or ""),
                    "visual_intent": str(scene.get("visual_intent") or ""),
                    "provider": str(asset.get("provider") or ""),
                    "semantic_match": _float(asset.get("semantic_match")),
                    "total_score": _float(asset.get("total_score")),
                    "passed": not scene_reasons,
                    "reasons": scene_reasons,
                }
            )

        payoff_reasons = self._validate_payoff_scene(ordered_scenes, payoff_frame)
        reasons.extend(payoff_reasons)
        metrics = {
            "asset_visual_gate_pass": not reasons,
            "checked": True,
            "hook_scene_id": hook_scene_id,
            "hook_semantic_threshold": round(hook_semantic_threshold, 3),
            "hook_total_threshold": round(hook_total_threshold, 3),
            "hook_must_show_count": len(_text_list(hook_frame.get("must_show"))),
            "hook_negative_read_count": len(_text_list(hook_frame.get("negative_reads"))),
            "forbidden_early_reveal_count": len(forbidden_terms),
            "scenes": scene_reports,
        }
        return AssetVisualGateResult(passed=not reasons, reasons=reasons, metrics=metrics)

    def _validate_hook_asset(
        self,
        scene: dict[str, Any],
        asset: dict[str, Any],
        hook_frame: dict[str, Any],
        *,
        semantic_threshold: float,
        total_threshold: float,
    ) -> list[str]:
        reasons: list[str] = []
        if str(scene.get("retention_role") or "").strip().lower() != "visual_hook":
            reasons.append("hook_role_mismatch")
        expected_intent = _normalized_text(hook_frame.get("recommended_visual_intent"))
        actual_intent = _normalized_text(scene.get("visual_intent"))
        if expected_intent and actual_intent != expected_intent:
            reasons.append("hook_visual_intent_mismatch")
        if _float(asset.get("semantic_match")) < semantic_threshold:
            reasons.append("hook_semantic_match_below_visual_threshold")
        if _float(asset.get("total_score")) < total_threshold:
            reasons.append("hook_total_score_below_visual_threshold")
        corpus = _asset_scene_corpus(scene, asset)
        must_show = _text_list(hook_frame.get("must_show"))
        if must_show and not any(_contains_term(corpus, item) for item in must_show):
            reasons.append("hook_must_show_missing_from_asset_prompt")
        for item in _text_list(hook_frame.get("must_hide")):
            if _contains_unnegated_term(corpus, item):
                reasons.append("hook_reveals_hidden_element_in_asset_prompt")
                break
        for item in _text_list(hook_frame.get("negative_reads")):
            if _contains_unnegated_term(corpus, item):
                reasons.append("hook_negative_read_present_in_asset_prompt")
                break
        return reasons

    def _validate_payoff_scene(self, ordered_scenes: list[dict[str, Any]], payoff_frame: dict[str, Any]) -> list[str]:
        expected_intent = _normalized_text(payoff_frame.get("recommended_visual_intent"))
        if not expected_intent:
            return []
        payoff_scenes = [
            scene
            for scene in ordered_scenes
            if str(scene.get("retention_role") or "").strip().lower() in PAYOFF_ROLES
        ]
        if not payoff_scenes:
            return ["payoff_scene_missing"]
        if not any(_normalized_text(scene.get("visual_intent")) == expected_intent for scene in payoff_scenes):
            return ["payoff_visual_intent_mismatch"]
        return []

    def _payoff_start_order(self, ordered_scenes: list[dict[str, Any]]) -> int:
        for scene in ordered_scenes:
            if str(scene.get("retention_role") or "").strip().lower() in PAYOFF_ROLES:
                return int(scene.get("order", 0) or 0)
        return int(ordered_scenes[-1].get("order", 0) or 0) + 1


def _asset_scene_corpus(scene: dict[str, Any], asset: dict[str, Any]) -> str:
    return _normalized_text(
        " ".join(
            str(value or "")
            for value in [
                scene.get("narration_text"),
                scene.get("primary_subject"),
                scene.get("topic_hint"),
                scene.get("image_prompt"),
                scene.get("visual_intent"),
                asset.get("prompt_snapshot"),
                asset.get("provider"),
                asset.get("source_url"),
                asset.get("attribution"),
                asset.get("license_note"),
            ]
        )
    )


def _contains_term(corpus: str, term: str) -> bool:
    normalized = _normalized_text(term)
    if not normalized:
        return False
    if normalized in corpus:
        return True
    tokens = [token for token in normalized.split() if len(token) >= 4]
    return bool(tokens) and all(token in corpus.split() for token in tokens)


def _contains_unnegated_term(corpus: str, term: str) -> bool:
    normalized = _normalized_text(term)
    if not normalized:
        return False
    corpus_tokens = corpus.split()
    term_tokens = [token for token in normalized.split() if len(token) >= 3]
    if not term_tokens:
        return False
    for index, token in enumerate(corpus_tokens):
        if token not in term_tokens:
            continue
        before = corpus_tokens[max(0, index - 3) : index]
        if any(item in NEGATION_TOKENS for item in before):
            continue
        if len(term_tokens) == 1:
            return True
        token_window = corpus_tokens[index : index + max(len(term_tokens) + 4, 6)]
        if all(item in token_window for item in term_tokens):
            return True
    return False


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalized_text(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())
