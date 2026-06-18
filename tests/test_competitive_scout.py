from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.competitive_scout import CompetitiveScout, HeuristicScoutAnalyzer, classify_editorial_line, parse_youtube_duration
from app.config import Settings
from app.db import SessionLocal
from app.models import Job, LearnedRetentionProfile, ReferenceChannel, ReferenceShort, RetentionExperiment, RetentionExperimentJob, ScoutRun, YouTubeAnalyticsSnapshot
from app.utils import new_id, stable_hash, utcnow


class FakeYouTubeScoutClient:
    def __init__(self, videos: list[dict], *, search_video_ids: list[str] | None = None) -> None:
        self.videos = {str(video["id"]): video for video in videos}
        self.search_video_ids = search_video_ids or list(self.videos)
        self.search_calls: list[dict] = []

    def search_public_videos(self, **kwargs):
        self.search_calls.append(kwargs)
        return [{"id": {"videoId": video_id}, "snippet": {"channelId": self.videos[video_id]["snippet"]["channelId"]}} for video_id in self.search_video_ids]

    def fetch_public_videos(self, video_ids: list[str]):
        return [self.videos[video_id] for video_id in video_ids if video_id in self.videos]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        competitive_scout_min_maturity_hours=24,
        competitive_scout_max_video_duration_sec=90,
        competitive_scout_reference_batch_limit=5,
        competitive_scout_min_reference_views=10_000,
        competitive_scout_min_profile_references=2,
    )


def _video(video_id: str, *, channel_id: str = "UC-ref", title: str = "Por que o celular esquenta no sol?", hours_old: int = 72, views: int = 80_000, duration: str = "PT58S") -> dict:
    published_at = (datetime.now(UTC) - timedelta(hours=hours_old)).isoformat().replace("+00:00", "Z")
    return {
        "id": video_id,
        "snippet": {
            "channelId": channel_id,
            "channelTitle": f"Canal {channel_id}",
            "title": title,
            "description": "Curiosidade cotidiana sobre celular, sol e calor.",
            "publishedAt": published_at,
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": str(views), "likeCount": "3200", "commentCount": "180"},
    }


def test_youtube_duration_parser_and_line_classifier() -> None:
    assert parse_youtube_duration("PT58S") == 58
    assert parse_youtube_duration("PT1M12S") == 72
    assert parse_youtube_duration("PT1H2M3S") == 3723
    assert classify_editorial_line("Por que o celular esquenta no sol?", "") == "curiosidade_cotidiana"
    assert classify_editorial_line("O tubarão que muda tudo no escuro", "") == "natureza_payoff_visual"


def test_competitive_scout_persists_channels_shorts_run_and_json_artifact(tmp_path) -> None:
    settings = _settings(tmp_path)
    youtube = FakeYouTubeScoutClient([_video("viral-001", channel_id="UC-viral")])
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())

    result = scout.run(queries=["curiosidades celular"], now=utcnow())

    assert result["status"] == "completed"
    assert result["shorts_selected"] == 1
    with SessionLocal() as session:
        channel = session.scalar(select(ReferenceChannel).where(ReferenceChannel.youtube_channel_id == "UC-viral"))
        short = session.scalar(select(ReferenceShort).where(ReferenceShort.youtube_video_id == "viral-001"))
        run = session.get(ScoutRun, result["run_id"])
    assert channel is not None
    assert channel.status == "candidate"
    assert short is not None
    assert short.status == "selected"
    assert short.line_id == "curiosidade_cotidiana"
    assert short.performance_score and short.performance_score > 0
    assert short.analysis_summary["analysis_provider"] == "heuristic"
    assert run is not None
    assert run.shorts_selected == 1
    artifact = tmp_path / "artifacts" / result["artifact_path"]
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["selected"][0]["youtube_video_id"] == "viral-001"


def test_competitive_scout_filters_immature_or_long_reference(tmp_path) -> None:
    settings = _settings(tmp_path)
    youtube = FakeYouTubeScoutClient(
        [
            _video("new-short", channel_id="UC-new", hours_old=3, views=90_000),
            _video("long-short", channel_id="UC-new", hours_old=72, views=90_000, duration="PT2M10S"),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())

    result = scout.run(queries=["curiosidades"], now=utcnow())

    assert result["shorts_considered"] == 2
    assert result["shorts_selected"] == 0
    with SessionLocal() as session:
        statuses = {
            short.youtube_video_id: short.status
            for short in session.scalars(
                select(ReferenceShort).where(ReferenceShort.youtube_video_id.in_(["new-short", "long-short"]))
            )
        }
    assert statuses == {"new-short": "candidate", "long-short": "candidate"}


def test_competitive_scout_uses_approved_channels_when_no_sources_are_passed(tmp_path) -> None:
    settings = _settings(tmp_path)
    channel_id = "UC-approved-scout"
    with SessionLocal() as session:
        existing = session.scalar(select(ReferenceChannel).where(ReferenceChannel.youtube_channel_id == channel_id))
        if existing is None:
            session.add(
                ReferenceChannel(
                    reference_channel_id="ref-approved-scout",
                    youtube_channel_id=channel_id,
                    schema_version="1.0.0",
                    content_hash=stable_hash(channel_id),
                    status="approved",
                    niche_id="curiosidades",
                    title="Canal aprovado",
                    confidence="alta",
                )
            )
        session.commit()
    youtube = FakeYouTubeScoutClient([_video("approved-video-001", channel_id=channel_id)])
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())

    result = scout.run(now=utcnow())

    assert result["channels_considered"] == 1
    assert youtube.search_calls[0]["channel_id"] == channel_id


def test_scout_synthesizes_approved_profile_and_starts_experiment(tmp_path) -> None:
    settings = _settings(tmp_path)
    youtube = FakeYouTubeScoutClient(
        [
            _video("profile-video-001", channel_id="UC-profile-1", title="Por que o celular esquenta no sol?"),
            _video("profile-video-002", channel_id="UC-profile-2", title="Por que a tela do celular piora no sol?"),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())
    run_result = scout.run(queries=["curiosidades celular"], now=utcnow())

    profile_result = scout.synthesize_profiles_from_run(run_result["run_id"], min_references=2)

    assert profile_result["created"][0]["references"] == 2
    profile_id = profile_result["created"][0]["profile_id"]
    with SessionLocal() as session:
        profile = session.get(LearnedRetentionProfile, profile_id)
    assert profile is not None
    assert profile.status == "pending_approval"
    assert profile.dominant_skeleton["mode"] == "aggressive_skeleton_copy"
    assert "structure_sequence" in profile.dominant_skeleton
    assert (tmp_path / "artifacts" / profile.analysis_artifact_path).exists()

    approved = scout.approve_profile(profile_id)
    experiment = scout.start_experiment(profile_id, target_job_count=2)
    guidance = scout.active_experiment_guidance(niche_id="curiosidades")

    assert approved["status"] == "approved"
    assert experiment["status"] == "running"
    assert guidance is not None
    assert guidance["experiment_id"] == experiment["experiment_id"]
    assert "copiar agressivamente o esqueleto" in guidance["guidance_text"]


def test_competitive_scout_automation_cycle_advances_to_running_experiment(tmp_path) -> None:
    settings = _settings(tmp_path)
    with SessionLocal() as session:
        for experiment in session.scalars(select(RetentionExperiment).where(RetentionExperiment.status == "running")):
            experiment.status = "completed"
        session.commit()
    youtube = FakeYouTubeScoutClient(
        [
            _video("auto-cycle-001", channel_id="UC-auto-1", title="Por que o celular esquenta no sol?"),
            _video("auto-cycle-002", channel_id="UC-auto-2", title="Por que a tela do celular piora no sol?"),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())

    result = scout.run_automation_cycle(niche_id="curiosidades", queries=["curiosidades celular"], now=utcnow())

    assert result["status"] == "completed"
    assert result["scout_run"]["shorts_selected"] == 2
    assert result["approved_profiles"]
    assert result["started_experiments"]
    profile_id = result["approved_profiles"][0]["profile_id"]
    experiment_id = result["started_experiments"][0]["experiment_id"]
    with SessionLocal() as session:
        profile = session.get(LearnedRetentionProfile, profile_id)
        experiment = session.get(RetentionExperiment, experiment_id)
    assert profile is not None
    assert profile.status == "approved"
    assert experiment is not None
    assert experiment.status == "running"


def test_retention_experiment_attaches_job_and_evaluates_success(tmp_path) -> None:
    settings = _settings(tmp_path)
    youtube = FakeYouTubeScoutClient(
        [
            _video("experiment-video-001", channel_id="UC-exp-1", title="Por que o celular esquenta no sol?"),
            _video("experiment-video-002", channel_id="UC-exp-2", title="Por que a tela do celular piora no sol?"),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())
    run_result = scout.run(queries=["curiosidades celular"], now=utcnow())
    profile_id = scout.synthesize_profiles_from_run(run_result["run_id"], min_references=2)["created"][0]["profile_id"]
    scout.approve_profile(profile_id)
    experiment_id = scout.start_experiment(profile_id, target_job_count=1)["experiment_id"]
    job_id = f"experiment-job-{new_id()}"
    with SessionLocal() as session:
        session.add(
            Job(
                job_id=job_id,
                schema_version="1.0.0",
                content_hash=stable_hash(job_id),
                status="published",
                niche_id="curiosidades",
                language="pt-BR",
                target_duration_sec=50,
                topic_request_id=f"topic-{job_id}",
            )
        )
        session.add(
            YouTubeAnalyticsSnapshot(
                snapshot_id=f"snapshot-{job_id}",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash=stable_hash({"job_id": job_id, "retention": 84}),
                youtube_video_id="yt-experiment-001",
                start_date="2026-06-01",
                end_date="2026-06-18",
                summary_metrics={
                    "views": 420,
                    "averageViewPercentage": 84.0,
                    "averageViewDuration": 42.0,
                    "shares": 8,
                    "subscribersGained": 3,
                },
                daily_rows=[],
                raw_response={},
            )
        )
        session.commit()

    attached = scout.attach_job_to_experiment(experiment_id, job_id)
    result = scout.evaluate_experiment(experiment_id)

    assert attached["status"] == "assigned"
    assert result["decision"] == "success_strong"
    assert result["status"] == "completed"
    assert result["winner_job_ids"] == [job_id]
    with SessionLocal() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        assignment = session.scalar(select(RetentionExperimentJob).where(RetentionExperimentJob.experiment_id == experiment_id))
    assert experiment is not None
    assert experiment.decision == "success_strong"
    assert assignment is not None
    assert assignment.status == "measured"

    old_profile_id = f"old-profile-{new_id()}"
    with SessionLocal() as session:
        session.add(
            LearnedRetentionProfile(
                profile_id=old_profile_id,
                schema_version="1.0.0",
                content_hash=stable_hash(old_profile_id),
                version="old-curiosidade-cotidiana",
                status="promoted",
                niche_id="curiosidades",
                line_id="curiosidade_cotidiana",
                title="Perfil antigo",
                confidence="media",
                supporting_reference_short_ids=[],
                dominant_skeleton={"line_id": "curiosidade_cotidiana", "structure_sequence": ["antigo"], "retention_moves": ["antigo"]},
                metrics={},
            )
        )
        session.commit()

    promoted = scout.promote_experiment_winner(experiment_id)

    assert promoted["status"] == "promoted"
    assert old_profile_id in promoted["archived_profile_ids"]
    with SessionLocal() as session:
        for running_experiment in session.scalars(select(RetentionExperiment).where(RetentionExperiment.status == "running")):
            running_experiment.status = "completed"
        promoted_profile = session.get(LearnedRetentionProfile, profile_id)
        old_profile = session.get(LearnedRetentionProfile, old_profile_id)
        experiment = session.get(RetentionExperiment, experiment_id)
        session.commit()
    guidance = scout.active_retention_guidance(niche_id="curiosidades")
    assert guidance is not None
    assert guidance["source_kind"] == "promoted_profile"
    assert guidance["profile_id"] == profile_id
    assert "Perfil de Retencao Promovido ativo" in guidance["guidance_text"]
    assert promoted_profile is not None
    assert promoted_profile.status == "promoted"
    assert promoted_profile.metrics["promoted_from_experiment_id"] == experiment_id
    assert old_profile is not None
    assert old_profile.status == "archived"
    assert experiment is not None
    assert experiment.result_summary["promoted_profile_id"] == profile_id
