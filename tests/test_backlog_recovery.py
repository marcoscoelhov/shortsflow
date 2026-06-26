from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import delete, func, select

from tests.e2e_support import *  # noqa: F403
from tests.e2e_support import _create_basic_job
from app.backlog_recovery import BacklogRecoveryService
from app.models import BacklogRecoveryAttempt, NarrationAsset, RenderOutput, SceneAsset


@pytest.fixture(autouse=True)
def clean_backlog_rows():
    with SessionLocal() as session:
        session.execute(delete(BacklogRecoveryAttempt).where(BacklogRecoveryAttempt.job_id.like("backlog-%")))
        session.execute(delete(PublicationSchedule).where(PublicationSchedule.job_id.like("backlog-%")))
        session.execute(delete(RenderOutput).where(RenderOutput.job_id.like("backlog-%")))
        session.execute(delete(SceneAsset).where(SceneAsset.job_id.like("backlog-%")))
        session.execute(delete(NarrationAsset).where(NarrationAsset.job_id.like("backlog-%")))
        session.execute(delete(TopicRequest).where(TopicRequest.job_id.like("backlog-%")))
        session.execute(delete(Job).where(Job.job_id.like("backlog-%")))
        session.commit()
    yield
    with SessionLocal() as session:
        session.execute(delete(BacklogRecoveryAttempt).where(BacklogRecoveryAttempt.job_id.like("backlog-%")))
        session.execute(delete(PublicationSchedule).where(PublicationSchedule.job_id.like("backlog-%")))
        session.execute(delete(RenderOutput).where(RenderOutput.job_id.like("backlog-%")))
        session.execute(delete(SceneAsset).where(SceneAsset.job_id.like("backlog-%")))
        session.execute(delete(NarrationAsset).where(NarrationAsset.job_id.like("backlog-%")))
        session.execute(delete(TopicRequest).where(TopicRequest.job_id.like("backlog-%")))
        session.execute(delete(Job).where(Job.job_id.like("backlog-%")))
        session.commit()


def _settings():
    return SimpleNamespace(schema_version="1.0.0")


def _service():
    return BacklogRecoveryService(_settings(), orchestrator)


def _add_render(session, job_id: str) -> Path:
    path = _write_job_artifact(job_id, "render/final.mp4", "video")
    session.add(
        RenderOutput(
            render_id=f"{job_id}-render",
            job_id=job_id,
            schema_version="1.0.0",
            content_hash=f"{job_id}-render-hash",
            video_uri=path.resolve().as_uri(),
            duration_ms=45000,
            resolution="1080x1920",
            video_codec="h264",
            audio_codec="aac",
            filesize_bytes=5,
            ffmpeg_log_uri="file:///tmp/ffmpeg.log",
        )
    )
    return path


def _add_audio(session, job_id: str) -> None:
    path = _write_job_artifact(job_id, "audio/narration.wav", "audio")
    session.add(
        NarrationAsset(
            narration_id=f"{job_id}-narration",
            job_id=job_id,
            schema_version="1.0.0",
            content_hash=f"{job_id}-narration-hash",
            provider="mock",
            voice="mock",
            audio_uri=path.resolve().as_uri(),
            duration_ms=45000,
            sample_rate_hz=24000,
            channels=1,
        )
    )


def _add_asset(session, job_id: str) -> None:
    path = _write_job_artifact(job_id, "assets/scene-1.png", "image")
    session.add(
        SceneAsset(
            asset_id=f"{job_id}-asset",
            job_id=job_id,
            scene_id="scene-1",
            schema_version="1.0.0",
            content_hash=f"{job_id}-asset-hash",
            provider="mock",
            kind="image",
            uri=path.resolve().as_uri(),
            width=1080,
            height=1920,
            selected=True,
            scores={},
        )
    )


def test_scan_classifies_rendered_monetization_review_as_near_publishable() -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-near-render", status="monetization_review")
        _add_render(session, "backlog-near-render")
        session.commit()

    report = _service().scan()
    candidate = next(item for item in report.candidates if item.job_id == "backlog-near-render")

    assert candidate.classification == "near_publishable"
    assert "monetization_readiness_gate" in candidate.allowed_repairs


def test_scan_classifies_active_schedule_as_already_scheduled() -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-scheduled", status="ready_for_upload")
        _add_render(session, "backlog-scheduled")
        session.add(
            PublicationSchedule(
                schedule_id="backlog-scheduled-schedule",
                job_id="backlog-scheduled",
                schema_version="1.0.0",
                content_hash="backlog-scheduled-schedule-hash",
                scheduled_for_utc=utcnow() + timedelta(days=1),
                timezone="America/Sao_Paulo",
                youtube_visibility="public",
                status="scheduled",
            )
        )
        session.commit()

    candidate = next(item for item in _service().scan().candidates if item.job_id == "backlog-scheduled")

    assert candidate.classification == "already_scheduled"


def test_scan_classifies_empty_failed_job_as_not_worth_recovering() -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-empty", status="render_quality_failed")
        session.commit()

    candidate = next(item for item in _service().scan().candidates if item.job_id == "backlog-empty")

    assert candidate.classification == "not_worth_recovering"
    assert candidate.reasons == ["no_useful_artifacts"]


def test_scan_sends_factual_or_duplicate_risk_to_checkpoint() -> None:
    with SessionLocal() as session:
        _create_basic_job(
            session,
            job_id="backlog-factual-risk",
            status="blocked_for_monetization",
            quality_summary={"hard_blockers": ["unsupported_claim"]},
        )
        _add_render(session, "backlog-factual-risk")
        session.commit()

    candidate = next(item for item in _service().scan().candidates if item.job_id == "backlog-factual-risk")

    assert candidate.classification == "needs_checkpoint"
    assert candidate.risk == "high"


def test_same_repair_failed_twice_marks_not_worth_recovering() -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-failed-twice", status="monetization_review")
        _add_render(session, "backlog-failed-twice")
        for idx in range(2):
            session.add(
                BacklogRecoveryAttempt(
                    recovery_attempt_id=f"backlog-failed-twice-attempt-{idx}",
                    job_id="backlog-failed-twice",
                    schema_version="1.0.0",
                    content_hash=f"hash-{idx}",
                    status="failed",
                    repair_kind="monetization_readiness_gate",
                    before_status="monetization_review",
                    after_status=None,
                    reasons=["test"],
                    error="boom",
                )
            )
        session.commit()

    candidate = next(item for item in _service().scan().candidates if item.job_id == "backlog-failed-twice")

    assert candidate.classification == "not_worth_recovering"
    assert "same_repair_failed_twice" in candidate.reasons


def test_dry_run_does_not_record_attempts() -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-dry-run", status="monetization_review")
        _add_render(session, "backlog-dry-run")
        session.commit()

    report = _service().run(mode="weekly", dry_run=True, job_id="backlog-dry-run")

    assert report.dry_run is True
    assert report.actions == []
    with SessionLocal() as session:
        attempts = session.scalar(select(func.count()).select_from(BacklogRecoveryAttempt).where(BacklogRecoveryAttempt.job_id == "backlog-dry-run"))
    assert attempts == 0


def test_run_records_recovery_attempt(monkeypatch) -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id="backlog-run", status="monetization_review")
        _add_render(session, "backlog-run")
        session.commit()

    monkeypatch.setattr(orchestrator, "reprocess_job_from_step", lambda job_id, step: "ready_for_upload")

    report = _service().run(mode="reactive", job_id="backlog-run")

    assert report.actions[0]["status"] == "recovered"
    with SessionLocal() as session:
        attempt = session.scalar(select(BacklogRecoveryAttempt).where(BacklogRecoveryAttempt.job_id == "backlog-run"))
    assert attempt is not None
    assert attempt.status == "recovered"
