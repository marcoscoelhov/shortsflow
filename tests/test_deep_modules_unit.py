from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.hub_context import HubContext
from app.pipelines.script_audit import ScriptAuditDomain
from app.pipelines.script_metrics import normalize_script_metrics
from app.publication_ops import PublicationOperations
from app.utils import utcnow
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


def test_publication_ops_unit_retention_metadata_uses_publishable_ttl() -> None:
    settings = SimpleNamespace(
        artifact_ttl_hard_failure_hours=24,
        artifact_ttl_recoverable_hours=168,
        artifact_ttl_publishable_hours=504,
    )
    ops = PublicationOperations(SimpleNamespace(settings=settings))
    base_time = utcnow()
    job = SimpleNamespace(status="approved_for_publish", created_at=base_time, updated_at=base_time)

    metadata = ops._retention_metadata(job, None, now=base_time)

    assert metadata is not None
    assert metadata["classification"] == "publishable"
    assert metadata["expires_at"] == (base_time + timedelta(hours=504)).isoformat()


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
