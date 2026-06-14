from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.llm_tournament import compare_llm_tournament_decision_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two LLM tournament decision reports.")
    parser.add_argument("baseline_report", type=Path, help="Path to baseline decision_report.json.")
    parser.add_argument("candidate_report", type=Path, help="Path to candidate decision_report.json.")
    parser.add_argument("--output-dir", type=Path, help="Directory for decision_report_comparison.json and .md.")
    args = parser.parse_args()

    comparison = compare_llm_tournament_decision_reports(
        baseline_report_path=args.baseline_report,
        candidate_report_path=args.candidate_report,
        output_dir=args.output_dir,
    )
    changed_stages = [
        stage
        for stage, payload in (comparison.get("stage_changes") or {}).items()
        if isinstance(payload, dict) and payload.get("changed")
    ]
    print(
        json.dumps(
            {
                "comparison_json": comparison["output_paths"]["json"],
                "comparison_markdown": comparison["output_paths"]["markdown"],
                "changed_stages": changed_stages,
                "scale_route_changed": comparison["route_changes"]["scale_route"]["changed"],
                "premium_route_changed": comparison["route_changes"]["premium_route"]["changed"],
                "best_single_model_changed": comparison["best_single_model_change"]["changed"],
                "risk_changes": comparison["risk_changes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
