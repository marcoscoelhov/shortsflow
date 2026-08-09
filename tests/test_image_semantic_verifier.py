from __future__ import annotations

import json

from app.config import get_settings
from app.providers.image import SemanticVerifier


def test_vision_json_parser_accepts_fence_trailing_text_and_duplicate_object(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "disabled")
    get_settings.cache_clear()
    verifier = SemanticVerifier()
    first = {
        "description": "Jupiter, not Venus",
        "aligned_boolean": False,
        "alignment_score_0_to_1": 0.1,
    }
    content = f"```json\n{json.dumps(first)}\n```\n{json.dumps({'ignored': True})}"

    assert verifier._parse_vision_json(content, provider="test") == first

    get_settings.cache_clear()


def test_candidate_scoring_does_not_run_expensive_pixel_verification(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "disabled")
    get_settings.cache_clear()
    verifier = SemanticVerifier()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("candidate scoring must not call the vision model")

    monkeypatch.setattr(verifier, "_vision_score", fail_if_called)
    result = verifier.score_candidate(
        {"primary_subject": "Saturn", "image_prompt": "Saturn with visible rings"},
        {"provider": "minimax", "uri": "file:///tmp/saturn.png", "prompt_snapshot": "Saturn with visible rings"},
    )

    assert result["verification_mode"] == "prompt_heuristic"
    assert result["pixel_verified"] is False

    get_settings.cache_clear()


def test_prompt_heuristic_requires_visual_review_for_hook_and_payoff(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "disabled")
    get_settings.cache_clear()

    verifier = SemanticVerifier()
    asset = {
        "provider": "minimax",
        "uri": "file:///tmp/scene.png",
        "prompt_snapshot": "octopus changing skin color, no readable text anywhere",
    }

    for retention_role in ("visual_hook", "turn_or_payoff", "loop_close"):
        result = verifier.score(
            {
                "retention_role": retention_role,
                "primary_subject": "octopus",
                "narration_text": "The octopus changes its skin color.",
                "image_prompt": asset["prompt_snapshot"],
            },
            asset,
        )

        assert result["verification_mode"] == "prompt_heuristic"
        assert result["visual_review_required"] is True
        assert result["visual_review_reason"] == "critical_scene_requires_pixel_verification"
        assert result.get("pixel_verified") is not True

    get_settings.cache_clear()
