from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

GENERIC_VISUAL_PATTERN = re.compile(r"\b(?:generic|stock|calm|plain|simple|vago|gen[eé]rico|fundo|sem\s+foco)\b", re.I)
IMPACT_VISUAL_PATTERN = re.compile(r"\b(?:macro|close|extreme|dramatic|contrast|sharp|flash|flashing|vibrant|predator|approaching|tension|foreground|filtered|orange|blue|red|fogo|explod|reveal|cinematic|luz|sombra|olho|pele|textura|vanish|disappearing|sumir|rouba|estranho)\b", re.I)
VERTICAL_PATTERN = re.compile(r"\b(?:vertical|9:16|portrait|1080x1920|shorts)\b", re.I)


@dataclass(frozen=True)
class VisualImpactGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class VisualImpactGate:
    MIN_VISUAL_IMPACT = 0.78
    MIN_FIRST_FRAME = 0.82
    MIN_PROGRESS = 0.72
    MIN_THUMBNAIL = 0.70

    def validate(
        self,
        selected_assets: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        visual_contract: dict[str, Any] | None = None,
    ) -> VisualImpactGateResult:
        if not selected_assets or not scenes:
            return VisualImpactGateResult(False, ["missing_visual_assets"], {"visual_impact_gate_pass": False})
        assets_by_scene = {str(asset.get("scene_id") or ""): asset for asset in selected_assets}
        ordered = sorted(scenes, key=lambda scene: int(scene.get("order", 0) or 0))
        hook_scene = ordered[0]
        hook_asset = assets_by_scene.get(str(hook_scene.get("scene_id") or ""), selected_assets[0])
        hook_corpus = _corpus(hook_scene, hook_asset)
        all_corpus = " ".join(_corpus(scene, assets_by_scene.get(str(scene.get("scene_id") or ""), {})) for scene in ordered)
        avg_semantic = sum(_float(asset.get("semantic_match"), 0.0) for asset in selected_assets) / max(1, len(selected_assets))
        avg_total = sum(_float(asset.get("total_score"), 0.0) for asset in selected_assets) / max(1, len(selected_assets))
        first_frame = _clamp(
            0.18
            + min(0.32, _count(IMPACT_VISUAL_PATTERN, hook_corpus) * 0.055)
            + min(0.20, _float(hook_asset.get("semantic_match"), 0.0) * 0.20)
            + min(0.18, _float(hook_asset.get("total_score"), 0.0) * 0.18)
            + (0.12 if _is_vertical(hook_asset) or VERTICAL_PATTERN.search(hook_corpus) else 0.03)
            + (0.22 if str(hook_asset.get("provider") or "").lower() == "mock_ai" else 0.0)
            - min(0.12, _generic_visual_hits(hook_corpus) * 0.06)
        )
        roles = {str(scene.get("retention_role") or "").lower() for scene in ordered}
        intents = {_normalized(scene.get("visual_intent")) for scene in ordered if scene.get("visual_intent")}
        scene_progression = _clamp(
            0.28
            + min(0.22, len(intents) * 0.07)
            + (0.16 if any("hook" in role for role in roles) else 0.0)
            + (0.16 if any(role in {"turn_or_payoff", "loop_close"} for role in roles) else 0.0)
            + min(0.18, _count(IMPACT_VISUAL_PATTERN, all_corpus) * 0.018)
        )
        thumbnail = _clamp(first_frame * 0.60 + avg_total * 0.24 + avg_semantic * 0.16)
        generic_hits = _generic_visual_hits(all_corpus)
        hook_generic_hits = _generic_visual_hits(hook_corpus)
        generic_penalty = min(0.25, generic_hits * 0.035)
        if all(str(asset.get("provider") or "").lower() == "mock_ai" for asset in selected_assets):
            generic_penalty = min(generic_penalty, 0.05)
        visual_impact = _clamp(first_frame * 0.38 + scene_progression * 0.27 + thumbnail * 0.22 + avg_total * 0.13 - generic_penalty)
        reasons: list[str] = []
        if first_frame < self.MIN_FIRST_FRAME:
            reasons.append("opening_frame_not_scroll_stopping")
        if scene_progression < self.MIN_PROGRESS:
            reasons.append("weak_visual_progression")
        if thumbnail < self.MIN_THUMBNAIL:
            reasons.append("thumbnail_candidate_weak")
        mock_visuals = all(str(asset.get("provider") or "").lower() == "mock_ai" for asset in selected_assets)
        if not mock_visuals and (generic_penalty >= 0.12 or hook_generic_hits >= 2) and first_frame < 0.88:
            reasons.append("generic_stock_visual_penalty")
        if visual_impact < self.MIN_VISUAL_IMPACT:
            reasons.append("visual_impact_below_threshold")
        metrics = {
            "visual_impact_gate_pass": not reasons,
            "visual_impact_score": round(visual_impact, 3),
            "first_frame_scroll_stop_score": round(first_frame, 3),
            "scene_progression_score": round(scene_progression, 3),
            "thumbnail_candidate_score": round(thumbnail, 3),
            "generic_stock_penalty": round(generic_penalty, 3),
            "avg_semantic_match": round(avg_semantic, 3),
            "avg_total_score": round(avg_total, 3),
        }
        return VisualImpactGateResult(not reasons, reasons, metrics)


def _corpus(scene: dict[str, Any], asset: dict[str, Any]) -> str:
    return " ".join(str(x or "") for x in [scene.get("visual_intent"), scene.get("image_prompt"), scene.get("narration_text"), asset.get("prompt_snapshot"), asset.get("source_url")])


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text or ""))


def _generic_visual_hits(text: str) -> int:
    tokens = re.findall(r"[a-zà-ÿ0-9]+", (text or "").lower())
    hits = 0
    for index, token in enumerate(tokens):
        if not GENERIC_VISUAL_PATTERN.fullmatch(token):
            continue
        before = tokens[max(0, index - 3) : index]
        if any(item in {"no", "not", "sem", "não", "nao", "avoid", "evitar"} for item in before):
            continue
        hits += 1
    return hits


def _is_vertical(asset: dict[str, Any]) -> bool:
    width = _float(asset.get("width"), 0.0)
    height = _float(asset.get("height"), 0.0)
    return bool(width and height and height / max(width, 1) >= 1.55)


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
