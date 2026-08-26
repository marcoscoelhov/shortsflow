from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.editorial_lanes import editorial_lane_for_niche
from app.microdrama_pilot import build_microdrama_pilot_plan, start_microdrama_pilot
from app.remote_runtime import RemoteRuntimeClient, current_revision, resume_deployed_revision
from app.runtime_execution import assert_real_execution_location
from app.schemas import SUPPORTED_NICHES


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="shortsflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("automation-run", help="Executa um ciclo diario de automacao")
    run_parser.add_argument("--force", action="store_true", help="Reabre o ciclo da data local atual")

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

    import_parser = subparsers.add_parser("import-ready-scripts", help="Importa lote de roteiros prontos")
    import_parser.add_argument("path", type=Path, help="Arquivo txt/md com roteiros rotulados")

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

    for command, help_text in (
        ("job", "Cria um job real na producao remota"),
        ("validate", "Valida a revisao implantada no staging com um job real"),
    ):
        remote_parser = subparsers.add_parser(command, help=help_text)
        remote_parser.add_argument("--theme", required=True, help="Tema do video")
        remote_parser.add_argument("--duration", type=int, default=None, choices=range(35, 151))
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
        lane = editorial_lane_for_niche(args.niche)
        target_duration_sec = args.duration if args.duration is not None else lane.default_duration_sec
        if not lane.minimum_duration_sec <= target_duration_sec <= lane.maximum_duration_sec:
            parser.error(
                f"--duration for {lane.niche_id} must be between "
                f"{lane.minimum_duration_sec} and {lane.maximum_duration_sec} seconds"
            )
        is_validation = args.command == "validate"
        base_url = settings.remote_staging_url if is_validation else settings.remote_production_url
        client = RemoteRuntimeClient(base_url, auth_token=getattr(settings, "hub_auth_token", None))
        if is_validation:
            client.require_revision(current_revision(), environment="staging")
        submitted = client.submit_job(
            theme=args.theme,
            target_duration_sec=target_duration_sec,
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
            client=RemoteRuntimeClient(base_url, auth_token=getattr(settings, "hub_auth_token", None)),
            repo_path=args.repo.resolve(),
        )
        print(json.dumps({"branch": branch, "repo": str(args.repo.resolve()), "status": "ready"}, indent=2))
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

    init_db()
    apply_operational_settings(orchestrator.settings)
    service = AutomationService(orchestrator)

    if args.command == "microdrama-pilot-start":
        result = start_microdrama_pilot(orchestrator, seed=args.seed)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "automation-run":
        result = service.run_daily_cycle(force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "failed":
            sys.exit(1)
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

    if args.command == "import-ready-scripts":
        raw_text = args.path.read_text(encoding="utf-8")
        result = service.import_ready_script_batch(raw_text, source=str(args.path))
        print(json.dumps({"imported": result.imported, "errors": result.errors}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
