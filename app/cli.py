from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.microdrama_pilot import build_microdrama_pilot_plan, start_microdrama_pilot
from app.remote_runtime import RemoteRuntimeClient, current_revision, resume_deployed_revision
from app.runtime_execution import assert_real_execution_location
from app.schemas import SUPPORTED_NICHES
from app.survival_experiment import build_survival_cohort_plan
from app.traction_pilot import start_traction_pilot


def main(argv: list[str] | None = None) -> None:
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


    airtable_parser = subparsers.add_parser("airtable-ready-scripts-sync", help="Sincroniza roteiros prontos futuros do Airtable")
    airtable_parser.add_argument("--dry-run", action="store_true", help="Lista elegíveis sem importar ou marcar no Airtable")
    airtable_parser.add_argument("--limit", type=int, default=None, help="Limite de registros elegíveis")

    survival_parser = subparsers.add_parser(
        "survival-cohort-plan",
        help="Gera plano JSON seco de 6 cenários do experimento survival_decisions",
    )
    survival_parser.add_argument("--seed", type=int, required=True, help="Seed inteira para seleção determinística")

    microdrama_plan_parser = subparsers.add_parser(
        "microdrama-pilot-plan",
        help="Imprime o plano JSON seco do piloto de microdramas",
    )
    microdrama_plan_parser.add_argument("--seed", type=int, required=True, help="Seed inteira para ordem determinística")

    microdrama_start_parser = subparsers.add_parser(
        "microdrama-pilot-start",
        help="Persiste o piloto de microdramas e cria três canários sem publicar",
    )
    microdrama_start_parser.add_argument("--seed", type=int, required=True, help="Seed inteira para ordem determinística")

    pilot_parser = subparsers.add_parser(
        "pilot-10k-start",
        help="Persiste o piloto A/B/C e cria os três canários sem publicar",
    )
    pilot_parser.add_argument("--seed", type=int, required=True, help="Seed inteira para ordem determinística")
    pilot_parser.add_argument("--process", action="store_true", help="Gera e renderiza os três canários")

    for command, help_text in (
        ("job", "Cria um job real na producao remota"),
        ("validate", "Valida a revisao implantada no staging com um job real"),
    ):
        remote_parser = subparsers.add_parser(command, help=help_text)
        remote_parser.add_argument("--theme", required=True, help="Tema do video")
        remote_parser.add_argument("--duration", type=int, default=45, choices=range(35, 151))
        remote_parser.add_argument("--niche", choices=sorted(SUPPORTED_NICHES), default="curiosidades")
        remote_parser.add_argument("--angle", default=None, help="Angulo editorial solicitado")
        remote_parser.add_argument("--wait", action="store_true", help="Aguarda o estado terminal do job")
        remote_parser.add_argument("--request-id", default=None, help="Reutilize após timeout para evitar job duplicado")

    resume_parser = subparsers.add_parser("resume", help="Retoma o SHA implantado em checkout limpo")
    resume_parser.add_argument("environment", choices=["staging", "production"], help="Runtime remoto")
    resume_parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Checkout Git local")

    args = parser.parse_args(argv)

    if args.command in {"job", "validate"}:
        settings = get_settings()
        is_validation = args.command == "validate"
        base_url = settings.remote_staging_url if is_validation else settings.remote_production_url
        client = RemoteRuntimeClient(base_url)
        if is_validation:
            client.require_revision(current_revision(), environment="staging")
        submitted = client.submit_job(
            theme=args.theme,
            target_duration_sec=args.duration,
            niche_id=args.niche,
            requested_angle=args.angle,
            request_id=args.request_id,
        )
        payload: dict[str, object] = {
            "environment": "staging" if is_validation else "production",
            "job_id": submitted.job_id,
            "job_url": submitted.job_url,
            "request_id": submitted.request_id,
        }
        if args.wait:
            payload["result"] = client.wait_for_job(submitted.job_id)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "resume":
        settings = get_settings()
        base_url = settings.remote_staging_url if args.environment == "staging" else settings.remote_production_url
        branch = resume_deployed_revision(
            args.environment,
            client=RemoteRuntimeClient(base_url),
            repo_path=args.repo.resolve(),
        )
        print(json.dumps({"branch": branch, "repo": str(args.repo.resolve()), "status": "ready"}, indent=2))
        return
    if args.command == "survival-cohort-plan":
        print(json.dumps(build_survival_cohort_plan(seed=args.seed), ensure_ascii=False, indent=2))
        return
    if args.command == "microdrama-pilot-plan":
        print(json.dumps(build_microdrama_pilot_plan(seed=args.seed), ensure_ascii=False, indent=2))
        return

    runtime_settings = get_settings()
    assert_real_execution_location(
        environment=runtime_settings.runtime_environment,
        use_mock_providers=runtime_settings.use_mock_providers,
    )

    from app.automation import AutomationService
    from app.backlog_recovery import BacklogRecoveryService
    from app.db import init_db
    from app.operational_settings import apply_operational_settings
    from app.orchestrator import orchestrator
    from app.production_readiness import ProductionReadinessService
    from app.watchdog import AutomationWatchdog

    init_db()
    apply_operational_settings(orchestrator.settings)
    service = AutomationService(orchestrator)

    if args.command == "microdrama-pilot-start":
        result = start_microdrama_pilot(orchestrator, seed=args.seed)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "pilot-10k-start":
        result = start_traction_pilot(orchestrator, seed=args.seed, canary_count=3)
        processed = 0
        if args.process:
            if runtime_settings.use_mock_providers:
                parser.error("o piloto real não aceita mock providers")
            for canary in result["canaries"]:
                orchestrator.process_job(str(canary["job_id"]))
                processed += 1
        result["processed_job_count"] = processed
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

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
        result = service.import_ready_script_batch(raw_text, source=str(args.path))
        print(json.dumps({"imported": result.imported, "errors": result.errors}, ensure_ascii=False, indent=2))
        return

    if args.command == "airtable-ready-scripts-sync":
        result = service.sync_airtable_ready_scripts(dry_run=args.dry_run, limit=args.limit)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.errors:
            sys.exit(1)
        return


if __name__ == "__main__":
    main()
