from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.llm_tournament import build_llm_tournament_decision_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the LLM tournament decision report from a committee packet.")
    parser.add_argument("committee_packet", type=Path, help="Path to committee_packet.json.")
    parser.add_argument("--output-dir", type=Path, help="Directory for decision_report.json and decision_report.md.")
    parser.add_argument("--price-table", type=Path, help="Optional versioned model price table JSON.")
    args = parser.parse_args()

    report = build_llm_tournament_decision_report(
        committee_packet_path=args.committee_packet,
        output_dir=args.output_dir,
        price_table_path=args.price_table,
    )
    print(
        json.dumps(
            {
                "decision_report_json": report["output_paths"]["json"],
                "decision_report_markdown": report["output_paths"]["markdown"],
                "scale_route": report["scale_route"],
                "premium_route": report["premium_route"],
                "best_single_model": report["best_single_model"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
