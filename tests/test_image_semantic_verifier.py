from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.providers.image import SemanticVerifier


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"description":"imagem alinhada","aligned_boolean":true,"alignment_score_0_to_1":0.94,"subject_visibility_score_0_to_1":0.91,"style_match_score_0_to_1":0.88,"text_or_watermark_penalty_0_to_1":0.0,"artifact_penalty_0_to_1":0.02,"reasons":["assunto central visivel"]}'
                    }
                }
            ]
        }


def test_local_openai_vision_verifier_scores_image(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "local_openai")
    monkeypatch.setenv("SHORTSFLOW_LOCAL_VISION_BASE_URL", "http://127.0.0.1:8081/v1")
    monkeypatch.setenv("SHORTSFLOW_LOCAL_VISION_MODEL", "gemma-4-e2b-it")
    get_settings.cache_clear()

    image_path = tmp_path / "scene.png"
    Image.new("RGB", (16, 16), (20, 40, 80)).save(image_path)
    captured: dict = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _FakeResponse()

    monkeypatch.setattr("app.providers.image.httpx.post", fake_post)

    verifier = SemanticVerifier()
    result = verifier.score(
        {"topic_hint": "musica grudada na cabeca", "narration_text": "Uma musica repete sem parar.", "image_prompt": "cerebro com notas musicais"},
        {"provider": "minimax", "uri": image_path.as_posix(), "prompt_snapshot": "cerebro com notas musicais"},
    )

    assert captured["url"] == "http://127.0.0.1:8081/v1/chat/completions"
    assert captured["json"]["model"] == "gemma-4-e2b-it"
    assert captured["json"]["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert result["verification_mode"] == "vision"
    assert result["vision_provider"] == "local_openai"
    assert result["vision_model"] == "gemma-4-e2b-it"
    assert result["vision_aligned"] is True
    assert result["semantic_match"] == 0.94

    get_settings.cache_clear()


def test_qwen_json_parser_accepts_fence_trailing_text_and_duplicate_object(monkeypatch) -> None:
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
    monkeypatch.setenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", "local_openai")
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
