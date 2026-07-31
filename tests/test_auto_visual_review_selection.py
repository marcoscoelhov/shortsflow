from __future__ import annotations

from types import SimpleNamespace

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
