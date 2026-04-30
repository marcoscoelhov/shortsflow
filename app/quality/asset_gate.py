from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings


@dataclass(frozen=True)
class AssetGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class AssetGate:
    def validate_selected(self, selected_assets: list[dict[str, Any]]) -> AssetGateResult:
        settings = get_settings()
        semantic_threshold = settings.asset_semantic_threshold
        total_threshold = settings.asset_total_threshold
        reasons: list[str] = []
        scene_results = []
        for asset in selected_assets:
            scene_id = str(asset.get("scene_id") or "unknown")
            scene_reasons = []
            if float(asset.get("semantic_match", 0.0)) < semantic_threshold:
                scene_reasons.append("semantic_match_below_threshold")
            if float(asset.get("total_score", 0.0)) < total_threshold:
                scene_reasons.append("total_score_below_threshold")
            if float(asset.get("text_or_watermark_penalty", 0.0)) > 0.15:
                scene_reasons.append("text_or_watermark_penalty_high")
            if float(asset.get("artifact_penalty", 0.0)) > 0.30:
                scene_reasons.append("artifact_penalty_high")
            scene_results.append({"scene_id": scene_id, "passed": not scene_reasons, "reasons": scene_reasons})
            reasons.extend(f"{scene_id}:{reason}" for reason in scene_reasons)
        mean_semantic = sum(float(item.get("semantic_match", 0.0)) for item in selected_assets) / max(len(selected_assets), 1)
        return AssetGateResult(
            passed=not reasons,
            reasons=reasons,
            metrics={"asset_semantic_score_avg": round(mean_semantic, 3), "scene_count": len(selected_assets), "scenes": scene_results},
        )

