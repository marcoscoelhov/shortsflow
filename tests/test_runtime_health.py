from __future__ import annotations

from types import SimpleNamespace

from app.routes import health as health_module


def test_healthcheck_exposes_deployed_runtime_identity(monkeypatch, tmp_path) -> None:
    settings = SimpleNamespace(
        app_name="ShortsFlow",
        app_host="127.0.0.1",
        app_port=8082,
        tailscale_hostname="srv",
        tailnet_domain="example.ts.net",
        use_mock_providers=False,
        llm_primary_provider="openai",
        llm_gate_judge_provider="xai",
        llm_gate_judge_model="grok",
        tts_primary_provider="edge_tts",
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path,
        runtime_environment="staging",
        deployment_revision="abc123",
        runtime_drain_path=tmp_path / "drain",
        heavy_job_lock_path=tmp_path / "heavy.lock",
        heavy_job_lock_enabled=False,
        staging_min_free_disk_gb=0.0,
        staging_min_available_memory_gb=0.0,
        staging_max_artifacts_gb=0.0,
        worker_enabled=True,
    )
    monkeypatch.setattr(health_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        health_module.RemotionCliRenderer,
        "preflight_environment",
        lambda self: {"ready": True, "missing_items": []},
    )

    payload = health_module.healthcheck()

    assert payload["runtime"]["environment"] == "staging"
    assert payload["runtime"]["revision"] == "abc123"
    assert payload["runtime"]["worker_enabled"] is True
    assert payload["runtime"]["admission"]["allowed"] is True
