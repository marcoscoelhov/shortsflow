from __future__ import annotations

from types import SimpleNamespace

from app.config import get_settings
from app.quality.auto_visual_review import AutoVisualReviewService


def test_critical_visual_review_selects_hook_proof_and_payoff_only() -> None:
    scenes = [
        {"scene_id": "scene-1", "order": 1, "retention_role": "visual_hook"},
        {"scene_id": "scene-2", "order": 2, "retention_role": "escalation"},
        {"scene_id": "scene-3", "order": 3, "retention_role": "proof_or_tension"},
        {"scene_id": "scene-4", "order": 4, "retention_role": "escalation"},
        {"scene_id": "scene-5", "order": 5, "retention_role": "loop_close"},
    ]
    assets = [SimpleNamespace(scene_id=f"scene-{index}") for index in range(1, 6)]

    selected = AutoVisualReviewService.critical_assets(assets, scenes)

    assert [asset.scene_id for asset in selected] == ["scene-1", "scene-3", "scene-5"]


def test_critical_visual_review_falls_back_to_middle_scene() -> None:
    scenes = [
        {"scene_id": "scene-1", "order": 1, "retention_role": "visual_hook"},
        {"scene_id": "scene-2", "order": 2, "retention_role": "escalation"},
        {"scene_id": "scene-3", "order": 3, "retention_role": "loop_close"},
    ]
    assets = [SimpleNamespace(scene_id=f"scene-{index}") for index in range(1, 4)]

    selected = AutoVisualReviewService.critical_assets(assets, scenes)

    assert [asset.scene_id for asset in selected] == ["scene-1", "scene-2", "scene-3"]


def test_real_visual_evidence_requires_every_critical_scene(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_LOCAL_VISION_RELEASE_APPROVED", "true")
    get_settings.cache_clear()
    service = object.__new__(AutoVisualReviewService)
    summary = {
        "asset_visual_critical_scene_ids": ["scene-1", "scene-3", "scene-5"],
        "asset_visual_verified_critical_scene_ids": ["scene-1", "scene-5"],
    }

    assert service._has_real_visual_evidence(summary, {"vision"}, [{"vision_aligned": True}]) is False

    summary["asset_visual_verified_critical_scene_ids"].append("scene-3")

    assert service._has_real_visual_evidence(summary, {"vision"}, [{"vision_aligned": True}]) is True

    get_settings.cache_clear()


def test_qwen_cannot_authorize_publication_before_release_eval(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_LOCAL_VISION_RELEASE_APPROVED", "false")
    get_settings.cache_clear()

    assert AutoVisualReviewService._local_model_has_publication_authority() is False

    get_settings.cache_clear()


def test_forged_qwen_authority_cannot_accept_complete_exact_qwen_evidence(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_LOCAL_VISION_RELEASE_APPROVED", "false")
    get_settings.cache_clear()
    service = object.__new__(AutoVisualReviewService)
    summary = {
        "asset_visual_critical_scene_ids": ["scene-1", "scene-3", "scene-5"],
        "asset_visual_verified_critical_scene_ids": ["scene-1", "scene-3", "scene-5"],
    }

    assert service._local_model_has_publication_authority() is False
    assert service._has_real_visual_evidence(summary, {"vision"}, [{"vision_aligned": True}]) is False

    get_settings.cache_clear()
    service = object.__new__(AutoVisualReviewService)
    summary = {
        "asset_visual_critical_scene_ids": ["scene-1", "scene-3", "scene-5"],
        "asset_visual_verified_critical_scene_ids": ["scene-1", "scene-3", "scene-5"],
    }

    assert service._has_real_visual_evidence(summary, {"vision"}, [{"vision_aligned": True}]) is False

    get_settings.cache_clear()
