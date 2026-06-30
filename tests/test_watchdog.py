from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import delete

from tests.e2e_support import *  # noqa: F403
from tests.e2e_support import _create_basic_job
from app.watchdog import AutomationWatchdog


@pytest.fixture(autouse=True)
def clean_watchdog_rows():
    with SessionLocal() as session:
        session.execute(delete(PublicationSchedule).where(PublicationSchedule.job_id.like("watchdog-%")))
        session.execute(delete(RenderOutput).where(RenderOutput.job_id.like("watchdog-%")))
        session.execute(delete(AutomationAttempt).where(AutomationAttempt.run_id.like("watchdog-%")))
        session.execute(delete(AutomationRun).where(AutomationRun.run_id.like("watchdog-%")))
        session.execute(delete(TopicRequest).where(TopicRequest.job_id.like("watchdog-%")))
        session.execute(delete(Job).where(Job.job_id.like("watchdog-%")))
        session.commit()
    yield
    with SessionLocal() as session:
        session.execute(delete(PublicationSchedule).where(PublicationSchedule.job_id.like("watchdog-%")))
        session.execute(delete(RenderOutput).where(RenderOutput.job_id.like("watchdog-%")))
        session.execute(delete(AutomationAttempt).where(AutomationAttempt.run_id.like("watchdog-%")))
        session.execute(delete(AutomationRun).where(AutomationRun.run_id.like("watchdog-%")))
        session.execute(delete(TopicRequest).where(TopicRequest.job_id.like("watchdog-%")))
        session.execute(delete(Job).where(Job.job_id.like("watchdog-%")))
        session.commit()


def _settings(**overrides):
    defaults = {
        "automation_daily_timezone": "America/Sao_Paulo",
        "watchdog_daily_check_time": "04:00",
        "watchdog_min_future_coverage_days": 1,
        "watchdog_max_automation_runtime_minutes": 90,
        "watchdog_queued_stuck_minutes": 99999999,
        "watchdog_running_stuck_minutes": 99999999,
        "watchdog_publishing_stuck_minutes": 99999999,
        "watchdog_recurring_error_threshold": 2,
        "youtube_api_enabled": False,
        "watchdog_alert_delivery": "record_only",
        "watchdog_telegram_bot_token": None,
        "watchdog_telegram_chat_id": None,
        "data_dir": Path(os.environ["SHORTSFLOW_DATA_DIR"]),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _watchdog(settings=None):
    return AutomationWatchdog(settings or _settings(), orchestrator)


def _add_future_schedule(session, job_id: str, when: datetime) -> None:
    _create_basic_job(session, job_id=job_id, status="approved_for_publish")
    session.add(
        PublicationSchedule(
            schedule_id=f"{job_id}-schedule",
            job_id=job_id,
            schema_version="1.0.0",
            content_hash=f"{job_id}-schedule-hash",
            scheduled_for_utc=when,
            timezone="America/Sao_Paulo",
            youtube_visibility="public",
            status="scheduled",
        )
    )


def test_watchdog_silent_when_latest_run_succeeded_and_coverage_exists() -> None:
    now = datetime(2099, 6, 26, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-ok-run",
                schema_version="1.0.0",
                content_hash="watchdog-ok-run",
                local_date="2099-06-26",
                timezone="America/Sao_Paulo",
                status="succeeded",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                run_metadata={"schedule_complete": True},
            )
        )
        _add_future_schedule(session, "watchdog-ok-job", now + timedelta(days=1))
        session.commit()

    report = _watchdog().evaluate(now=now)

    assert report.status == "silent"
    assert report.findings == []


def test_watchdog_reports_failed_latest_run() -> None:
    now = datetime(2099, 6, 27, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-failed-run",
                schema_version="1.0.0",
                content_hash="watchdog-failed-run",
                local_date="2099-06-27",
                timezone="America/Sao_Paulo",
                status="failed",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                error="max_generation_attempts_exhausted",
            )
        )
        _add_future_schedule(session, "watchdog-failed-coverage", now + timedelta(days=1))
        session.commit()

    report = _watchdog().evaluate(now=now)

    assert report.status == "alert"
    assert any(f.kind == "automation_run_failed" and f.run_id == "watchdog-failed-run" for f in report.findings)


def test_watchdog_reports_long_running_run() -> None:
    now = datetime(2099, 6, 28, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-running-run",
                schema_version="1.0.0",
                content_hash="watchdog-running-run",
                local_date="2099-06-28",
                timezone="America/Sao_Paulo",
                status="running",
                started_at=now - timedelta(minutes=120),
            )
        )
        _add_future_schedule(session, "watchdog-running-coverage", now + timedelta(days=1))
        session.commit()

    report = _watchdog().evaluate(now=now)

    assert any(f.kind == "automation_run_stuck" for f in report.findings)


def test_watchdog_reports_low_future_coverage() -> None:
    now = datetime(2099, 6, 29, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-low-coverage-run",
                schema_version="1.0.0",
                content_hash="watchdog-low-coverage-run",
                local_date="2099-06-29",
                timezone="America/Sao_Paulo",
                status="succeeded",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                run_metadata={"schedule_complete": True},
            )
        )
        session.commit()

    report = _watchdog(_settings(watchdog_min_future_coverage_days=999999)).evaluate(now=now)

    assert any(f.kind == "future_coverage_low" for f in report.findings)


def test_watchdog_recovery_plan_recommends_reactive_backlog_for_low_coverage() -> None:
    now = datetime(2099, 6, 29, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-low-coverage-plan-run",
                schema_version="1.0.0",
                content_hash="watchdog-low-coverage-plan-run",
                local_date="2099-06-29",
                timezone="America/Sao_Paulo",
                status="succeeded",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                run_metadata={"schedule_complete": False, "unfilled_slots": ["2099-06-30T11:00"]},
            )
        )
        session.commit()

    watchdog = _watchdog(_settings(watchdog_min_future_coverage_days=999999))
    report = watchdog.evaluate(now=now)
    plan = watchdog.recovery_plan(report)

    assert plan["should_recover"] is True
    assert plan["mode"] == "reactive"
    assert plan["command"] == ".venv/bin/python -m app.cli backlog-recovery-run --mode reactive --json"
    assert "future_coverage_low" in plan["triggers"]


def test_watchdog_reports_stuck_jobs_by_status() -> None:
    now = datetime(2099, 6, 30, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-stuck-run",
                schema_version="1.0.0",
                content_hash="watchdog-stuck-run",
                local_date="2099-06-30",
                timezone="America/Sao_Paulo",
                status="succeeded",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                run_metadata={"schedule_complete": True},
            )
        )
        _add_future_schedule(session, "watchdog-stuck-coverage", now + timedelta(days=1))
        _create_basic_job(session, job_id="watchdog-stuck-queued", status="queued", updated_at=now - timedelta(minutes=31))
        _create_basic_job(session, job_id="watchdog-stuck-running", status="running", updated_at=now - timedelta(minutes=91))
        _create_basic_job(session, job_id="watchdog-stuck-publishing", status="publishing", updated_at=now - timedelta(minutes=31))
        session.commit()

    report = _watchdog(_settings(watchdog_queued_stuck_minutes=30, watchdog_running_stuck_minutes=90, watchdog_publishing_stuck_minutes=30)).evaluate(now=now)
    stuck_ids = {f.job_id for f in report.findings if f.kind == "job_stuck"}

    assert {"watchdog-stuck-queued", "watchdog-stuck-running", "watchdog-stuck-publishing"}.issubset(stuck_ids)


def test_watchdog_persists_report_and_renders_silent() -> None:
    now = datetime(2099, 7, 1, 8, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            AutomationRun(
                run_id="watchdog-persist-run",
                schema_version="1.0.0",
                content_hash="watchdog-persist-run",
                local_date="2099-07-01",
                timezone="America/Sao_Paulo",
                status="succeeded",
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=10),
                run_metadata={"schedule_complete": True},
            )
        )
        _add_future_schedule(session, "watchdog-persist-coverage", now + timedelta(days=1))
        session.commit()

    watchdog = _watchdog()
    report = watchdog.evaluate(now=now)
    paths = watchdog.persist_report(report)

    assert watchdog.telegram_brief(report) == "[SILENT]"
    assert Path(paths["latest"]).exists()
