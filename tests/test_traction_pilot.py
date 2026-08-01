from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from app import cli
from app.db import SessionLocal
from app.models import Job
from app.orchestrator import JobOrchestrator
from app.schemas import TopicRequestCreate
from app.traction_pilot import build_programmatic_pilot_asset, build_traction_pilot_plan, get_traction_pilot, start_traction_pilot


def test_traction_pilot_plan_interleaves_six_items_per_arm() -> None:
    plan = build_traction_pilot_plan(seed=20260731)

    assert plan["experiment_id"] == "niche_traction_minimax_fit_20260731_s20260731"
    assert plan["language"] == "pt-BR"
    assert plan["target_duration_sec"] == 40
    assert plan["acceptable_duration_sec"] == {"min": 30, "max": 50}
    assert plan["publishes_or_schedules"] is False
    assert [item["arm"] for item in plan["items"]] == ["A", "B", "C"] * 6
    assert len({item["concept_id"] for item in plan["items"]}) == 18
    assert all(item["vision_policy"] == "qwen_local_exact_no_fallback" for item in plan["items"])
    assert all(item["human_review_required"] is False for item in plan["items"])


def test_starting_three_canaries_is_persistent_and_idempotent() -> None:
    service = JobOrchestrator()

    first = start_traction_pilot(service, seed=99117, canary_count=3)
    second = start_traction_pilot(service, seed=99117, canary_count=3)
    persisted = get_traction_pilot(first["experiment_id"])

    assert first["created_job_count"] == 3
    assert second["created_job_count"] == 0
    assert [item["arm"] for item in first["canaries"]] == ["A", "B", "C"]
    assert [item["job_id"] for item in second["canaries"]] == [item["job_id"] for item in first["canaries"]]
    assert persisted["status"] == "canaries_created"
    assert len(persisted["assignments"]) == 18
    assert sum(item["job_id"] is not None for item in persisted["assignments"]) == 3
    _cancel_test_jobs([item["job_id"] for item in first["canaries"]])


def test_pilot_start_cli_creates_three_canaries_without_processing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["shortsflow", "pilot-10k-start", "--seed", "88103"])

    cli.main()

    output = json.loads(capsys.readouterr().out)
    assert output["created_job_count"] == 3
    assert output["processed_job_count"] == 0
    assert [item["arm"] for item in output["canaries"]] == ["A", "B", "C"]
    _cancel_test_jobs([item["job_id"] for item in output["canaries"]])


def test_traction_pilot_survival_job_records_qwen_instead_of_human_review() -> None:
    payload = TopicRequestCreate(
        seed_theme="No elevador apagado: LUZ ou PORTA?",
        niche_id="survival_decisions",
        target_duration_sec=35,
        notes=(
            "experiment_id=niche_traction_minimax_fit_20260731_s7\n"
            "pilot_qwen_autoapproval=true\n"
            "human_review_required=false"
        ),
        job_origin="manual_theme",
        creation_via="cli",
    )

    assert "pilot_qwen_autoapproval=true" in (payload.notes or "")
    assert "human_review_required=true" not in (payload.notes or "")
    assert "automatic_publication_allowed=false" in (payload.notes or "")


def _cancel_test_jobs(job_ids: list[str | None]) -> None:
    with SessionLocal() as session:
        for job_id in job_ids:
            if not job_id:
                continue
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "cancelled"
        session.commit()


def test_jwst_canary_uses_programmatic_factual_proof(tmp_path: Path) -> None:
    output = tmp_path / "spectrum.png"

    asset = build_programmatic_pilot_asset(
        "jwst_exoplanet_spectrum",
        {"retention_role": "proof_or_tension", "order": 3},
        output,
    )

    assert asset is not None
    assert asset["provider"] == "programmatic"
    assert asset["source_url"].startswith("https://science.nasa.gov/")
    assert asset["license_note"] == "Programmatic explanatory visual grounded in the cited NASA source."
    assert Image.open(output).size == (1080, 1920)
