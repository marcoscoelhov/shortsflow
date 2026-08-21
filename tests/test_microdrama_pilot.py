from __future__ import annotations

from datetime import date
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import cli
from app.automation import AutomationService
from app.db import SessionLocal
from app.hub_job_request import build_hub_job_request
from app.microdrama_pilot import (
    MICRODRAMA_NICHE_ID,
    build_microdrama_pilot_plan,
    get_microdrama_pilot,
)
from app.niche_classification import classify_niche_contract
from app.editorial.topic_mode import resolve_editorial_mode
from app.models import ChannelPublication, Job, PublicationSchedule, RetentionExperiment, RetentionExperimentAssignment, TopicRequest
from app.orchestrator import JobOrchestrator
from app.schemas import TopicRequestCreate
from app.survival_experiment import select_niche_policy


def test_microdrama_request_accepts_manual_creation_and_restores_policy_notes() -> None:
    payload = TopicRequestCreate(
        seed_theme="A carta que chegou vinte anos tarde",
        niche_id=MICRODRAMA_NICHE_ID,
        target_duration_sec=40,
        notes=(
            "direcao_criativa=final_ambiguo\n"
            "fictional_scenario=false\n"
            "fiction_format=novela_copiada\n"
            "automatic_publication_allowed=true\n"
            "human_review_required=false\n"
            "originality_review_required=false"
        ),
        requested_angle="Uma filha reconhece a letra da mãe desaparecida.",
        job_origin="manual_title",
        creation_via="hub",
    )

    notes = (payload.notes or "").splitlines()
    assert "direcao_criativa=final_ambiguo" in notes
    assert notes.count("fictional_scenario=true") == 1
    assert notes.count("fiction_format=microdrama") == 1
    assert notes.count("automatic_publication_allowed=false") == 1
    assert notes.count("human_review_required=true") == 1
    assert notes.count("originality_review_required=true") == 1
    assert not any(line.endswith("=false") for line in notes if line.split("=", 1)[0] in {
        "fictional_scenario",
        "human_review_required",
        "originality_review_required",
    })
    assert any(
        "tramas originais" in line
        and "Reddit" in line
        and "novela" in line
        and "sem gore" in line
        and "eventos reais" in line
        for line in notes
    )


def test_microdrama_explicit_niche_wins_over_incidental_astronomy_terms() -> None:
    classification = classify_niche_contract(
        "A voz da Iara veio do observatório sob a Lua",
        "Ficção sobrenatural no Bairro da Estação",
        fallback_niche=MICRODRAMA_NICHE_ID,
    )

    assert classification.niche == MICRODRAMA_NICHE_ID
    assert classification.subniche == "suspense_emocional"
    assert classification.source == "explicit_request_niche"
    assert classification.allowed_keywords == ("microdrama", "ficção", "suspense", "história")


def test_microdrama_editorial_mode_stays_entertainment_even_with_surgery_word() -> None:
    request = type(
        "Request",
        (),
        {
            "notes": "fictional_scenario=true\nfiction_format=microdrama",
            "requested_angle": "Uma irmã decide se ouve a confissão antes da cirurgia fictícia.",
            "seed_theme": "O áudio antes da cirurgia",
        },
    )()

    assert resolve_editorial_mode(None, request) == "viral_curiosidades"
    assert resolve_editorial_mode(
        {
            "canonical_topic": "Microdrama sobre uma escolha diante do perigo fictício",
            "angle": "Suspense emocional sem instrução real",
            "hook_promise": "Uma decisão muda a família",
            "quality_metrics": {
                "editorial_mode": "viral_curiosidades",
                "topic_niche": MICRODRAMA_NICHE_ID,
            },
        },
        None,
    ) == "viral_curiosidades"


@pytest.mark.parametrize(
    ("job_origin", "creation_via"),
    [
        ("automatic_topic", "cli"),
        ("ready_script_bank", "api"),
        ("manual_theme", "daily_cycle"),
    ],
)
def test_microdrama_request_rejects_automated_lanes(job_origin: str, creation_via: str) -> None:
    with pytest.raises(ValidationError, match="fiction_microdrama.*manual"):
        TopicRequestCreate(
            seed_theme="O retrato que muda toda madrugada",
            niche_id=MICRODRAMA_NICHE_ID,
            job_origin=job_origin,
            creation_via=creation_via,
        )


def test_microdrama_requires_human_publication_decision() -> None:
    job_id = JobOrchestrator().create_job(
        TopicRequestCreate(
            seed_theme="A carta que chegou vinte anos tarde",
            niche_id=MICRODRAMA_NICHE_ID,
            target_duration_sec=40,
            job_origin="manual_theme",
            creation_via="cli",
        ).model_dump()
    )
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "ready_for_upload"
        session.commit()

    with pytest.raises(RuntimeError, match="fiction_microdrama_requires_human_publication_decision"):
        AutomationService(JobOrchestrator())._approve_and_schedule(job_id, date(2026, 8, 21))

    with SessionLocal() as session:
        assert session.scalar(
            select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.job_id == job_id)
        ) == 0
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "cancelled"
        session.commit()


def test_microdrama_hub_requires_manual_theme_title_or_script() -> None:
    def forbidden_trend_resolution(_: str) -> object:
        raise AssertionError("manual-only niche must not resolve an automatic trend")

    with pytest.raises(ValueError, match="fiction_microdrama.*explicit theme"):
        build_hub_job_request(
            seed_theme="",
            input_mode="theme",
            niche_id=MICRODRAMA_NICHE_ID,
            language="pt-BR",
            target_duration_sec=40,
            tone="suspense_emocional",
            cta_style="soft",
            notes=None,
            requested_angle=None,
            custom_angle=None,
            ready_script_text=None,
            default_niche_id="curiosidades",
            retention_optimized_duration_sec=40,
            viral_prompt_template="",
            trend_seed_resolver=forbidden_trend_resolution,
        )


def test_microdrama_plan_is_deterministic_interleaved_and_diverse() -> None:
    first = build_microdrama_pilot_plan(seed=20260820)
    second = build_microdrama_pilot_plan(seed=20260820)
    different_seed = build_microdrama_pilot_plan(seed=17)

    assert first == second
    assert first != different_seed
    assert first["publishes_or_schedules"] is False
    assert [item["arm"] for item in first["items"]] == ["A", "B", "C"] * 6
    assert len(first["items"]) == 18
    assert len({item["concept_id"] for item in first["items"]}) == 18
    assert len({item["seed_theme"] for item in first["items"]}) == 18
    assert all(item["niche_id"] == MICRODRAMA_NICHE_ID for item in first["items"])
    assert all(item["target_duration_sec"] == 40 for item in first["items"])
    assert all(item["language"] == "pt-BR" for item in first["items"])
    assert all(item["human_review_required"] is True for item in first["items"])
    assert all(item["automatic_publication_allowed"] is False for item in first["items"])
    assert all(item["requested_angle"] for item in first["items"])
    assert all(item["story_format"] in {"standalone", "arc_2_parts", "arc_3_parts", "arc_4_parts"} for item in first["items"])
    assert all(item["fictional_universe"] == "Bairro da Estação" for item in first["items"])
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "A"} == {
        "betrayal_revenge_family_secret_emotional_suspense"
    }
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "B"} == {
        "impossible_decisions_moral_dilemmas"
    }
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "C"} == {
        "brazilian_folklore_psychological_supernatural_no_gore"
    }
    combined_text = json.dumps(first, ensure_ascii=False).casefold()
    assert "ceo" not in combined_text
    assert "bilionário" not in combined_text


def test_microdrama_plan_cli_is_json_only_and_has_no_database_side_effects(capsys) -> None:
    before = _table_counts()

    cli.main(["microdrama-pilot-plan", "--seed", "31415"])

    output = json.loads(capsys.readouterr().out)
    assert output == build_microdrama_pilot_plan(seed=31415)
    assert _table_counts() == before


def test_microdrama_start_cli_is_idempotent_and_creates_only_three_canaries(capsys) -> None:
    argv = ["microdrama-pilot-start", "--seed", "271828"]

    cli.main(argv)
    first = json.loads(capsys.readouterr().out)
    cli.main(argv)
    second = json.loads(capsys.readouterr().out)
    persisted = get_microdrama_pilot(first["experiment_id"])

    assert first["created_job_count"] == 3
    assert second["created_job_count"] == 0
    assert first["publishes_or_schedules"] is False
    assert second["publishes_or_schedules"] is False
    assert [item["arm"] for item in first["canaries"]] == ["A", "B", "C"]
    assert [item["job_id"] for item in second["canaries"]] == [item["job_id"] for item in first["canaries"]]
    assert len(persisted["assignments"]) == 18
    assert sum(item["job_id"] is not None for item in persisted["assignments"]) == 3
    with SessionLocal() as session:
        job_ids = [item["job_id"] for item in first["canaries"]]
        jobs = session.scalars(select(Job).where(Job.job_id.in_(job_ids))).all()
        requests = session.scalars(select(TopicRequest).where(TopicRequest.job_id.in_(job_ids))).all()
        assert len(jobs) == 3
        assert all(job.status == "queued" for job in jobs)
        assert all(job.review_state is None for job in jobs)
        assert len(requests) == 3
        assert all("automatic_publication_allowed=false" in (request.notes or "") for request in requests)
        assert session.scalar(select(func.count()).select_from(PublicationSchedule).where(PublicationSchedule.job_id.in_(job_ids))) == 0
        assert session.scalar(select(func.count()).select_from(ChannelPublication).where(ChannelPublication.job_id.in_(job_ids))) == 0
        for job in jobs:
            job.status = "cancelled"
        session.commit()


def test_microdrama_is_part_of_public_niche_policy_contract() -> None:
    policy = select_niche_policy(MICRODRAMA_NICHE_ID)

    assert policy.niche_id == MICRODRAMA_NICHE_ID
    assert policy.hypothetical is True
    assert "human_review_required=true" in policy.policy_notes


def _table_counts() -> tuple[int, int, int]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(Job)) or 0,
            session.scalar(select(func.count()).select_from(RetentionExperiment)) or 0,
            session.scalar(select(func.count()).select_from(RetentionExperimentAssignment)) or 0,
        )
