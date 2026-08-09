from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_render_primary_backend_defaults_to_remotion(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    settings = Settings(_env_file=None)

    assert settings.render_primary_backend == "remotion"


def test_viral_intensity_defaults_to_review_warning(monkeypatch) -> None:
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_HARD_BLOCK", raising=False)
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_MIN_SCORE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.viral_intensity_hard_block is False
    assert settings.viral_intensity_min_score == 0.72


def test_render_primary_backend_accepts_ffmpeg_override(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    settings = Settings(_env_file=None, render_primary_backend="FFmpeg")

    assert settings.render_primary_backend == "ffmpeg"


def test_render_primary_backend_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    with pytest.raises(ValidationError, match="render_primary_backend must be one of: ffmpeg, remotion"):
        Settings(_env_file=None, render_primary_backend="browser")


def test_runtime_environment_is_normalized() -> None:
    settings = Settings(_env_file=None, runtime_environment="STAGING")

    assert settings.runtime_environment == "staging"


def test_runtime_environment_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="runtime_environment must be one of"):
        Settings(_env_file=None, runtime_environment="laptop")


def test_vision_verifier_provider_accepts_local_openai(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None, vision_verifier_provider="LOCAL_OPENAI")

    assert settings.vision_verifier_provider == "local_openai"


def test_local_vision_defaults_to_qwen_cpu_candidate(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_LOCAL_VISION_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.local_vision_model == "qwen3-vl-2b-instruct-q4-k-m"
    assert settings.local_vision_release_approved is False


def test_vision_verifier_provider_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    with pytest.raises(ValidationError, match="vision_verifier_provider must be one of"):
        Settings(_env_file=None, vision_verifier_provider="gemma")


@pytest.mark.parametrize("field", ["openai_reasoning_effort", "xai_reasoning_effort"])
def test_reasoning_effort_rejects_unknown_values(field: str) -> None:
    with pytest.raises(ValidationError, match="reasoning effort must be one of"):
        Settings(_env_file=None, **{field: "turbo"})
