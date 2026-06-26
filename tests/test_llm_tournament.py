from __future__ import annotations

import json

from app.llm_tournament import load_llm_tournament_candidates


def test_llm_tournament_candidates_manifest_loads() -> None:
    candidates = load_llm_tournament_candidates()
    candidate_ids = {candidate.candidate_id for candidate in candidates}

    assert "openai-gpt-5.5-medium" in candidate_ids
    assert "openai-gpt-5.4-nano" in candidate_ids
    assert "gemini-3.1-pro" in candidate_ids
    assert "deepseek-v4-pro" in candidate_ids
    assert "deepseek-v4-flash" in candidate_ids
    assert "gemini-3.5-flash" in candidate_ids
    assert "minimax-m3" in candidate_ids
    assert "minimax-m2" in candidate_ids
    assert "kimi-k2.6" in candidate_ids
    assert "kimi-k2.7-code" in candidate_ids
    assert "qwen3.5-plus" in candidate_ids
    assert "qwen3.7-max" in candidate_ids
    assert "grok-4.20-non-reasoning" in candidate_ids
    assert "grok-4.20-reasoning" in candidate_ids
    assert "grok-4.3" in candidate_ids
    assert "glm-4.7" in candidate_ids
    assert "glm-5.1" in candidate_ids
    assert "glm-5" in candidate_ids
    assert "glm-5-turbo" in candidate_ids
    assert all(candidate.roles for candidate in candidates)


def test_llm_tournament_candidate_configuration_uses_env(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SHORTSFLOW_TEST_TOURNAMENT_API_KEY", raising=False)
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "test-provider-model",
                        "provider": "openai_compatible",
                        "model": "test-provider-model",
                        "api_key_env": "SHORTSFLOW_TEST_TOURNAMENT_API_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    candidates = {candidate.candidate_id: candidate for candidate in load_llm_tournament_candidates(manifest)}

    assert candidates["test-provider-model"].configured is False

    monkeypatch.setenv("SHORTSFLOW_TEST_TOURNAMENT_API_KEY", "test-key")

    candidates = {candidate.candidate_id: candidate for candidate in load_llm_tournament_candidates(manifest)}

    assert candidates["test-provider-model"].configured is True
