from types import SimpleNamespace

import pytest

from app.quality.premium_publish_gate import PREMIUM_PUBLISH_AUDIT_STAGES, PremiumPublishGate


def _complete_audit(score):
    return {
        "job_id": "complete-test-audit",
        "target_score": 9.4,
        "overall_min_score": score,
        "passed_target": score >= 9.4,
        "stages": [
            {
                "stage": stage,
                "score": score,
                "target_pass": score >= 9.4,
                "evidence": ["complete test audit"],
                "gaps": [] if score >= 9.4 else ["score below target"],
            }
            for stage in PREMIUM_PUBLISH_AUDIT_STAGES
        ],
    }


def _gate(tmp_path):
    return PremiumPublishGate(
        settings=SimpleNamespace(),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: tmp_path),
        audit_func=lambda _root: _complete_audit(6.5),
    )


def test_publish_score_is_diagnostic_not_a_gate(tmp_path):
    result = _gate(tmp_path).evaluate(SimpleNamespace(job_id="job-low-score"))

    assert result.passed is True
    assert "premium_publish_score_below_threshold" not in result.reasons


def test_visual_review_still_blocks_low_score_publish(tmp_path):
    result = _gate(tmp_path).evaluate(
        SimpleNamespace(job_id="job-visual-review"), visual_review_required=True
    )

    assert result.passed is False
    assert result.reasons == ["visual_review_required"]


def test_visual_review_confirmation_allows_low_score_publish(tmp_path):
    result = _gate(tmp_path).evaluate(
        SimpleNamespace(job_id="job-visual-reviewed"),
        confirmations={"visual_review_confirmed"},
        visual_review_required=True,
    )

    assert result.passed is True


def test_missing_premium_publish_artifacts_fail_closed(tmp_path):
    missing_job_dir = tmp_path / "missing-job"
    gate = PremiumPublishGate(
        settings=SimpleNamespace(),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: missing_job_dir),
    )

    result = gate.evaluate(SimpleNamespace(job_id="job-without-artifacts"))

    assert result.passed is False
    assert result.reasons == ["premium_publish_artifacts_missing"]


def test_empty_premium_publish_artifact_directory_fails_closed(tmp_path):
    gate = PremiumPublishGate(
        settings=SimpleNamespace(),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: tmp_path),
    )

    result = gate.evaluate(SimpleNamespace(job_id="job-with-empty-artifact-dir"))

    assert result.passed is False
    assert result.reasons == ["premium_publish_artifacts_missing"]


@pytest.mark.parametrize(
    "audit_payload",
    [
        {"stages": [{}]},
        {
            "target_score": 9.4,
            "overall_min_score": 6.5,
            "passed_target": False,
            "stages": [
                {
                    "stage": "script",
                    "score": 6.5,
                    "target_pass": False,
                    "evidence": [],
                    "gaps": [],
                }
            ],
        },
    ],
)
def test_malformed_or_partial_premium_publish_audit_fails_closed(tmp_path, audit_payload):
    gate = PremiumPublishGate(
        settings=SimpleNamespace(),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: tmp_path),
        audit_func=lambda _root: audit_payload,
    )

    result = gate.evaluate(SimpleNamespace(job_id="job-with-invalid-audit"))

    assert result.passed is False
    assert result.reasons == ["premium_publish_audit_failed"]


def test_premium_publish_audit_exception_fails_closed(tmp_path):
    def failing_audit(_root):
        raise RuntimeError("audit unavailable")

    gate = PremiumPublishGate(
        settings=SimpleNamespace(),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: tmp_path),
        audit_func=failing_audit,
    )

    result = gate.evaluate(SimpleNamespace(job_id="job-with-audit-error"))

    assert result.passed is False
    assert result.reasons == ["premium_publish_audit_failed"]
    assert result.audit["error"] == "audit unavailable"
