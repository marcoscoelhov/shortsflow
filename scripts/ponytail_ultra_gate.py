#!/usr/bin/env python3
"""Static Ponytail Ultra gate for ShortsFlow.

The score is intentionally about operational simplicity, not beauty: fewer Hub
branches, source-isolated automation, a cheap fast lane, and no runtime DB junk
in the repo root. Run the full pytest suite separately before commit/push.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    weight: float
    passed: bool
    evidence: str


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    main_py = _text("app/main.py")
    planning_py = _text("app/automation_planning.py")
    readme = _text("README.md")
    runbook = _text("docs/runbook-inicializacao.md")
    checks = [
        Check(
            "hub_main_under_900_lines",
            1.2,
            len(main_py.splitlines()) <= 900,
            f"app/main.py has {len(main_py.splitlines())} lines",
        ),
        Check(
            "llm_tournament_out_of_main",
            1.4,
            "def llm_tournament_page" not in main_py
            and "def llm_tournament_file" not in main_py
            and (ROOT / "app/routes/llm_tournament.py").exists(),
            "LLM tournament routes live in app/routes/llm_tournament.py",
        ),
        Check(
            "fast_lane_formalized",
            1.4,
            (ROOT / "scripts/shortsflow_fast_lane.py").exists()
            and "scripts/shortsflow_fast_lane.py" in readme
            and "scripts/shortsflow_fast_lane.py" in runbook,
            "fast lane script documented in README and runbook",
        ),
        Check(
            "automatic_topic_no_lane_fallback",
            1.5,
            "return None" in planning_py
            and "fallback_source=automation_fallback_source_for_time" not in planning_py
            and "return [self.source]" in planning_py,
            "publish plans carry only the primary lane source; fallback helper returns None",
        ),
        Check(
            "automatic_topic_contract_tests_exist",
            1.3,
            (ROOT / "tests/test_topic_mode.py").exists()
            and (ROOT / "tests/test_test_harness_isolation.py").exists()
            and "structured_viral_contract_preserves_topic_niche_quality_metrics" in _text("tests/test_pipeline_script.py"),
            "topic/harness/structured contract tests are present",
        ),
        Check(
            "runtime_db_not_in_repo_root",
            0.8,
            not (ROOT / "shortsflow.db").exists(),
            "shortsflow.db absent from repo root",
        ),
        Check(
            "operator_hub_copy_is_human_review_safe",
            1.0,
            "revisão final no YouTube Studio" in _text("app/templates/job_detail.html"),
            "job detail approval copy preserves final YouTube Studio review",
        ),
        Check(
            "ponytail_docs_not_phantom",
            1.4,
            "Lane rapida Ponytail/operacional" in readme and "Lane rapida Ponytail/operacional" in runbook,
            "Ponytail operational docs point to executable code, not TODO cards",
        ),
    ]
    score = round(sum(check.weight for check in checks if check.passed), 1)
    total = round(sum(check.weight for check in checks), 1)
    print(f"Ponytail Ultra score: {score:.1f}/{total:.1f}")
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"{marker:4} {check.name} ({check.weight:.1f}) — {check.evidence}")
    if score < 9.5:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
