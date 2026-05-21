from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.automation import AutomationService
from app.db import init_db
from app.operational_settings import apply_operational_settings
from app.orchestrator import orchestrator


def main() -> None:
    parser = argparse.ArgumentParser(prog="yts-render")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("automation-run", help="Executa um ciclo diario de automacao")
    run_parser.add_argument("--force", action="store_true", help="Reabre o ciclo da data local atual")

    import_parser = subparsers.add_parser("import-ready-scripts", help="Importa lote de roteiros prontos")
    import_parser.add_argument("path", type=Path, help="Arquivo txt/md com roteiros rotulados")
    import_parser.add_argument("--fact-check-confirmed", action="store_true", help="Assume a confirmacao factual do lote")

    args = parser.parse_args()
    init_db()
    apply_operational_settings(orchestrator.settings)
    service = AutomationService(orchestrator)

    if args.command == "automation-run":
        result = service.run_daily_cycle(force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "failed":
            sys.exit(1)
        return

    if args.command == "import-ready-scripts":
        raw_text = args.path.read_text(encoding="utf-8")
        result = service.import_ready_script_batch(raw_text, fact_check_confirmed=args.fact_check_confirmed, source=str(args.path))
        print(json.dumps({"imported": result.imported, "errors": result.errors}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
