from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Semaphore
from typing import Any

from google import genai
from google.genai import types as genai_types
from openai import OpenAI

from app.editorial.retention import EDITORIAL_PROMPT_VERSION, build_retention_map, build_visual_opening_brief
from app.utils import sentence_split, word_tokens


DEFAULT_CANDIDATES_PATH = Path("benchmarks/llm/candidates.v1.json")
DEFAULT_EDITORIAL_BENCHMARK_PATH = Path("benchmarks/editorial/benchmark.v1.json")
DEFAULT_PROBE_OUTPUT_DIR = Path("data/llm_tournament")
DEFAULT_TOURNAMENT_RUNS_DIR = Path("data/llm_tournament/runs")
PROBE_PROMPT = (
    "Responda apenas JSON valido, sem markdown. "
    'Use exatamente este formato: {"ok": true, "model_role": "llm_tournament_probe", "language": "pt-BR"}.'
)
SCRIPT_REQUIRED_FIELDS = {
    "title",
    "hook",
    "body_beats",
    "ending",
    "cta",
    "full_narration",
    "estimated_duration_sec",
    "key_facts",
    "source_fact_ids",
    "claim_trace",
    "token_count",
    "language",
    "retention_map",
    "visual_opening",
    "qa_metrics",
    "prompt_version",
}
REPAIR_REQUIRED_FIELDS = {
    "repaired_script",
    "fixed_issue_slugs",
    "remaining_issue_slugs",
    "repair_notes",
}
AUDIT_REQUIRED_FIELDS = {
    "decision",
    "reason_slugs",
    "severity",
    "detected_issue_slugs",
}
TEXTUAL_TOURNAMENT_STAGES = ("script", "repair", "audit")
GENERIC_HOOK_OPENINGS = (
    "voce sabia",
    "você sabia",
    "ja imaginou",
    "já imaginou",
    "nesse video",
    "nesse vídeo",
)


@dataclass(frozen=True)
class LlmTournamentCandidate:
    candidate_id: str
    provider: str
    model: str
    api_key_env: str
    roles: tuple[str, ...]
    enabled: bool
    base_url: str | None = None
    provider_options: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(_env_value(self.api_key_env))


@dataclass(frozen=True)
class LlmTournamentProbeResult:
    candidate_id: str
    provider: str
    model: str
    enabled: bool
    configured: bool
    status: str
    latency_ms: int | None = None
    output_tokens: int | None = None
    input_tokens: int | None = None
    total_tokens: int | None = None
    json_valid: bool | None = None
    error_type: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "provider": self.provider,
            "model": self.model,
            "enabled": self.enabled,
            "configured": self.configured,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "json_valid": self.json_valid,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def _env_value(name: str, env_file: Path | str = ".env") -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    path = Path(env_file)
    if not path.exists():
        return None
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        raw_value = stripped[len(prefix) :].strip().strip('"').strip("'")
        return raw_value or None
    return None


def load_llm_tournament_candidates(path: Path | str = DEFAULT_CANDIDATES_PATH) -> list[LlmTournamentCandidate]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        raise ValueError("llm tournament candidates manifest must contain a candidates list")
    return [_candidate_from_payload(item) for item in candidates]


def run_llm_tournament_probe(
    *,
    manifest_path: Path | str = DEFAULT_CANDIDATES_PATH,
    candidate_ids: set[str] | None = None,
    include_disabled: bool = False,
    dry_run: bool = False,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    candidates = load_llm_tournament_candidates(manifest_path)
    if candidate_ids:
        candidates = [candidate for candidate in candidates if candidate.candidate_id in candidate_ids]
    results = [
        probe_llm_tournament_candidate(
            candidate,
            include_disabled=include_disabled,
            dry_run=dry_run,
            timeout_sec=timeout_sec,
        ).as_dict()
        for candidate in candidates
    ]
    summary = _probe_summary(results)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "timeout_sec": timeout_sec,
        "manifest_path": str(manifest_path),
        "summary": summary,
        "results": results,
    }


def write_llm_tournament_probe_report(report: dict[str, Any], output_dir: Path | str = DEFAULT_PROBE_OUTPUT_DIR) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = path / f"llm-tournament-probe-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def load_editorial_benchmark(path: Path | str = DEFAULT_EDITORIAL_BENCHMARK_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("editorial benchmark must contain a non-empty cases list")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("editorial benchmark case must be an object")
        case_id = str(case.get("case_id") or "").strip()
        topic = str(case.get("topic") or "").strip()
        fact_pack = case.get("fact_pack")
        evidence_cards = fact_pack.get("evidence_cards") if isinstance(fact_pack, dict) else None
        if not case_id or not topic or not isinstance(fact_pack, dict) or not isinstance(evidence_cards, list):
            raise ValueError("editorial benchmark case requires case_id, topic and fact_pack.evidence_cards")
    return payload


def plan_llm_tournament_textual_round(
    *,
    benchmark_path: Path | str = DEFAULT_EDITORIAL_BENCHMARK_PATH,
    manifest_path: Path | str = DEFAULT_CANDIDATES_PATH,
    candidate_ids: set[str] | None = None,
    triage_mode: str = "quick",
    full_mode: str = "full",
    max_failures_per_candidate: int = 2,
    min_triage_pass_rate: float = 0.67,
    finalist_top_n: int = 3,
    triage_only: bool = False,
    timeout_sec: float = 60.0,
    parallelism: int = 24,
) -> dict[str, Any]:
    benchmark = load_editorial_benchmark(benchmark_path)
    all_candidates = load_llm_tournament_candidates(manifest_path)
    triage_cases = _benchmark_cases_for_mode(benchmark, triage_mode)
    full_cases = _benchmark_cases_for_mode(benchmark, full_mode)
    stages: dict[str, Any] = {}
    total_triage_tasks = 0
    total_full_worst_case_tasks = 0
    for stage in TEXTUAL_TOURNAMENT_STAGES:
        configured = _stage_candidates(all_candidates, stage, candidate_ids)
        configured_ids = [candidate.candidate_id for candidate in configured]
        unconfigured_ids = [
            candidate.candidate_id
            for candidate in all_candidates
            if candidate.enabled
            and not candidate.configured
            and stage in candidate.roles
            and (not candidate_ids or candidate.candidate_id in candidate_ids)
        ]
        triage_tasks = len(_textual_stage_tasks(configured, triage_cases, benchmark, stage))
        full_worst_case_tasks = 0 if triage_only else len(_textual_stage_tasks(configured, full_cases, benchmark, stage))
        total_triage_tasks += triage_tasks
        total_full_worst_case_tasks += full_worst_case_tasks
        fixture_multiplier = (
            triage_tasks // max(1, len(configured) * len(triage_cases))
            if configured and triage_cases
            else 0
        )
        stages[stage] = {
            "configured_candidate_count": len(configured),
            "configured_candidate_ids": configured_ids,
            "unconfigured_candidate_ids": unconfigured_ids,
            "triage_case_count": len(triage_cases),
            "full_case_count": 0 if triage_only else len(full_cases),
            "fixture_multiplier_per_case": fixture_multiplier,
            "triage_task_count": triage_tasks,
            "full_worst_case_task_count": full_worst_case_tasks,
            "max_failures_per_candidate": max_failures_per_candidate,
        }
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": "textual_round_plan",
        "benchmark_id": benchmark.get("benchmark_id"),
        "benchmark_path": str(benchmark_path),
        "manifest_path": str(manifest_path),
        "triage_mode": triage_mode,
        "full_mode": full_mode,
        "triage_only": triage_only,
        "min_triage_pass_rate": min_triage_pass_rate,
        "finalist_top_n": finalist_top_n,
        "timeout_sec": timeout_sec,
        "parallelism": parallelism,
        "stages": stages,
        "summary": {
            "triage_task_count": total_triage_tasks,
            "full_worst_case_task_count": total_full_worst_case_tasks,
            "provider_call_upper_bound": total_triage_tasks + total_full_worst_case_tasks,
        },
        "notes": [
            "Este plano nao chama providers externos.",
            "A rodada full real pode ser menor que o pior caso se a triagem eliminar candidatos.",
            "Quando triage_only=true, o plano nao inclui chamadas da rodada full.",
            "script usa 1 fixture por caso; repair e audit usam 6 fixtures por caso.",
        ],
    }


def run_llm_tournament_script_stage(
    *,
    mode: str = "quick",
    benchmark_path: Path | str = DEFAULT_EDITORIAL_BENCHMARK_PATH,
    manifest_path: Path | str = DEFAULT_CANDIDATES_PATH,
    output_dir: Path | str = DEFAULT_TOURNAMENT_RUNS_DIR,
    candidate_ids: set[str] | None = None,
    judge_candidate_id: str = "openai-gpt-5.5-medium",
    judge_mode: str = "none",
    judge_top_n: int = 5,
    max_failures_per_candidate: int = 3,
    timeout_sec: float = 60.0,
    parallelism: int = 2,
    emit_progress: bool = False,
) -> dict[str, Any]:
    benchmark = load_editorial_benchmark(benchmark_path)
    candidates = _script_stage_candidates(load_llm_tournament_candidates(manifest_path), candidate_ids)
    cases = _benchmark_cases_for_mode(benchmark, mode)
    if mode == "finalists" and not candidate_ids:
        raise ValueError("finalists mode requires at least one --candidate")
    normalized_judge_mode = judge_mode.strip().lower()
    if normalized_judge_mode not in {"none", "all", "top-n"}:
        raise ValueError("judge_mode must be one of: none, all, top-n")
    judge_candidate = (
        _candidate_by_id(load_llm_tournament_candidates(manifest_path), judge_candidate_id)
        if normalized_judge_mode != "none"
        else None
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + f"-script-{mode}"
    run_dir = Path(output_dir) / run_id
    outputs_dir = run_dir / "outputs" / "script"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.json"
    ranking_path = run_dir / "ranking.json"

    started_at = time.monotonic()
    provider_semaphores = _provider_semaphores(candidates, per_provider_limit=1)
    tasks: list[tuple[LlmTournamentCandidate, dict[str, Any]]] = [(candidate, case) for candidate in candidates for case in cases]
    results: list[dict[str, Any]] = []
    total_tasks = len(tasks)
    max_workers = max(1, int(parallelism or 1))
    base_report = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "benchmark_id": benchmark.get("benchmark_id"),
        "benchmark_path": str(benchmark_path),
        "manifest_path": str(manifest_path),
        "judge_candidate_id": judge_candidate_id,
        "judge_mode": normalized_judge_mode,
        "judge_top_n": judge_top_n,
        "max_failures_per_candidate": max_failures_per_candidate,
        "stage": "script",
        "case_count": len(cases),
        "candidate_count": len(candidates),
    }
    _write_tournament_progress(
        base_report,
        results,
        results_path=results_path,
        ranking_path=ranking_path,
        started_at=started_at,
        status="running",
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending: set[Any] = set()
        future_map: dict[Any, tuple[LlmTournamentCandidate, dict[str, Any]]] = {}
        task_index = 0
        skipped_failures: dict[str, int] = {}
        while task_index < len(tasks) or pending:
            while task_index < len(tasks) and len(pending) < max_workers:
                candidate, case = tasks[task_index]
                task_index += 1
                current_failures = _candidate_operational_failure_count(results, candidate.candidate_id)
                if current_failures >= max_failures_per_candidate:
                    skipped_failures[candidate.candidate_id] = skipped_failures.get(candidate.candidate_id, 0) + 1
                    result = _skipped_after_failure_budget(candidate, case, max_failures_per_candidate)
                    results.append(result)
                    _emit_progress(emit_progress, result, len(results), total_tasks)
                    _write_tournament_progress(
                        base_report,
                        sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id")))),
                        results_path=results_path,
                        ranking_path=ranking_path,
                        started_at=started_at,
                        status="running",
                    )
                    continue
                future = executor.submit(
                    _run_script_stage_case,
                    candidate,
                    case,
                    benchmark,
                    outputs_dir,
                    timeout_sec,
                    provider_semaphores,
                )
                pending.add(future)
                future_map[future] = (candidate, case)
            if not pending:
                continue
            for future in as_completed(pending):
                pending.remove(future)
                result = future.result()
                results.append(result)
                _emit_progress(emit_progress, result, len(results), total_tasks)
                _write_tournament_progress(
                    base_report,
                    sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id")), str(item.get("fixture_id") or ""))),
                    results_path=results_path,
                    ranking_path=ranking_path,
                    started_at=started_at,
                    status="running",
                )
                break

    results = sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id"))))
    if judge_candidate is not None and normalized_judge_mode in {"all", "top-n"}:
        results = _judge_script_results(
            results,
            cases=cases,
            judge_candidate=judge_candidate,
            judge_mode=normalized_judge_mode,
            judge_top_n=judge_top_n,
            outputs_dir=outputs_dir,
            timeout_sec=timeout_sec,
            emit_progress=emit_progress,
        )
    ranking = build_script_stage_ranking(results)
    report = {
        **base_report,
        "status": "completed",
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "results": results,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ranking_path.write_text(json.dumps(ranking, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_path = Path(output_dir).parent / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps({"run_id": run_id, "run_dir": str(run_dir), "ranking_path": str(run_dir / "ranking.json")}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**report, "ranking": ranking, "run_dir": str(run_dir)}


def run_llm_tournament_textual_round(
    *,
    benchmark_path: Path | str = DEFAULT_EDITORIAL_BENCHMARK_PATH,
    manifest_path: Path | str = DEFAULT_CANDIDATES_PATH,
    output_dir: Path | str = DEFAULT_TOURNAMENT_RUNS_DIR,
    candidate_ids: set[str] | None = None,
    triage_mode: str = "quick",
    full_mode: str = "full",
    max_failures_per_candidate: int = 2,
    min_triage_pass_rate: float = 0.67,
    finalist_top_n: int = 3,
    triage_only: bool = False,
    timeout_sec: float = 60.0,
    parallelism: int = 2,
    price_table_path: Path | str | None = None,
    emit_progress: bool = False,
) -> dict[str, Any]:
    benchmark = load_editorial_benchmark(benchmark_path)
    all_candidates = load_llm_tournament_candidates(manifest_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-textual"
    run_dir = Path(output_dir) / run_id
    started_at = time.monotonic()
    triage_reports: dict[str, dict[str, Any]] = {}
    full_reports: dict[str, dict[str, Any]] = {}
    survivors_by_stage: dict[str, list[str]] = {}

    for stage in TEXTUAL_TOURNAMENT_STAGES:
        candidates = _stage_candidates(all_candidates, stage, candidate_ids)
        stage_run_dir = run_dir / "triage" / stage
        cases = _benchmark_cases_for_mode(benchmark, triage_mode)
        report = _run_textual_stage_phase(
            stage=stage,
            phase="triage",
            mode=triage_mode,
            benchmark=benchmark,
            benchmark_path=benchmark_path,
            manifest_path=manifest_path,
            run_id=f"{run_id}-triage-{stage}",
            run_dir=stage_run_dir,
            candidates=candidates,
            cases=cases,
            max_failures_per_candidate=max_failures_per_candidate,
            timeout_sec=timeout_sec,
            parallelism=parallelism,
            emit_progress=emit_progress,
        )
        triage_reports[stage] = report
        survivors_by_stage[stage] = _surviving_candidate_ids(
            report["ranking"],
            min_pass_rate=min_triage_pass_rate,
            max_failures_per_candidate=max_failures_per_candidate,
        )

    if triage_only:
        run_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "stage": "textual_triage",
            "benchmark_id": benchmark.get("benchmark_id"),
            "benchmark_path": str(benchmark_path),
            "manifest_path": str(manifest_path),
            "triage_mode": triage_mode,
            "full_mode": None,
            "triage_only": True,
            "max_failures_per_candidate": max_failures_per_candidate,
            "min_triage_pass_rate": min_triage_pass_rate,
            "finalist_top_n": finalist_top_n,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "survivors_by_stage": survivors_by_stage,
            "triage_reports": triage_reports,
            "full_reports": {},
            "decision_report": None,
        }
        triage_results_path = run_dir / "textual_triage_results.json"
        triage_results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        latest_path = Path(output_dir).parent / "latest-textual-triage.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "results_path": str(triage_results_path),
                    "survivors_by_stage": survivors_by_stage,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {**report, "run_dir": str(run_dir)}

    for stage in TEXTUAL_TOURNAMENT_STAGES:
        survivor_ids = set(survivors_by_stage.get(stage) or [])
        candidates = _stage_candidates(all_candidates, stage, survivor_ids) if survivor_ids else []
        stage_run_dir = run_dir / "full" / stage
        cases = _benchmark_cases_for_mode(benchmark, full_mode)
        if not candidates:
            full_reports[stage] = _empty_textual_stage_report(
                stage=stage,
                phase="full",
                mode=full_mode,
                benchmark=benchmark,
                benchmark_path=benchmark_path,
                manifest_path=manifest_path,
                run_id=f"{run_id}-full-{stage}",
                run_dir=stage_run_dir,
                cases=cases,
                reason="no_triage_survivors",
            )
            continue
        full_reports[stage] = _run_textual_stage_phase(
            stage=stage,
            phase="full",
            mode=full_mode,
            benchmark=benchmark,
            benchmark_path=benchmark_path,
            manifest_path=manifest_path,
            run_id=f"{run_id}-full-{stage}",
            run_dir=stage_run_dir,
            candidates=candidates,
            cases=cases,
            max_failures_per_candidate=max_failures_per_candidate,
            timeout_sec=timeout_sec,
            parallelism=parallelism,
            emit_progress=emit_progress,
        )

    committee_packet = _build_committee_packet(
        triage_reports=triage_reports,
        full_reports=full_reports,
        finalist_top_n=finalist_top_n,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    committee_packet_path = run_dir / "committee_packet.json"
    committee_packet_path.write_text(json.dumps(committee_packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decision_report = build_llm_tournament_decision_report(
        committee_packet_path=committee_packet_path,
        output_dir=run_dir,
        price_table_path=price_table_path,
    )
    report = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "stage": "textual_round",
        "benchmark_id": benchmark.get("benchmark_id"),
        "benchmark_path": str(benchmark_path),
        "manifest_path": str(manifest_path),
        "triage_mode": triage_mode,
        "full_mode": full_mode,
        "max_failures_per_candidate": max_failures_per_candidate,
        "min_triage_pass_rate": min_triage_pass_rate,
        "finalist_top_n": finalist_top_n,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "survivors_by_stage": survivors_by_stage,
        "triage_reports": triage_reports,
        "full_reports": full_reports,
        "committee_packet": committee_packet,
        "decision_report": decision_report,
    }
    (run_dir / "textual_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_path = Path(output_dir).parent / "latest-textual.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "results_path": str(run_dir / "textual_results.json"),
                "committee_packet_path": str(committee_packet_path),
                "decision_report_json": decision_report["output_paths"]["json"],
                "decision_report_markdown": decision_report["output_paths"]["markdown"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {**report, "run_dir": str(run_dir)}


def build_llm_tournament_decision_report(
    *,
    committee_packet_path: Path | str,
    output_dir: Path | str | None = None,
    price_table_path: Path | str | None = None,
) -> dict[str, Any]:
    packet_path = Path(committee_packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    price_table = _load_price_table(price_table_path)
    destination = Path(output_dir) if output_dir is not None else packet_path.parent
    destination.mkdir(parents=True, exist_ok=True)

    stage_winners: dict[str, Any] = {}
    stage_scores_by_candidate: dict[str, list[dict[str, Any]]] = {}
    evidence_summary: dict[str, Any] = {}
    for stage, stage_payload in (packet.get("stages") or {}).items():
        ranking = stage_payload.get("ranking") if isinstance(stage_payload, dict) else {}
        ranking = ranking if isinstance(ranking, dict) else {}
        rows = [dict(item) for item in ranking.get("all_candidates") or [] if isinstance(item, dict)]
        scored_rows = [_decision_scored_row(row, stage=str(stage), price_table=price_table) for row in rows]
        scored_rows.sort(key=lambda item: item["cost_benefit_score"], reverse=True)
        for row in scored_rows:
            stage_scores_by_candidate.setdefault(str(row.get("candidate_id")), []).append(row)
        scale = _first_dict(ranking.get("recommended_scale_routes"))
        premium = _first_dict(ranking.get("recommended_premium_routes"))
        stage_winners[str(stage)] = {
            "cost_benefit": scored_rows[0] if scored_rows else None,
            "scale": _decision_scored_row(scale, stage=str(stage), price_table=price_table) if scale else None,
            "premium": _decision_scored_row(premium, stage=str(stage), price_table=price_table) if premium else None,
        }
        evidence_summary[str(stage)] = _stage_evidence_summary(stage_payload)

    scale_route = {
        stage: winner["cost_benefit"]["candidate_id"]
        for stage, winner in stage_winners.items()
        if isinstance(winner.get("cost_benefit"), dict)
    }
    premium_route = {
        stage: winner["premium"]["candidate_id"]
        for stage, winner in stage_winners.items()
        if isinstance(winner.get("premium"), dict)
    }
    best_single_model = _best_single_model(stage_scores_by_candidate, expected_stages=set(stage_winners))
    risks = _decision_risks(packet, stage_winners, best_single_model)
    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_committee_packet_path": str(packet_path),
        "decision_mode": "codex_post_tournament_artifact_review",
        "cost_basis": "observed_operational_cost" if price_table is None else "observed_operational_cost_and_versioned_estimated_money",
        "price_table": _price_table_public_payload(price_table),
        "stage_winners": stage_winners,
        "scale_route": scale_route,
        "premium_route": premium_route,
        "best_single_model": best_single_model,
        "eliminated_candidates": packet.get("eliminated_candidates") or {},
        "non_comparable_candidates": packet.get("non_comparable_candidates") or {},
        "evidence_summary": evidence_summary,
        "risks": risks,
        "decision_notes": [
            "Este relatorio nao chama providers externos.",
            "Custo monetario fica indisponivel ate existir tabela local de precos versionada.",
            "A aplicacao no Hub exige aprovacao humana.",
        ],
    }
    json_path = destination / "decision_report.json"
    markdown_path = destination / "decision_report.md"
    report["output_paths"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_decision_report_markdown(report), encoding="utf-8")
    return report


def compare_llm_tournament_decision_reports(
    *,
    baseline_report_path: Path | str,
    candidate_report_path: Path | str,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    baseline_path = Path(baseline_report_path)
    candidate_path = Path(candidate_report_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    destination = Path(output_dir) if output_dir is not None else candidate_path.parent
    destination.mkdir(parents=True, exist_ok=True)

    stage_changes = _compare_stage_winners(
        baseline.get("stage_winners") if isinstance(baseline.get("stage_winners"), dict) else {},
        candidate.get("stage_winners") if isinstance(candidate.get("stage_winners"), dict) else {},
    )
    route_changes = {
        "scale_route": _dict_delta(baseline.get("scale_route"), candidate.get("scale_route")),
        "premium_route": _dict_delta(baseline.get("premium_route"), candidate.get("premium_route")),
    }
    comparison = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_report_path": str(baseline_path),
        "candidate_report_path": str(candidate_path),
        "baseline_generated_at": baseline.get("generated_at"),
        "candidate_generated_at": candidate.get("generated_at"),
        "stage_changes": stage_changes,
        "route_changes": route_changes,
        "best_single_model_change": _candidate_delta(baseline.get("best_single_model"), candidate.get("best_single_model")),
        "risk_changes": {
            "added": sorted(set(candidate.get("risks") or []) - set(baseline.get("risks") or [])),
            "removed": sorted(set(baseline.get("risks") or []) - set(candidate.get("risks") or [])),
        },
    }
    json_path = destination / "decision_report_comparison.json"
    markdown_path = destination / "decision_report_comparison.md"
    comparison["output_paths"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_decision_report_comparison_markdown(comparison), encoding="utf-8")
    return comparison


def latest_llm_tournament_decision_summary(
    base_dir: Path | str = DEFAULT_PROBE_OUTPUT_DIR,
) -> dict[str, Any]:
    root = Path(base_dir)
    latest_path = root / "latest-textual.json"
    latest_triage = _latest_textual_triage_summary(root)
    recent_triages = _recent_textual_triage_summaries(root)
    commands = _llm_tournament_hub_commands()
    if not latest_path.exists():
        return {
            "status": "missing",
            "message": _llm_tournament_missing_report_message(latest_triage),
            "latest_textual_path": str(latest_path),
            "latest_triage": latest_triage,
            "recent_triages": recent_triages,
            "commands": commands,
            "start_command": commands[1]["command"],
        }
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        report_path = Path(str(latest.get("decision_report_json") or ""))
        if not report_path.exists():
            return {
                "status": "missing_report",
                "message": "O ponteiro latest-textual.json existe, mas o decision_report.json nao foi encontrado.",
                "latest_textual_path": str(latest_path),
                "decision_report_json": str(report_path),
                "latest_triage": latest_triage,
                "recent_triages": recent_triages,
                "commands": commands,
                "start_command": commands[1]["command"],
            }
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "read_error",
            "message": f"Nao foi possivel ler o ultimo relatorio: {type(exc).__name__}: {str(exc)[:160]}",
            "latest_textual_path": str(latest_path),
            "latest_triage": latest_triage,
            "recent_triages": recent_triages,
            "commands": commands,
            "start_command": commands[1]["command"],
        }
    stages = []
    for stage, winners in (report.get("stage_winners") or {}).items():
        winners = winners if isinstance(winners, dict) else {}
        cost_benefit = winners.get("cost_benefit") if isinstance(winners.get("cost_benefit"), dict) else None
        stages.append(
            {
                "stage": stage,
                "cost_benefit": _candidate_summary_for_hub(cost_benefit),
                "scale_candidate_id": (winners.get("scale") or {}).get("candidate_id") if isinstance(winners.get("scale"), dict) else None,
                "premium_candidate_id": (winners.get("premium") or {}).get("candidate_id") if isinstance(winners.get("premium"), dict) else None,
            }
        )
    return {
        "status": "ready",
        "run_id": latest.get("run_id"),
        "generated_at": report.get("generated_at"),
        "cost_basis": report.get("cost_basis"),
        "price_table": report.get("price_table"),
        "stages": stages,
        "scale_route": report.get("scale_route") or {},
        "premium_route": report.get("premium_route") or {},
        "best_single_model": _candidate_summary_for_hub(report.get("best_single_model")),
        "risks": report.get("risks") or [],
        "latest_triage": latest_triage,
        "recent_triages": recent_triages,
        "commands": commands,
        "paths": {
            "run_dir": latest.get("run_dir"),
            "committee_packet": latest.get("committee_packet_path"),
            "decision_report_json": report.get("output_paths", {}).get("json") or str(report_path),
            "decision_report_markdown": report.get("output_paths", {}).get("markdown"),
            "latest_textual": str(latest_path),
        },
        "start_command": commands[1]["command"],
    }


def judge_existing_llm_tournament_script_run(
    *,
    results_path: Path | str,
    benchmark_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
    judge_candidate_id: str = "openai-gpt-5.5-medium",
    judge_mode: str = "top-n",
    judge_top_n: int = 5,
    timeout_sec: float = 60.0,
    emit_progress: bool = False,
) -> dict[str, Any]:
    path = Path(results_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("stage") != "script":
        raise ValueError("only script-stage tournament runs can be judged")
    normalized_judge_mode = judge_mode.strip().lower()
    if normalized_judge_mode not in {"all", "top-n"}:
        raise ValueError("judge_mode must be one of: all, top-n")

    resolved_benchmark_path = benchmark_path or report.get("benchmark_path") or DEFAULT_EDITORIAL_BENCHMARK_PATH
    resolved_manifest_path = manifest_path or report.get("manifest_path") or DEFAULT_CANDIDATES_PATH
    benchmark = load_editorial_benchmark(resolved_benchmark_path)
    cases = _benchmark_cases_for_mode(benchmark, str(report.get("mode") or "full"))
    judge_candidate = _candidate_by_id(load_llm_tournament_candidates(resolved_manifest_path), judge_candidate_id)
    run_dir = path.parent
    outputs_dir = run_dir / "outputs" / "script"

    started_at = time.monotonic()
    judged_results = _judge_script_results(
        list(report.get("results") or []),
        cases=cases,
        judge_candidate=judge_candidate,
        judge_mode=normalized_judge_mode,
        judge_top_n=judge_top_n,
        outputs_dir=outputs_dir,
        timeout_sec=timeout_sec,
        emit_progress=emit_progress,
    )
    ranking = build_script_stage_ranking(judged_results)
    updated_report = {
        **report,
        "status": "completed",
        "judge_candidate_id": judge_candidate_id,
        "judge_mode": normalized_judge_mode,
        "judge_top_n": judge_top_n,
        "judged_at": datetime.now(timezone.utc).isoformat(),
        "judge_duration_ms": int((time.monotonic() - started_at) * 1000),
        "results": judged_results,
    }
    path.write_text(json.dumps(updated_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ranking_path = run_dir / "ranking.json"
    ranking_path.write_text(json.dumps(ranking, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**updated_report, "ranking": ranking, "run_dir": str(run_dir)}


def deterministic_script_vetoes(script: Any, case: dict[str, Any]) -> list[str]:
    if not isinstance(script, dict):
        return ["invalid_json_contract"]
    vetoes: list[str] = []
    missing = sorted(field for field in SCRIPT_REQUIRED_FIELDS if field not in script)
    if missing:
        vetoes.append("missing_required_fields")
    body_beats = script.get("body_beats")
    if not isinstance(body_beats, list) or len([item for item in body_beats if str(item).strip()]) < 3:
        vetoes.append("invalid_body_beats")
    elif not all(isinstance(item, str) for item in body_beats):
        vetoes.append("invalid_body_beats")
    language = str(script.get("language") or "").strip().lower()
    if language and language not in {"pt-br", "pt_br", "português brasileiro", "portugues brasileiro"}:
        vetoes.append("language_not_pt_br")
    narrated_text = _script_narrated_text(script)
    if _has_disallowed_unicode(narrated_text):
        vetoes.append("language_not_pt_br")
    hook = str(script.get("hook") or "").strip().lower()
    if any(hook.startswith(opening) for opening in GENERIC_HOOK_OPENINGS):
        vetoes.append("generic_hook_opening")
    if "—" in narrated_text or "–" in narrated_text:
        vetoes.append("disallowed_dash")
    duration = _float_or_none(script.get("estimated_duration_sec"))
    if duration is not None and not 30 <= duration <= 60:
        vetoes.append("duration_out_of_range")
    if _contains_forbidden_claim(narrated_text, case):
        vetoes.append("forbidden_claim")
    valid_fact_ids = _case_fact_ids(case)
    used_fact_ids = _script_used_fact_ids(script)
    if valid_fact_ids:
        if not used_fact_ids:
            vetoes.append("missing_source_fact_ids")
        if any(source_id not in valid_fact_ids for source_id in used_fact_ids):
            vetoes.append("invented_source_fact_ids")
        trace = script.get("claim_trace")
        if not isinstance(trace, list) or not trace:
            vetoes.append("missing_claim_trace")
    full_narration = str(script.get("full_narration") or "").strip()
    if len(word_tokens(full_narration)) < 55:
        vetoes.append("too_short_for_shorts")
    if len(sentence_split(full_narration)) < 4:
        vetoes.append("too_few_sentences")
    return list(dict.fromkeys(vetoes))


def deterministic_repair_vetoes(payload: Any, case: dict[str, Any], fixture: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(payload, dict):
        return ["invalid_json_contract"]
    vetoes: list[str] = []
    missing = sorted(field for field in REPAIR_REQUIRED_FIELDS if field not in payload)
    if missing:
        vetoes.append("missing_required_fields")
    repaired_script = payload.get("repaired_script")
    script_vetoes = deterministic_script_vetoes(repaired_script, case)
    if script_vetoes:
        vetoes.extend(f"repaired_{veto}" for veto in script_vetoes)
    fixed = payload.get("fixed_issue_slugs")
    remaining = payload.get("remaining_issue_slugs")
    if not isinstance(fixed, list) or not all(isinstance(item, str) for item in fixed):
        vetoes.append("invalid_fixed_issue_slugs")
    if not isinstance(remaining, list) or not all(isinstance(item, str) for item in remaining):
        vetoes.append("invalid_remaining_issue_slugs")
    if isinstance(remaining, list) and any(str(item).strip() for item in remaining):
        vetoes.append("remaining_repair_issues")
    expected_issues = {str(item) for item in (fixture or {}).get("expected_issue_slugs") or [] if str(item).strip()}
    fixed_issues = {str(item) for item in fixed or [] if str(item).strip()} if isinstance(fixed, list) else set()
    if expected_issues and not expected_issues.issubset(fixed_issues):
        vetoes.append("missed_expected_repair_issue")
    return list(dict.fromkeys(vetoes))


def deterministic_audit_vetoes(payload: Any, fixture: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["invalid_json_contract"]
    vetoes: list[str] = []
    missing = sorted(field for field in AUDIT_REQUIRED_FIELDS if field not in payload)
    if missing:
        vetoes.append("missing_required_fields")
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"approve", "block", "repair"}:
        vetoes.append("invalid_decision")
    expected_decision = str(fixture.get("expected_decision") or "").strip().lower()
    if expected_decision and decision and decision != expected_decision:
        vetoes.append("wrong_audit_decision")
    severity = str(payload.get("severity") or "").strip().lower()
    if severity not in {"low", "medium", "high"}:
        vetoes.append("invalid_severity")
    reason_slugs = payload.get("reason_slugs")
    detected = payload.get("detected_issue_slugs")
    if not isinstance(reason_slugs, list) or not all(isinstance(item, str) for item in reason_slugs):
        vetoes.append("invalid_reason_slugs")
    if not isinstance(detected, list) or not all(isinstance(item, str) for item in detected):
        vetoes.append("invalid_detected_issue_slugs")
    expected_issues = {str(item) for item in fixture.get("expected_issue_slugs") or [] if str(item).strip()}
    detected_issues = {str(item) for item in detected or [] if str(item).strip()} if isinstance(detected, list) else set()
    if expected_issues and not expected_issues.issubset(detected_issues):
        vetoes.append("missed_expected_issue")
    if not expected_issues and detected_issues:
        vetoes.append("false_positive_audit_issue")
    return list(dict.fromkeys(vetoes))


def build_script_stage_ranking(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get("candidate_id") or ""), []).append(result)
    rows: list[dict[str, Any]] = []
    for candidate_id, items in grouped.items():
        judged = [item for item in items if isinstance(item.get("judge"), dict) and item["judge"].get("status") == "passed"]
        generated = [item for item in items if item.get("status") in {"generated", "judged"}]
        vetoed = [item for item in items if item.get("vetoes")]
        failures = [item for item in items if item.get("status") == "failed"]
        skipped = [item for item in items if item.get("status") == "skipped_failure_budget"]
        avg_overall = _average(
            _float_or_none(item.get("judge", {}).get("overall_score"))
            for item in judged
        )
        avg_hook = _average(_float_or_none(item.get("judge", {}).get("hook_strength_score")) for item in judged)
        avg_factual = _average(_float_or_none(item.get("judge", {}).get("factual_obedience_score")) for item in judged)
        input_tokens = sum(int(item.get("input_tokens") or 0) for item in items)
        output_tokens = sum(int(item.get("output_tokens") or 0) for item in items)
        total_tokens = sum(int(item.get("total_tokens") or 0) for item in items)
        avg_latency_ms = _average(_float_or_none(item.get("latency_ms")) for item in generated)
        passed_veto = [item for item in generated if not item.get("vetoes")]
        pass_rate = len(passed_veto) / len(items) if items else 0.0
        publicable_rate = len(judged) / len(items) if items else 0.0
        deterministic_score = pass_rate
        score_base = ((avg_overall if judged else deterministic_score) or 0.0) * max(pass_rate, publicable_rate)
        rows.append(
            {
                "candidate_id": candidate_id,
                "cases": len(items),
                "generated": len(generated),
                "judged": len(judged),
                "vetoed": len(vetoed),
                "failed": len(failures),
                "skipped": len(skipped),
                "pass_rate": round(pass_rate, 4),
                "publicable_rate": round(publicable_rate, 4),
                "avg_overall_score": round(avg_overall or 0.0, 4),
                "avg_hook_strength_score": round(avg_hook or 0.0, 4),
                "avg_factual_obedience_score": round(avg_factual or 0.0, 4),
                "avg_latency_ms": round(avg_latency_ms or 0.0, 1),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "script_score": round(score_base, 4),
            }
        )
    premium = sorted(
        rows,
        key=lambda item: (
            item["avg_overall_score"] or item["pass_rate"],
            item["pass_rate"],
            item["publicable_rate"],
            -item["failed"],
            -item["vetoed"],
            -item["avg_latency_ms"],
        ),
        reverse=True,
    )
    scale = sorted(
        rows,
        key=lambda item: (
            item["script_score"],
            item["pass_rate"],
            item["publicable_rate"],
            item["avg_overall_score"],
            -item["total_tokens"],
            -item["avg_latency_ms"],
        ),
        reverse=True,
    )
    return {
        "schema_version": "1.0.0",
        "stage": "script",
        "recommended_premium_routes": premium[:5],
        "recommended_scale_routes": scale[:5],
        "do_not_promote": [
            item for item in rows if item["publicable_rate"] < 0.5 or item["failed"] == item["cases"]
        ],
        "all_candidates": sorted(rows, key=lambda item: item["candidate_id"]),
    }


def build_textual_stage_ranking(results: list[dict[str, Any]], *, stage: str) -> dict[str, Any]:
    if stage == "script":
        return build_script_stage_ranking(results)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get("candidate_id") or ""), []).append(result)
    rows: list[dict[str, Any]] = []
    for candidate_id, items in grouped.items():
        generated = [item for item in items if item.get("status") == "generated"]
        vetoed = [item for item in items if item.get("vetoes")]
        failures = [item for item in items if item.get("status") == "failed"]
        skipped = [item for item in items if item.get("status") == "skipped_failure_budget"]
        passed_veto = [item for item in generated if not item.get("vetoes")]
        input_tokens = sum(int(item.get("input_tokens") or 0) for item in items)
        output_tokens = sum(int(item.get("output_tokens") or 0) for item in items)
        total_tokens = sum(int(item.get("total_tokens") or 0) for item in items)
        avg_latency_ms = _average(_float_or_none(item.get("latency_ms")) for item in generated)
        pass_rate = len(passed_veto) / len(items) if items else 0.0
        success_rate = len(generated) / len(items) if items else 0.0
        stage_score = pass_rate * success_rate
        rows.append(
            {
                "candidate_id": candidate_id,
                "cases": len(items),
                "generated": len(generated),
                "vetoed": len(vetoed),
                "failed": len(failures),
                "skipped": len(skipped),
                "pass_rate": round(pass_rate, 4),
                "success_rate": round(success_rate, 4),
                "avg_latency_ms": round(avg_latency_ms or 0.0, 1),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "stage_score": round(stage_score, 4),
            }
        )
    scale = sorted(
        rows,
        key=lambda item: (
            item["stage_score"],
            item["pass_rate"],
            item["success_rate"],
            -item["failed"],
            -item["vetoed"],
            -item["total_tokens"],
            -item["avg_latency_ms"],
        ),
        reverse=True,
    )
    premium = sorted(
        rows,
        key=lambda item: (
            item["pass_rate"],
            item["success_rate"],
            item["stage_score"],
            -item["failed"],
            -item["vetoed"],
            -item["avg_latency_ms"],
        ),
        reverse=True,
    )
    return {
        "schema_version": "1.0.0",
        "stage": stage,
        "recommended_premium_routes": premium[:5],
        "recommended_scale_routes": scale[:5],
        "do_not_promote": [
            item for item in rows if item["pass_rate"] < 0.5 or item["failed"] == item["cases"]
        ],
        "all_candidates": sorted(rows, key=lambda item: item["candidate_id"]),
    }


def _surviving_candidate_ids(
    ranking: dict[str, Any],
    *,
    min_pass_rate: float,
    max_failures_per_candidate: int,
) -> list[str]:
    survivors: list[str] = []
    for item in ranking.get("all_candidates") or []:
        pass_rate = _float_or_none(item.get("pass_rate")) or 0.0
        failures = int(item.get("failed") or 0)
        if pass_rate >= min_pass_rate and failures < max_failures_per_candidate:
            survivors.append(str(item.get("candidate_id")))
    return survivors


def _build_committee_packet(
    *,
    triage_reports: dict[str, dict[str, Any]],
    full_reports: dict[str, dict[str, Any]],
    finalist_top_n: int,
) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    eliminated: dict[str, list[dict[str, Any]]] = {}
    non_comparable: dict[str, list[dict[str, Any]]] = {}
    for stage, report in full_reports.items():
        ranking = report.get("ranking") or {}
        finalists = list((ranking.get("recommended_scale_routes") or [])[: max(1, int(finalist_top_n or 1))])
        results = list(report.get("results") or [])
        stages[stage] = {
            "ranking": ranking,
            "finalists": [
                {
                    **item,
                    "representative_artifacts": _representative_artifacts(results, str(item.get("candidate_id"))),
                }
                for item in finalists
            ],
        }
    for stage, report in triage_reports.items():
        ranking = report.get("ranking") or {}
        eliminated[stage] = [
            item
            for item in ranking.get("all_candidates") or []
            if item.get("candidate_id") not in {candidate.get("candidate_id") for candidate in (full_reports.get(stage, {}).get("ranking", {}).get("all_candidates") or [])}
        ]
    for stage, report in full_reports.items():
        if report.get("status") == "skipped":
            non_comparable[stage] = [
                {
                    "stage": stage,
                    "reason": report.get("skip_reason"),
                }
            ]
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "committee": "codex-post-tournament",
        "decision_mode": "artifact_review_finalists_only",
        "stages": stages,
        "eliminated_candidates": eliminated,
        "non_comparable_candidates": non_comparable,
    }


def _representative_artifacts(results: list[dict[str, Any]], candidate_id: str) -> list[dict[str, Any]]:
    candidate_results = [result for result in results if result.get("candidate_id") == candidate_id]
    passed = [result for result in candidate_results if result.get("status") == "generated" and not result.get("vetoes")]
    vetoed = [result for result in candidate_results if result.get("vetoes")]
    failed = [result for result in candidate_results if result.get("status") == "failed"]
    selected = (passed[:2] + vetoed[:1] + failed[:1])[:4]
    return [
        {
            "case_id": result.get("case_id"),
            "fixture_id": result.get("fixture_id"),
            "status": result.get("status"),
            "vetoes": result.get("vetoes") or [],
            "failure_type": result.get("failure_type"),
            "latency_ms": result.get("latency_ms"),
            "total_tokens": result.get("total_tokens"),
            "output_path": result.get("output_path"),
        }
        for result in selected
    ]


def _audit_decision_metrics(payload: Any, fixture: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"false_positive_count": 0, "false_negative_count": len(fixture.get("expected_issue_slugs") or [])}
    expected_issues = {str(item) for item in fixture.get("expected_issue_slugs") or [] if str(item).strip()}
    detected = payload.get("detected_issue_slugs")
    detected_issues = {str(item) for item in detected or [] if str(item).strip()} if isinstance(detected, list) else set()
    return {
        "expected_decision": fixture.get("expected_decision"),
        "actual_decision": str(payload.get("decision") or "").strip().lower(),
        "false_positive_count": len(detected_issues - expected_issues),
        "false_negative_count": len(expected_issues - detected_issues),
    }


def _decision_scored_row(row: dict[str, Any], *, stage: str, price_table: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = (
        _float_or_none(row.get("script_score"))
        or _float_or_none(row.get("stage_score"))
        or _float_or_none(row.get("pass_rate"))
        or 0.0
    )
    pass_rate = _float_or_none(row.get("pass_rate")) or 0.0
    success_rate = _float_or_none(row.get("success_rate"))
    if success_rate is None:
        generated = _float_or_none(row.get("generated")) or 0.0
        cases = _float_or_none(row.get("cases")) or 0.0
        success_rate = generated / cases if cases else pass_rate
    total_tokens = _float_or_none(row.get("total_tokens")) or 0.0
    avg_latency_ms = _float_or_none(row.get("avg_latency_ms")) or 0.0
    failures = _float_or_none(row.get("failed")) or 0.0
    vetoed = _float_or_none(row.get("vetoed")) or 0.0
    operational_cost = 1.0 + (total_tokens / 50000.0) + (avg_latency_ms / 120000.0) + (failures * 0.25) + (vetoed * 0.1)
    score = (quality * pass_rate * success_rate) / operational_cost if operational_cost else 0.0
    scored = {
        **row,
        "stage": stage,
        "quality_score": round(quality, 4),
        "observed_operational_cost_index": round(operational_cost, 4),
        "cost_benefit_score": round(score, 4),
    }
    estimated = _estimated_money_cost(row, price_table)
    if estimated is not None:
        scored["estimated_money_cost"] = estimated
    return scored


def _load_price_table(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    prices = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(prices, list):
        raise ValueError("price table must contain a prices list")
    by_candidate: dict[str, dict[str, Any]] = {}
    for item in prices:
        if not isinstance(item, dict):
            raise ValueError("price table price entries must be objects")
        candidate_id = str(item.get("candidate_id") or "").strip()
        input_price = _float_or_none(item.get("input_usd_per_1m_tokens"))
        output_price = _float_or_none(item.get("output_usd_per_1m_tokens"))
        if not candidate_id or input_price is None or output_price is None:
            raise ValueError("price table entries require candidate_id, input_usd_per_1m_tokens and output_usd_per_1m_tokens")
        by_candidate[candidate_id] = item
    return {
        "schema_version": payload.get("schema_version"),
        "price_table_id": payload.get("price_table_id"),
        "effective_date": payload.get("effective_date"),
        "currency": payload.get("currency") or "USD",
        "source": payload.get("source"),
        "by_candidate": by_candidate,
    }


def _price_table_public_payload(price_table: dict[str, Any] | None) -> dict[str, Any] | None:
    if price_table is None:
        return None
    return {
        "schema_version": price_table.get("schema_version"),
        "price_table_id": price_table.get("price_table_id"),
        "effective_date": price_table.get("effective_date"),
        "currency": price_table.get("currency"),
        "source": price_table.get("source"),
        "candidate_count": len(price_table.get("by_candidate") or {}),
    }


def _estimated_money_cost(row: dict[str, Any], price_table: dict[str, Any] | None) -> dict[str, Any] | None:
    if price_table is None:
        return None
    candidate_id = str(row.get("candidate_id") or "")
    price = (price_table.get("by_candidate") or {}).get(candidate_id)
    if not isinstance(price, dict):
        return {
            "status": "missing_price",
            "currency": price_table.get("currency") or "USD",
        }
    input_tokens = int(row.get("input_tokens") or 0)
    output_tokens = int(row.get("output_tokens") or 0)
    input_price = float(price.get("input_usd_per_1m_tokens") or 0.0)
    output_price = float(price.get("output_usd_per_1m_tokens") or 0.0)
    estimated = (input_tokens / 1_000_000.0 * input_price) + (output_tokens / 1_000_000.0 * output_price)
    return {
        "status": "estimated",
        "currency": price_table.get("currency") or "USD",
        "amount": round(estimated, 8),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_usd_per_1m_tokens": input_price,
        "output_usd_per_1m_tokens": output_price,
    }


def _stage_evidence_summary(stage_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(stage_payload, dict):
        return []
    summaries: list[dict[str, Any]] = []
    for finalist in stage_payload.get("finalists") or []:
        if not isinstance(finalist, dict):
            continue
        artifacts = []
        for artifact in finalist.get("representative_artifacts") or []:
            if isinstance(artifact, dict):
                artifacts.append(_summarize_artifact(artifact))
        summaries.append(
            {
                "candidate_id": finalist.get("candidate_id"),
                "pass_rate": finalist.get("pass_rate"),
                "failed": finalist.get("failed"),
                "vetoed": finalist.get("vetoed"),
                "input_tokens": finalist.get("input_tokens"),
                "output_tokens": finalist.get("output_tokens"),
                "total_tokens": finalist.get("total_tokens"),
                "avg_latency_ms": finalist.get("avg_latency_ms"),
                "representative_artifacts": artifacts,
            }
        )
    return summaries


def _summarize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    output_path = artifact.get("output_path")
    summary = {
        "case_id": artifact.get("case_id"),
        "fixture_id": artifact.get("fixture_id"),
        "status": artifact.get("status"),
        "vetoes": artifact.get("vetoes") or [],
        "failure_type": artifact.get("failure_type"),
            "latency_ms": artifact.get("latency_ms"),
            "input_tokens": artifact.get("input_tokens"),
            "output_tokens": artifact.get("output_tokens"),
            "total_tokens": artifact.get("total_tokens"),
        "output_path": output_path,
    }
    if not output_path:
        return summary
    path = Path(str(output_path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {**summary, "artifact_read_error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    parsed = payload.get("parsed")
    if isinstance(parsed, dict):
        summary["parsed_summary"] = _parsed_artifact_summary(parsed)
    fixture = payload.get("fixture")
    if isinstance(fixture, dict):
        summary["fixture_summary"] = {
            "fixture_id": fixture.get("fixture_id"),
            "fixture_kind": fixture.get("fixture_kind"),
            "expected_decision": fixture.get("expected_decision"),
            "expected_issue_slugs": fixture.get("expected_issue_slugs"),
        }
    return summary


def _parsed_artifact_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    if "repaired_script" in parsed:
        script = parsed.get("repaired_script") if isinstance(parsed.get("repaired_script"), dict) else {}
        return {
            "kind": "repair",
            "fixed_issue_slugs": parsed.get("fixed_issue_slugs") or [],
            "remaining_issue_slugs": parsed.get("remaining_issue_slugs") or [],
            "title": script.get("title"),
            "hook": script.get("hook"),
            "word_count": len(word_tokens(str(script.get("full_narration") or ""))),
            "claim_trace_count": len(script.get("claim_trace") or []) if isinstance(script.get("claim_trace"), list) else 0,
        }
    if "decision" in parsed:
        return {
            "kind": "audit",
            "decision": parsed.get("decision"),
            "severity": parsed.get("severity"),
            "reason_slugs": parsed.get("reason_slugs") or [],
            "detected_issue_slugs": parsed.get("detected_issue_slugs") or [],
        }
    return {
        "kind": "script",
        "title": parsed.get("title"),
        "hook": parsed.get("hook"),
        "word_count": len(word_tokens(str(parsed.get("full_narration") or ""))),
        "source_fact_ids": parsed.get("source_fact_ids") or [],
        "claim_trace_count": len(parsed.get("claim_trace") or []) if isinstance(parsed.get("claim_trace"), list) else 0,
        "narration_excerpt": str(parsed.get("full_narration") or "")[:280],
    }


def _best_single_model(stage_scores_by_candidate: dict[str, list[dict[str, Any]]], *, expected_stages: set[str]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for candidate_id, rows in stage_scores_by_candidate.items():
        covered = {str(row.get("stage")) for row in rows}
        if expected_stages and covered != expected_stages:
            continue
        avg_score = _average(_float_or_none(row.get("cost_benefit_score")) for row in rows) or 0.0
        min_pass_rate = min((_float_or_none(row.get("pass_rate")) or 0.0 for row in rows), default=0.0)
        total_failures = sum(int(row.get("failed") or 0) for row in rows)
        total_tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
        estimated_costs = [
            row.get("estimated_money_cost", {}).get("amount")
            for row in rows
            if isinstance(row.get("estimated_money_cost"), dict)
            and row.get("estimated_money_cost", {}).get("status") == "estimated"
        ]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "covered_stages": sorted(covered),
                "average_cost_benefit_score": round(avg_score, 4),
                "min_pass_rate": round(min_pass_rate, 4),
                "total_failures": total_failures,
                "total_tokens": total_tokens,
                "estimated_money_cost": round(sum(float(value) for value in estimated_costs), 8) if estimated_costs else None,
                "stage_rows": sorted(rows, key=lambda item: str(item.get("stage"))),
            }
        )
    candidates.sort(
        key=lambda item: (
            item["average_cost_benefit_score"],
            item["min_pass_rate"],
            -item["total_failures"],
            -item["total_tokens"],
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _decision_risks(packet: dict[str, Any], stage_winners: dict[str, Any], best_single_model: dict[str, Any] | None) -> list[str]:
    risks: list[str] = []
    if any(packet.get("non_comparable_candidates", {}).values()):
        risks.append("Ha candidatos nao comparaveis; nao trate ausencia de dados como derrota editorial.")
    if any(packet.get("eliminated_candidates", {}).values()):
        risks.append("Ha candidatos eliminados na triagem; corrija acesso, limite ou contrato antes de retestar.")
    if best_single_model is None:
        risks.append("Nenhum modelo unico cobriu todas as etapas com dados suficientes.")
    for stage, winners in stage_winners.items():
        cost_benefit = winners.get("cost_benefit") if isinstance(winners, dict) else None
        if not isinstance(cost_benefit, dict):
            risks.append(f"Etapa {stage} nao tem vencedor de custo-beneficio.")
            continue
        if (_float_or_none(cost_benefit.get("pass_rate")) or 0.0) < 0.8:
            risks.append(f"Vencedor da etapa {stage} tem pass_rate abaixo de 0.8.")
        if int(cost_benefit.get("failed") or 0) > 0:
            risks.append(f"Vencedor da etapa {stage} ainda teve falhas operacionais.")
    return list(dict.fromkeys(risks))


def _decision_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Relatorio de Decisao do Torneio",
        "",
        f"- Gerado em: {report.get('generated_at')}",
        f"- Base de custo: {report.get('cost_basis')}",
        f"- Pacote fonte: `{report.get('source_committee_packet_path')}`",
        f"- Tabela de preco: `{(report.get('price_table') or {}).get('price_table_id') or 'indisponivel'}`",
        "",
        "## Vencedores por etapa",
        "",
    ]
    for stage, winners in (report.get("stage_winners") or {}).items():
        cost_benefit = winners.get("cost_benefit") if isinstance(winners, dict) else None
        scale = winners.get("scale") if isinstance(winners, dict) else None
        premium = winners.get("premium") if isinstance(winners, dict) else None
        lines.append(f"### {stage}")
        lines.append(f"- Custo-beneficio: {_candidate_line(cost_benefit)}")
        lines.append(f"- Escala: {_candidate_line(scale)}")
        lines.append(f"- Premium: {_candidate_line(premium)}")
        lines.append("")
    lines.extend(
        [
            "## Rotas recomendadas",
            "",
            f"- Escala: `{json.dumps(report.get('scale_route') or {}, ensure_ascii=False)}`",
            f"- Premium: `{json.dumps(report.get('premium_route') or {}, ensure_ascii=False)}`",
            f"- Modelo unico: {_candidate_line(report.get('best_single_model'))}",
            "",
            "## Riscos",
            "",
        ]
    )
    risks = report.get("risks") or []
    if risks:
        lines.extend(f"- {risk}" for risk in risks)
    else:
        lines.append("- Nenhum risco operacional relevante nos dados analisados.")
    lines.extend(["", "## Evidencia dos finalistas", ""])
    for stage, summaries in (report.get("evidence_summary") or {}).items():
        lines.append(f"### {stage}")
        for summary in summaries or []:
            lines.append(
                f"- `{summary.get('candidate_id')}`: pass_rate={summary.get('pass_rate')}, "
                f"falhas={summary.get('failed')}, vetos={summary.get('vetoed')}, "
                f"tokens_in={summary.get('input_tokens')}, tokens_out={summary.get('output_tokens')}, tokens={summary.get('total_tokens')}, "
                f"latencia_media_ms={summary.get('avg_latency_ms')}"
            )
            for artifact in summary.get("representative_artifacts") or []:
                parsed = artifact.get("parsed_summary") or {}
                label = parsed.get("title") or parsed.get("decision") or parsed.get("kind") or artifact.get("status")
                fixture_label = f"/{artifact.get('fixture_id')}" if artifact.get("fixture_id") else ""
                lines.append(f"  - {artifact.get('case_id')}{fixture_label}: {artifact.get('status')} `{label}` ({artifact.get('output_path')})")
        lines.append("")
    lines.extend(["## Observacoes", ""])
    lines.extend(f"- {note}" for note in report.get("decision_notes") or [])
    return "\n".join(lines).rstrip() + "\n"


def _compare_stage_winners(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for stage in sorted(set(baseline) | set(candidate)):
        baseline_winners = baseline.get(stage) if isinstance(baseline.get(stage), dict) else {}
        candidate_winners = candidate.get(stage) if isinstance(candidate.get(stage), dict) else {}
        stage_change = {
            "cost_benefit": _candidate_delta(baseline_winners.get("cost_benefit"), candidate_winners.get("cost_benefit")),
            "scale": _candidate_delta(baseline_winners.get("scale"), candidate_winners.get("scale")),
            "premium": _candidate_delta(baseline_winners.get("premium"), candidate_winners.get("premium")),
        }
        stage_change["changed"] = any(bool(item.get("changed")) for item in stage_change.values() if isinstance(item, dict))
        changes[stage] = stage_change
    return changes


def _dict_delta(baseline: Any, candidate: Any) -> dict[str, Any]:
    baseline_dict = baseline if isinstance(baseline, dict) else {}
    candidate_dict = candidate if isinstance(candidate, dict) else {}
    fields: dict[str, Any] = {}
    for key in sorted(set(baseline_dict) | set(candidate_dict)):
        baseline_value = baseline_dict.get(key)
        candidate_value = candidate_dict.get(key)
        if baseline_value != candidate_value:
            fields[key] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
            }
    return {
        "changed": bool(fields),
        "fields": fields,
    }


def _candidate_delta(baseline: Any, candidate: Any) -> dict[str, Any]:
    baseline_summary = _candidate_delta_summary(baseline)
    candidate_summary = _candidate_delta_summary(candidate)
    delta = {
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "changed": baseline_summary.get("candidate_id") != candidate_summary.get("candidate_id"),
    }
    numeric_fields = (
        "score",
        "pass_rate",
        "failures",
        "total_tokens",
        "estimated_money_cost",
        "observed_operational_cost_index",
        "avg_latency_ms",
    )
    for field in numeric_fields:
        value = _numeric_delta(baseline_summary.get(field), candidate_summary.get(field))
        if value is not None:
            delta[f"{field}_delta"] = value
    if baseline_summary != candidate_summary:
        delta["changed"] = True
    return delta


def _candidate_delta_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"candidate_id": None}
    score = (
        _float_or_none(payload.get("cost_benefit_score"))
        or _float_or_none(payload.get("average_cost_benefit_score"))
        or _float_or_none(payload.get("stage_score"))
        or _float_or_none(payload.get("script_score"))
    )
    pass_rate = _float_or_none(payload.get("pass_rate"))
    if pass_rate is None:
        pass_rate = _float_or_none(payload.get("min_pass_rate"))
    failures = _float_or_none(payload.get("failed"))
    if failures is None:
        failures = _float_or_none(payload.get("total_failures"))
    return {
        "candidate_id": payload.get("candidate_id"),
        "score": score,
        "pass_rate": pass_rate,
        "failures": failures,
        "total_tokens": _float_or_none(payload.get("total_tokens")),
        "estimated_money_cost": _candidate_money_amount(payload.get("estimated_money_cost")),
        "observed_operational_cost_index": _float_or_none(payload.get("observed_operational_cost_index")),
        "avg_latency_ms": _float_or_none(payload.get("avg_latency_ms")),
    }


def _candidate_money_amount(value: Any) -> float | None:
    if isinstance(value, dict):
        if value.get("status") != "estimated":
            return None
        return _float_or_none(value.get("amount"))
    return _float_or_none(value)


def _numeric_delta(baseline: Any, candidate: Any) -> float | None:
    baseline_value = _float_or_none(baseline)
    candidate_value = _float_or_none(candidate)
    if baseline_value is None or candidate_value is None:
        return None
    return round(candidate_value - baseline_value, 8)


def _decision_report_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Comparacao de Relatorios de Decisao",
        "",
        f"- Gerado em: {comparison.get('generated_at')}",
        f"- Baseline: `{comparison.get('baseline_report_path')}`",
        f"- Candidato: `{comparison.get('candidate_report_path')}`",
        "",
        "## Mudancas por etapa",
        "",
    ]
    for stage, changes in (comparison.get("stage_changes") or {}).items():
        lines.append(f"### {stage}")
        for kind in ("cost_benefit", "scale", "premium"):
            delta = changes.get(kind) if isinstance(changes, dict) else None
            if not isinstance(delta, dict):
                continue
            baseline_id = (delta.get("baseline") or {}).get("candidate_id")
            candidate_id = (delta.get("candidate") or {}).get("candidate_id")
            marker = "mudou" if delta.get("changed") else "igual"
            lines.append(f"- {kind}: {marker}, `{baseline_id}` -> `{candidate_id}`{_delta_suffix(delta)}")
        lines.append("")
    lines.extend(["## Rotas", ""])
    for route_name, route_delta in (comparison.get("route_changes") or {}).items():
        changed = route_delta.get("changed") if isinstance(route_delta, dict) else False
        lines.append(f"### {route_name}")
        if not changed:
            lines.append("- Sem mudancas.")
            lines.append("")
            continue
        for stage, field_delta in (route_delta.get("fields") or {}).items():
            lines.append(f"- {stage}: `{field_delta.get('baseline')}` -> `{field_delta.get('candidate')}`")
        lines.append("")
    best = comparison.get("best_single_model_change") if isinstance(comparison.get("best_single_model_change"), dict) else {}
    lines.extend(
        [
            "## Melhor modelo unico",
            "",
            (
                f"- {'Mudou' if best.get('changed') else 'Sem mudanca'}: "
                f"`{(best.get('baseline') or {}).get('candidate_id')}` -> `{(best.get('candidate') or {}).get('candidate_id')}`"
                f"{_delta_suffix(best)}"
            ),
            "",
            "## Riscos",
            "",
        ]
    )
    risks = comparison.get("risk_changes") if isinstance(comparison.get("risk_changes"), dict) else {}
    added = risks.get("added") or []
    removed = risks.get("removed") or []
    if not added and not removed:
        lines.append("- Sem mudancas.")
    for risk in added:
        lines.append(f"- Adicionado: {risk}")
    for risk in removed:
        lines.append(f"- Removido: {risk}")
    return "\n".join(lines).rstrip() + "\n"


def _candidate_summary_for_hub(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    return {
        "candidate_id": candidate.get("candidate_id"),
        "score": candidate.get("cost_benefit_score") or candidate.get("average_cost_benefit_score"),
        "pass_rate": candidate.get("pass_rate") if candidate.get("pass_rate") is not None else candidate.get("min_pass_rate"),
        "failed": candidate.get("failed") if candidate.get("failed") is not None else candidate.get("total_failures"),
        "vetoed": candidate.get("vetoed"),
        "total_tokens": candidate.get("total_tokens"),
        "estimated_money_cost": _candidate_money_amount(candidate.get("estimated_money_cost")),
        "observed_operational_cost_index": candidate.get("observed_operational_cost_index"),
    }


def _latest_textual_triage_summary(root: Path) -> dict[str, Any] | None:
    latest_path = root / "latest-textual-triage.json"
    if not latest_path.exists():
        return None
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        results_path = Path(str(latest.get("results_path") or ""))
        if not results_path.exists():
            return {
                "status": "missing_results",
                "run_id": latest.get("run_id"),
                "results_path": str(results_path),
                "message": "latest-textual-triage.json aponta para um arquivo ausente.",
            }
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        return _triage_summary_for_hub(payload, results_path=results_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "read_error",
            "message": f"Nao foi possivel ler a ultima triagem: {type(exc).__name__}: {str(exc)[:160]}",
        }


def _recent_textual_triage_summaries(root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*/textual_triage_results.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            summaries.append(_triage_summary_for_hub(payload, results_path=path))
        except Exception as exc:  # noqa: BLE001
            summaries.append(
                {
                    "status": "read_error",
                    "run_id": path.parent.name,
                    "results_path": str(path),
                    "message": f"{type(exc).__name__}: {str(exc)[:160]}",
                }
            )
        if len(summaries) >= limit:
            break
    return summaries


def _triage_summary_for_hub(payload: dict[str, Any], *, results_path: Path) -> dict[str, Any]:
    survivors = payload.get("survivors_by_stage") if isinstance(payload.get("survivors_by_stage"), dict) else {}
    stages = []
    for stage in TEXTUAL_TOURNAMENT_STAGES:
        report = (payload.get("triage_reports") or {}).get(stage)
        ranking = report.get("ranking") if isinstance(report, dict) else {}
        rows = []
        for row in (ranking or {}).get("all_candidates") or []:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "candidate_id": row.get("candidate_id"),
                    "pass_rate": row.get("pass_rate"),
                    "success_rate": row.get("success_rate"),
                    "failed": row.get("failed"),
                    "skipped": row.get("skipped"),
                    "vetoed": row.get("vetoed"),
                    "total_tokens": row.get("total_tokens"),
                    "score": row.get("stage_score") if row.get("stage_score") is not None else row.get("script_score"),
                    "survived": row.get("candidate_id") in set(survivors.get(stage) or []),
                }
            )
        stages.append(
            {
                "stage": stage,
                "task_count": report.get("task_count") if isinstance(report, dict) else None,
                "candidate_count": report.get("candidate_count") if isinstance(report, dict) else None,
                "duration_ms": report.get("duration_ms") if isinstance(report, dict) else None,
                "survivors": survivors.get(stage) or [],
                "rows": rows,
                "ranking_path": str(results_path.parent / "triage" / stage / "ranking.json"),
            }
        )
    audit_survivors = survivors.get("audit") or []
    return {
        "status": payload.get("status") or "unknown",
        "run_id": payload.get("run_id"),
        "generated_at": payload.get("generated_at"),
        "duration_ms": payload.get("duration_ms"),
        "triage_mode": payload.get("triage_mode"),
        "min_triage_pass_rate": payload.get("min_triage_pass_rate"),
        "ready_for_full": bool(audit_survivors),
        "block_reason": None if audit_survivors else "Nenhum candidato sobreviveu em audit; nao rode full ainda.",
        "survivors_by_stage": survivors,
        "stages": stages,
        "paths": {
            "run_dir": str(results_path.parent),
            "results": str(results_path),
            "script_ranking": str(results_path.parent / "triage" / "script" / "ranking.json"),
            "repair_ranking": str(results_path.parent / "triage" / "repair" / "ranking.json"),
            "audit_ranking": str(results_path.parent / "triage" / "audit" / "ranking.json"),
        },
    }


def _llm_tournament_missing_report_message(latest_triage: dict[str, Any] | None) -> str:
    if latest_triage and latest_triage.get("ready_for_full"):
        return "A triagem tem sobreviventes em audit, mas a Rodada Textual Completa ainda nao foi gerada."
    if latest_triage:
        return "A ultima triagem nao encontrou sobrevivente em audit; rode nova triagem antes da rodada full."
    return "Nenhuma Rodada Textual Completa do Torneio foi encontrada."


def _llm_tournament_start_command() -> str:
    return (
        "python scripts/run_llm_tournament.py --textual-round --triage-only "
        "--candidate grok-4.20-non-reasoning --candidate minimax-m3 --timeout-sec 35 "
        "--parallelism 2 --max-failures-per-candidate 2"
    )


def _llm_tournament_hub_commands() -> list[dict[str, str]]:
    return [
        {
            "label": "Planejar próxima triagem",
            "description": "Nao chama providers. Use antes de gastar quota.",
            "command": (
                "python scripts/run_llm_tournament.py --textual-round --triage-only --plan-only "
                "--candidate openai-gpt-5.4-nano --candidate deepseek-v4-pro "
                "--timeout-sec 35 --parallelism 2 --max-failures-per-candidate 2"
            ),
        },
        {
            "label": "Rodar próxima triagem",
            "description": "Caminho recomendado agora, porque audit ainda nao tem sobrevivente.",
            "command": (
                "python scripts/run_llm_tournament.py --textual-round --triage-only "
                "--candidate openai-gpt-5.4-nano --candidate deepseek-v4-pro "
                "--timeout-sec 35 --parallelism 2 --max-failures-per-candidate 2"
            ),
        },
        {
            "label": "Rodar full com preços",
            "description": "Use somente depois de audit ter pelo menos um sobrevivente.",
            "command": (
                "python scripts/run_llm_tournament.py --textual-round "
                "--price-table benchmarks/llm/prices.v1.json --triage-mode quick --full-mode full "
                "--timeout-sec 35 --parallelism 2 --max-failures-per-candidate 2"
            ),
        },
        {
            "label": "Regressão focada",
            "description": "Rode depois de cada triagem ou rodada full relevante.",
            "command": "pytest -q tests/test_llm_tournament.py tests/test_llm_tournament_probe.py tests/test_llm_tournament_runner.py",
        },
    ]


def _delta_suffix(delta: dict[str, Any]) -> str:
    parts: list[str] = []
    for field, label in (
        ("score_delta", "score"),
        ("pass_rate_delta", "pass_rate"),
        ("failures_delta", "falhas"),
        ("total_tokens_delta", "tokens"),
        ("estimated_money_cost_delta", "custo"),
    ):
        value = delta.get(field)
        if value is not None:
            parts.append(f"{label}_delta={value}")
    return f" ({', '.join(parts)})" if parts else ""


def _candidate_line(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return "indisponivel"
    candidate_id = candidate.get("candidate_id")
    score = candidate.get("cost_benefit_score") or candidate.get("average_cost_benefit_score")
    pass_rate = candidate.get("pass_rate") or candidate.get("min_pass_rate")
    failures = candidate.get("failed") if "failed" in candidate else candidate.get("total_failures")
    money = candidate.get("estimated_money_cost")
    if isinstance(money, dict):
        money_label = f", custo={money.get('amount')} {money.get('currency')}" if money.get("status") == "estimated" else ", custo=preco_indisponivel"
    elif money is not None:
        money_label = f", custo={money}"
    else:
        money_label = ""
    return f"`{candidate_id}` score={score}, pass_rate={pass_rate}, falhas={failures}{money_label}"


def _first_dict(items: Any) -> dict[str, Any] | None:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                return item
    return None


def probe_llm_tournament_candidate(
    candidate: LlmTournamentCandidate,
    *,
    include_disabled: bool = False,
    dry_run: bool = False,
    timeout_sec: float = 30.0,
) -> LlmTournamentProbeResult:
    configured = candidate.configured
    if not candidate.enabled and not include_disabled:
        return _probe_skipped(candidate, configured, "disabled")
    if not configured:
        return _probe_skipped(candidate, configured, "missing_api_key")
    if dry_run:
        return LlmTournamentProbeResult(
            candidate_id=candidate.candidate_id,
            provider=candidate.provider,
            model=candidate.model,
            enabled=candidate.enabled,
            configured=configured,
            status="dry_run_ready",
        )
    started_at = time.monotonic()
    try:
        raw_text, usage = _probe_candidate_text(candidate, timeout_sec=timeout_sec)
        latency_ms = int((time.monotonic() - started_at) * 1000)
        parsed = json.loads(_extract_json(raw_text) or raw_text)
        json_valid = isinstance(parsed, dict) and parsed.get("ok") is True
        return LlmTournamentProbeResult(
            candidate_id=candidate.candidate_id,
            provider=candidate.provider,
            model=candidate.model,
            enabled=candidate.enabled,
            configured=configured,
            status="passed" if json_valid else "invalid_json_contract",
            latency_ms=latency_ms,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            json_valid=json_valid,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - started_at) * 1000)
        return LlmTournamentProbeResult(
            candidate_id=candidate.candidate_id,
            provider=candidate.provider,
            model=candidate.model,
            enabled=candidate.enabled,
            configured=configured,
            status="failed",
            latency_ms=latency_ms,
            json_valid=False,
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
        )


def _candidate_from_payload(payload: Any) -> LlmTournamentCandidate:
    if not isinstance(payload, dict):
        raise ValueError("llm tournament candidate must be an object")
    candidate_id = str(payload.get("candidate_id") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    api_key_env = str(payload.get("api_key_env") or "").strip()
    roles = tuple(str(role).strip() for role in (payload.get("roles") or []) if str(role).strip())
    if not candidate_id or not provider or not model or not api_key_env or not roles:
        raise ValueError("llm tournament candidate requires candidate_id, provider, model, api_key_env and roles")
    provider_options = payload.get("provider_options")
    return LlmTournamentCandidate(
        candidate_id=candidate_id,
        provider=provider,
        model=model,
        api_key_env=api_key_env,
        roles=roles,
        enabled=bool(payload.get("enabled", True)),
        base_url=str(payload.get("base_url")).strip() if payload.get("base_url") else None,
        provider_options=provider_options if isinstance(provider_options, dict) else {},
    )


def _probe_skipped(candidate: LlmTournamentCandidate, configured: bool, reason: str) -> LlmTournamentProbeResult:
    return LlmTournamentProbeResult(
        candidate_id=candidate.candidate_id,
        provider=candidate.provider,
        model=candidate.model,
        enabled=candidate.enabled,
        configured=configured,
        status=f"skipped_{reason}",
    )


def _probe_candidate_text(candidate: LlmTournamentCandidate, *, timeout_sec: float) -> tuple[str, dict[str, int | None]]:
    provider = candidate.provider.lower()
    if provider == "gemini":
        return _probe_gemini(candidate, timeout_sec=timeout_sec)
    if provider in {"openai", "deepseek", "qwen", "minimax", "openai_compatible"}:
        return _probe_openai_compatible(candidate, timeout_sec=timeout_sec)
    raise ValueError(f"unsupported llm tournament provider: {candidate.provider}")


def _probe_openai_compatible(candidate: LlmTournamentCandidate, *, timeout_sec: float) -> tuple[str, dict[str, int | None]]:
    api_key = _env_value(candidate.api_key_env)
    if not api_key:
        raise ValueError(f"missing api key: {candidate.api_key_env}")
    client = OpenAI(
        api_key=api_key,
        base_url=_candidate_base_url(candidate),
        timeout=timeout_sec,
        max_retries=0,
    )
    if candidate.provider.lower() == "openai":
        response = client.responses.create(
            model=candidate.model,
            instructions="Return valid JSON only. No markdown fences.",
            input=PROBE_PROMPT,
            text={"format": {"type": "json_object"}},
            timeout=timeout_sec,
        )
        return (getattr(response, "output_text", None) or "").strip(), _responses_usage(response)
    extra_body = _candidate_extra_body(candidate)
    request_kwargs = {"extra_body": extra_body} if extra_body else {}
    response = client.chat.completions.create(
        model=candidate.model,
        messages=[
            {"role": "system", "content": "Return valid JSON only. No markdown fences."},
            {"role": "user", "content": PROBE_PROMPT},
        ],
        temperature=_candidate_temperature(candidate),
        timeout=timeout_sec,
        **request_kwargs,
    )
    raw = (response.choices[0].message.content or "").strip()
    return raw, _chat_usage(response)


def _probe_gemini(candidate: LlmTournamentCandidate, *, timeout_sec: float) -> tuple[str, dict[str, int | None]]:
    api_key = _env_value(candidate.api_key_env)
    if not api_key:
        raise ValueError(f"missing api key: {candidate.api_key_env}")
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=int(timeout_sec * 1000)),
    )
    response = client.models.generate_content(
        model=candidate.model,
        contents=PROBE_PROMPT,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return (getattr(response, "text", None) or "").strip(), _gemini_usage(response)


def _candidate_base_url(candidate: LlmTournamentCandidate) -> str | None:
    if candidate.base_url:
        return candidate.base_url
    provider = candidate.provider.lower()
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "deepseek":
        return "https://api.deepseek.com"
    if provider == "qwen":
        return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    if provider == "minimax":
        return "https://api.minimax.io/v1"
    return None


def _candidate_extra_body(candidate: LlmTournamentCandidate) -> dict[str, Any]:
    options = candidate.provider_options or {}
    thinking = str(options.get("thinking") or "").strip().lower()
    if thinking in {"enabled", "disabled"}:
        return {"thinking": {"type": thinking}}
    if candidate.provider.lower() == "minimax" and candidate.model.lower() == "minimax-m3":
        return {"thinking": {"type": "disabled"}}
    return {}


def _candidate_temperature(candidate: LlmTournamentCandidate) -> float:
    options = candidate.provider_options or {}
    value = options.get("temperature")
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _extract_json(raw: str) -> str | None:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    first = stripped.find("{")
    if first == -1:
        return None
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(stripped[first:])
    if not isinstance(parsed, dict):
        return None
    return stripped[first : first + end]


def _responses_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _chat_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _gemini_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    total_tokens = getattr(usage, "total_token_count", None)
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _probe_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    statuses: dict[str, int] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "total": len(results),
        "passed": statuses.get("passed", 0),
        "failed": statuses.get("failed", 0),
        "dry_run_ready": statuses.get("dry_run_ready", 0),
        "skipped_disabled": statuses.get("skipped_disabled", 0),
        "skipped_missing_api_key": statuses.get("skipped_missing_api_key", 0),
        "invalid_json_contract": statuses.get("invalid_json_contract", 0),
    }


def _script_stage_candidates(
    candidates: list[LlmTournamentCandidate],
    candidate_ids: set[str] | None,
) -> list[LlmTournamentCandidate]:
    selected = _stage_candidates(candidates, "script", candidate_ids)
    if not selected:
        raise ValueError("no configured script candidates selected for llm tournament")
    return selected


def _stage_candidates(
    candidates: list[LlmTournamentCandidate],
    stage: str,
    candidate_ids: set[str] | None,
) -> list[LlmTournamentCandidate]:
    selected = [
        candidate
        for candidate in candidates
        if candidate.enabled
        and candidate.configured
        and stage in candidate.roles
        and (not candidate_ids or candidate.candidate_id in candidate_ids)
    ]
    return selected


def _candidate_by_id(candidates: list[LlmTournamentCandidate], candidate_id: str) -> LlmTournamentCandidate:
    for candidate in candidates:
        if candidate.candidate_id == candidate_id:
            if not candidate.configured:
                raise ValueError(f"judge candidate is not configured: {candidate_id}")
            return candidate
    raise ValueError(f"candidate not found: {candidate_id}")


def _benchmark_cases_for_mode(benchmark: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    cases = [case for case in benchmark.get("cases") or [] if isinstance(case, dict)]
    normalized = mode.strip().lower()
    if normalized == "quick":
        return cases[:3]
    if normalized in {"full", "finalists"}:
        return cases
    raise ValueError("mode must be one of: quick, full, finalists")


def _provider_semaphores(candidates: list[LlmTournamentCandidate], *, per_provider_limit: int) -> dict[str, Semaphore]:
    return {
        candidate.provider: Semaphore(max(1, per_provider_limit))
        for candidate in candidates
    }


def _candidate_operational_failure_count(results: list[dict[str, Any]], candidate_id: str) -> int:
    return sum(
        1
        for result in results
        if result.get("candidate_id") == candidate_id
        and result.get("status") == "failed"
        and result.get("failure_type") in {"provider_limit", "timeout", "auth_error", "permission_denied", "model_not_found", "invalid_json"}
    )


def _skipped_after_failure_budget(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    max_failures_per_candidate: int,
    *,
    stage: str = "script",
    fixture_id: str | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "model": candidate.model,
        "case_id": case.get("case_id"),
        "fixture_id": fixture_id,
        "stage": stage,
        "status": "skipped_failure_budget",
        "latency_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "failure_type": "failure_budget_exceeded",
        "error_type": None,
        "error_message": f"skipped after {max_failures_per_candidate} operational failures",
        "vetoes": [],
    }


def _emit_progress(emit_progress: bool, result: dict[str, Any], completed: int, total: int) -> None:
    if not emit_progress:
        return
    print(
        json.dumps(
            {
                "event": "llm_tournament_progress",
                "completed": completed,
                "total": total,
                "candidate_id": result.get("candidate_id"),
                "case_id": result.get("case_id"),
                "fixture_id": result.get("fixture_id"),
                "status": result.get("status"),
                "vetoes": result.get("vetoes") or [],
                "failure_type": result.get("failure_type"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def _judge_script_results(
    results: list[dict[str, Any]],
    *,
    cases: list[dict[str, Any]],
    judge_candidate: LlmTournamentCandidate,
    judge_mode: str,
    judge_top_n: int,
    outputs_dir: Path,
    timeout_sec: float,
    emit_progress: bool,
) -> list[dict[str, Any]]:
    case_by_id = {str(case.get("case_id")): case for case in cases}
    judged_results = [dict(result) for result in results]
    candidates_to_judge = _candidates_for_judging(judged_results, judge_mode=judge_mode, judge_top_n=judge_top_n)
    for index, result in enumerate(list(judged_results)):
        if result.get("candidate_id") not in candidates_to_judge:
            continue
        if result.get("status") != "generated" or result.get("vetoes"):
            continue
        case = case_by_id.get(str(result.get("case_id")))
        if not case:
            continue
        updated = _attach_judge_result(
            result,
            judge_candidate=judge_candidate,
            case=case,
            outputs_dir=outputs_dir,
            timeout_sec=timeout_sec,
        )
        judged_results[index] = updated
        _emit_progress(
            emit_progress,
            {
                **updated,
                "status": f"judge_{updated.get('status')}",
                "failure_type": (updated.get("judge") or {}).get("failure_type"),
            },
            index + 1,
            len(judged_results),
        )
    return judged_results


def _candidates_for_judging(results: list[dict[str, Any]], *, judge_mode: str, judge_top_n: int) -> set[str]:
    if judge_mode == "all":
        return {str(result.get("candidate_id")) for result in results}
    ranking = build_script_stage_ranking(results)
    return {
        str(item.get("candidate_id"))
        for item in ranking.get("recommended_scale_routes", [])[: max(1, int(judge_top_n or 1))]
    }


def _write_tournament_progress(
    base_report: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    results_path: Path,
    ranking_path: Path,
    started_at: float,
    status: str,
) -> None:
    report = {
        **base_report,
        "status": status,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "results": results,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ranking_path.write_text(json.dumps(build_script_stage_ranking(results), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_textual_stage_phase(
    *,
    stage: str,
    phase: str,
    mode: str,
    benchmark: dict[str, Any],
    benchmark_path: Path | str,
    manifest_path: Path | str,
    run_id: str,
    run_dir: Path,
    candidates: list[LlmTournamentCandidate],
    cases: list[dict[str, Any]],
    max_failures_per_candidate: int,
    timeout_sec: float,
    parallelism: int,
    emit_progress: bool,
) -> dict[str, Any]:
    outputs_dir = run_dir / "outputs" / stage
    outputs_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.json"
    ranking_path = run_dir / "ranking.json"
    started_at = time.monotonic()
    provider_semaphores = _provider_semaphores(candidates, per_provider_limit=1)
    tasks = _textual_stage_tasks(candidates, cases, benchmark, stage)
    results: list[dict[str, Any]] = []
    total_tasks = len(tasks)
    max_workers = max(1, int(parallelism or 1))
    base_report = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "mode": mode,
        "benchmark_id": benchmark.get("benchmark_id"),
        "benchmark_path": str(benchmark_path),
        "manifest_path": str(manifest_path),
        "max_failures_per_candidate": max_failures_per_candidate,
        "stage": stage,
        "case_count": len(cases),
        "task_count": len(tasks),
        "candidate_count": len(candidates),
    }
    _write_textual_stage_progress(
        base_report,
        results,
        results_path=results_path,
        ranking_path=ranking_path,
        started_at=started_at,
        status="running",
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending: set[Any] = set()
        task_index = 0
        while task_index < len(tasks) or pending:
            while task_index < len(tasks) and len(pending) < max_workers:
                candidate, case, fixture = tasks[task_index]
                task_index += 1
                current_failures = _candidate_operational_failure_count(results, candidate.candidate_id)
                if current_failures >= max_failures_per_candidate:
                    result = _skipped_after_failure_budget(
                        candidate,
                        case,
                        max_failures_per_candidate,
                        stage=stage,
                        fixture_id=str(fixture.get("fixture_id")) if isinstance(fixture, dict) else None,
                    )
                    results.append(result)
                    _emit_progress(emit_progress, result, len(results), total_tasks)
                    _write_textual_stage_progress(
                        base_report,
                        sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id")), str(item.get("fixture_id") or ""))),
                        results_path=results_path,
                        ranking_path=ranking_path,
                        started_at=started_at,
                        status="running",
                    )
                    continue
                future = executor.submit(
                    _run_textual_stage_case,
                    stage,
                    candidate,
                    case,
                    benchmark,
                    outputs_dir,
                    timeout_sec,
                    provider_semaphores,
                    fixture,
                )
                pending.add(future)
            if not pending:
                continue
            for future in as_completed(pending):
                pending.remove(future)
                result = future.result()
                results.append(result)
                _emit_progress(emit_progress, result, len(results), total_tasks)
                _write_textual_stage_progress(
                    base_report,
                    sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id")), str(item.get("fixture_id") or ""))),
                    results_path=results_path,
                    ranking_path=ranking_path,
                    started_at=started_at,
                    status="running",
                )
                break

    results = sorted(results, key=lambda item: (str(item.get("candidate_id")), str(item.get("case_id")), str(item.get("fixture_id") or "")))
    ranking = build_textual_stage_ranking(results, stage=stage)
    report = {
        **base_report,
        "status": "completed",
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "results": results,
        "ranking": ranking,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ranking_path.write_text(json.dumps(ranking, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**report, "run_dir": str(run_dir)}


def _write_textual_stage_progress(
    base_report: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    results_path: Path,
    ranking_path: Path,
    started_at: float,
    status: str,
) -> None:
    stage = str(base_report.get("stage") or "")
    report = {
        **base_report,
        "status": status,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "results": results,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ranking_path.write_text(json.dumps(build_textual_stage_ranking(results, stage=stage), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _empty_textual_stage_report(
    *,
    stage: str,
    phase: str,
    mode: str,
    benchmark: dict[str, Any],
    benchmark_path: Path | str,
    manifest_path: Path | str,
    run_id: str,
    run_dir: Path,
    cases: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    ranking = build_textual_stage_ranking([], stage=stage)
    report = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "skipped",
        "skip_reason": reason,
        "phase": phase,
        "mode": mode,
        "benchmark_id": benchmark.get("benchmark_id"),
        "benchmark_path": str(benchmark_path),
        "manifest_path": str(manifest_path),
        "stage": stage,
        "case_count": len(cases),
        "candidate_count": 0,
        "duration_ms": 0,
        "results": [],
        "ranking": ranking,
        "run_dir": str(run_dir),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "ranking.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _textual_stage_tasks(
    candidates: list[LlmTournamentCandidate],
    cases: list[dict[str, Any]],
    benchmark: dict[str, Any],
    stage: str,
) -> list[tuple[LlmTournamentCandidate, dict[str, Any], dict[str, Any] | None]]:
    tasks: list[tuple[LlmTournamentCandidate, dict[str, Any], dict[str, Any] | None]] = []
    for case in cases:
        if stage == "audit":
            fixtures = _audit_fixtures_for_case(case, benchmark)
        elif stage == "repair":
            fixtures = _repair_fixtures_for_case(case, benchmark)
        else:
            fixtures = [None]
        for fixture in fixtures:
            for candidate in candidates:
                tasks.append((candidate, case, fixture))
    return tasks


def _run_textual_stage_case(
    stage: str,
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    benchmark: dict[str, Any],
    outputs_dir: Path,
    timeout_sec: float,
    provider_semaphores: dict[str, Semaphore],
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage == "script":
        return _run_script_stage_case(candidate, case, benchmark, outputs_dir, timeout_sec, provider_semaphores)
    if stage == "repair":
        return _run_repair_stage_case(candidate, case, benchmark, outputs_dir, timeout_sec, provider_semaphores, fixture)
    if stage == "audit":
        return _run_audit_stage_case(candidate, case, benchmark, outputs_dir, timeout_sec, provider_semaphores, fixture)
    raise ValueError(f"unsupported textual tournament stage: {stage}")


def _run_script_stage_case(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    benchmark: dict[str, Any],
    outputs_dir: Path,
    timeout_sec: float,
    provider_semaphores: dict[str, Semaphore],
) -> dict[str, Any]:
    started_at = time.monotonic()
    prompt = _build_script_stage_prompt(case, benchmark)
    output_path = outputs_dir / f"{_safe_filename(case['case_id'])}__{_safe_filename(candidate.candidate_id)}.json"
    semaphore = provider_semaphores.get(candidate.provider) or Semaphore(1)
    try:
        with semaphore:
            raw_text, usage = _candidate_json_completion(candidate, prompt, timeout_sec=timeout_sec)
        parsed = json.loads(_extract_json(raw_text) or raw_text)
        vetoes = deterministic_script_vetoes(parsed, case)
        result = {
            "candidate_id": candidate.candidate_id,
            "provider": candidate.provider,
            "model": candidate.model,
            "case_id": case.get("case_id"),
            "stage": "script",
            "status": "generated",
            "latency_ms": int((time.monotonic() - started_at) * 1000),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "vetoes": vetoes,
            "output_path": str(output_path),
        }
        output_path.write_text(
            json.dumps(
                {
                    "candidate": _candidate_public_payload(candidate),
                    "case_id": case.get("case_id"),
                    "prompt": prompt,
                    "raw_text": raw_text,
                    "parsed": parsed,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result = {
            "candidate_id": candidate.candidate_id,
            "provider": candidate.provider,
            "model": candidate.model,
            "case_id": case.get("case_id"),
            "stage": "script",
            "status": "failed",
            "latency_ms": int((time.monotonic() - started_at) * 1000),
            "failure_type": _classify_provider_exception(exc),
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
            "vetoes": [],
            "output_path": str(output_path),
        }
        output_path.write_text(
            json.dumps(
                {
                    "candidate": _candidate_public_payload(candidate),
                    "case_id": case.get("case_id"),
                    "prompt": prompt,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return result


def _run_repair_stage_case(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    benchmark: dict[str, Any],
    outputs_dir: Path,
    timeout_sec: float,
    provider_semaphores: dict[str, Semaphore],
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    fixture = fixture or _repair_fixture_for_case(case, benchmark)
    prompt = _build_repair_stage_prompt(case, benchmark, fixture)
    output_path = outputs_dir / f"{_safe_filename(case['case_id'])}__{_safe_filename(str(fixture.get('fixture_id')))}__{_safe_filename(candidate.candidate_id)}.json"
    semaphore = provider_semaphores.get(candidate.provider) or Semaphore(1)
    try:
        with semaphore:
            raw_text, usage = _candidate_json_completion(candidate, prompt, timeout_sec=timeout_sec)
        parsed = json.loads(_extract_json(raw_text) or raw_text)
        vetoes = deterministic_repair_vetoes(parsed, case, fixture)
        result = _textual_result(
            candidate,
            case,
            stage="repair",
            status="generated",
            started_at=started_at,
            usage=usage,
            vetoes=vetoes,
            output_path=output_path,
            fixture_id=str(fixture.get("fixture_id")),
        )
        output_path.write_text(
            json.dumps(
                {
                    "candidate": _candidate_public_payload(candidate),
                    "case_id": case.get("case_id"),
                    "fixture": fixture,
                    "prompt": prompt,
                    "raw_text": raw_text,
                    "parsed": parsed,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_textual_stage_case(
            candidate,
            case,
            stage="repair",
            started_at=started_at,
            output_path=output_path,
            prompt=prompt,
            exc=exc,
            fixture_id=str(fixture.get("fixture_id")),
        )


def _run_audit_stage_case(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    benchmark: dict[str, Any],
    outputs_dir: Path,
    timeout_sec: float,
    provider_semaphores: dict[str, Semaphore],
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    fixture = fixture or _audit_fixtures_for_case(case, benchmark)[0]
    prompt = _build_audit_stage_prompt(case, benchmark, fixture)
    output_path = outputs_dir / f"{_safe_filename(case['case_id'])}__{_safe_filename(str(fixture.get('fixture_id')))}__{_safe_filename(candidate.candidate_id)}.json"
    semaphore = provider_semaphores.get(candidate.provider) or Semaphore(1)
    try:
        with semaphore:
            raw_text, usage = _candidate_json_completion(candidate, prompt, timeout_sec=timeout_sec)
        parsed = json.loads(_extract_json(raw_text) or raw_text)
        vetoes = deterministic_audit_vetoes(parsed, fixture)
        metrics = _audit_decision_metrics(parsed, fixture)
        result = {
            **_textual_result(
                candidate,
                case,
                stage="audit",
                status="generated",
                started_at=started_at,
                usage=usage,
                vetoes=vetoes,
                output_path=output_path,
                fixture_id=str(fixture.get("fixture_id")),
            ),
            "audit_metrics": metrics,
        }
        output_path.write_text(
            json.dumps(
                {
                    "candidate": _candidate_public_payload(candidate),
                    "case_id": case.get("case_id"),
                    "fixture": fixture,
                    "prompt": prompt,
                    "raw_text": raw_text,
                    "parsed": parsed,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_textual_stage_case(
            candidate,
            case,
            stage="audit",
            started_at=started_at,
            output_path=output_path,
            prompt=prompt,
            exc=exc,
            fixture_id=str(fixture.get("fixture_id")),
        )


def _textual_result(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    *,
    stage: str,
    status: str,
    started_at: float,
    usage: dict[str, int | None],
    vetoes: list[str],
    output_path: Path,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "model": candidate.model,
        "case_id": case.get("case_id"),
        "fixture_id": fixture_id,
        "stage": stage,
        "status": status,
        "latency_ms": int((time.monotonic() - started_at) * 1000),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "vetoes": vetoes,
        "output_path": str(output_path),
    }


def _failed_textual_stage_case(
    candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    *,
    stage: str,
    started_at: float,
    output_path: Path,
    prompt: str,
    exc: Exception,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    result = {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "model": candidate.model,
        "case_id": case.get("case_id"),
        "fixture_id": fixture_id,
        "stage": stage,
        "status": "failed",
        "latency_ms": int((time.monotonic() - started_at) * 1000),
        "failure_type": _classify_provider_exception(exc),
        "error_type": type(exc).__name__,
        "error_message": str(exc)[:500],
        "vetoes": [],
        "output_path": str(output_path),
    }
    output_path.write_text(
        json.dumps(
            {
                "candidate": _candidate_public_payload(candidate),
                "case_id": case.get("case_id"),
                "prompt": prompt,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def _attach_judge_result(
    result: dict[str, Any],
    *,
    judge_candidate: LlmTournamentCandidate,
    case: dict[str, Any],
    outputs_dir: Path,
    timeout_sec: float,
) -> dict[str, Any]:
    output_path = Path(str(result.get("output_path") or ""))
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        script = payload.get("parsed")
        judge_prompt = _build_judge_prompt(case, script)
        raw_text, usage = _candidate_json_completion(judge_candidate, judge_prompt, timeout_sec=timeout_sec)
        judge = json.loads(_extract_json(raw_text) or raw_text)
        normalized = _normalize_judge_payload(judge)
        judged_result = {
            **result,
            "status": "judged",
            "judge": {
                **normalized,
                "status": "passed",
                "judge_candidate_id": judge_candidate.candidate_id,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        }
        judge_path = outputs_dir / f"{_safe_filename(case['case_id'])}__{_safe_filename(result['candidate_id'])}__judge.json"
        judge_path.write_text(
            json.dumps(
                {
                    "judge_candidate": _candidate_public_payload(judge_candidate),
                    "case_id": case.get("case_id"),
                    "candidate_id": result.get("candidate_id"),
                    "prompt": judge_prompt,
                    "raw_text": raw_text,
                    "parsed": normalized,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        payload["result"] = judged_result
        payload["judge_output_path"] = str(judge_path)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return judged_result
    except Exception as exc:  # noqa: BLE001
        return {
            **result,
            "status": "judge_failed",
            "judge": {
                "status": "failed",
                "judge_candidate_id": judge_candidate.candidate_id,
                "failure_type": _classify_provider_exception(exc),
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        }


def _build_script_stage_prompt(case: dict[str, Any], benchmark: dict[str, Any]) -> str:
    plan = _case_plan(case, benchmark)
    return f"""
Escreva um Roteiro Viral Estruturado para YouTube Shorts em pt-BR.
Entrada JSON: {json.dumps(plan, ensure_ascii=False)}

Retorne JSON estrito com exatamente estes campos:
title, hook, body_beats, ending, cta, full_narration, estimated_duration_sec, key_facts, source_fact_ids, claim_trace, token_count, language, retention_map, visual_opening, qa_metrics, prompt_version

Tipos obrigatorios:
- body_beats deve ser array de strings, nao objetos.
- key_facts deve ser array de strings.
- source_fact_ids deve ser array de strings.
- claim_trace deve ser array de objetos com text, source_fact_ids e grounding.

Regras obrigatorias:
- prompt_version deve ser "{EDITORIAL_PROMPT_VERSION}".
- 35 a 55 segundos, com 80 a 120 palavras quando possivel.
- primeira frase com no maximo 12 palavras.
- hook agressivo nos primeiros 0 a 2 segundos, sem "voce sabia", "ja imaginou" ou introducao generica.
- body_beats deve ter pelo menos 3 beats em escalada: tensao, prova, virada e payoff tardio.
- ending deve fechar o loop e fazer o inicio ganhar novo sentido no replay.
- todos os campos narrados devem estar em portugues do Brasil.
- nao use markdown, SSML, tags, ingles decorativo, travessao ou en dash.
- cta deve ser null.
- use fact_pack.evidence_cards como fonte factual e editorial preferencial.
- use aggressive_hook_options sem ultrapassar claim, safe_language e do_not_claim.
- use retention_use para organizar hook, loop, escalada, payoff e loop_close.
- use visual_metaphors para imagem mental e visual_opening quando fizer sentido.
- toda afirmacao factual de risco deve caber em claim ou safe_language de evidence_cards com allowed_script_use=true.
- nunca afirme nada listado em do_not_claim, nem como metafora.
- source_fact_ids deve conter apenas fact_id existentes em fact_pack.facts.
- claim_trace deve mapear cada afirmacao factual de risco para fact_id existentes; se nao houver lastro, remova a afirmacao.
- key_facts deve refletir apenas fatos realmente usados no roteiro.
- nao cite fontes no texto narrado.

qa_metrics deve incluir hook_score, clarity_score, information_density_score, ending_strength_score e script_gate_pass.
Sem markdown.
""".strip()


def _build_repair_stage_prompt(case: dict[str, Any], benchmark: dict[str, Any], fixture: dict[str, Any]) -> str:
    plan = _case_plan(case, benchmark)
    payload = {
        "fixture_id": fixture.get("fixture_id"),
        "fixture_kind": fixture.get("fixture_kind"),
        "plan": plan,
        "broken_script": fixture["broken_script"],
        "known_issue_slugs": fixture["expected_issue_slugs"],
    }
    return f"""
Repare um Roteiro Viral Estruturado para YouTube Shorts em pt-BR.
Entrada JSON: {json.dumps(payload, ensure_ascii=False)}

Retorne JSON estrito com exatamente estes campos:
repaired_script, fixed_issue_slugs, remaining_issue_slugs, repair_notes

Regras obrigatorias:
- repaired_script deve seguir o mesmo contrato de roteiro: title, hook, body_beats, ending, cta, full_narration, estimated_duration_sec, key_facts, source_fact_ids, claim_trace, token_count, language, retention_map, visual_opening, qa_metrics, prompt_version.
- remova claims proibidas por do_not_claim.
- quando uma promessa depender de claim irrecuperavel, remova a promessa e reconstrua o loop com fatos permitidos.
- corrija idioma, estilo, rastreabilidade e estrutura sem inventar fatos novos.
- preserve apenas fatos cobertos por fact_pack.evidence_cards com allowed_script_use=true.
- source_fact_ids e claim_trace devem usar apenas fact_id existentes.
- 35 a 55 segundos, pt-BR natural, sem markdown, SSML, tags, travessao ou en dash.
- fixed_issue_slugs deve listar problemas corrigidos.
- remaining_issue_slugs deve ser [] quando o roteiro ficou publicavel.
- cta deve ser null.
Sem markdown.
""".strip()


def _build_audit_stage_prompt(case: dict[str, Any], benchmark: dict[str, Any], fixture: dict[str, Any]) -> str:
    payload = {
        "fixture_id": fixture.get("fixture_id"),
        "fixture_kind": fixture.get("fixture_kind"),
        "case": {
            "case_id": case.get("case_id"),
            "topic": case.get("topic"),
            "case_type": case.get("case_type"),
            "retention_brief": case.get("retention_brief"),
            "fact_pack": case.get("fact_pack"),
            "benchmark_id": benchmark.get("benchmark_id"),
        },
        "script_to_audit": fixture["script_to_audit"],
    }
    return f"""
Audite um roteiro de YouTube Shorts para decidir se ele pode seguir para producao.
Entrada JSON: {json.dumps(payload, ensure_ascii=False)}

Retorne JSON estrito com exatamente estes campos:
decision, reason_slugs, severity, detected_issue_slugs

Valores permitidos:
- decision: approve, block ou repair.
- severity: low, medium ou high.

Regras obrigatorias:
- bloqueie claims listadas em do_not_claim.
- bloqueie fact_id inventado, ausencia de source_fact_ids ou claim_trace vazio em afirmacoes factuais de risco.
- peca repair para claim parcialmente suportada, exagero corrigivel, estrutura fraca, idioma errado ou rastreabilidade incompleta.
- peca repair quando o problema for corrigivel sem trocar tema.
- aprove apenas quando o roteiro estiver factual, rastreavel e dentro do contrato editorial.
- detected_issue_slugs deve usar slugs curtos e concretos.
Sem markdown.
""".strip()


def _case_plan(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    topic = str(case.get("topic") or "").strip()
    target_duration = int(case.get("target_duration_sec") or 45)
    plan = {
        "canonical_topic": topic,
        "angle": case.get("retention_brief", {}).get("hook_direction") or topic,
        "hook_promise": case.get("retention_brief", {}).get("loop_question") or topic,
        "title_candidates": [topic],
        "editorial_mode": "viral_curiosidades",
        "evidence_profile": case.get("evidence_profile"),
        "target_duration_sec": target_duration,
        "case_id": case.get("case_id"),
        "case_type": case.get("case_type"),
        "benchmark_id": benchmark.get("benchmark_id"),
        "editorial_prompt_version": benchmark.get("prompt_version") or EDITORIAL_PROMPT_VERSION,
        "retention_brief": case.get("retention_brief") or {},
        "retention_map": build_retention_map(target_duration),
        "fact_pack": case.get("fact_pack") or {},
    }
    plan["visual_opening"] = build_visual_opening_brief(plan)
    return plan


def _repair_fixtures_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = str(case.get("case_id") or "case")
    return [
        {
            "fixture_id": f"{case_id}-repair-forbidden-v1",
            "fixture_kind": "factual_repair",
            "broken_script": _broken_script_for_case(case, benchmark),
            "expected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "fixture_id": f"{case_id}-repair-missing-trace-v1",
            "fixture_kind": "missing_trace",
            "broken_script": _repairable_audit_script_for_case(case, benchmark),
            "expected_issue_slugs": ["missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "fixture_id": f"{case_id}-repair-structure-v1",
            "fixture_kind": "structure",
            "broken_script": _weak_structure_script_for_case(case, benchmark),
            "expected_issue_slugs": ["generic_hook_opening", "too_short_for_shorts", "too_few_sentences"],
        },
        {
            "fixture_id": f"{case_id}-repair-language-style-v1",
            "fixture_kind": "language_style",
            "broken_script": _language_style_script_for_case(case, benchmark),
            "expected_issue_slugs": ["language_not_pt_br", "disallowed_dash"],
        },
        {
            "fixture_id": f"{case_id}-repair-invented-source-v1",
            "fixture_kind": "traceability",
            "broken_script": _invented_source_script_for_case(case, benchmark),
            "expected_issue_slugs": ["invented_source_fact_ids"],
        },
        {
            "fixture_id": f"{case_id}-repair-unrecoverable-v1",
            "fixture_kind": "unrecoverable_claim",
            "broken_script": _irrecoverable_script_for_case(case, benchmark),
            "expected_issue_slugs": ["forbidden_claim", "unrecoverable_claim_removed"],
        },
    ]


def _repair_fixture_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    return _repair_fixtures_for_case(case, benchmark)[0]


def _audit_fixtures_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = str(case.get("case_id") or "case")
    return [
        {
            "fixture_id": f"{case_id}-audit-approve-v1",
            "fixture_kind": "approve",
            "script_to_audit": _grounded_script_for_case(case, benchmark),
            "expected_decision": "approve",
            "expected_issue_slugs": [],
        },
        {
            "fixture_id": f"{case_id}-audit-repair-v1",
            "fixture_kind": "repair",
            "script_to_audit": _repairable_audit_script_for_case(case, benchmark),
            "expected_decision": "repair",
            "expected_issue_slugs": ["missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "fixture_id": f"{case_id}-audit-block-v1",
            "fixture_kind": "block",
            "script_to_audit": _broken_script_for_case(case, benchmark),
            "expected_decision": "block",
            "expected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "fixture_id": f"{case_id}-audit-false-block-guard-v1",
            "fixture_kind": "false_block_guard",
            "script_to_audit": _grounded_script_for_case(case, benchmark),
            "expected_decision": "approve",
            "expected_issue_slugs": [],
        },
        {
            "fixture_id": f"{case_id}-audit-improper-approval-v1",
            "fixture_kind": "improper_approval_guard",
            "script_to_audit": _broken_script_for_case(case, benchmark),
            "expected_decision": "block",
            "expected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "fixture_id": f"{case_id}-audit-partial-support-v1",
            "fixture_kind": "partial_support",
            "script_to_audit": _partial_support_script_for_case(case, benchmark),
            "expected_decision": "repair",
            "expected_issue_slugs": ["partially_supported_claim"],
        },
    ]


def _audit_fixture_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    return _audit_fixtures_for_case(case, benchmark)[-1]


def _grounded_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    plan = _case_plan(case, benchmark)
    facts = [fact for fact in (case.get("fact_pack") or {}).get("facts") or [] if isinstance(fact, dict)]
    fact_ids = [str(fact.get("fact_id")) for fact in facts if fact.get("fact_id")]
    fact_claims = [str(fact.get("claim") or "").strip() for fact in facts if str(fact.get("claim") or "").strip()]
    topic = str(case.get("topic") or "curiosidade")
    first_fact = fact_claims[0] if fact_claims else topic
    second_fact = fact_claims[1] if len(fact_claims) > 1 else first_fact
    narration = (
        f"{topic} parece simples, mas tem uma pegadinha. "
        f"A base segura e esta: {first_fact} "
        f"Tambem importa lembrar que {second_fact} "
        "Entao a virada nao e uma promessa extrema, e sim o limite do que a evidencia permite. "
        "No fim, a melhor resposta e mais cuidadosa do que o boato."
    )
    return {
        "title": topic,
        "hook": f"{topic} tem uma pegadinha.",
        "body_beats": [
            f"A primeira pista e: {first_fact}",
            f"A segunda pista limita o exagero: {second_fact}",
            "A conclusao fica forte sem ultrapassar a evidencia.",
        ],
        "ending": "No fim, a melhor resposta e mais cuidadosa do que o boato.",
        "cta": None,
        "full_narration": narration,
        "estimated_duration_sec": int(plan.get("target_duration_sec") or 45),
        "key_facts": fact_claims[:2],
        "source_fact_ids": fact_ids[:2],
        "claim_trace": [
            {"text": claim, "source_fact_ids": [fact_id], "grounding": "fact_pack"}
            for claim, fact_id in zip(fact_claims[:2], fact_ids[:2], strict=False)
        ],
        "token_count": len(word_tokens(narration)),
        "language": "pt-BR",
        "retention_map": plan.get("retention_map") or {},
        "visual_opening": plan.get("visual_opening") or {},
        "qa_metrics": {"script_gate_pass": True},
        "prompt_version": benchmark.get("prompt_version") or EDITORIAL_PROMPT_VERSION,
    }


def _repairable_audit_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _grounded_script_for_case(case, benchmark)
    script["source_fact_ids"] = []
    script["claim_trace"] = []
    script["qa_metrics"] = {"script_gate_pass": False}
    return script


def _weak_structure_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _grounded_script_for_case(case, benchmark)
    topic = str(case.get("topic") or "curiosidade")
    narration = f"Voce sabia? {topic} tem uma explicacao simples. No fim, era isso."
    script.update(
        {
            "hook": "Voce sabia?",
            "body_beats": ["Tem uma explicacao simples."],
            "ending": "No fim, era isso.",
            "full_narration": narration,
            "estimated_duration_sec": 18,
            "token_count": len(word_tokens(narration)),
            "qa_metrics": {"script_gate_pass": False},
        }
    )
    return script


def _language_style_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _grounded_script_for_case(case, benchmark)
    topic = str(case.get("topic") or "curiosidade")
    narration = (
        f"This short explains {topic} with a dramatic twist — but it stops sounding like pt-BR. "
        "The idea may be factual, but the narration breaks the language contract and uses a forbidden dash. "
        "A repair must bring the rhythm back to natural Brazilian Portuguese. "
        "The final version also needs to keep the evidence trace intact."
    )
    script.update(
        {
            "hook": f"This short explains {topic}.",
            "body_beats": [
                "The narration is in English.",
                "It uses a forbidden dash.",
                "It must be rewritten without changing the factual basis.",
            ],
            "ending": "The final version needs natural pt-BR.",
            "full_narration": narration,
            "language": "en-US",
            "token_count": len(word_tokens(narration)),
            "qa_metrics": {"script_gate_pass": False},
        }
    )
    return script


def _invented_source_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _grounded_script_for_case(case, benchmark)
    script["source_fact_ids"] = list(script.get("source_fact_ids") or []) + ["F999"]
    script["claim_trace"] = list(script.get("claim_trace") or []) + [
        {"text": "Afirmação rastreada para uma fonte inexistente.", "source_fact_ids": ["F999"], "grounding": "fact_pack"}
    ]
    script["qa_metrics"] = {"script_gate_pass": False}
    return script


def _partial_support_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _grounded_script_for_case(case, benchmark)
    topic = str(case.get("topic") or "curiosidade")
    overreach = f"Por isso, {topic} sempre prova uma regra geral em qualquer pessoa."
    script["full_narration"] = f"{script.get('full_narration')} {overreach}"
    script["body_beats"] = list(script.get("body_beats") or []) + [overreach]
    script["key_facts"] = list(script.get("key_facts") or []) + [overreach]
    script["claim_trace"] = list(script.get("claim_trace") or []) + [
        {"text": overreach, "source_fact_ids": list(script.get("source_fact_ids") or [])[:1], "grounding": "partial_overreach"}
    ]
    script["token_count"] = len(word_tokens(str(script.get("full_narration") or "")))
    script["qa_metrics"] = {"script_gate_pass": False}
    return script


def _irrecoverable_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    script = _broken_script_for_case(case, benchmark)
    topic = str(case.get("topic") or "curiosidade")
    script["full_narration"] = (
        f"O roteiro inteiro depende de uma promessa proibida sobre {topic}. "
        f"{script.get('full_narration')} "
        "Se essa promessa sair, o roteiro precisa trocar o centro narrativo e reconstruir o loop."
    )
    script["token_count"] = len(word_tokens(str(script.get("full_narration") or "")))
    return script


def _broken_script_for_case(case: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    plan = _case_plan(case, benchmark)
    fact_pack = case.get("fact_pack") if isinstance(case.get("fact_pack"), dict) else {}
    evidence_cards = [card for card in fact_pack.get("evidence_cards") or [] if isinstance(card, dict)]
    card = evidence_cards[0] if evidence_cards else {}
    forbidden = str((card.get("do_not_claim") or ["fato proibido sem fonte"])[0])
    topic = str(case.get("topic") or "curiosidade")
    narration = (
        f"Voce sabia que {forbidden}? "
        f"Isso muda tudo sobre {topic}. "
        "O detalhe parece pequeno, mas prova uma conclusao maior sem precisar de fonte. "
        "No fim, a resposta e mais extrema do que parece."
    )
    return {
        "title": topic,
        "hook": f"Voce sabia que {forbidden}?",
        "body_beats": [
            f"A ideia central e que {forbidden}.",
            "O roteiro usa essa frase como se fosse fato confirmado.",
            "A conclusao amplia a promessa sem rastrear evidencia.",
        ],
        "ending": "No fim, a resposta e mais extrema do que parece.",
        "cta": None,
        "full_narration": narration,
        "estimated_duration_sec": int(plan.get("target_duration_sec") or 45),
        "key_facts": [forbidden],
        "source_fact_ids": [],
        "claim_trace": [],
        "token_count": len(word_tokens(narration)),
        "language": "pt-BR",
        "retention_map": plan.get("retention_map") or {},
        "visual_opening": plan.get("visual_opening") or {},
        "qa_metrics": {"script_gate_pass": False},
        "prompt_version": benchmark.get("prompt_version") or EDITORIAL_PROMPT_VERSION,
    }


def _build_judge_prompt(case: dict[str, Any], script: Any) -> str:
    payload = {
        "case": {
            "case_id": case.get("case_id"),
            "topic": case.get("topic"),
            "case_type": case.get("case_type"),
            "retention_brief": case.get("retention_brief"),
            "fact_pack": case.get("fact_pack"),
        },
        "script": script,
    }
    return f"""
Voce e o Juiz Editorial Versionado judge-editorial-v1 do Torneio de LLMs.
Avalie se o roteiro abaixo e forte para Shorts, factual, agressivo sem mentir e fiel aos Cartoes de Evidencia.
Entrada JSON: {json.dumps(payload, ensure_ascii=False)}

Responda JSON estrito com:
factual_obedience_score, hook_strength_score, loop_replay_score, escalation_payoff_score, pt_br_clarity_score, viral_retention_score, overall_score, reasons, hard_concerns

Escala:
- scores de 0 a 1.
- factual_obedience_score mede obediencia a evidence_cards, safe_language e do_not_claim.
- hook_strength_score mede forca dos primeiros segundos sem clickbait falso.
- loop_replay_score mede tensao aberta e vontade de reassistir.
- escalation_payoff_score mede progressao e payoff tardio.
- pt_br_clarity_score mede naturalidade brasileira, ritmo oral e clareza.
- viral_retention_score mede potencial de retencao e compartilhamento.
- overall_score deve refletir qualidade publicavel, nao apenas texto bonito.

Regras:
- Penalize forte qualquer claim fora dos Cartoes de Evidencia.
- Penalize linguagem generica de IA, aula enciclopedica, final meta ou payoff cedo.
- Nao premie sensacionalismo falso.
- hard_concerns deve listar slugs curtos quando houver risco serio.
Sem markdown.
""".strip()


def _candidate_json_completion(
    candidate: LlmTournamentCandidate,
    prompt: str,
    *,
    timeout_sec: float,
) -> tuple[str, dict[str, int | None]]:
    provider = candidate.provider.lower()
    if provider == "gemini":
        return _gemini_json_completion(candidate, prompt, timeout_sec=timeout_sec)
    if provider in {"openai", "deepseek", "qwen", "minimax", "openai_compatible"}:
        return _openai_compatible_json_completion(candidate, prompt, timeout_sec=timeout_sec)
    raise ValueError(f"unsupported llm tournament provider: {candidate.provider}")


def _openai_compatible_json_completion(
    candidate: LlmTournamentCandidate,
    prompt: str,
    *,
    timeout_sec: float,
) -> tuple[str, dict[str, int | None]]:
    api_key = _env_value(candidate.api_key_env)
    if not api_key:
        raise ValueError(f"missing api key: {candidate.api_key_env}")
    client = OpenAI(
        api_key=api_key,
        base_url=_candidate_base_url(candidate),
        timeout=timeout_sec,
        max_retries=0,
    )
    if candidate.provider.lower() == "openai":
        response = client.responses.create(
            model=candidate.model,
            instructions="Return valid JSON only. No markdown fences.",
            input=prompt,
            text={"format": {"type": "json_object"}},
            timeout=timeout_sec,
        )
        return (getattr(response, "output_text", None) or "").strip(), _responses_usage(response)
    extra_body = _candidate_extra_body(candidate)
    request_kwargs = {"extra_body": extra_body} if extra_body else {}
    response = client.chat.completions.create(
        model=candidate.model,
        messages=[
            {"role": "system", "content": "Return valid JSON only. No markdown fences."},
            {"role": "user", "content": prompt},
        ],
        temperature=_candidate_temperature(candidate),
        timeout=timeout_sec,
        **request_kwargs,
    )
    return (response.choices[0].message.content or "").strip(), _chat_usage(response)


def _gemini_json_completion(
    candidate: LlmTournamentCandidate,
    prompt: str,
    *,
    timeout_sec: float,
) -> tuple[str, dict[str, int | None]]:
    api_key = _env_value(candidate.api_key_env)
    if not api_key:
        raise ValueError(f"missing api key: {candidate.api_key_env}")
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=int(timeout_sec * 1000)),
    )
    response = client.models.generate_content(
        model=candidate.model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=_candidate_temperature(candidate),
        ),
    )
    return (getattr(response, "text", None) or "").strip(), _gemini_usage(response)


def _normalize_judge_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("judge returned non-object json")
    score_fields = [
        "factual_obedience_score",
        "hook_strength_score",
        "loop_replay_score",
        "escalation_payoff_score",
        "pt_br_clarity_score",
        "viral_retention_score",
        "overall_score",
    ]
    normalized: dict[str, Any] = {}
    for field in score_fields:
        value = _float_or_none(payload.get(field))
        normalized[field] = max(0.0, min(1.0, value if value is not None else 0.0))
    reasons = payload.get("reasons")
    hard_concerns = payload.get("hard_concerns")
    normalized["reasons"] = [str(item).strip() for item in reasons if str(item).strip()] if isinstance(reasons, list) else []
    normalized["hard_concerns"] = [str(item).strip() for item in hard_concerns if str(item).strip()] if isinstance(hard_concerns, list) else []
    return normalized


def _candidate_public_payload(candidate: LlmTournamentCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "model": candidate.model,
        "roles": list(candidate.roles),
        "base_url": candidate.base_url,
        "provider_options": candidate.provider_options or {},
    }


def _classify_provider_exception(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "rate" in text or "quota" in text or "limit" in text or "429" in text or "credit" in text:
        return "provider_limit"
    if "auth" in text or "unauthorized" in text or "api key" in text or "401" in text:
        return "auth_error"
    if "not found" in text or "model" in text and "404" in text:
        return "model_not_found"
    if "permission" in text or "403" in text:
        return "permission_denied"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return "provider_error"


def _script_narrated_text(script: dict[str, Any]) -> str:
    pieces: list[str] = [
        str(script.get("title") or ""),
        str(script.get("hook") or ""),
        " ".join(str(item) for item in script.get("body_beats") or []),
        str(script.get("ending") or ""),
        str(script.get("full_narration") or ""),
        " ".join(str(item) for item in script.get("key_facts") or []),
    ]
    return " ".join(piece for piece in pieces if piece)


def _has_disallowed_unicode(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))


def _contains_forbidden_claim(text: str, case: dict[str, Any]) -> bool:
    normalized_text = _normalize_text(text)
    fact_pack = case.get("fact_pack") if isinstance(case.get("fact_pack"), dict) else {}
    for card in fact_pack.get("evidence_cards") or []:
        if not isinstance(card, dict):
            continue
        for forbidden in card.get("do_not_claim") or []:
            normalized_forbidden = _normalize_text(str(forbidden))
            if normalized_forbidden and normalized_forbidden in normalized_text:
                return True
    return False


def _case_fact_ids(case: dict[str, Any]) -> set[str]:
    fact_pack = case.get("fact_pack") if isinstance(case.get("fact_pack"), dict) else {}
    return {
        str(fact.get("fact_id"))
        for fact in fact_pack.get("facts") or []
        if isinstance(fact, dict) and fact.get("fact_id")
    }


def _script_used_fact_ids(script: dict[str, Any]) -> set[str]:
    source_ids = script.get("source_fact_ids") or []
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    used = {str(item) for item in source_ids if str(item).strip()}
    trace = script.get("claim_trace")
    if isinstance(trace, list):
        for item in trace:
            if not isinstance(item, dict):
                continue
            for source_id in item.get("source_fact_ids") or []:
                if str(source_id).strip():
                    used.add(str(source_id))
    return used


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: Any) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return sum(nums) / len(nums) if nums else None


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
    normalized = normalized.replace("é", "e").replace("ê", "e")
    normalized = normalized.replace("í", "i")
    normalized = normalized.replace("ó", "o").replace("õ", "o").replace("ô", "o")
    normalized = normalized.replace("ú", "u").replace("ç", "c")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(normalized.split())


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")[:120]
