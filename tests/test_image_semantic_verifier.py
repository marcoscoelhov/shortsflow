from __future__ import annotations

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
    assert result["verification_mode"] == "vision"
    assert result["vision_provider"] == "local_openai"
    assert result["vision_model"] == "gemma-4-e2b-it"
    assert result["vision_aligned"] is True
    assert result["semantic_match"] == 0.94

    get_settings.cache_clear()
