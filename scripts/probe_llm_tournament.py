from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.llm_tournament import run_llm_tournament_probe, write_llm_tournament_probe_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe LLM tournament candidates with a minimal JSON request.")
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/llm/candidates.v1.json"))
    parser.add_argument("--candidate", action="append", default=[], help="Candidate id to probe. Repeat for many.")
    parser.add_argument("--include-disabled", action="store_true", help="Probe disabled candidates too.")
    parser.add_argument("--dry-run", action="store_true", help="Only report configured candidates. Does not call providers.")
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, default=Path("data/llm_tournament"))
    args = parser.parse_args()

    report = run_llm_tournament_probe(
        manifest_path=args.manifest,
        candidate_ids=set(args.candidate) if args.candidate else None,
        include_disabled=args.include_disabled,
        dry_run=args.dry_run,
        timeout_sec=args.timeout_sec,
    )
    report_path = write_llm_tournament_probe_report(report, args.output_dir)
    print(json.dumps({"report_path": str(report_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 1 if report["summary"].get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
