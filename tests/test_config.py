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
        "LLM_REPAIR_MODEL",
        "LLM_REPAIR_REASONING_EFFORT",
        "LLM_REPAIR_TIMEOUT_SEC",
        "LLM_SCENE_PROVIDER",
        "LLM_FALLBACK_PROVIDER",
        "LLM_ENABLE_FALLBACK",
        "LLM_GATE_JUDGE_PROVIDER",
        "LLM_GATE_JUDGE_MODEL",
        "LLM_PREMIUM_REVIEW_PROVIDER",
        "LLM_PREMIUM_REVIEW_MODEL",
        "XAI_BASE_URL",
        "XAI_MODEL",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
    )
    for field in fields:
        monkeypatch.delenv(f"SHORTSFLOW_{field}", raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.openai_model == "gpt-5.6-luna"
    assert settings.llm_primary_provider == "openai"
    assert settings.llm_script_draft_provider == "openai"
    assert settings.llm_repair_provider == "openai"
    assert settings.llm_repair_model == "gpt-5.6-luna"
    assert settings.llm_repair_reasoning_effort == "max"
    assert settings.llm_repair_timeout_sec == 360.0
    assert settings.llm_scene_provider == "openai"
    assert settings.llm_fallback_provider == "deepseek"
    assert settings.llm_enable_fallback is True
    assert settings.deepseek_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.llm_gate_judge_provider == "xai"
    assert settings.xai_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.xai_model == "kimi-k3"
    assert settings.llm_gate_judge_model == "kimi-k3"
    assert settings.llm_premium_review_provider == "deepseek"
    assert settings.llm_premium_review_model == "deepseek-v4-pro"


def test_viral_intensity_defaults_to_review_warning(monkeypatch) -> None:
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_HARD_BLOCK", raising=False)
    monkeypatch.delenv("YTS_VIRAL_INTENSITY_MIN_SCORE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.viral_intensity_hard_block is False
    assert settings.viral_intensity_min_score == 0.72


def test_runtime_environment_is_normalized() -> None:
    settings = Settings(_env_file=None, runtime_environment="STAGING")

    assert settings.runtime_environment == "staging"


def test_runtime_environment_accepts_safe_channel_instance_slug() -> None:
    """Channel instance slugs (for metrics-only secondary instances) are accepted and lowercased."""
    settings = Settings(_env_file=None, runtime_environment="jarvis")
    assert settings.runtime_environment == "jarvis"

    settings2 = Settings(_env_file=None, runtime_environment="CHANNEL-A")
    assert settings2.runtime_environment == "channel-a"

    settings3 = Settings(_env_file=None, runtime_environment="my-channel-42")
    assert settings3.runtime_environment == "my-channel-42"


def test_runtime_environment_rejects_unknown_value() -> None:
    # 'laptop' is now a valid safe slug; use values that are invalid even after lowercasing
    for bad in ("", "1foo", "foo_bar", "foo bar", "STAGING_Mode"):
        with pytest.raises(ValidationError, match="runtime_environment must be one of"):
            Settings(_env_file=None, runtime_environment=bad)


def test_visual_review_defaults_to_human_only(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None)

    assert settings.vision_verifier_provider == "disabled"


def test_microdrama_script_generation_parallelism_is_bounded() -> None:
    assert Settings(_env_file=None).microdrama_script_generation_parallelism == 2
    assert Settings(
        _env_file=None,
        microdrama_script_generation_parallelism=4,
    ).microdrama_script_generation_parallelism == 4

    with pytest.raises(ValidationError, match="microdrama_script_generation_parallelism"):
        Settings(_env_file=None, microdrama_script_generation_parallelism=5)


def test_vision_verifier_provider_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    with pytest.raises(ValidationError, match="vision_verifier_provider must be one of"):
        Settings(_env_file=None, vision_verifier_provider="local_openai")


def test_vision_verifier_provider_accepts_gemini(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_VISION_VERIFIER_PROVIDER", raising=False)

    settings = Settings(_env_file=None, vision_verifier_provider="gemini")

    assert settings.vision_verifier_provider == "gemini"
    assert settings.gemini_vision_model == "gemini-3.5-flash"


@pytest.mark.parametrize("field", ["openai_reasoning_effort", "xai_reasoning_effort", "llm_repair_reasoning_effort"])
def test_reasoning_effort_rejects_unknown_values(field: str) -> None:
    with pytest.raises(ValidationError, match="reasoning effort must be one of"):
        Settings(_env_file=None, **{field: "turbo"})
