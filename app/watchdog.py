from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select

from app.db import session_scope
from app.domain_contracts import (
    ACTIVE_SCHEDULE_STATUSES,
    AUTOMATION_SOURCE_READY_SCRIPT,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    PUBLICATION_STATUS_PUBLISHING,
    PUBLICATION_STATUS_SCHEDULED,
)
from app.models import AutomationAttempt, AutomationRun, Job, PublicationSchedule
from app.utils import utcnow

STUCK_JOB_STATUSES = {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, PUBLICATION_STATUS_PUBLISHING}


@dataclass(frozen=True)
class WatchdogFinding:
    kind: str
    severity: str
    title: str
    detail: str
    action: str | None = None
    job_id: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchdogReport:
    status: str
    checked_at: str
    findings: list[WatchdogFinding]
    future_scheduled_count: int
    delivery_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "findings": [item.to_dict() for item in self.findings],
            "future_scheduled_count": self.future_scheduled_count,
            "delivery_status": self.delivery_status,
        }


class AutomationWatchdog:
    def __init__(self, settings: Any, orchestrator: Any) -> None:
        self.settings = settings
        self.orchestrator = orchestrator

    def evaluate(self, *, now: datetime | None = None) -> WatchdogReport:
        now = _ensure_utc(now or utcnow())
        findings: list[WatchdogFinding] = []
        future_count = self._future_scheduled_count(now)
        coverage_ok = future_count >= int(self.settings.watchdog_min_future_coverage_days)
        findings.extend(self._automation_run_findings(now, coverage_ok=coverage_ok))
        findings.extend(self._stuck_job_findings(now))
        findings.extend(self._recurring_error_findings(coverage_ok=coverage_ok))
        findings.extend(self._youtube_preflight_findings())
        if future_count < int(self.settings.watchdog_min_future_coverage_days):
            findings.append(
                WatchdogFinding(
                    kind="future_coverage_low",
                    severity="warning",
                    title="Cobertura futura abaixo do mínimo",
                    detail=f"{future_count} slots futuros agendados; mínimo={self.settings.watchdog_min_future_coverage_days}",
                    action="Rodar backlog recovery reativo ou geração automática.",
                )
            )
        alert_kinds = {"future_coverage_low", "automation_timer_missing", "automation_run_stuck", "job_stuck", "youtube_preflight_failed"}
        status = "alert" if any(item.severity == "critical" or item.kind in alert_kinds for item in findings) else "silent"
        return WatchdogReport(
            status=status,
            checked_at=now.isoformat(),
            findings=findings,
            future_scheduled_count=future_count,
        )

    def _automation_run_findings(self, now: datetime, *, coverage_ok: bool = False) -> list[WatchdogFinding]:
        findings: list[WatchdogFinding] = []
        local_tz = ZoneInfo(str(self.settings.automation_daily_timezone))
        local_now = now.astimezone(local_tz)
        grace_time = _parse_hhmm(str(self.settings.watchdog_daily_check_time))
        today_key = local_now.date().isoformat()
        with session_scope() as session:
            today_run = session.scalar(select(AutomationRun).where(AutomationRun.local_date == today_key).order_by(AutomationRun.created_at.desc()).limit(1))
            latest_run = session.scalar(select(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(1))
        run = today_run or latest_run
        if local_now.time() >= grace_time and not today_run:
            findings.append(
                WatchdogFinding(
                    kind="automation_timer_missing",
                    severity="critical",
                    title="Automação diária não registrou run até a janela limite",
                    detail=f"Nenhuma automation_run para {today_key} até {self.settings.watchdog_daily_check_time} BRT.",
                    action="Verificar shortsflow-automation.timer/service.",
                )
            )
        if not run:
            return findings
        if run.status == "running" and run.started_at:
            started = _ensure_utc(run.started_at)
            age_minutes = (now - started).total_seconds() / 60
            if age_minutes > int(self.settings.watchdog_max_automation_runtime_minutes):
                findings.append(
                    WatchdogFinding(
                        kind="automation_run_stuck",
                        severity="critical",
                        title="Automation run possivelmente travada",
                        detail=f"Run {run.run_id} está running há {age_minutes:.0f} min.",
                        action="Inspecionar logs e jobs em execução.",
                        run_id=run.run_id,
                    )
                )
        if run.status == "failed":
            if coverage_ok and _is_ready_script_no_topic_failure(run):
                return findings
            if coverage_ok:
                findings.append(
                    WatchdogFinding(
                        kind="automation_run_failed_historical",
                        severity="warning",
                        title="Automation run falhou, mas cobertura está recomposta",
                        detail=run.error or "Run terminou como failed sem erro detalhado.",
                        action="Sem ação imediata enquanto a cobertura futura estiver no mínimo.",
                        run_id=run.run_id,
                    )
                )
            else:
                findings.append(
                    WatchdogFinding(
                        kind="automation_run_failed",
                        severity="critical",
                        title="Automation run falhou",
                        detail=run.error or "Run terminou como failed sem erro detalhado.",
                        action="Classificar falha e acionar backlog recovery se cobertura estiver em risco.",
                        run_id=run.run_id,
                    )
                )
        if run.status == "succeeded" and (run.run_metadata or {}).get("schedule_complete") is False:
            findings.append(
                WatchdogFinding(
                    kind="automation_incomplete_schedule",
                    severity="warning",
                    title="Automation run não preencheu todos os slots",
                    detail=f"Slots não preenchidos: {(run.run_metadata or {}).get('unfilled_slots') or []}",
                    action="Rodar backlog recovery reativo.",
                    run_id=run.run_id,
                )
            )
        return findings

    def _stuck_job_findings(self, now: datetime) -> list[WatchdogFinding]:
        thresholds = {
            JOB_STATUS_QUEUED: int(self.settings.watchdog_queued_stuck_minutes),
            JOB_STATUS_RUNNING: int(self.settings.watchdog_running_stuck_minutes),
            PUBLICATION_STATUS_PUBLISHING: int(self.settings.watchdog_publishing_stuck_minutes),
        }
        findings: list[WatchdogFinding] = []
        with session_scope() as session:
            jobs = session.scalars(select(Job).where(Job.status.in_(STUCK_JOB_STATUSES)).order_by(Job.updated_at.asc()).limit(25)).all()
        for job in jobs:
            updated = _ensure_utc(job.updated_at or job.created_at)
            age_minutes = (now - updated).total_seconds() / 60
            threshold = thresholds.get(job.status, 999999)
            if age_minutes > threshold:
                findings.append(
                    WatchdogFinding(
                        kind="job_stuck",
                        severity="warning",
                        title=f"Job travado em {job.status}",
                        detail=f"Job {job.job_id} está em {job.status} há {age_minutes:.0f} min; limite={threshold} min.",
                        action="Inspecionar worker, logs e artefatos do job.",
                        job_id=job.job_id,
                    )
                )
        return findings

    def _recurring_error_findings(self, *, coverage_ok: bool = False) -> list[WatchdogFinding]:
        threshold = int(self.settings.watchdog_recurring_error_threshold)
        if threshold <= 1:
            threshold = 2
        with session_scope() as session:
            rows = session.execute(
                select(AutomationAttempt.error, func.count())
                .where(AutomationAttempt.error.is_not(None))
                .group_by(AutomationAttempt.error)
                .having(func.count() >= threshold)
                .limit(5)
            ).all()
        return [
            WatchdogFinding(
                kind="recurring_error",
                severity="warning",
                title="Erro recorrente na automação",
                detail=f"{count} ocorrências: {error}",
                action="Agrupar causa raiz antes de novas tentativas.",
            )
            for error, count in rows
            if error and not (coverage_ok and _is_ready_script_no_topic_error(str(error)))
        ]

    def _youtube_preflight_findings(self) -> list[WatchdogFinding]:
        try:
            if not getattr(self.settings, "youtube_api_enabled", False):
                return []
            status = self.orchestrator.youtube.connection_status()
            missing = [item for item in getattr(status, "missing_items", []) if item]
            if not getattr(status, "connected", False) or missing:
                return [
                    WatchdogFinding(
                        kind="youtube_preflight_failed",
                        severity="critical",
                        title="Integração YouTube indisponível",
                        detail=", ".join(missing) or "connection_status retornou desconectado.",
                        action="Corrigir credenciais/configuração do YouTube.",
                    )
                ]
        except Exception as exc:  # noqa: BLE001
            return [
                WatchdogFinding(
                    kind="youtube_preflight_failed",
                    severity="critical",
                    title="Erro ao verificar YouTube",
                    detail=str(exc),
                    action="Inspecionar integração YouTube.",
                )
            ]
        return []

    def _future_scheduled_count(self, now: datetime) -> int:
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

    def persist_report(self, report: WatchdogReport) -> dict[str, str]:
        root = Path(self.settings.data_dir) / "watchdog"
        root.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        latest = root / "latest.json"
        stamp = report.checked_at.replace(":", "-").replace("+00:00", "Z")
        historical = root / f"{stamp}.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        latest.write_text(text, encoding="utf-8")
        historical.write_text(text, encoding="utf-8")
        return {"latest": str(latest), "historical": str(historical)}

    def telegram_brief(self, report: WatchdogReport) -> str:
        if report.status != "alert":
            return "[SILENT]"
        lines = ["## ShortsFlow Watchdog — alerta", ""]
        for finding in report.findings[:8]:
            lines.append(f"- **{finding.title}** — {finding.detail}")
            if finding.action:
                lines.append(f"  Ação: {finding.action}")
        command = self.recommended_backlog_command(report)
        if command:
            lines.extend(["", f"Comando recomendado: `{command}`"])
        return "\n".join(lines)

    def recommended_backlog_command(self, report: WatchdogReport) -> str | None:
        plan = self.recovery_plan(report)
        return str(plan["command"]) if plan["should_recover"] else None

    def recovery_plan(self, report: WatchdogReport) -> dict[str, Any]:
        trigger_kinds = {"future_coverage_low", "automation_run_failed", "automation_incomplete_schedule"}
        triggers = [finding.kind for finding in report.findings if finding.kind in trigger_kinds]
        should_recover = bool(triggers)
        return {
            "should_recover": should_recover,
            "mode": "reactive" if should_recover else None,
            "command": ".venv/bin/python -m app.cli backlog-recovery-run --mode reactive --json" if should_recover else None,
            "triggers": triggers,
        }

    def deliver_alert(self, report: WatchdogReport) -> WatchdogReport:
        if report.status != "alert":
            return WatchdogReport(**{**report.to_dict(), "findings": report.findings, "delivery_status": "silent"})
        if str(self.settings.watchdog_alert_delivery) != "telegram":
            return WatchdogReport(**{**report.to_dict(), "findings": report.findings, "delivery_status": "skipped_record_only"})
        token = self.settings.watchdog_telegram_bot_token
        chat_id = self.settings.watchdog_telegram_chat_id
        if not token or not chat_id:
            return WatchdogReport(**{**report.to_dict(), "findings": report.findings, "delivery_status": "skipped_missing_config"})
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": self.telegram_brief(report), "parse_mode": "Markdown"},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        response.raise_for_status()
        return WatchdogReport(**{**report.to_dict(), "findings": report.findings, "delivery_status": "sent_telegram"})


def _is_ready_script_no_topic_failure(run: AutomationRun) -> bool:
    if run.error != "max_generation_attempts_exhausted":
        return False
    blockers = (run.run_metadata or {}).get("publish_blockers") or []
    return bool(blockers) and all(
        item.get("source") == AUTOMATION_SOURCE_READY_SCRIPT and item.get("reason_code") == "no_topic"
        for item in blockers
        if isinstance(item, dict)
    )


def _is_ready_script_no_topic_error(error: str) -> bool:
    return "reason_code=no_topic" in error and "Banco de roteiros" in error


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))
