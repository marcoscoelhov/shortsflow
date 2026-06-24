from __future__ import annotations

from app.quality.llm_judge import (
    LlmJudgeResult,
    LlmQualityJudge,
    build_editorial_judge_payload,
)


def test_llm_judge_overrides_soft_editorial_reasons() -> None:
    judge = LlmQualityJudge(
        enabled=True,
        timeout_sec=30.0,
        gray_zone_low=0.72,
        gray_zone_high=0.82,
        judge_callable=lambda gate, payload: {
            "passed": True,
            "confidence": 0.91,
            "reasons": [],
            "scores": {"viral_intensity": 0.9},
            "provider": "mock",
        },
    )
    local_reasons = ["weak_ending"]
    result = judge.judge_editorial(build_editorial_judge_payload(script={"title": "x", "hook": "y"}, local_reasons=local_reasons, gate_name="test"))
    assert judge.should_override(local_passed=False, local_reasons=local_reasons, judge=result)


def test_llm_judge_does_not_override_hard_reasons() -> None:
    judge = LlmQualityJudge(
        enabled=True,
        timeout_sec=30.0,
        gray_zone_low=0.72,
        gray_zone_high=0.82,
        judge_callable=lambda gate, payload: {"passed": True, "confidence": 0.95, "reasons": []},
    )
    assert not judge.can_override_local_failure(["missing_full_narration"])
    assert not judge.should_override(
        local_passed=False,
        local_reasons=["missing_full_narration"],
        judge=LlmJudgeResult(True, confidence=0.95),
    )


def test_growth_gray_zone_detection() -> None:
    judge = LlmQualityJudge(enabled=True, timeout_sec=30.0, gray_zone_low=0.72, gray_zone_high=0.82, judge_callable=None)
    assert judge.in_growth_gray_zone(0.75)
    assert not judge.in_growth_gray_zone(0.85)


def test_disabled_judge_skips_override_consideration() -> None:
    judge = LlmQualityJudge(enabled=False, timeout_sec=30.0, gray_zone_low=0.72, gray_zone_high=0.82, judge_callable=lambda *_: {"passed": True, "confidence": 0.95})
    assert not judge.may_consider_override(["weak_ending"])