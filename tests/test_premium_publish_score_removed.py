from types import SimpleNamespace

from app.quality.premium_publish_gate import PremiumPublishGate


def test_publish_score_is_diagnostic_not_a_gate(tmp_path):
    gate = PremiumPublishGate(
        settings=SimpleNamespace(premium_publish_min_score=9.4),
        storage=SimpleNamespace(job_dir=lambda *_args, **_kwargs: tmp_path),
        audit_func=lambda _root: {
            "overall_min_score": 6.5,
            "stages": [{"stage": "script", "score": 6.5, "gaps": ["score below target"]}],
        },
    )

    result = gate.evaluate(SimpleNamespace(job_id="job-low-score"))

    assert result.passed is True
    assert "premium_publish_score_below_threshold" not in result.reasons
