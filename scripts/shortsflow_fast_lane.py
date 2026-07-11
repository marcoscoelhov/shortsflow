#!/usr/bin/env python3
"""Run the ShortsFlow operational fast lane.

This is the cheap confidence gate for operator-facing contracts: test harness
isolation, automatic_topic source/niche contracts, Hub action/auth/refresh
summaries, and the structured viral contract. It intentionally does not run the
heavy full pipeline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST_TESTS = [
    "tests/test_test_harness_isolation.py",
    "tests/test_topic_mode.py",
    "tests/test_astronomy_niche_contract.py",
    "tests/test_hub_publication.py::test_hub_auth_token_protects_pages_and_artifacts",
    "tests/test_hub_publication.py::test_jobs_route_serves_full_page_and_htmx_fragment",
    "tests/test_hub_publication.py::test_publication_dashboard_fragment_focuses_on_growth_analytics",
    "tests/test_hub_publication.py::test_automatic_topic_attempt_rejects_ready_script_origin_fallback",
    "tests/test_hub_publication.py::test_automatic_topic_payload_rejection_reason_codes",
    "tests/test_pipeline_script.py::test_automatic_topic_payload_uses_cosmos_focus",
    "tests/test_pipeline_script.py::test_structured_viral_contract_preserves_topic_niche_quality_metrics",
]


def main() -> int:
    python = ROOT / ".venv" / "bin" / "python"
    executable = str(python) if python.exists() else sys.executable
    command = [executable, "-m", "pytest", "-q", *FAST_TESTS]
    print("shortsflow fast lane:", " ".join(command), flush=True)
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
