from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.orchestrator import orchestrator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocess a Job de Video from a pipeline step.")
    parser.add_argument("job_id")
    parser.add_argument("--from-step", default="tts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        status = orchestrator.reprocess_job_from_step(args.job_id, args.from_step)
    except Exception as exc:  # noqa: BLE001
        payload = {"job_id": args.job_id, "from_step": args.from_step, "passed": False, "error": str(exc)}
        _emit(payload, as_json=args.json)
        return 1
    failed = status == "failed" or status == "cancelled" or status.endswith("_failed")
    payload = {"job_id": args.job_id, "from_step": args.from_step, "passed": not failed, "status": status}
    _emit(payload, as_json=args.json)
    return 1 if failed else 0


def _emit(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, value in payload.items():
        print(f"{key}= {value}")


if __name__ == "__main__":
    raise SystemExit(main())
