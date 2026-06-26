from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.automation import AutomationService
from app.backlog_recovery import BacklogRecoveryService
from app.competitive_scout import CompetitiveScout
from app.db import init_db
from app.operational_settings import apply_operational_settings
from app.orchestrator import orchestrator
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

    scout_parser = subparsers.add_parser("competitive-scout", help="Executa scout competitivo de Shorts por canal ou busca")
    scout_parser.add_argument("--niche-id", default="curiosidades", help="Nicho do scout competitivo")
    scout_parser.add_argument("--channel-id", action="append", default=None, help="Canal de referencia do YouTube; pode repetir")
    scout_parser.add_argument("--query", action="append", default=None, help="Busca textual no YouTube; pode repetir")
    scout_parser.add_argument("--max-results", type=int, default=None, help="Resultados por canal ou busca")

    scout_profiles_parser = subparsers.add_parser("competitive-scout-profiles", help="Sintetiza perfis de retencao de uma rodada de scout")
    scout_profiles_parser.add_argument("run_id", help="ID da rodada de scout")
    scout_profiles_parser.add_argument("--min-references", type=int, default=None, help="Referencias minimas por linha")
    scout_profiles_parser.add_argument("--conservative", action="store_true", help="Gera perfil menos agressivo")

    profile_approve_parser = subparsers.add_parser("retention-profile-approve", help="Aprova um perfil de retencao aprendido")
    profile_approve_parser.add_argument("profile_id", help="ID do perfil de retencao")

    profile_reject_parser = subparsers.add_parser("retention-profile-reject", help="Rejeita um perfil de retencao aprendido")
    profile_reject_parser.add_argument("profile_id", help="ID do perfil de retencao")

    experiment_parser = subparsers.add_parser("retention-experiment-start", help="Inicia experimento de retencao com perfil aprovado")
    experiment_parser.add_argument("profile_id", help="ID do perfil de retencao aprovado")
    experiment_parser.add_argument("--target-job-count", type=int, default=None, help="Quantidade alvo de Jobs no experimento")

    experiment_eval_parser = subparsers.add_parser("retention-experiment-evaluate", help="Avalia experimento de retencao com Analytics do canal")
    experiment_eval_parser.add_argument("experiment_id", help="ID do experimento")

    experiment_promote_parser = subparsers.add_parser("retention-experiment-promote", help="Promove perfil de retencao vencedor depois de success_strong")
    experiment_promote_parser.add_argument("experiment_id", help="ID do experimento com success_strong")

    scout_auto_parser = subparsers.add_parser("competitive-scout-auto-cycle", help="Roda o ciclo automatico do scout competitivo")
    scout_auto_parser.add_argument("--niche-id", default="curiosidades", help="Nicho do scout competitivo")

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
        if args.deliver:
            report = watchdog.deliver_alert(report)
        watchdog.persist_report(report)
        if args.emit_alert:
            print(watchdog.telegram_brief(report) if report.status == "alert" else "[SILENT]")
        else:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
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

    if args.command == "competitive-scout":
        result = CompetitiveScout(settings=orchestrator.settings).run(
            niche_id=args.niche_id,
            channel_ids=args.channel_id,
            queries=args.query,
            max_results_per_source=args.max_results,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "competitive-scout-profiles":
        result = CompetitiveScout(settings=orchestrator.settings).synthesize_profiles_from_run(
            args.run_id,
            min_references=args.min_references,
            aggressive=not args.conservative,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retention-profile-approve":
        result = CompetitiveScout(settings=orchestrator.settings).approve_profile(args.profile_id, action="approve")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retention-profile-reject":
        result = CompetitiveScout(settings=orchestrator.settings).approve_profile(args.profile_id, action="reject")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retention-experiment-start":
        result = CompetitiveScout(settings=orchestrator.settings).start_experiment(args.profile_id, target_job_count=args.target_job_count)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retention-experiment-evaluate":
        result = CompetitiveScout(settings=orchestrator.settings).evaluate_experiment(args.experiment_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retention-experiment-promote":
        result = CompetitiveScout(settings=orchestrator.settings).promote_experiment_winner(args.experiment_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "competitive-scout-auto-cycle":
        result = CompetitiveScout(settings=orchestrator.settings).run_automation_cycle(niche_id=args.niche_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "import-ready-scripts":
        raw_text = args.path.read_text(encoding="utf-8")
        result = service.import_ready_script_batch(raw_text, fact_check_confirmed=args.fact_check_confirmed, source=str(args.path))
        print(json.dumps({"imported": result.imported, "errors": result.errors}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
