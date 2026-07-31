from __future__ import annotations

import json
import random
import sys
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import cli
from app.automation import AutomationService
from app.automation_topics import COSMOS_CURIOSITY_POOL
from app.hub_job_request import build_hub_job_request
from app.models import Job, TopicRequest
from app.orchestrator import JobOrchestrator
from app.schemas import TopicRequestCreate
from app.survival_experiment import (
    SURVIVAL_COHORT_ID,
    SURVIVAL_EXPERIMENT_ID,
    SURVIVAL_NICHE_ID,
    SURVIVAL_SCENARIO_POOL,
    build_survival_cohort_plan,
    select_niche_policy,
)
from tests.e2e_support import SessionLocal


def test_explicit_niche_selection_returns_survival_policy_while_default_stays_cosmos() -> None:
    default_policy = select_niche_policy()
    survival_policy = select_niche_policy(SURVIVAL_NICHE_ID)

    assert default_policy.niche_id == "curiosidades"
    assert default_policy.seed_pool is COSMOS_CURIOSITY_POOL
    assert survival_policy.niche_id == SURVIVAL_NICHE_ID
    assert survival_policy.label_pt_br == "Sobrevivência e decisões impossíveis"
    assert survival_policy.seed_pool is SURVIVAL_SCENARIO_POOL
    assert len(survival_policy.seed_pool) >= 12
    assert survival_policy.hypothetical is True


def test_seeded_survival_cohort_plan_is_deterministic_and_varied() -> None:
    first = build_survival_cohort_plan(seed=20260730, item_count=6)
    second = build_survival_cohort_plan(seed=20260730, item_count=6)

    assert first == second
    assert first["niche_id"] == SURVIVAL_NICHE_ID
    assert first["experiment_id"] == SURVIVAL_EXPERIMENT_ID
    assert first["cohort_id"] == SURVIVAL_COHORT_ID
    assert first["experimental"] is True
    assert first["hypothetical"] is True
    assert first["dry_run"] is True
    assert first["creates_jobs"] is False
    assert first["publishes_or_schedules"] is False
    assert len(first["items"]) == 6
    assert len({item["scenario_family"] for item in first["items"]}) == 6
    assert len({item["hazard"] for item in first["items"]}) == 6
    assert len({item["decision_mechanic"] for item in first["items"]}) == 6
    for item in first["items"]:
        assert {
            "title_seed",
            "hook_seed",
            "scenario_family",
            "hazard",
            "decision_mechanic",
            "visual_seed",
            "safety_framing",
        } <= item.keys()
        assert "ficcional" in item["safety_framing"].casefold()


def test_survival_payload_persists_experiment_and_hypothetical_markers() -> None:
    payload = TopicRequestCreate(
        seed_theme="Elevador parado ou escada no escuro?",
        niche_id=SURVIVAL_NICHE_ID,
        notes="scenario_id=elevador_ou_escada",
        job_origin="manual_theme",
        creation_via="api",
    )

    assert f"experiment_id={SURVIVAL_EXPERIMENT_ID}" in (payload.notes or "")
    assert f"cohort_id={SURVIVAL_COHORT_ID}" in (payload.notes or "")
    assert "experimental=true" in (payload.notes or "")
    assert "hypothetical=true" in (payload.notes or "")

    job_id = JobOrchestrator().create_job(payload.model_dump())
    with SessionLocal() as session:
        persisted = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job_id))
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "cancelled"
        session.commit()

    assert persisted is not None
    assert persisted.niche_id == SURVIVAL_NICHE_ID
    assert f"experiment_id={SURVIVAL_EXPERIMENT_ID}" in (persisted.notes or "")
    assert f"cohort_id={SURVIVAL_COHORT_ID}" in (persisted.notes or "")
    assert "experimental=true" in (persisted.notes or "")
    assert "hypothetical=true" in (persisted.notes or "")


def test_survival_niche_cannot_enter_automatic_topic_lane() -> None:
    with pytest.raises(ValidationError, match="survival_decisions must be explicitly invoked"):
        TopicRequestCreate(
            seed_theme="Cenário ficcional",
            niche_id=SURVIVAL_NICHE_ID,
            job_origin="automatic_topic",
            creation_via="daily_cycle",
        )

    assert select_niche_policy().seed_pool is COSMOS_CURIOSITY_POOL


def test_survival_niche_rejects_automated_ready_script_origin() -> None:
    with pytest.raises(ValidationError, match="cannot enter automated creation or publication lanes"):
        TopicRequestCreate(
            seed_theme="Cenário ficcional",
            niche_id=SURVIVAL_NICHE_ID,
            job_origin="ready_script_bank",
            creation_via="api",
        )


def test_survival_job_cannot_be_scheduled_by_daily_automation() -> None:
    payload = TopicRequestCreate(
        seed_theme="Escolha ficcional no elevador",
        niche_id=SURVIVAL_NICHE_ID,
        job_origin="manual_theme",
        creation_via="hub",
    )
    job_id = JobOrchestrator().create_job(payload.model_dump())
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "ready_for_upload"
        session.commit()

    with pytest.raises(RuntimeError, match="survival_decisions_requires_human_publication_decision"):
        AutomationService(JobOrchestrator())._approve_and_schedule(job_id, date(2026, 8, 2))

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "cancelled"
        session.commit()


def test_empty_survival_hub_request_fails_before_automatic_topic_resolution() -> None:
    def forbidden_trend_resolution(_niche_id: str):
        raise AssertionError("survival experiment must not fall back to automatic topic")

    with pytest.raises(ValueError, match="requires an explicit theme, title, or ready script"):
        build_hub_job_request(
            seed_theme="",
            input_mode="theme",
            niche_id=SURVIVAL_NICHE_ID,
            language="pt-BR",
            target_duration_sec=45,
            tone="intrigante_direto",
            cta_style="none",
            notes=None,
            requested_angle=None,
            custom_angle=None,
            ready_script_text=None,
            default_niche_id="curiosidades",
            retention_optimized_duration_sec=45,
            viral_prompt_template="",
            trend_seed_resolver=forbidden_trend_resolution,
        )


def test_dry_run_cli_is_machine_readable_and_skips_runtime_services(monkeypatch, capsys) -> None:
    assert "orchestrator" not in vars(cli)
    assert "AutomationService" not in vars(cli)
    monkeypatch.setattr(sys, "argv", ["shortsflow", "survival-cohort-plan", "--seed", "41"])

    cli.main()

    output = json.loads(capsys.readouterr().out)
    assert output == build_survival_cohort_plan(seed=41, item_count=6)


def test_survival_selector_uses_supplied_rng_without_global_random_state() -> None:
    plan = build_survival_cohort_plan(seed=7, item_count=6, rng=random.Random(7))

    assert len(plan["items"]) == 6
