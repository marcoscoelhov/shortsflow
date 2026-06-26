from __future__ import annotations

import json
from types import SimpleNamespace

from app.llm_tournament import LlmTournamentCandidate, probe_llm_tournament_candidate, run_llm_tournament_probe


def test_llm_tournament_probe_dry_run_marks_configured_candidate_ready(monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_TEST_LLM_KEY", "test-key")
    candidate = LlmTournamentCandidate(
        candidate_id="provider-model",
        provider="openai_compatible",
        model="provider-model",
        api_key_env="SHORTSFLOW_TEST_LLM_KEY",
        roles=("script",),
        enabled=True,
        base_url="https://provider.example/v1",
    )

    result = probe_llm_tournament_candidate(candidate, dry_run=True)

    assert result.status == "dry_run_ready"
    assert result.configured is True
    assert result.json_valid is None


def test_llm_tournament_probe_skips_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("SHORTSFLOW_MISSING_LLM_KEY", raising=False)
    candidate = LlmTournamentCandidate(
        candidate_id="provider-model",
        provider="openai_compatible",
        model="provider-model",
        api_key_env="SHORTSFLOW_MISSING_LLM_KEY",
        roles=("script",),
        enabled=True,
        base_url="https://provider.example/v1",
    )

    result = probe_llm_tournament_candidate(candidate)

    assert result.status == "skipped_missing_api_key"
    assert result.configured is False


def test_llm_tournament_probe_openai_compatible_json_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("SHORTSFLOW_TEST_LLM_KEY", "test-key")

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {"ok": True, "model_role": "llm_tournament_probe", "language": "pt-BR"}
                            )
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=9, total_tokens=21),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.llm_tournament.OpenAI", FakeOpenAI)
    candidate = LlmTournamentCandidate(
        candidate_id="provider-model",
        provider="openai_compatible",
        model="provider-model",
        api_key_env="SHORTSFLOW_TEST_LLM_KEY",
        roles=("script",),
        enabled=True,
        base_url="https://provider.example/v1",
    )

    result = probe_llm_tournament_candidate(candidate, timeout_sec=3)

    assert result.status == "passed"
    assert result.json_valid is True
    assert result.input_tokens == 12
    assert result.output_tokens == 9
    assert result.total_tokens == 21
    assert captured["model"] == "provider-model"
    assert captured["client_kwargs"] == {
        "api_key": "test-key",
        "base_url": "https://provider.example/v1",
        "max_retries": 0,
        "timeout": 3,
    }


def test_llm_tournament_probe_report_summarizes_dry_run_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHORTSFLOW_TEST_LLM_KEY", "test-key")
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "ready-model",
                        "provider": "openai_compatible",
                        "model": "ready-model",
                        "api_key_env": "SHORTSFLOW_TEST_LLM_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    },
                    {
                        "candidate_id": "disabled-model",
                        "provider": "openai_compatible",
                        "model": "disabled-model",
                        "api_key_env": "SHORTSFLOW_TEST_LLM_KEY",
                        "roles": ["script"],
                        "enabled": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = run_llm_tournament_probe(manifest_path=manifest, dry_run=True)

    assert report["summary"]["total"] == 2
    assert report["summary"]["dry_run_ready"] == 1
    assert report["summary"]["skipped_disabled"] == 1
