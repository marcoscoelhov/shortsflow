from __future__ import annotations

import json
from pathlib import Path

from app.llm_tournament import (
    LlmTournamentCandidate,
    build_llm_tournament_decision_report,
    build_script_stage_ranking,
    compare_llm_tournament_decision_reports,
    deterministic_audit_vetoes,
    deterministic_repair_vetoes,
    deterministic_script_vetoes,
    judge_existing_llm_tournament_script_run,
    load_editorial_benchmark,
    plan_llm_tournament_textual_round,
    run_llm_tournament_script_stage,
    run_llm_tournament_textual_round,
    _textual_stage_tasks,
)


def _valid_script() -> dict[str, object]:
    narration = (
        "Cafe nao cria energia do nada. Ele pode esconder o aviso de sono por um tempo. "
        "A cafeina aumenta o alerta, mas o corpo ainda carrega o cansaco. "
        "Perto da hora de dormir, esse atraso pode baguncar o descanso de algumas pessoas. "
        "No fim, a xicara nao era bateria: era uma mascara para o sono."
    )
    return {
        "title": "Cafe tarde pode mentir para o seu sono",
        "hook": "Cafe nao cria energia do nada.",
        "body_beats": [
            "Ele pode esconder o aviso de sono por um tempo.",
            "A cafeina aumenta o alerta, mas o corpo ainda carrega o cansaco.",
            "Perto da hora de dormir, esse atraso pode baguncar o descanso de algumas pessoas.",
        ],
        "ending": "No fim, a xicara nao era bateria: era uma mascara para o sono.",
        "cta": None,
        "full_narration": narration,
        "estimated_duration_sec": 42,
        "key_facts": ["Cafeina pode aumentar alerta.", "Cafeina perto da hora de dormir pode atrapalhar o sono."],
        "source_fact_ids": ["F1", "F2"],
        "claim_trace": [
            {"text": "Cafeina pode aumentar alerta.", "source_fact_ids": ["F1"], "grounding": "fact_pack"},
            {"text": "Cafeina perto da hora de dormir pode atrapalhar o sono.", "source_fact_ids": ["F2"], "grounding": "fact_pack"},
        ],
        "token_count": 80,
        "language": "pt-BR",
        "retention_map": {},
        "visual_opening": {},
        "qa_metrics": {"script_gate_pass": True},
        "prompt_version": "shorts-retention-v3",
    }


def test_editorial_benchmark_manifest_loads() -> None:
    benchmark = load_editorial_benchmark()

    assert benchmark["benchmark_id"] == "editorial-v1"
    assert len(benchmark["cases"]) == 12
    assert benchmark["cases"][0]["fact_pack"]["evidence_cards"]


def test_deterministic_script_vetoes_accept_grounded_script() -> None:
    case = load_editorial_benchmark()["cases"][0]

    assert deterministic_script_vetoes(_valid_script(), case) == []


def test_deterministic_script_vetoes_reject_forbidden_claim_and_missing_sources() -> None:
    case = load_editorial_benchmark()["cases"][0]
    script = _valid_script()
    script["full_narration"] = "Cafe da energia do nada. " + str(script["full_narration"])
    script["source_fact_ids"] = []
    script["claim_trace"] = []

    vetoes = deterministic_script_vetoes(script, case)

    assert "forbidden_claim" in vetoes
    assert "missing_source_fact_ids" in vetoes
    assert "missing_claim_trace" in vetoes


def test_repair_and_audit_vetoes_accept_valid_contracts() -> None:
    case = load_editorial_benchmark()["cases"][0]

    assert deterministic_repair_vetoes(
        {
            "repaired_script": _valid_script(),
            "fixed_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
            "remaining_issue_slugs": [],
            "repair_notes": "corrigido",
        },
        case,
    ) == []
    assert deterministic_repair_vetoes(
        {
            "repaired_script": _valid_script(),
            "fixed_issue_slugs": ["missing_source_fact_ids"],
            "remaining_issue_slugs": [],
            "repair_notes": "parcial",
        },
        case,
        {"expected_issue_slugs": ["missing_source_fact_ids", "missing_claim_trace"]},
    ) == ["missed_expected_repair_issue"]
    assert deterministic_audit_vetoes(
        {
            "decision": "block",
            "reason_slugs": ["forbidden_claim"],
            "severity": "high",
            "detected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
        },
        {
            "expected_decision": "block",
            "expected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
        },
    ) == []
    assert deterministic_audit_vetoes(
        {
            "decision": "approve",
            "reason_slugs": [],
            "severity": "low",
            "detected_issue_slugs": ["invented_problem"],
        },
        {
            "expected_decision": "approve",
            "expected_issue_slugs": [],
        },
    ) == ["false_positive_audit_issue"]


def test_script_stage_ranking_prefers_higher_publicable_score() -> None:
    ranking = build_script_stage_ranking(
        [
            {
                "candidate_id": "cheap",
                "status": "judged",
                "vetoes": [],
                "total_tokens": 100,
                "latency_ms": 1000,
                "judge": {"status": "passed", "overall_score": 0.7, "hook_strength_score": 0.7, "factual_obedience_score": 0.8},
            },
            {
                "candidate_id": "strong",
                "status": "judged",
                "vetoes": [],
                "total_tokens": 200,
                "latency_ms": 1500,
                "judge": {"status": "passed", "overall_score": 0.9, "hook_strength_score": 0.9, "factual_obedience_score": 0.95},
            },
            {
                "candidate_id": "broken",
                "status": "failed",
                "vetoes": [],
                "total_tokens": 0,
                "latency_ms": 10,
            },
        ]
    )

    assert ranking["recommended_premium_routes"][0]["candidate_id"] == "strong"
    assert ranking["recommended_scale_routes"][0]["candidate_id"] == "strong"
    assert ranking["do_not_promote"][0]["candidate_id"] == "broken"


def test_textual_round_plan_counts_tasks_without_provider_calls(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "configured",
                        "provider": "openai_compatible",
                        "model": "configured",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script", "repair", "audit"],
                        "enabled": True,
                    },
                    {
                        "candidate_id": "missing-key",
                        "provider": "openai_compatible",
                        "model": "missing-key",
                        "api_key_env": "YTS_MISSING_CANDIDATE_KEY",
                        "roles": ["script", "repair", "audit"],
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    source = load_editorial_benchmark()
    source["cases"] = source["cases"][:1]
    benchmark.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")
    monkeypatch.delenv("YTS_MISSING_CANDIDATE_KEY", raising=False)
    monkeypatch.setattr(
        "app.llm_tournament._candidate_json_completion",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("plan must not call providers")),
    )

    plan = plan_llm_tournament_textual_round(
        benchmark_path=benchmark,
        manifest_path=manifest,
        triage_mode="quick",
        full_mode="quick",
    )

    assert plan["summary"]["triage_task_count"] == 13
    assert plan["summary"]["provider_call_upper_bound"] == 26
    assert plan["stages"]["script"]["triage_task_count"] == 1
    assert plan["stages"]["repair"]["triage_task_count"] == 6
    assert plan["stages"]["audit"]["triage_task_count"] == 6
    assert plan["stages"]["audit"]["unconfigured_candidate_ids"] == ["missing-key"]


def test_textual_stage_tasks_interleave_candidates_for_parallel_provider_calls() -> None:
    candidates = [
        LlmTournamentCandidate(
            candidate_id="candidate-a",
            provider="provider-a",
            model="model-a",
            api_key_env="YTS_TEST_CANDIDATE_A_KEY",
            roles=("script",),
            enabled=True,
        ),
        LlmTournamentCandidate(
            candidate_id="candidate-b",
            provider="provider-b",
            model="model-b",
            api_key_env="YTS_TEST_CANDIDATE_B_KEY",
            roles=("script",),
            enabled=True,
        ),
    ]
    benchmark = load_editorial_benchmark()
    cases = benchmark["cases"][:2]

    tasks = _textual_stage_tasks(candidates, cases, benchmark, "script")

    assert [task[0].candidate_id for task in tasks[:4]] == [
        "candidate-a",
        "candidate-b",
        "candidate-a",
        "candidate-b",
    ]
    assert [task[1]["case_id"] for task in tasks[:2]] == [cases[0]["case_id"], cases[0]["case_id"]]


def test_run_script_stage_persists_outputs_and_ranking(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    },
                    {
                        "candidate_id": "judge",
                        "provider": "openai",
                        "model": "judge",
                        "api_key_env": "YTS_TEST_JUDGE_KEY",
                        "roles": ["audit"],
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    source = load_editorial_benchmark()
    source["cases"] = source["cases"][:1]
    benchmark.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")
    monkeypatch.setenv("YTS_TEST_JUDGE_KEY", "judge-key")

    def fake_completion(candidate, prompt, *, timeout_sec):
        if candidate.candidate_id == "judge":
            return (
                json.dumps(
                    {
                        "factual_obedience_score": 0.9,
                        "hook_strength_score": 0.8,
                        "loop_replay_score": 0.85,
                        "escalation_payoff_score": 0.82,
                        "pt_br_clarity_score": 0.88,
                        "viral_retention_score": 0.84,
                        "overall_score": 0.86,
                        "reasons": ["bom hook"],
                        "hard_concerns": [],
                    }
                ),
                {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        return json.dumps(_valid_script()), {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50}

    monkeypatch.setattr("app.llm_tournament._candidate_json_completion", fake_completion)

    report = run_llm_tournament_script_stage(
        mode="quick",
        benchmark_path=benchmark,
        manifest_path=manifest,
        output_dir=tmp_path / "runs",
        judge_candidate_id="judge",
        timeout_sec=1,
    )

    run_dir = Path(report["run_dir"])
    assert (run_dir / "results.json").exists()
    assert (run_dir / "ranking.json").exists()
    assert list((run_dir / "outputs" / "script").glob("*.json"))
    assert report["ranking"]["recommended_premium_routes"][0]["candidate_id"] == "candidate-a"


def test_run_script_stage_can_skip_judge_by_default(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    source = load_editorial_benchmark()
    source["cases"] = source["cases"][:1]
    benchmark.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")
    monkeypatch.setattr(
        "app.llm_tournament._candidate_json_completion",
        lambda *_args, **_kwargs: (json.dumps(_valid_script()), {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50}),
    )

    report = run_llm_tournament_script_stage(
        mode="quick",
        benchmark_path=benchmark,
        manifest_path=manifest,
        output_dir=tmp_path / "runs",
        timeout_sec=1,
    )

    result = report["results"][0]
    assert result["status"] == "generated"
    assert "judge" not in result
    assert report["ranking"]["recommended_scale_routes"][0]["pass_rate"] == 1.0


def test_judge_existing_script_run_updates_results_without_regeneration(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    },
                    {
                        "candidate_id": "candidate-b",
                        "provider": "openai_compatible",
                        "model": "candidate-b",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script"],
                        "enabled": True,
                    },
                    {
                        "candidate_id": "judge",
                        "provider": "openai",
                        "model": "judge",
                        "api_key_env": "YTS_TEST_JUDGE_KEY",
                        "roles": ["audit"],
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    source = load_editorial_benchmark()
    source["cases"] = source["cases"][:1]
    benchmark.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")
    monkeypatch.setenv("YTS_TEST_JUDGE_KEY", "judge-key")

    run_dir = tmp_path / "runs" / "existing"
    outputs_dir = run_dir / "outputs" / "script"
    outputs_dir.mkdir(parents=True)
    case_id = source["cases"][0]["case_id"]
    script_path = outputs_dir / f"{case_id}__candidate-a.json"
    script_path.write_text(json.dumps({"parsed": _valid_script()}), encoding="utf-8")
    results_path = run_dir / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": "existing",
                "status": "completed",
                "mode": "quick",
                "stage": "script",
                "benchmark_path": str(benchmark),
                "manifest_path": str(manifest),
                "results": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "case_id": case_id,
                        "stage": "script",
                        "status": "generated",
                        "latency_ms": 1000,
                        "total_tokens": 100,
                        "vetoes": [],
                        "output_path": str(script_path),
                    },
                    {
                        "candidate_id": "candidate-b",
                        "provider": "openai_compatible",
                        "model": "candidate-b",
                        "case_id": case_id,
                        "stage": "script",
                        "status": "generated",
                        "latency_ms": 1000,
                        "total_tokens": 100,
                        "vetoes": ["too_short_for_shorts"],
                        "output_path": str(outputs_dir / f"{case_id}__candidate-b.json"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_completion(candidate, prompt, *, timeout_sec):
        assert candidate.candidate_id == "judge"
        return (
            json.dumps(
                {
                    "factual_obedience_score": 0.9,
                    "hook_strength_score": 0.8,
                    "loop_replay_score": 0.85,
                    "escalation_payoff_score": 0.82,
                    "pt_br_clarity_score": 0.88,
                    "viral_retention_score": 0.84,
                    "overall_score": 0.86,
                    "reasons": ["bom hook"],
                    "hard_concerns": [],
                }
            ),
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    monkeypatch.setattr("app.llm_tournament._candidate_json_completion", fake_completion)

    report = judge_existing_llm_tournament_script_run(
        results_path=results_path,
        benchmark_path=benchmark,
        manifest_path=manifest,
        judge_candidate_id="judge",
        judge_mode="top-n",
        judge_top_n=1,
        timeout_sec=1,
    )

    assert report["results"][0]["status"] == "judged"
    assert report["results"][0]["judge"]["overall_score"] == 0.86
    assert report["results"][1]["status"] == "generated"
    assert (run_dir / "ranking.json").exists()
    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    assert persisted["judge_mode"] == "top-n"
    assert persisted["results"][0]["status"] == "judged"


def test_textual_round_runs_triage_and_full_stages(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script", "repair", "audit"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    source = load_editorial_benchmark()
    source["cases"] = source["cases"][:1]
    benchmark.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")

    def fake_completion(candidate, prompt, *, timeout_sec):
        if "repaired_script, fixed_issue_slugs" in prompt:
            return (
                json.dumps(
                        {
                            "repaired_script": _valid_script(),
                            "fixed_issue_slugs": [
                                "forbidden_claim",
                                "missing_source_fact_ids",
                                "missing_claim_trace",
                            "generic_hook_opening",
                            "too_short_for_shorts",
                            "too_few_sentences",
                            "language_not_pt_br",
                            "disallowed_dash",
                            "invented_source_fact_ids",
                            "unrecoverable_claim_removed",
                        ],
                            "remaining_issue_slugs": [],
                            "repair_notes": "corrigido",
                        }
                ),
                {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50},
            )
        if "decision, reason_slugs, severity, detected_issue_slugs" in prompt:
            if "audit-approve" in prompt or "audit-false-block-guard" in prompt:
                return (
                    json.dumps(
                        {
                            "decision": "approve",
                            "reason_slugs": [],
                            "severity": "low",
                            "detected_issue_slugs": [],
                        }
                    ),
                    {"input_tokens": 15, "output_tokens": 10, "total_tokens": 25},
                )
            if "audit-repair" in prompt:
                return (
                    json.dumps(
                        {
                            "decision": "repair",
                            "reason_slugs": ["missing_trace"],
                            "severity": "medium",
                            "detected_issue_slugs": ["missing_source_fact_ids", "missing_claim_trace"],
                        }
                    ),
                    {"input_tokens": 15, "output_tokens": 10, "total_tokens": 25},
                )
            if "audit-partial-support" in prompt:
                return (
                    json.dumps(
                        {
                            "decision": "repair",
                            "reason_slugs": ["partially_supported_claim"],
                            "severity": "medium",
                            "detected_issue_slugs": ["partially_supported_claim"],
                        }
                    ),
                    {"input_tokens": 15, "output_tokens": 10, "total_tokens": 25},
                )
            return (
                json.dumps(
                    {
                        "decision": "block",
                        "reason_slugs": ["forbidden_claim"],
                        "severity": "high",
                        "detected_issue_slugs": ["forbidden_claim", "missing_source_fact_ids", "missing_claim_trace"],
                    }
                ),
                {"input_tokens": 15, "output_tokens": 10, "total_tokens": 25},
            )
        return json.dumps(_valid_script()), {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50}

    monkeypatch.setattr("app.llm_tournament._candidate_json_completion", fake_completion)

    report = run_llm_tournament_textual_round(
        benchmark_path=benchmark,
        manifest_path=manifest,
        output_dir=tmp_path / "runs",
        triage_mode="quick",
        full_mode="quick",
        max_failures_per_candidate=2,
        timeout_sec=1,
    )

    run_dir = Path(report["run_dir"])
    assert (run_dir / "textual_results.json").exists()
    assert (run_dir / "committee_packet.json").exists()
    assert (run_dir / "decision_report.json").exists()
    assert (run_dir / "decision_report.md").exists()
    assert report["survivors_by_stage"] == {
        "script": ["candidate-a"],
        "repair": ["candidate-a"],
        "audit": ["candidate-a"],
    }
    assert set(report["full_reports"]) == {"script", "repair", "audit"}
    assert report["full_reports"]["repair"]["task_count"] == 6
    assert report["full_reports"]["audit"]["task_count"] == 6
    assert report["committee_packet"]["stages"]["script"]["finalists"][0]["candidate_id"] == "candidate-a"
    assert report["decision_report"]["scale_route"] == {
        "script": "candidate-a",
        "repair": "candidate-a",
        "audit": "candidate-a",
    }

    price_table = tmp_path / "prices.json"
    price_table.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "price_table_id": "test-prices-v1",
                "effective_date": "2026-06-14",
                "currency": "USD",
                "source": "test fixture",
                "prices": [
                    {
                        "candidate_id": "candidate-a",
                        "input_usd_per_1m_tokens": 1.0,
                        "output_usd_per_1m_tokens": 2.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    decision_report = build_llm_tournament_decision_report(
        committee_packet_path=run_dir / "committee_packet.json",
        price_table_path=price_table,
    )

    assert Path(decision_report["output_paths"]["json"]).exists()
    assert Path(decision_report["output_paths"]["markdown"]).exists()
    assert decision_report["scale_route"] == {
        "script": "candidate-a",
        "repair": "candidate-a",
        "audit": "candidate-a",
    }
    assert decision_report["best_single_model"]["candidate_id"] == "candidate-a"
    assert decision_report["price_table"]["price_table_id"] == "test-prices-v1"
    assert decision_report["stage_winners"]["script"]["cost_benefit"]["estimated_money_cost"]["status"] == "estimated"
    assert decision_report["evidence_summary"]["script"][0]["representative_artifacts"][0]["parsed_summary"]["kind"] == "script"


def test_textual_round_can_stop_after_triage(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "provider": "openai_compatible",
                        "model": "candidate-a",
                        "api_key_env": "YTS_TEST_CANDIDATE_KEY",
                        "roles": ["script", "repair", "audit"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_TEST_CANDIDATE_KEY", "candidate-key")
    calls: list[tuple[str, str]] = []

    def fake_phase(**kwargs):
        calls.append((kwargs["phase"], kwargs["stage"]))
        return {
            "status": "completed",
            "stage": kwargs["stage"],
            "phase": kwargs["phase"],
            "ranking": {
                "all_candidates": [{"candidate_id": "candidate-a", "pass_rate": 1.0, "failed": 0}],
                "recommended_scale_routes": [{"candidate_id": "candidate-a", "pass_rate": 1.0, "failed": 0}],
                "recommended_premium_routes": [{"candidate_id": "candidate-a", "pass_rate": 1.0, "failed": 0}],
            },
            "results": [],
        }

    monkeypatch.setattr("app.llm_tournament._run_textual_stage_phase", fake_phase)

    report = run_llm_tournament_textual_round(
        manifest_path=manifest,
        output_dir=tmp_path / "runs",
        triage_only=True,
    )

    assert calls == [("triage", "script"), ("triage", "repair"), ("triage", "audit")]
    assert report["stage"] == "textual_triage"
    assert report["decision_report"] is None
    assert report["full_reports"] == {}
    assert Path(report["run_dir"], "textual_triage_results.json").exists()


def test_compare_decision_reports_highlights_winner_route_and_risk_changes(tmp_path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-14T00:00:00+00:00",
                "stage_winners": {
                    "script": {
                        "cost_benefit": {
                            "candidate_id": "model-a",
                            "cost_benefit_score": 0.8,
                            "pass_rate": 1.0,
                            "failed": 0,
                            "total_tokens": 100,
                            "estimated_money_cost": {"status": "estimated", "amount": 0.01},
                        },
                        "scale": {"candidate_id": "model-a", "cost_benefit_score": 0.8, "pass_rate": 1.0},
                        "premium": {"candidate_id": "model-a", "cost_benefit_score": 0.8, "pass_rate": 1.0},
                    }
                },
                "scale_route": {"script": "model-a"},
                "premium_route": {"script": "model-a"},
                "best_single_model": {
                    "candidate_id": "model-a",
                    "average_cost_benefit_score": 0.8,
                    "min_pass_rate": 1.0,
                    "total_failures": 0,
                    "total_tokens": 100,
                    "estimated_money_cost": 0.01,
                },
                "risks": ["risco antigo"],
            }
        ),
        encoding="utf-8",
    )
    candidate_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-14T01:00:00+00:00",
                "stage_winners": {
                    "script": {
                        "cost_benefit": {
                            "candidate_id": "model-b",
                            "cost_benefit_score": 0.9,
                            "pass_rate": 0.9,
                            "failed": 1,
                            "total_tokens": 80,
                            "estimated_money_cost": {"status": "estimated", "amount": 0.008},
                        },
                        "scale": {"candidate_id": "model-b", "cost_benefit_score": 0.9, "pass_rate": 0.9},
                        "premium": {"candidate_id": "model-a", "cost_benefit_score": 0.8, "pass_rate": 1.0},
                    }
                },
                "scale_route": {"script": "model-b"},
                "premium_route": {"script": "model-a"},
                "best_single_model": {
                    "candidate_id": "model-b",
                    "average_cost_benefit_score": 0.9,
                    "min_pass_rate": 0.9,
                    "total_failures": 1,
                    "total_tokens": 80,
                    "estimated_money_cost": 0.008,
                },
                "risks": ["risco novo"],
            }
        ),
        encoding="utf-8",
    )

    comparison = compare_llm_tournament_decision_reports(
        baseline_report_path=baseline_path,
        candidate_report_path=candidate_path,
        output_dir=tmp_path / "out",
    )

    assert Path(comparison["output_paths"]["json"]).exists()
    assert Path(comparison["output_paths"]["markdown"]).exists()
    assert comparison["stage_changes"]["script"]["cost_benefit"]["changed"] is True
    assert comparison["stage_changes"]["script"]["cost_benefit"]["score_delta"] == 0.1
    assert comparison["stage_changes"]["script"]["cost_benefit"]["total_tokens_delta"] == -20
    assert comparison["route_changes"]["scale_route"]["fields"]["script"] == {
        "baseline": "model-a",
        "candidate": "model-b",
    }
    assert comparison["route_changes"]["premium_route"]["changed"] is False
    assert comparison["best_single_model_change"]["changed"] is True
    assert comparison["risk_changes"] == {
        "added": ["risco novo"],
        "removed": ["risco antigo"],
    }
