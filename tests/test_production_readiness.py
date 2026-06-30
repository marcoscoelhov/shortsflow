from __future__ import annotations

from types import SimpleNamespace

from app.production_readiness import ProductionReadinessService, parse_tailscale_serve_status


class FakeRenderer:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    def preflight_environment(self) -> dict[str, object]:
        return {"ready": self.ready, "missing_items": [] if self.ready else ["remotion build missing"]}


class FakeYouTube:
    def __init__(self, connected: bool = True, missing_items: list[str] | None = None) -> None:
        self._connected = connected
        self._missing_items = missing_items or []

    def connection_status(self) -> SimpleNamespace:
        return SimpleNamespace(connected=self._connected, missing_items=self._missing_items)


class FakeOrchestrator:
    def __init__(self, *, remotion_ready: bool = True, youtube_connected: bool = True) -> None:
        self.premium_finishing = SimpleNamespace(renderer=FakeRenderer(remotion_ready))
        self.youtube = FakeYouTube(youtube_connected, [] if youtube_connected else ["oauth_missing"])


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "hub_auth_token": None,
        "youtube_api_enabled": True,
        "use_mock_providers": False,
        "real_run_allow_mock_fallback": False,
        "llm_fallback_provider": "disabled",
        "watchdog_alert_delivery": "record_only",
        "render_primary_backend": "remotion",
        "watchdog_min_future_coverage_days": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_readiness_flags_missing_hub_token_as_blocker() -> None:
    report = ProductionReadinessService(
        _settings(hub_auth_token=None),
        FakeOrchestrator(),
        future_scheduled_count=lambda: 3,
        tailscale_status=lambda: "https://srv.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8080",
    ).evaluate()

    assert report.status == "not_ready"
    assert report.checks["hub_auth_token"].passed is False
    assert report.checks["hub_auth_token"].severity == "critical"


def test_tailscale_parser_rejects_dead_shortsflow_route() -> None:
    status = """https://srv.ts.net (tailnet only)
|-- /           proxy http://127.0.0.1:8080
|-- /shortsflow proxy http://127.0.0.1:8082
"""

    parsed = parse_tailscale_serve_status(status)

    assert parsed["has_dead_shortsflow_route"] is True
    assert "8082" in parsed["details"]


def test_readiness_passes_when_required_operational_contracts_hold() -> None:
    report = ProductionReadinessService(
        _settings(hub_auth_token="set", watchdog_alert_delivery="telegram"),
        FakeOrchestrator(),
        future_scheduled_count=lambda: 3,
        tailscale_status=lambda: "https://srv.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8080",
    ).evaluate()

    assert report.status == "ready"
    assert report.failed_checks == []
    assert report.checks["future_schedule_coverage"].passed is True


def test_readiness_report_serializes_without_secret_values() -> None:
    report = ProductionReadinessService(
        _settings(hub_auth_token="super-secret-token"),
        FakeOrchestrator(),
        future_scheduled_count=lambda: 3,
        tailscale_status=lambda: "",
    ).evaluate()

    payload = report.to_dict()

    assert "super-secret-token" not in str(payload)
    assert payload["checks"]["hub_auth_token"]["detail"] == "configured"
