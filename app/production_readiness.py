from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.db import session_scope
from app.domain_contracts import PUBLICATION_STATUS_PUBLISHING, PUBLICATION_STATUS_SCHEDULED
from app.models import PublicationSchedule
from app.utils import utcnow


@dataclass(frozen=True)
class ProductionReadinessCheck:
    name: str
    passed: bool
    severity: str
    detail: str
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductionReadinessReport:
    status: str
    checked_at: str
    checks: dict[str, ProductionReadinessCheck]

    @property
    def failed_checks(self) -> list[str]:
        return [name for name, check in self.checks.items() if not check.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "failed_checks": self.failed_checks,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
        }


def parse_tailscale_serve_status(status_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in status_text.splitlines() if line.strip()]
    dead_shortsflow_routes = [line for line in lines if "/shortsflow" in line and "8082" in line]
    return {
        "configured": bool(lines),
        "has_dead_shortsflow_route": bool(dead_shortsflow_routes),
        "details": "; ".join(dead_shortsflow_routes) if dead_shortsflow_routes else "ok" if lines else "not_configured",
    }


class ProductionReadinessService:
    def __init__(
        self,
        settings: Any,
        orchestrator: Any,
        *,
        future_scheduled_count: Callable[[], int] | None = None,
        tailscale_status: Callable[[], str] | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self._future_scheduled_count = future_scheduled_count or self._count_future_schedule
        self._tailscale_status = tailscale_status or _tailscale_serve_status
        self._now = now

    def evaluate(self) -> ProductionReadinessReport:
        checks = {
            "hub_auth_token": self._hub_auth_token_check(),
            "youtube_connection": self._youtube_connection_check(),
            "future_schedule_coverage": self._future_schedule_check(),
            "provider_mode": self._provider_mode_check(),
            "mock_fallback_policy": self._mock_fallback_policy_check(),
            "remotion_preflight": self._remotion_preflight_check(),
            "tailscale_serve": self._tailscale_serve_check(),
            "watchdog_delivery": self._watchdog_delivery_check(),
        }
        critical_failed = any(not check.passed and check.severity == "critical" for check in checks.values())
        warning_failed = any(not check.passed for check in checks.values())
        status = "not_ready" if critical_failed else "warning" if warning_failed else "ready"
        return ProductionReadinessReport(status=status, checked_at=self._now().isoformat(), checks=checks)

    def _hub_auth_token_check(self) -> ProductionReadinessCheck:
        configured = bool(getattr(self.settings, "hub_auth_token", None))
        return ProductionReadinessCheck(
            name="hub_auth_token",
            passed=configured,
            severity="critical",
            detail="configured" if configured else "missing",
            action="Set SHORTSFLOW_HUB_AUTH_TOKEN before exposing Hub surfaces." if not configured else None,
        )

    def _youtube_connection_check(self) -> ProductionReadinessCheck:
        if not bool(getattr(self.settings, "youtube_api_enabled", False)):
            return ProductionReadinessCheck("youtube_connection", True, "warning", "youtube api disabled")
        try:
            status = self.orchestrator.youtube.connection_status()
            missing = [item for item in getattr(status, "missing_items", []) if item]
            connected = bool(getattr(status, "connected", False)) and not missing
        except Exception as exc:  # noqa: BLE001
            return ProductionReadinessCheck("youtube_connection", False, "critical", str(exc), "Fix YouTube OAuth/configuration.")
        return ProductionReadinessCheck(
            "youtube_connection",
            connected,
            "critical",
            "connected" if connected else ", ".join(missing) or "disconnected",
            None if connected else "Connect YouTube OAuth before automatic publish.",
        )

    def _future_schedule_check(self) -> ProductionReadinessCheck:
        count = int(self._future_scheduled_count())
        minimum = int(getattr(self.settings, "watchdog_min_future_coverage_days", 3))
        passed = count >= minimum
        return ProductionReadinessCheck(
            "future_schedule_coverage",
            passed,
            "critical" if not passed else "info",
            f"{count} future slots; minimum={minimum}",
            None if passed else "Run safe backlog recovery or manual scheduling.",
        )

    def _provider_mode_check(self) -> ProductionReadinessCheck:
        use_mock = bool(getattr(self.settings, "use_mock_providers", False))
        return ProductionReadinessCheck(
            "provider_mode",
            not use_mock,
            "critical",
            "mock providers enabled" if use_mock else "production providers",
            None if not use_mock else "Disable SHORTSFLOW_USE_MOCK_PROVIDERS for production.",
        )

    def _mock_fallback_policy_check(self) -> ProductionReadinessCheck:
        allowed = bool(getattr(self.settings, "real_run_allow_mock_fallback", False))
        return ProductionReadinessCheck(
            "mock_fallback_policy",
            not allowed,
            "critical",
            "mock fallback allowed" if allowed else "mock fallback blocked",
            None if not allowed else "Disable real_run_allow_mock_fallback.",
        )

    def _remotion_preflight_check(self) -> ProductionReadinessCheck:
        if str(getattr(self.settings, "render_primary_backend", "")).lower() != "remotion":
            return ProductionReadinessCheck("remotion_preflight", True, "warning", "remotion not primary")
        try:
            preflight = self.orchestrator.premium_finishing.renderer.preflight_environment()
        except Exception as exc:  # noqa: BLE001
            return ProductionReadinessCheck("remotion_preflight", False, "critical", str(exc), "Fix render environment.")
        ready = bool(preflight.get("ready"))
        missing = [str(item) for item in preflight.get("missing_items") or []]
        return ProductionReadinessCheck(
            "remotion_preflight",
            ready,
            "critical",
            "ready" if ready else ", ".join(missing) or "not ready",
            None if ready else "Run Remotion setup/typecheck before publishing.",
        )

    def _tailscale_serve_check(self) -> ProductionReadinessCheck:
        try:
            parsed = parse_tailscale_serve_status(self._tailscale_status())
        except Exception as exc:  # noqa: BLE001
            return ProductionReadinessCheck("tailscale_serve", False, "warning", str(exc), "Inspect tailscale serve status manually.")
        passed = not bool(parsed["has_dead_shortsflow_route"])
        return ProductionReadinessCheck(
            "tailscale_serve",
            passed,
            "warning",
            str(parsed["details"]),
            None if passed else "Remove stale /shortsflow -> 8082 serve route.",
        )

    def _watchdog_delivery_check(self) -> ProductionReadinessCheck:
        delivery = str(getattr(self.settings, "watchdog_alert_delivery", "record_only"))
        passed = delivery != "record_only"
        return ProductionReadinessCheck(
            "watchdog_delivery",
            passed,
            "warning",
            delivery,
            None if passed else "Configure alert delivery when silent local files are not enough.",
        )

    def _count_future_schedule(self) -> int:
        now = self._now()
        with session_scope() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(PublicationSchedule)
                    .where(PublicationSchedule.status.in_({PUBLICATION_STATUS_SCHEDULED, PUBLICATION_STATUS_PUBLISHING}))
                    .where(PublicationSchedule.scheduled_for_utc > now)
                )
                or 0
            )


def _tailscale_serve_status() -> str:
    result = subprocess.run(["tailscale", "serve", "status"], capture_output=True, text=True, check=False, timeout=10)
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip()
    return result.stdout
