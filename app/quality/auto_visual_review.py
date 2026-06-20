from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, RenderOutput, SceneAsset, ScenePlan
from app.providers.image import SemanticVerifier
from app.storage import StorageManager
from app.utils import utcnow


class AutoVisualReviewService:
    ARTIFACT_NAME = "auto_visual_review.json"

    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage

    def review(self, session: Session, job: Job) -> dict[str, Any]:
        quality_summary = dict(job.quality_summary or {})
        asset_summary = dict(quality_summary.get("assets") or {})
        selected_assets = session.scalars(
            select(SceneAsset).where(SceneAsset.job_id == job.job_id, SceneAsset.selected.is_(True))
        ).all()
        selected_asset_count = len(selected_assets)
        render_exists = session.scalar(select(RenderOutput.render_id).where(RenderOutput.job_id == job.job_id)) is not None
        modes = {str(item) for item in asset_summary.get("asset_visual_verification_modes") or []}
        selected_asset_scores = [dict(asset.scores or {}) for asset in selected_assets]
        verification_attempts = self._verify_prompt_heuristic_assets(
            session,
            job,
            selected_assets,
            asset_summary,
            modes,
            selected_asset_scores,
        )
        real_visual_evidence = self._has_real_visual_evidence(asset_summary, modes, selected_asset_scores)

        reasons: list[str] = []
        if asset_summary.get("asset_visual_gate_pass") is not True:
            reasons.append("asset_visual_gate_not_passed")
        if asset_summary.get("asset_visual_gate_checked") is not True:
            reasons.append("asset_visual_gate_not_checked")
        if asset_summary.get("semantic_threshold_pass") is not True:
            reasons.append("asset_semantic_threshold_not_passed")
        if selected_asset_count < 1:
            reasons.append("selected_assets_missing")
        if not render_exists:
            reasons.append("render_artifact_missing")
        if not real_visual_evidence:
            reasons.append("real_visual_evidence_missing")

        result = {
            "passed": not reasons,
            "reviewer": "automation_visual_review",
            "reasons": reasons,
            "checked_at": utcnow().isoformat(),
            "signals": {
                "asset_visual_gate_pass": asset_summary.get("asset_visual_gate_pass") is True,
                "asset_visual_gate_checked": asset_summary.get("asset_visual_gate_checked") is True,
                "semantic_threshold_pass": asset_summary.get("semantic_threshold_pass") is True,
                "selected_asset_count": selected_asset_count,
                "render_exists": render_exists,
                "verification_modes": sorted(modes),
                "real_visual_evidence": real_visual_evidence,
                "verification_attempts": verification_attempts,
            },
        }
        self.storage.persist_json(job.job_id, self.ARTIFACT_NAME, result)

        artifact_index = dict(job.artifact_index or {})
        artifact_index["auto_visual_review"] = self.ARTIFACT_NAME
        job.artifact_index = artifact_index
        if result["passed"]:
            modes = [str(item) for item in asset_summary.get("asset_visual_verification_modes") or []]
            if "automation_visual_review" not in modes:
                modes.append("automation_visual_review")
            asset_summary.update(
                {
                    "asset_visual_real_vision_checked": True,
                    "asset_visual_verification_modes": modes,
                    "asset_visual_review_artifact": self.ARTIFACT_NAME,
                }
            )
            quality_summary["assets"] = asset_summary
            job.quality_summary = quality_summary
        return result

    def _verify_prompt_heuristic_assets(
        self,
        session: Session,
        job: Job,
        selected_assets: list[SceneAsset],
        asset_summary: dict[str, Any],
        modes: set[str],
        selected_asset_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self._has_real_visual_evidence(asset_summary, modes, selected_asset_scores):
            return []
        if not selected_assets:
            return []
        scene_plan = session.scalar(select(ScenePlan).where(ScenePlan.job_id == job.job_id))
        if not scene_plan or not isinstance(scene_plan.scenes, list):
            return []
        scenes_by_id = {str(scene.get("scene_id") or ""): scene for scene in scene_plan.scenes if isinstance(scene, dict)}
        verifier = SemanticVerifier()
        attempts: list[dict[str, Any]] = []
        for asset in selected_assets:
            scene = scenes_by_id.get(str(asset.scene_id))
            if not scene:
                attempts.append({"scene_id": asset.scene_id, "passed": False, "reason": "scene_missing"})
                continue
            try:
                scores = verifier.score(
                    scene,
                    {
                        "provider": asset.provider,
                        "uri": asset.uri,
                        "prompt_snapshot": asset.prompt_snapshot or "",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                attempts.append({"scene_id": asset.scene_id, "passed": False, "reason": str(exc)})
                continue
            asset.scores = scores
            selected_asset_scores.append(dict(scores))
            mode = str(scores.get("verification_mode") or "")
            if mode:
                modes.add(mode)
            attempts.append(
                {
                    "scene_id": asset.scene_id,
                    "passed": mode == "vision" and scores.get("vision_aligned") is True,
                    "verification_mode": mode,
                    "vision_provider": scores.get("vision_provider"),
                    "vision_model": scores.get("vision_model"),
                    "vision_aligned": scores.get("vision_aligned"),
                    "total_score": scores.get("total_score"),
                    "fallback_reason": scores.get("verification_fallback_reason"),
                }
            )
        if attempts and any(item.get("passed") for item in attempts):
            asset_summary["asset_visual_verification_modes"] = sorted(modes)
            asset_summary["asset_visual_real_vision_checked"] = self._has_real_visual_evidence(asset_summary, modes, selected_asset_scores)
            asset_summary["asset_visual_review_artifact"] = self.ARTIFACT_NAME
        return attempts

    def _has_real_visual_evidence(
        self,
        asset_summary: dict[str, Any],
        modes: set[str],
        selected_asset_scores: list[dict[str, Any]],
    ) -> bool:
        return (
            asset_summary.get("asset_visual_real_vision_checked") is True
            or any(mode and mode != "prompt_heuristic" for mode in modes)
            or any(
                scores.get("vision_aligned") is True and not scores.get("verification_fallback_reason")
                for scores in selected_asset_scores
            )
        )
