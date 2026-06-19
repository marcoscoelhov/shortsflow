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
        competitive_scout_global_enabled=False,
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
    assert payload["selected"][0]["discovery_contexts"][0]["region_code"] == "BR"


def test_competitive_scout_expands_queries_across_global_regions_with_caps(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        competitive_scout_min_maturity_hours=24,
        competitive_scout_max_video_duration_sec=90,
        competitive_scout_reference_batch_limit=5,
        competitive_scout_min_reference_views=10_000,
        competitive_scout_min_profile_references=2,
        competitive_scout_global_enabled=True,
        competitive_scout_regions="IN\nUS\nBR",
        competitive_scout_max_query_region_pairs=4,
        competitive_scout_max_analyses_per_run=1,
        competitive_scout_llm_analysis_enabled=False,
    )
    youtube = FakeYouTubeScoutClient(
        [
            _video("global-low", channel_id="UC-global-1", title="science facts about light", views=40_000),
            _video("global-high", channel_id="UC-global-2", title="animal facts that look impossible", views=900_000),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube)

    result = scout.run(queries=["science facts shorts", "animal facts shorts"], now=utcnow())

    assert result["queries_considered"] == 2
    assert result["regions_considered"] == ["BR", "IN", "US"]
    assert result["search_requests_considered"] == 4
    assert result["shorts_matched_filters"] == 2
    assert result["shorts_selected"] == 1
    assert [call["region_code"] for call in youtube.search_calls] == ["IN", "US", "BR", "IN"]
    artifact = tmp_path / "artifacts" / result["artifact_path"]
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["selected"][0]["youtube_video_id"] == "global-high"
    assert payload["selected"][0]["analysis"]["analysis_provider"] == "heuristic"
    assert payload["selected"][0]["discovery_contexts"][0]["query"] == "science facts shorts"


def test_retention_profile_skeleton_treats_llm_string_fields_as_items(tmp_path) -> None:
    scout = CompetitiveScout(settings=_settings(tmp_path), analyzer=HeuristicScoutAnalyzer())
    shorts = [
        ReferenceShort(
            reference_short_id="reference-string-fields",
            schema_version="1.0.0",
            content_hash="reference-string-fields-hash",
            youtube_video_id="video-string-fields",
            status="selected",
            source_type="external",
            niche_id="curiosidades",
            line_id="curiosidade_cotidiana",
            title="Fun Facts That Are Not Funny",
            youtube_channel_id="UC-string",
            duration_sec=35,
            published_at=utcnow(),
            view_count=1_000_000,
            like_count=50_000,
            comment_count=100,
            performance_score=1000.0,
            confidence="media",
            analysis_summary={
                "observed_structure": "Hook inicial com contraste; sequência rápida de fatos; virada final",
                "retention_moves": "Curiosity gap; pattern interrupt; payoff tardio",
                "risks": "exagero factual; fadiga de formato",
                "forbidden_copy_elements": "titulo literal; sequência exata de fatos",
                "why_it_might_work": "Contraste e recompensa rápida sustentam retenção.",
            },
            raw_metadata={},
        )
    ]

    skeleton = scout._dominant_skeleton(line_id="curiosidade_cotidiana", shorts=shorts, aggressive=True)

    assert skeleton["structure_sequence"][:3] == ["Hook inicial com contraste", "sequência rápida de fatos", "virada final"]
    assert skeleton["retention_moves"][:3] == ["Curiosity gap", "pattern interrupt", "payoff tardio"]
    assert all(len(item) > 1 for item in skeleton["structure_sequence"])


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
    assert "transferir apenas a funcao narrativa" in guidance["guidance_text"]
    assert "Movimentos transferiveis" in guidance["guidance_text"]


def test_competitive_scout_automation_cycle_advances_to_running_experiment(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        competitive_scout_min_maturity_hours=24,
        competitive_scout_max_video_duration_sec=90,
        competitive_scout_reference_batch_limit=5,
        competitive_scout_min_reference_views=10_000,
        competitive_scout_min_profile_references=2,
        competitive_scout_global_enabled=False,
        competitive_scout_auto_approve_profiles=True,
        competitive_scout_auto_start_experiments=True,
    )
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


def test_competitive_scout_automation_cycle_defaults_to_human_profile_decision(tmp_path) -> None:
    settings = _settings(tmp_path)
    with SessionLocal() as session:
        for experiment in session.scalars(select(RetentionExperiment).where(RetentionExperiment.status == "running")):
            experiment.status = "completed"
        session.commit()
    youtube = FakeYouTubeScoutClient(
        [
            _video("manual-cycle-001", channel_id="UC-manual-1", title="Por que o celular esquenta no sol?"),
            _video("manual-cycle-002", channel_id="UC-manual-2", title="Por que a tela do celular piora no sol?"),
        ]
    )
    scout = CompetitiveScout(settings=settings, youtube=youtube, analyzer=HeuristicScoutAnalyzer())

    result = scout.run_automation_cycle(niche_id="curiosidades", queries=["curiosidades celular"], now=utcnow())

    assert result["status"] == "completed"
    assert result["profiles"]["created"]
    assert result["approved_profiles"] == []
    assert result["started_experiments"] == []
    profile_id = result["profiles"]["created"][0]["profile_id"]
    with SessionLocal() as session:
        profile = session.get(LearnedRetentionProfile, profile_id)
        running_experiments = list(session.scalars(select(RetentionExperiment).where(RetentionExperiment.status == "running")).all())
    assert profile is not None
    assert profile.status == "pending_approval"
    assert running_experiments == []


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
    assert "Movimentos transferiveis" in guidance["guidance_text"]
    assert "TheManniiShow" not in guidance["guidance_text"]
    assert promoted_profile is not None
    assert promoted_profile.status == "promoted"
    assert promoted_profile.metrics["promoted_from_experiment_id"] == experiment_id
    assert old_profile is not None
    assert old_profile.status == "archived"
    assert experiment is not None
    assert experiment.result_summary["promoted_profile_id"] == profile_id


def test_retention_experiment_marks_unpublishable_job_as_failed_when_target_is_reached(tmp_path) -> None:
    settings = _settings(tmp_path)
    scout = CompetitiveScout(settings=settings, analyzer=HeuristicScoutAnalyzer())
    profile_id = f"profile-unpublishable-{new_id()}"
    job_id = f"job-unpublishable-{new_id()}"
    with SessionLocal() as session:
        session.add(
            LearnedRetentionProfile(
                profile_id=profile_id,
                schema_version="1.0.0",
                content_hash=stable_hash(profile_id),
                version="unpublishable-test",
                status="approved",
                niche_id="curiosidades",
                line_id="curiosidade_cotidiana",
                title="Perfil para falha antes de publicação",
                confidence="media",
                supporting_reference_short_ids=[],
                dominant_skeleton={
                    "line_id": "curiosidade_cotidiana",
                    "structure_sequence": ["abre com contraste"],
                    "retention_moves": ["payoff tardio"],
                },
                metrics={},
            )
        )
        session.add(
            Job(
                job_id=job_id,
                schema_version="1.0.0",
                content_hash=stable_hash(job_id),
                status="script_quality_failed",
                niche_id="curiosidades",
                language="pt-BR",
                target_duration_sec=50,
                topic_request_id=f"topic-{job_id}",
            )
        )
        session.commit()

    experiment_id = scout.start_experiment(profile_id, target_job_count=1)["experiment_id"]
    scout.attach_job_to_experiment(experiment_id, job_id)
    result = scout.evaluate_experiment(experiment_id)

    assert result["decision"] == "failed"
    assert result["status"] == "completed"
    assert result["unpublishable_jobs"] == 1
    assert result["pending_jobs"] == 0
    with SessionLocal() as session:
        assignment = session.scalar(select(RetentionExperimentJob).where(RetentionExperimentJob.experiment_id == experiment_id))
    assert assignment is not None
    assert assignment.status == "unpublishable"
    assert assignment.metrics["job_status"] == "script_quality_failed"


def test_retention_experiment_waits_when_published_job_has_low_confidence_snapshot(tmp_path) -> None:
    settings = _settings(tmp_path)
    scout = CompetitiveScout(settings=settings, analyzer=HeuristicScoutAnalyzer())
    profile_id = f"profile-low-confidence-{new_id()}"
    job_id = f"job-low-confidence-{new_id()}"
    with SessionLocal() as session:
        session.add(
            LearnedRetentionProfile(
                profile_id=profile_id,
                schema_version="1.0.0",
                content_hash=stable_hash(profile_id),
                version="low-confidence-test",
                status="approved",
                niche_id="curiosidades",
                line_id="ciencia_visual_simples",
                title="Perfil para aguardar Analytics",
                confidence="media",
                supporting_reference_short_ids=[],
                dominant_skeleton={
                    "line_id": "ciencia_visual_simples",
                    "structure_sequence": ["abre com contraste"],
                    "retention_moves": ["payoff tardio"],
                },
                metrics={},
            )
        )
        session.add(
            Job(
                job_id=job_id,
                schema_version="1.0.0",
                content_hash=stable_hash(job_id),
                status="published",
                niche_id="curiosidades",
                language="pt-BR",
                target_duration_sec=45,
                topic_request_id=f"topic-{job_id}",
            )
        )
        session.add(
            YouTubeAnalyticsSnapshot(
                snapshot_id=f"snapshot-low-confidence-{new_id()}",
                job_id=job_id,
                youtube_video_id="yt-low-confidence",
                schema_version="1.0.0",
                content_hash=stable_hash(job_id),
                fetched_at=utcnow(),
                start_date=str(utcnow().date()),
                end_date=str(utcnow().date()),
                summary_metrics={},
                daily_rows=[],
                raw_response={},
            )
        )
        session.commit()

    experiment_id = scout.start_experiment(profile_id, target_job_count=1)["experiment_id"]
    scout.attach_job_to_experiment(experiment_id, job_id)
    result = scout.evaluate_experiment(experiment_id)

    assert result["decision"] == "needs_more_data"
    assert result["status"] == "running"
    assert result["measured_jobs"] == 0
    assert result["low_confidence_measured_jobs"] == 1
    assert result["pending_jobs"] == 1
    with SessionLocal() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        assignment = session.scalar(select(RetentionExperimentJob).where(RetentionExperimentJob.experiment_id == experiment_id))
    assert experiment is not None
    assert experiment.finished_at is None
    assert assignment is not None
    assert assignment.status == "measured_low_confidence"
    assert assignment.metrics["youtube_video_id"] == "yt-low-confidence"
