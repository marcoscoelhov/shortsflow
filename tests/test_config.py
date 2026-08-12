from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_llm_defaults_route_luna_through_opencode_go_without_changing_models(monkeypatch) -> None:
    fields = (
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "LLM_PRIMARY_PROVIDER",
        "LLM_SCRIPT_DRAFT_PROVIDER",
        "LLM_REPAIR_PROVIDER",
        "LLM_SCENE_PROVIDER",
        "LLM_FALLBACK_PROVIDER",
        "LLM_GATE_JUDGE_PROVIDER",
        "XAI_MODEL",
    )
    for field in fields:
        monkeypatch.delenv(f"SHORTSFLOW_{field}", raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.openai_model == "gpt-5.6-luna"
    assert settings.llm_primary_provider == "openai"
    assert settings.llm_script_draft_provider == "openai"
    assert settings.llm_repair_provider == "openai"
    assert settings.llm_scene_provider == "openai"
    assert settings.llm_fallback_provider == "disabled"
    assert settings.llm_gate_judge_provider == "xai"
    assert settings.xai_model == "grok-4.5"


def test_viral_intensity_defaults_to_review_warning(monkeypatch) -> None:
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_HARD_BLOCK", raising=False)
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_MIN_SCORE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.viral_intensity_hard_block is False
    assert settings.viral_intensity_min_score == 0.72


def test_runtime_environment_is_normalized() -> None:
    settings = Settings(_env_file=None, runtime_environment="STAGING")

    assert settings.runtime_environment == "staging"


def test_runtime_environment_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="runtime_environment must be one of"):
        Settings(_env_file=None, runtime_environment="laptop")


def test_visual_review_defaults_to_human_only(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None)

    assert settings.vision_verifier_provider == "disabled"


def test_vision_verifier_provider_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    with pytest.raises(ValidationError, match="vision_verifier_provider must be one of"):
        Settings(_env_file=None, vision_verifier_provider="local_openai")


def test_vision_verifier_provider_accepts_gemini(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None, vision_verifier_provider="gemini")

    assert settings.vision_verifier_provider == "gemini"
    assert settings.gemini_vision_model == "gemini-3.5-flash"


@pytest.mark.parametrize("field", ["openai_reasoning_effort", "xai_reasoning_effort"])
def test_reasoning_effort_rejects_unknown_values(field: str) -> None:
    with pytest.raises(ValidationError, match="reasoning effort must be one of"):
        Settings(_env_file=None, **{field: "turbo"})
