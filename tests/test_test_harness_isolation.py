from __future__ import annotations

from app.config import get_settings
from app.providers.llm import LLMProviderRegistry
from tests.e2e_support import _write_job_artifact


def test_pytest_harness_uses_mock_llm_providers() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.use_mock_providers is True
    registry = LLMProviderRegistry()
    assert registry.primary_provider().provider_name == "mock"


def test_write_job_artifact_paths_are_absolute_for_file_uri() -> None:
    path = _write_job_artifact("iso-job", "render/final.mp4", "video")
    assert path.is_absolute()
    assert path.as_uri().startswith("file://")