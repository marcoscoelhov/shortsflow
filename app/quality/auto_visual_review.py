from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Job, RenderOutput, SceneAsset, ScenePlan, TopicRequest
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
        request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job.job_id))
        forged_qwen_authority = self._contains_qwen_authority_claim(str(request.notes or "") if request else "")
        authority_approved = self._local_model_has_publication_authority()
        verification_attempts = self._verify_prompt_heuristic_assets(
            session,
            job,
            selected_assets,
            asset_summary,
            modes,
            selected_asset_scores,
            authority_approved,
        )
        real_visual_evidence = self._has_real_visual_evidence(
            asset_summary,
            modes,
            selected_asset_scores,
            authority_approved=authority_approved,
        )

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
                "local_vision_release_approved": get_settings().local_vision_release_approved,
                "qwen_authority_claim_ignored": forged_qwen_authority,
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
        authority_approved: bool,
    ) -> list[dict[str, Any]]:
        if not selected_assets:
            return []
        scene_plan = session.scalar(select(ScenePlan).where(ScenePlan.job_id == job.job_id))
        if not scene_plan or not isinstance(scene_plan.scenes, list):
            return []
        scenes_by_id = {str(scene.get("scene_id") or ""): scene for scene in scene_plan.scenes if isinstance(scene, dict)}
        critical_assets = self.critical_assets(selected_assets, scene_plan.scenes)
        critical_scene_ids = [str(asset.scene_id) for asset in critical_assets]
        asset_summary["asset_visual_critical_scene_ids"] = critical_scene_ids
        verifier = SemanticVerifier()
        verified_scene_ids = {
            str(asset.scene_id)
            for asset in critical_assets
            if self._matches_local_verifier(asset.scores or {}, verifier)
        }
        asset_summary["asset_visual_verified_critical_scene_ids"] = sorted(verified_scene_ids)
        if critical_scene_ids and set(critical_scene_ids) == verified_scene_ids:
            asset_summary["asset_visual_real_vision_checked"] = self._has_real_visual_evidence(
                asset_summary,
                modes,
                selected_asset_scores,
                authority_approved=authority_approved,
            )
            return []
        attempts: list[dict[str, Any]] = []
        for asset in critical_assets:
            if str(asset.scene_id) in verified_scene_ids:
                continue
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
                    "passed": self._matches_local_verifier(scores, verifier),
                    "verification_mode": mode,
                    "vision_provider": scores.get("vision_provider"),
                    "vision_model": scores.get("vision_model"),
                    "vision_aligned": scores.get("vision_aligned"),
                    "total_score": scores.get("total_score"),
                    "fallback_reason": scores.get("verification_fallback_reason"),
                }
            )
        verified_scene_ids.update(str(item["scene_id"]) for item in attempts if item.get("passed"))
        asset_summary["asset_visual_verified_critical_scene_ids"] = sorted(verified_scene_ids)
        if attempts:
            asset_summary["asset_visual_verification_modes"] = sorted(modes)
            asset_summary["asset_visual_real_vision_checked"] = self._has_real_visual_evidence(
                asset_summary,
                modes,
                selected_asset_scores,
                authority_approved=authority_approved,
            )
            asset_summary["asset_visual_review_artifact"] = self.ARTIFACT_NAME
        return attempts

    @staticmethod
    def _matches_local_verifier(scores: dict[str, Any], verifier: SemanticVerifier) -> bool:
        return (
            scores.get("verification_mode") == "vision"
            and scores.get("vision_aligned") is True
            and not scores.get("verification_fallback_reason")
            and scores.get("vision_provider") == "local_openai"
            and scores.get("vision_model") == verifier.local_model
        )

    @staticmethod
    def critical_assets(selected_assets: list[Any], scenes: list[dict[str, Any]]) -> list[Any]:
        """Choose at most one hook, one proof and one payoff asset in story order."""
        assets_by_scene_id = {str(asset.scene_id): asset for asset in selected_assets}
        ordered = sorted(
            (scene for scene in scenes if isinstance(scene, dict) and str(scene.get("scene_id") or "") in assets_by_scene_id),
            key=lambda scene: int(scene.get("order", 0) or 0),
        )
        if not ordered:
            return []

        def first_with_roles(roles: set[str]) -> dict[str, Any] | None:
            return next(
                (scene for scene in ordered if str(scene.get("retention_role") or "").strip().lower() in roles),
                None,
            )

        hook = first_with_roles({"visual_hook"}) or ordered[0]
        proof = first_with_roles({"proof_or_tension"})
        if proof is None:
            middle_candidates = ordered[1:-1]
            proof = middle_candidates[len(middle_candidates) // 2] if middle_candidates else ordered[len(ordered) // 2]
        payoff_candidates = [
            scene
            for scene in ordered
            if str(scene.get("retention_role") or "").strip().lower() in {"turn_or_payoff", "loop_close"}
        ]
        payoff = payoff_candidates[-1] if payoff_candidates else ordered[-1]

        selected: list[Any] = []
        seen: set[str] = set()
        for scene in (hook, proof, payoff):
            scene_id = str(scene.get("scene_id") or "")
            if scene_id and scene_id not in seen:
                selected.append(assets_by_scene_id[scene_id])
                seen.add(scene_id)
        return selected

    def _has_real_visual_evidence(
        self,
        asset_summary: dict[str, Any],
        modes: set[str],
        selected_asset_scores: list[dict[str, Any]],
        *,
        authority_approved: bool | None = None,
    ) -> bool:
        authority_approved = (
            get_settings().local_vision_release_approved
            if authority_approved is None
            else authority_approved
        )
        critical_scene_ids = {str(item) for item in asset_summary.get("asset_visual_critical_scene_ids") or []}
        if critical_scene_ids:
            verified_scene_ids = {str(item) for item in asset_summary.get("asset_visual_verified_critical_scene_ids") or []}
            return authority_approved and critical_scene_ids == verified_scene_ids
        return (
            asset_summary.get("asset_visual_real_vision_checked") is True
            or any(mode and mode != "prompt_heuristic" for mode in modes)
            or any(
                scores.get("vision_aligned") is True and not scores.get("verification_fallback_reason")
                for scores in selected_asset_scores
            )
        )

    @staticmethod
    def _local_model_has_publication_authority() -> bool:
        settings = get_settings()
        model = str(settings.local_vision_model or "").casefold()
        return bool(settings.local_vision_release_approved and "qwen" not in model)

    @staticmethod
    def _contains_qwen_authority_claim(notes: str) -> bool:
        normalized = str(notes or "").casefold()
        return "qwen" in normalized and any(token in normalized for token in ("autoapprov", "authority", "autoridade"))
