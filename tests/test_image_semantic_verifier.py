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


def test_vision_json_parser_sanitizes_gemini_apostrophe_escape(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "disabled")
    get_settings.cache_clear()
    verifier = SemanticVerifier()
    # Gemini às vezes emite \' (apóstrofo escapado), inválido em JSON estrito
    content = '{"description": "marcas d\\\'água e sem artefatos", "aligned_boolean": true, "alignment_score_0_to_1": 0.9}'

    data = verifier._parse_vision_json(content, provider="gemini_vision")

    assert data["alignment_score_0_to_1"] == 0.9
    assert "água" in data["description"]

    get_settings.cache_clear()


def test_gemini_vision_flag_enabled_only_with_provider_and_key(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "gemini")
    monkeypatch.setenv("SHORTSFLOW_GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    verifier = SemanticVerifier()

    assert verifier.provider == "gemini"
    assert verifier.gemini_enabled is True
    assert verifier.gemini_model == "gemini-3.5-flash"
    assert verifier.mmx_enabled is False
    assert verifier.enabled is True

    get_settings.cache_clear()


def test_gemini_vision_parse_and_score_mapping(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "gemini")
    monkeypatch.setenv("SHORTSFLOW_GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    verifier = SemanticVerifier()

    raw = json.dumps(
        {
            "description": "estrada vazia, não é eclipse",
            "aligned_boolean": False,
            "alignment_score_0_to_1": 0.2,
            "subject_visibility_score_0_to_1": 0.1,
            "style_match_score_0_to_1": 0.3,
            "text_or_watermark_penalty_0_to_1": 0.0,
            "artifact_penalty_0_to_1": 0.1,
            "reasons": ["assunto errado"],
        }
    )
    data = verifier._parse_vision_json(raw, provider="gemini_vision")
    scores = verifier._vision_data_to_scores(data)

    assert scores["semantic_match"] == 0.2
    assert scores["vision_aligned"] is False

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
