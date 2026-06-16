from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.llm_tournament import (  # noqa: E402
    judge_existing_llm_tournament_script_run,
    plan_llm_tournament_textual_round,
    run_llm_tournament_script_stage,
    run_llm_tournament_textual_round,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the editorial LLM tournament.")
    parser.add_argument("--mode", choices=["quick", "full", "finalists"], default="quick")
    parser.add_argument("--benchmark", type=Path, default=Path("benchmarks/editorial/benchmark.v1.json"))
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/llm/candidates.v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/llm_tournament/runs"))
    parser.add_argument("--textual-round", action="store_true", help="Run triage plus full script, repair and audit stages.")
    parser.add_argument("--triage-only", action="store_true", help="Run only textual triage, without full rounds or decision report.")
    parser.add_argument("--triage-mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--full-mode", choices=["quick", "full"], default="full")
    parser.add_argument("--plan-only", action="store_true", help="Print the textual-round preflight plan without calling providers.")
    parser.add_argument("--judge-existing-results", type=Path, help="Judge an existing script-stage results.json without regenerating scripts.")
    parser.add_argument("--candidate", action="append", default=[], help="Candidate id to include. Repeat for many.")
    parser.add_argument("--judge-candidate", default="openai-gpt-5.5-medium")
    parser.add_argument("--judge-mode", choices=["none", "all", "top-n"], default="none")
    parser.add_argument("--judge-top-n", type=int, default=5)
    parser.add_argument("--max-failures-per-candidate", type=int, default=2)
    parser.add_argument("--min-triage-pass-rate", type=float, default=0.67)
    parser.add_argument("--finalist-top-n", type=int, default=3)
    parser.add_argument("--price-table", type=Path, help="Optional versioned model price table JSON for decision reports.")
    parser.add_argument("--timeout-sec", type=float, default=35.0)
    parser.add_argument("--parallelism", type=int, default=24)
    args = parser.parse_args()

    if args.plan_only and not args.textual_round:
        parser.error("--plan-only requires --textual-round")

    if args.textual_round and args.plan_only:
        plan = plan_llm_tournament_textual_round(
            benchmark_path=args.benchmark,
            manifest_path=args.manifest,
            candidate_ids=set(args.candidate) if args.candidate else None,
            triage_mode=args.triage_mode,
            full_mode=args.full_mode,
            max_failures_per_candidate=args.max_failures_per_candidate,
            min_triage_pass_rate=args.min_triage_pass_rate,
            finalist_top_n=args.finalist_top_n,
            triage_only=args.triage_only,
            timeout_sec=args.timeout_sec,
            parallelism=args.parallelism,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if args.textual_round:
        report = run_llm_tournament_textual_round(
            benchmark_path=args.benchmark,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            candidate_ids=set(args.candidate) if args.candidate else None,
            triage_mode=args.triage_mode,
            full_mode=args.full_mode,
            max_failures_per_candidate=args.max_failures_per_candidate,
            min_triage_pass_rate=args.min_triage_pass_rate,
            finalist_top_n=args.finalist_top_n,
            triage_only=args.triage_only,
            timeout_sec=args.timeout_sec,
            parallelism=args.parallelism,
            price_table_path=args.price_table,
            emit_progress=True,
        )
        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "run_dir": report["run_dir"],
                    "stage": report["stage"],
                    "survivors_by_stage": report["survivors_by_stage"],
                    "committee_packet_path": str(Path(report["run_dir"]) / "committee_packet.json") if report.get("decision_report") else None,
                    "decision_report_json": report["decision_report"]["output_paths"]["json"] if report.get("decision_report") else None,
                    "decision_report_markdown": report["decision_report"]["output_paths"]["markdown"] if report.get("decision_report") else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.judge_existing_results:
        if args.judge_mode == "none":
            parser.error("--judge-existing-results requires --judge-mode all or --judge-mode top-n")
        report = judge_existing_llm_tournament_script_run(
            results_path=args.judge_existing_results,
            benchmark_path=args.benchmark,
            manifest_path=args.manifest,
            judge_candidate_id=args.judge_candidate,
            judge_mode=args.judge_mode,
            judge_top_n=args.judge_top_n,
            timeout_sec=args.timeout_sec,
            emit_progress=True,
        )
    else:
        report = run_llm_tournament_script_stage(
            mode=args.mode,
            benchmark_path=args.benchmark,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            candidate_ids=set(args.candidate) if args.candidate else None,
            judge_candidate_id=args.judge_candidate,
            judge_mode=args.judge_mode,
            judge_top_n=args.judge_top_n,
            max_failures_per_candidate=args.max_failures_per_candidate,
            timeout_sec=args.timeout_sec,
            parallelism=args.parallelism,
            emit_progress=True,
        )
    ranking = report["ranking"]
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "run_dir": report["run_dir"],
                "mode": report["mode"],
                "stage": report["stage"],
                "case_count": report["case_count"],
                "candidate_count": report["candidate_count"],
                "recommended_scale": ranking["recommended_scale_routes"][:3],
                "recommended_premium": ranking["recommended_premium_routes"][:3],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
