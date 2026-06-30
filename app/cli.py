from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.automation import AutomationService
from app.backlog_recovery import BacklogRecoveryService
from app.db import init_db
from app.operational_settings import apply_operational_settings
from app.orchestrator import orchestrator
from app.production_readiness import ProductionReadinessService
from app.watchdog import AutomationWatchdog


def main() -> None:
    parser = argparse.ArgumentParser(prog="shortsflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("automation-run", help="Executa um ciclo diario de automacao")
    run_parser.add_argument("--force", action="store_true", help="Reabre o ciclo da data local atual")

    watchdog_parser = subparsers.add_parser("automation-watchdog", help="Avalia saúde da automação e agenda")
    watchdog_parser.add_argument("--json", action="store_true", help="Imprime o relatório JSON completo")
    watchdog_parser.add_argument("--emit-alert", action="store_true", help="Imprime brief de alerta ou [SILENT]")
    watchdog_parser.add_argument("--deliver", action="store_true", help="Entrega alerta se configurado")
    watchdog_parser.add_argument("--recover", action="store_true", help="Executa backlog recovery reativo se o watchdog recomendar")

    readiness_parser = subparsers.add_parser("production-readiness", help="Avalia se o ShortsFlow está pronto para operar em produção")
    readiness_parser.add_argument("--json", action="store_true", help="Imprime JSON completo")

    backlog_scan_parser = subparsers.add_parser("backlog-recovery-scan", help="Inventaria backlog recuperável sem mutações")
    backlog_scan_parser.add_argument("--json", action="store_true", help="Imprime JSON completo")
    backlog_scan_parser.add_argument("--limit", type=int, default=50, help="Limite de jobs avaliados")

    backlog_run_parser = subparsers.add_parser("backlog-recovery-run", help="Executa recuperação segura de backlog")
    backlog_run_parser.add_argument("--mode", choices=["reactive", "weekly", "manual"], default="reactive")
    backlog_run_parser.add_argument("--dry-run", action="store_true", help="Classifica sem mutar estado")
    backlog_run_parser.add_argument("--job-id", default=None, help="Job específico para recuperação manual")
    backlog_run_parser.add_argument("--limit", type=int, default=50, help="Limite de jobs avaliados")
    backlog_run_parser.add_argument("--json", action="store_true", help="Imprime JSON completo")

    analytics_parser = subparsers.add_parser("analytics-sync-run", help="Executa a coleta diaria de performance do YouTube")
    analytics_parser.add_argument("--days", type=int, default=28, help="Janela de Analytics por job, entre 1 e 90 dias")
    analytics_parser.add_argument("--limit", type=int, default=None, help="Limite de jobs processados nesta execucao")

    growth_parser = subparsers.add_parser("growth-report", help="Gera relatorio consolidado de crescimento do canal")
    growth_parser.add_argument("--minimum-views", type=int, default=100, help="Views minimas para marcar um video como evidencia confiavel")

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
        watchdog = AutomationWatchdog(orchestrator.settings, orchestrator)
        watchdog_report = watchdog.evaluate()
        watchdog.persist_report(watchdog_report)
        if result.get("status") == "failed":
            sys.exit(1)
        return

    if args.command == "automation-watchdog":
        watchdog = AutomationWatchdog(orchestrator.settings, orchestrator)
        report = watchdog.evaluate()
        recovery_result = None
        if args.recover and watchdog.recovery_plan(report)["should_recover"]:
            recovery_result = BacklogRecoveryService(orchestrator.settings, orchestrator).run(mode="reactive")
            report = watchdog.evaluate()
        if args.deliver:
            report = watchdog.deliver_alert(report)
        watchdog.persist_report(report)
        if args.emit_alert:
            print(watchdog.telegram_brief(report) if report.status == "alert" else "[SILENT]")
        else:
            payload = report.to_dict()
            payload["recovery_plan"] = watchdog.recovery_plan(report)
            if recovery_result is not None:
                payload["recovery_result"] = recovery_result.to_dict()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "production-readiness":
        report = ProductionReadinessService(orchestrator.settings, orchestrator).evaluate()
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        if report.status == "not_ready":
            sys.exit(1)
        return

    if args.command == "backlog-recovery-scan":
        result = BacklogRecoveryService(orchestrator.settings, orchestrator).scan(limit=args.limit)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.command == "backlog-recovery-run":
        result = BacklogRecoveryService(orchestrator.settings, orchestrator).run(
            mode=args.mode,
            dry_run=args.dry_run,
            job_id=args.job_id,
            limit=args.limit,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.command == "analytics-sync-run":
        result = orchestrator.sync_due_youtube_analytics_snapshots(days=args.days, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "partial":
            sys.exit(1)
        return

    if args.command == "growth-report":
        result = orchestrator.build_channel_growth_report(minimum_views=args.minimum_views)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "import-ready-scripts":
        raw_text = args.path.read_text(encoding="utf-8")
        result = service.import_ready_script_batch(raw_text, fact_check_confirmed=args.fact_check_confirmed, source=str(args.path))
        print(json.dumps({"imported": result.imported, "errors": result.errors}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
