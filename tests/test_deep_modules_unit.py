from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.artifact_retention import retention_metadata
from app.channel_publication import channel_publication_payload, refresh_channel_publication_hash, tiktok_caption
from app.hub_forms import build_performance_metric_payload, build_review_action_payload
from app.hub_job_request import HubTrendSeed, build_hub_job_request
from app.hub_prompt import DEFAULT_VIRAL_PROMPT_TEMPLATE, load_viral_prompt_template, save_viral_prompt_template
from app.hub_context import HubContext
from app.job_failure import build_failure_diagnosis, failure_status_for_step
from app.job_progress import PIPELINE_STEP_NAMES, build_job_progress
from app.pipelines.script_audit import ScriptAuditDomain
from app.pipelines.script_metrics import normalize_script_metrics
from app.publication_ops import PublicationOperations
from app.storage import StorageManager
from app.topic_scout import TopicScout
from app.trends import TrendCandidate
from app.utils import file_sha256, stable_hash, utcnow
from scripts.audit_system_quality import score_image_semantics, score_publish, score_script, score_topic


class _StorageSpy:
    def __init__(self) -> None:
        self.persisted: list[tuple[str, str, dict]] = []

    def persist_json(self, job_id: str, relative_path: str, payload: dict) -> None:
        self.persisted.append((job_id, relative_path, payload))


def test_script_metrics_unit_normalizes_provider_score_shapes() -> None:
    metrics = normalize_script_metrics(
        {
            "hook_score": "8/10",
            "clarity_score": "90%",
            "information_density_score": "7",
            "repetition_score": "0.95",
            "ending_strength_score": "aprovado",
        }
    )

    assert metrics["hook_score"] == 0.8
    assert metrics["clarity_score"] == 0.9
    assert metrics["information_density_score"] == 0.7
    assert metrics["repetition_score"] == 0.05
    assert metrics["ending_strength_score"] is True


def test_script_audit_unit_runs_for_limited_fact_pack_and_persists_artifact() -> None:
    storage = _StorageSpy()
    calls = {"count": 0}

    def audit_publish_package(payload):
        calls["count"] += 1
        return {"passed": True, "reasons": [], "provider": "unit-test"}

    owner = SimpleNamespace(
        settings=SimpleNamespace(schema_version="1.0.0", llm_publish_audit_timeout_sec=1, llm_enable_fallback=False),
        storage=storage,
        providers=SimpleNamespace(creative=SimpleNamespace(audit_publish_package=audit_publish_package)),
        _serialize_for_json=lambda payload: payload,
    )
    audit = ScriptAuditDomain(owner)._text_publish_audit("job-1", {"title": "x"}, {"status": "limited"})

    assert audit == {"passed": True, "reasons": [], "provider": "unit-test"}
    assert calls["count"] == 1
    assert storage.persisted[0][1] == "text_publish_audit.json"
    assert storage.persisted[0][2]["audit"]["provider"] == "unit-test"


def test_hub_context_unit_classifies_operational_status_for_scheduled_job() -> None:
    context = HubContext(SimpleNamespace(), SimpleNamespace(build_job_progress=lambda job: {}), SimpleNamespace())
    job = SimpleNamespace(status="approved_for_publish")
    schedule = SimpleNamespace(status="scheduled", scheduled_for_utc=utcnow() + timedelta(days=1))

    status = context._publication_operational_status(job, schedule)

    assert status["status"] == "scheduled_publication"
    assert status["stage"] == "Programação"
    assert status["label"] == "Programado"


def test_job_progress_uses_pipeline_steps_and_timeline_for_running_job() -> None:
    job = SimpleNamespace(status="running", current_step="scene_plan")
    progress = build_job_progress(
        job,
        performance_timeline={
            "steps": [
                {"step_name": "input_gate", "status": "succeeded", "attempt": 1, "duration_ms": 10},
                {"step_name": "topic_plan", "status": "succeeded", "attempt": 1, "duration_ms": 20},
                {"step_name": "script", "status": "succeeded", "attempt": 1, "duration_ms": 30},
            ]
        },
        events=[{"event": "script.succeeded"}],
    )

    assert progress["state"] == "running"
    assert progress["current_step"] == "scene_plan"
    assert progress["current_label"] == "Cenas"
    assert progress["completed_steps"] == 3
    assert progress["total_steps"] == len(PIPELINE_STEP_NAMES)
    assert progress["steps"][3]["status"] == "running"
    assert progress["last_event"] == {"event": "script.succeeded"}


def test_job_progress_marks_failed_current_step_without_timeline() -> None:
    job = SimpleNamespace(status="render_quality_failed", current_step="render")
    progress = build_job_progress(job)

    assert progress["state"] == "failed"
    assert progress["current_label"] == "Render"
    assert progress["steps"][8]["status"] == "failed"
    assert progress["steps"][0]["status"] == "completed"


def test_job_failure_status_maps_quality_gate_failures_by_step() -> None:
    assert failure_status_for_step("script", "gate failed") == "script_quality_failed"
    assert failure_status_for_step("render", "render quality gate failed") == "render_quality_failed"
    assert failure_status_for_step("scene_plan", "visual contract quality gate failed") == "visual_contract_quality_failed"
    assert failure_status_for_step("tts", "provider unavailable") == "failed"


def test_job_failure_diagnosis_explains_script_audit_without_verified_facts() -> None:
    diagnosis = build_failure_diagnosis(
        job_id="job-facts",
        status="failed",
        step_name="script",
        message="text publish audit failed: unsupported_claim",
        artifacts={
            "fact_pack": {"status": "limited", "facts": [], "sources": []},
            "text_publish_audit": {"audit": {"passed": False, "reasons": ["unsupported_claim"]}},
            "script_generation_debug": {
                "phase": "audit_failed",
                "script_provider": "deepseek",
                "fallback_reason": "Error code: 429 - insufficient_quota",
            },
        },
    )

    assert diagnosis["code"] == "script_audit_without_verified_facts"
    assert diagnosis["title"] == "Roteiro sem base factual verificável"
    assert "fact pack" in diagnosis["cause"]
    assert "OpenAI retornou 429 insufficient_quota" in " ".join(diagnosis["evidence"])


def test_hub_failure_diagnosis_prefers_persisted_job_diagnosis() -> None:
    context = HubContext(SimpleNamespace(), SimpleNamespace(build_job_progress=lambda job: {}), SimpleNamespace())
    job = SimpleNamespace(
        status="failed",
        failure_reason="script: text publish audit failed: unsupported_claim",
        quality_summary={
            "failure_diagnosis": {
                "code": "script_audit_without_verified_facts",
                "title": "Roteiro sem base factual verificável",
                "cause": "Fact pack vazio.",
                "action": "Reprocesse roteiro.",
                "evidence": ["fact_pack=limited; facts=0; sources=0"],
            }
        },
    )

    diagnosis = context._failure_diagnosis(job)

    assert diagnosis["code"] == "script_audit_without_verified_facts"
    assert diagnosis["title"] == "Roteiro sem base factual verificável"
    assert diagnosis["evidence"] == [
        "script: text publish audit failed: unsupported_claim",
        "fact_pack=limited; facts=0; sources=0",
    ]


def test_artifact_retention_metadata_uses_publishable_ttl() -> None:
    settings = SimpleNamespace(
        artifact_ttl_hard_failure_hours=24,
        artifact_ttl_recoverable_hours=168,
        artifact_ttl_publishable_hours=504,
    )
    base_time = utcnow()
    job = SimpleNamespace(status="approved_for_publish", created_at=base_time, updated_at=base_time)

    metadata = retention_metadata(settings, job, None, now=base_time)

    assert metadata is not None
    assert metadata["classification"] == "publishable"
    assert metadata["expires_at"] == (base_time + timedelta(hours=504)).isoformat()


def test_artifact_retention_treats_visual_contract_failure_as_hard_failure() -> None:
    settings = SimpleNamespace(
        artifact_ttl_hard_failure_hours=24,
        artifact_ttl_recoverable_hours=168,
        artifact_ttl_publishable_hours=504,
    )
    base_time = utcnow()
    job = SimpleNamespace(status="visual_contract_quality_failed", created_at=base_time, updated_at=base_time)

    metadata = retention_metadata(settings, job, None, now=base_time)

    assert metadata is not None
    assert metadata["classification"] == "hard_failure"
    assert metadata["expires_at"] == (base_time + timedelta(hours=24)).isoformat()


def test_channel_publication_payload_uses_local_schedule_fields() -> None:
    scheduled_for_utc = utcnow().replace(hour=15, minute=30, second=0, microsecond=0)
    publication = SimpleNamespace(
        publication_id="pub-1",
        job_id="job-1",
        channel="tiktok",
        status="scheduled",
        source="youtube_schedule",
        scheduled_for_utc=scheduled_for_utc,
        timezone="America/Sao_Paulo",
        privacy_level="PUBLIC_TO_EVERYONE",
        external_id=None,
        external_url=None,
        published_at=None,
        attempt_count=0,
        last_attempt_at=None,
        last_error=None,
        channel_metadata={},
        content_hash="",
    )

    refresh_channel_publication_hash(publication)
    payload = channel_publication_payload(publication, schema_version="1.0.0")

    assert publication.content_hash
    assert payload["schema_version"] == "1.0.0"
    assert payload["scheduled_for_utc"] == scheduled_for_utc.isoformat()
    assert payload["local_time"] == scheduled_for_utc.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")


def test_tiktok_caption_limits_hashtags_and_adds_missing_hash_prefix() -> None:
    caption = tiktok_caption({"title": "Titulo", "hashtags": ["shorts", "#curiosidades", "a", "b", "c", "d", "e", "f", "g"]})

    assert caption == "Titulo #shorts #curiosidades #a #b #c #d #e #f"


def test_hub_review_form_payload_merges_reason_and_confirmation_codes() -> None:
    payload = build_review_action_payload(
        reviewer_identity="reviewer",
        action="approve",
        reason_codes=["manual_a, manual_b", "manual_a"],
        confirmation_codes=["visual_review_confirmed", "manual_b"],
        rights_confirmed=True,
        metadata_confirmed=True,
    )

    assert payload.action == "approve"
    assert payload.reason_codes == [
        "manual_a",
        "manual_b",
        "visual_review_confirmed",
        "rights_confirmed",
        "metadata_confirmed",
    ]


def test_hub_performance_form_payload_parses_optional_numeric_fields() -> None:
    payload = build_performance_metric_payload(
        source="manual",
        retention_percent="82.5",
        viewed_vs_swiped_away_percent="",
        rewatch_rate=None,
        likes="10",
        shares="2",
        comments="0",
        rpm_usd="1.25",
        monetization_status="limited",
        notes="ok",
    )

    assert payload.retention_percent == 82.5
    assert payload.viewed_vs_swiped_away_percent is None
    assert payload.rewatch_rate is None
    assert payload.likes == 10
    assert payload.rpm_usd == 1.25


def test_hub_job_request_builds_manual_title_payload() -> None:
    result = build_hub_job_request(
        seed_theme="Por que polvos parecem alienigenas dos oceanos?",
        input_mode="title",
        niche_id="curiosidades",
        language="pt-BR",
        target_duration_sec=35,
        tone="mito_vs_realidade",
        cta_style="none",
        notes="nota editorial",
        requested_angle="comparacao inesperada",
        custom_angle="inteligencia biologica impossivel",
        ready_script_text=None,
        ready_script_fact_check_confirmed=False,
        default_niche_id="curiosidades",
        retention_optimized_duration_sec=50,
        viral_prompt_template="Use curiosidade forte.",
        trend_seed_resolver=lambda _niche: (_ for _ in ()).throw(AssertionError("manual title must not resolve trends")),
    )

    assert result.trend_report is None
    assert result.payload.job_origin == "manual_title"
    assert result.payload.creation_via == "hub"
    assert result.payload.requested_angle == "inteligencia biologica impossivel"
    assert "input_mode=title" in str(result.payload.notes)


def test_hub_job_request_empty_title_uses_automatic_topic_notes_mode() -> None:
    result = build_hub_job_request(
        seed_theme="",
        input_mode="title",
        niche_id="curiosidades",
        language="pt-BR",
        target_duration_sec=50,
        tone="intrigante_direto",
        cta_style="none",
        notes=None,
        requested_angle=None,
        custom_angle=None,
        ready_script_text=None,
        ready_script_fact_check_confirmed=False,
        default_niche_id="curiosidades",
        retention_optimized_duration_sec=50,
        viral_prompt_template="Use curiosidade forte.",
        trend_seed_resolver=lambda _niche: HubTrendSeed(
            seed_theme="Por que flamingos estao em alta?",
            requested_angle="Transformar tendencia em curiosidade.",
            notes="trend_research=real_source",
            report={"trend_research": "real_source"},
        ),
    )

    assert result.payload.job_origin == "automatic_topic"
    assert result.payload.requested_angle == "Transformar tendencia em curiosidade."
    assert result.trend_report == {"trend_research": "real_source"}
    assert "input_mode=theme" in str(result.payload.notes)
    assert "input_mode=title" not in str(result.payload.notes)


def test_topic_scout_prefers_everyday_curiosity_over_sciencey_trend() -> None:
    class FakeTrendResearcher:
        def find_topic(self, niche_id: str):
            return TrendCandidate(
                topic="Por que buraco negro virou assunto agora?",
                requested_angle="ciência espacial",
                source="google_trends_br",
                source_url="https://trends.google.com/trending/rss?geo=BR",
                score=9999,
                raw_title="buraco negro",
                familiarity_score=0.35,
                source_title="buraco negro",
            )

    result = TopicScout(FakeTrendResearcher()).find_topic("curiosidades", recent_topics=[])

    assert result is not None
    assert result.candidate.source == "everyday_curiosity_pool"
    assert "buraco negro" not in result.candidate.topic.lower()
    assert result.candidate.hook_seed
    assert result.candidate.visual_seed


def test_topic_scout_avoids_recent_repetition() -> None:
    result = TopicScout(rng=__import__("random").Random(1)).find_topic(
        "curiosidades",
        recent_topics=["Por que o pão fica duro e a bolacha fica mole?"],
    )

    assert result is not None
    assert result.rejected_recent_count >= 1
    assert result.candidate.topic != "Por que o pão fica duro e a bolacha fica mole?"


def test_hub_prompt_loads_default_for_invalid_payload_and_saves_sanitized_template(tmp_path) -> None:
    prompt_path = tmp_path / "hub_settings.json"
    prompt_path.write_text("[]", encoding="utf-8")

    assert load_viral_prompt_template(prompt_path) == DEFAULT_VIRAL_PROMPT_TEMPLATE

    save_viral_prompt_template(prompt_path, "  Prompt customizado  ")

    assert load_viral_prompt_template(prompt_path) == "Prompt customizado"


def test_quality_audit_accepts_ready_for_publish_package_status(tmp_path) -> None:
    (tmp_path / "monetization_report.json").write_text(
        '{"passed": true, "final_status": "ready_for_upload", "hard_blockers": [], "manual_required": []}',
        encoding="utf-8",
    )
    (tmp_path / "publish_package.json").write_text('{"status": "ready_for_publish"}', encoding="utf-8")

    score = score_publish(tmp_path)

    assert score.score == 9.7
    assert "publish_package status=ready_for_publish" in score.evidence
    assert not any("publish_package status=ready_for_publish" in gap for gap in score.gaps)


def test_quality_audit_accepts_human_confirmed_visual_review_for_prompt_heuristic(tmp_path) -> None:
    (tmp_path / "asset_visual_gate.json").write_text(
        """
        {
          "metrics": {
            "asset_visual_gate_pass": true,
            "checked": true,
            "scenes": [{"total_score": 0.91}]
          },
          "selected_assets": [{"provider": "minimax", "verification_mode": "prompt_heuristic"}]
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "human_review.json").write_text(
        '{"action": "approve", "reason_codes": ["visual_review_confirmed"]}',
        encoding="utf-8",
    )

    score = score_image_semantics(tmp_path)

    assert score.score == 9.4
    assert "visual review confirmed by human review" in score.evidence
    assert "image semantics used prompt heuristic instead of real vision" not in score.gaps


def test_quality_audit_topic_accepts_provider_metric_aliases(tmp_path) -> None:
    (tmp_path / "topic_plan.json").write_text(
        """
        {
          "quality_metrics": {
            "loop_strength": 9,
            "payoff_late": 10,
            "replay_potential": 8,
            "verifiable_promise": 10,
            "retencao_maxima": true,
            "topic_uniqueness_pass": true,
            "fallback_used": true
          }
        }
        """,
        encoding="utf-8",
    )

    score = score_topic(tmp_path)

    assert score.score == 10.0
    assert "5/5 topic quality fields passed" in score.evidence
    assert "topic provider fallback used" in score.gaps


def test_quality_audit_topic_does_not_infer_missing_editorial_metrics(tmp_path) -> None:
    (tmp_path / "topic_plan.json").write_text(
        """
        {
          "canonical_topic": "Sangue azul do caranguejo-ferradura",
          "quality_metrics": {
            "topic_uniqueness_pass": true,
            "fallback_used": true
          }
        }
        """,
        encoding="utf-8",
    )

    score = score_topic(tmp_path)

    assert score.score == 6.3
    assert "0/5 topic quality fields passed" in score.evidence
    assert "topic quality metrics incomplete: 0/5" in score.gaps
    assert "topic provider fallback used" in score.gaps


def test_quality_audit_script_reports_gate_warnings_as_gaps(tmp_path) -> None:
    (tmp_path / "script.json").write_text(
        """
        {
          "qa_metrics": {
            "hook_score": 0.9,
            "clarity_score": 0.9,
            "information_density_score": 0.85,
            "repetition_score": 0.1,
            "ending_strength_score": 0.88,
            "script_quality_gate_pass": true,
            "script_quality_gate_warnings": ["body_beat_count_invalid", "weak_loop_closure"],
            "fact_pack_consistency_pass": true,
            "claim_trace": {"missing_risky_claim_trace": false}
          }
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "text_publish_audit.json").write_text('{"passed": true}', encoding="utf-8")

    score = score_script(tmp_path)

    assert score.score == 9.1
    assert "script quality warning: body_beat_count_invalid" in score.gaps
    assert "script quality warning: weak_loop_closure" in score.gaps


def test_publication_ops_persists_human_review_artifact() -> None:
    storage = _StorageSpy()
    owner = SimpleNamespace(
        settings=SimpleNamespace(schema_version="1.0.0"),
        storage=storage,
        _serialize_for_json=lambda payload: payload,
    )
    ops = PublicationOperations(owner)

    ops._persist_human_review_artifact(
        "job-review-artifact",
        {
            "reviewer_identity": "test-reviewer",
            "reason_codes": ["visual_review_confirmed"],
            "notes": "visual ok",
        },
        action="approve",
        review_id="review-1",
    )

    assert storage.persisted[0][1] == "human_review.json"
    payload = storage.persisted[0][2]
    assert payload["action"] == "approve"
    assert payload["review_id"] == "review-1"
    assert payload["reason_codes"] == ["visual_review_confirmed"]


def test_file_sha256_matches_stable_hash_without_loading_callers_file() -> None:
    path = Path("data-test") / "file-hash-test.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"abc123" * 1024
    path.write_bytes(payload)

    assert file_sha256(path) == stable_hash(payload)


def test_storage_metadata_hashes_persisted_text_without_reading_whole_file(monkeypatch, tmp_path) -> None:
    storage = StorageManager()
    storage.settings = SimpleNamespace(artifacts_dir=tmp_path)

    def fail_read_bytes(self):
        raise AssertionError("StorageManager metadata must not call Path.read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    json_artifact = storage.persist_json("job-1", "report.json", {"status": "ok"})
    text_artifact = storage.persist_text("job-1", "notes.txt", "linha 1\nlinha 2")

    assert json_artifact.content_hash == file_sha256(tmp_path / "job-1" / "report.json")
    assert json_artifact.size_bytes == (tmp_path / "job-1" / "report.json").stat().st_size
    assert text_artifact.content_hash == file_sha256(tmp_path / "job-1" / "notes.txt")
    assert text_artifact.size_bytes == (tmp_path / "job-1" / "notes.txt").stat().st_size
