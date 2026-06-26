from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_render_primary_backend_defaults_to_remotion(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    settings = Settings(_env_file=None)

    assert settings.render_primary_backend == "remotion"


def test_render_primary_backend_accepts_ffmpeg_override(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    settings = Settings(_env_file=None, render_primary_backend="FFmpeg")

    assert settings.render_primary_backend == "ffmpeg"


def test_render_primary_backend_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_PRIMARY_BACKEND", raising=False)

    with pytest.raises(ValidationError, match="render_primary_backend must be one of: ffmpeg, remotion"):
        Settings(_env_file=None, render_primary_backend="browser")


def test_vision_verifier_provider_accepts_local_openai(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None, vision_verifier_provider="LOCAL_OPENAI")

    assert settings.vision_verifier_provider == "local_openai"


def test_vision_verifier_provider_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    with pytest.raises(ValidationError, match="vision_verifier_provider must be one of"):
        Settings(_env_file=None, vision_verifier_provider="gemma")
