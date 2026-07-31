from __future__ import annotations

import json
import random
import sys
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import cli
from app.automation import AutomationService
from app.automation_topics import COSMOS_CURIOSITY_POOL
from app.hub_job_request import build_hub_job_request
from app.models import Job, Script, TopicRequest
from app.orchestrator import JobOrchestrator
from app.schemas import TopicRequestCreate
from app.survival_experiment import (
    SURVIVAL_COHORT_ID,
    SURVIVAL_EXPERIMENT_ID,
    SURVIVAL_NICHE_ID,
    SURVIVAL_SCENARIO_POOL,
    build_survival_cohort_plan,
    extract_survival_choice_labels,
    select_niche_policy,
)
from app.youtube_publication_ops import YouTubePublicationOperations
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


def test_survival_choice_labels_cover_the_full_public_scenario_cohort() -> None:
    expected = {
        "elevador_botoes": ("LUZ", "PORTA"),
        "ponte_mochila": ("MOCHILA", "MAPA"),
        "trem_vagoes": ("AZUL", "VERMELHO"),
        "farol_bateria": ("RÁDIO", "LUZ"),
        "estufa_portais": ("PORTAL", "ILUMINADO"),
        "biblioteca_areia": ("CHAVE", "LIVRO"),
        "observatorio_cupula": ("CÚPULA", "SINAL"),
        "hotel_submerso": ("CORREDOR", "CÁPSULA"),
        "museu_relogio": ("FRENTE", "TRÁS"),
        "teleferico_caixas": ("CAIXA", "LEVE"),
        "shopping_robos": ("ROBÔ", "PEGADAS"),
        "jardim_gravidade": ("CORDA", "SEMENTE"),
    }

    assert {
        scenario.scenario_id: extract_survival_choice_labels(scenario.title_seed)
        for scenario in SURVIVAL_SCENARIO_POOL
    } == expected


def test_survival_choice_labels_handle_manual_and_no_article_seeds() -> None:
    assert extract_survival_choice_labels("a chave metálica ou o livro luminoso") == ("CHAVE", "LIVRO")
    assert extract_survival_choice_labels("Elevador parado ou escada no escuro?") == ("ELEVADOR", "ESCADA")
    assert extract_survival_choice_labels("vagão AZUL ou VERMELHO — decida agora") == ("AZUL", "VERMELHO")
    assert extract_survival_choice_labels("sem escolha binária aqui") is None


@pytest.mark.parametrize(
    "current_title",
    [
        "A resposta revela tudo",
        "A escolha correta vence: Biblioteca",
        "A saída real é o livro: Biblioteca",
    ],
)
def test_survival_publish_title_replaces_spoiler_stems(current_title: str) -> None:
    pipeline = JobOrchestrator().monetization_pipeline
    request = SimpleNamespace(seed_theme="a chave metálica ou o livro luminoso")

    assert pipeline._survival_publish_title(request, current_title) == "Decisão impossível: CHAVE OU LIVRO?"


@pytest.mark.parametrize(
    "current_title",
    [
        "O livro abre a saída",
        "Use o livro para escapar",
        "A chave destranca a porta",
    ],
)
def test_survival_publish_title_neutralizes_no_colon_declarative_stems(current_title: str) -> None:
    pipeline = JobOrchestrator().monetization_pipeline
    request = SimpleNamespace(seed_theme="a chave metálica ou o livro luminoso")

    assert pipeline._survival_publish_title(request, current_title) == "Decisão impossível: CHAVE OU LIVRO?"


def test_survival_publish_title_preserves_suffix_inside_hard_limit() -> None:
    pipeline = JobOrchestrator().monetization_pipeline
    request = SimpleNamespace(seed_theme="a chave metálica ou o livro luminoso")
    title = pipeline._survival_publish_title(request, "Biblioteca subterrânea " + "muito " * 30)

    assert len(title) <= 100
    assert title.endswith(": CHAVE OU LIVRO?")


def test_survival_publish_title_fails_closed_without_extractable_choices() -> None:
    pipeline = JobOrchestrator().monetization_pipeline
    request = SimpleNamespace(seed_theme="uma decisão sem alternativas nomeadas")

    assert pipeline._survival_publish_title(request, "Você entra OU sai?") == "Você entra OU sai?"
    assert pipeline._survival_publish_title(request, "Uma aventura na biblioteca") == "Decisão impossível: QUAL VOCÊ ESCOLHE?"
    assert pipeline._survival_publish_title(request, "A resposta correta: ENTRA OU SAI?") == (
        "Decisão impossível: QUAL VOCÊ ESCOLHE?"
    )


def test_survival_publish_package_preserves_choice_and_rejects_poisoned_metadata(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    job_id = orchestrator.create_job(
        TopicRequestCreate(
            seed_theme="Elevador parado ou escada no escuro?",
            niche_id=SURVIVAL_NICHE_ID,
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )
    with SessionLocal() as session:
        session.add(
            Script(
                script_id=f"{job_id}-script",
                job_id=job_id,
                content_hash="survival-script",
                title="Elevador parado ou escada no escuro?",
                hook="Você precisa escolher antes que a energia acabe.",
                body_beats=["A escada parece segura, mas esconde o risco."],
                ending="A porta errada era a do elevador.",
                full_narration="Você precisa escolher. A porta errada era a do elevador.",
                estimated_duration_sec=25,
                key_facts=[],
                token_count=12,
                language="pt-BR",
                qa_metrics={},
            )
        )
        session.commit()
    orchestrator.storage.persist_json(
        job_id,
        "publish_metadata_overrides.json",
        {
            "title": "A porta errada era a do elevador",
            "description": "O detalhe estranho antes de você notar revela a resposta.",
            "hashtags": ["#shorts", "#fatos"],
        },
    )
    monkeypatch.setattr(orchestrator.monetization_pipeline, "provider_publish_audit", lambda *args, **kwargs: {"passed": True, "reasons": []})
    monkeypatch.setattr(orchestrator.monetization_pipeline, "publish_readiness_report", lambda *args, **kwargs: {"passed": True, "reasons": []})

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        package = orchestrator.monetization_pipeline.build_publish_package(session, job)
        job.status = "cancelled"
        session.commit()

    assert package["title"] == "Elevador parado ou escada no escuro?"
    assert package["hashtags"] == ["#shorts", "#sobrevivencia", "#decisao", "#ficcao"]
    assert package["category"] == "Entertainment"
    assert "porta errada" not in package["description"].casefold()
    assert "o detalhe estranho antes de você notar" not in package["description"].casefold()


def test_survival_publish_package_rebuilds_choice_title_from_seed_when_script_reveals_outcome(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    job_id = orchestrator.create_job(
        TopicRequestCreate(
            seed_theme="Biblioteca subterrânea invadida por areia: escolher a chave metálica ou o livro luminoso",
            niche_id=SURVIVAL_NICHE_ID,
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )
    with SessionLocal() as session:
        session.add(
            Script(
                script_id=f"{job_id}-script",
                job_id=job_id,
                content_hash="survival-library-script",
                title="Biblioteca de areia: A CHAVE abre a porta errada",
                hook="Escolha a chave metálica ou o livro luminoso.",
                body_beats=["A areia sobe enquanto você decide."],
                ending="O livro revela a saída real.",
                full_narration="A chave abre a porta errada, mas o livro revela a saída real.",
                estimated_duration_sec=25,
                key_facts=[],
                token_count=15,
                language="pt-BR",
                qa_metrics={},
            )
        )
        session.commit()
    monkeypatch.setattr(orchestrator.monetization_pipeline, "provider_publish_audit", lambda *args, **kwargs: {"passed": True, "reasons": []})
    monkeypatch.setattr(orchestrator.monetization_pipeline, "publish_readiness_report", lambda *args, **kwargs: {"passed": True, "reasons": []})
    orchestrator.storage.persist_json(
        job_id,
        "monetization_report.json",
        {"ai_disclosure": {"description_notice": "Imagens ilustrativas geradas por IA."}},
    )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        package = orchestrator.monetization_pipeline.build_publish_package(session, job)
        job.status = "cancelled"
        session.commit()

    assert package["title"] == "Biblioteca de areia: CHAVE OU LIVRO?"
    assert "abre" not in package["title"].casefold()
    assert "errada" not in package["title"].casefold()
    assert "A CHAVE abre a porta errada" not in package["title"]
    assert package["description"] == (
        "Cenário ficcional: qual decisão você tomaria?\n\n"
        "Imagens ilustrativas geradas por IA.\n\n"
        "#shorts #sobrevivencia #decisao #ficcao"
    )


def test_curiosidades_publish_package_keeps_generic_metadata_behavior(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    job_id = orchestrator.create_job(
        TopicRequestCreate(
            seed_theme="Por que os polvos mudam de cor?",
            niche_id="curiosidades",
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )
    orchestrator.storage.persist_json(
        job_id,
        "publish_metadata_overrides.json",
        {
            "title": "O segredo das cores dos polvos",
            "description": "Uma curiosidade verificada sobre os polvos.",
            "hashtags": ["#shorts", "#polvos", "#biologia"],
        },
    )
    monkeypatch.setattr(orchestrator.monetization_pipeline, "provider_publish_audit", lambda *args, **kwargs: {"passed": True, "reasons": []})
    monkeypatch.setattr(orchestrator.monetization_pipeline, "publish_readiness_report", lambda *args, **kwargs: {"passed": True, "reasons": []})

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        package = orchestrator.monetization_pipeline.build_publish_package(session, job)
        job.status = "cancelled"
        session.commit()

    assert package["title"] == "O segredo das cores dos polvos"
    assert package["description"] == "Uma curiosidade verificada sobre os polvos."
    assert package["hashtags"] == ["#shorts", "#polvos", "#biologia"]
    assert package["category"] == "Education"


def test_youtube_upload_maps_entertainment_category_to_id_24() -> None:
    captured: dict = {}

    class YouTubeStub:
        def upload_video(self, **kwargs):
            captured.update(kwargs)
            return {"id": "video-24", "status": {"privacyStatus": "private"}}

    operations = YouTubePublicationOperations(
        SimpleNamespace(settings=SimpleNamespace(), youtube=YouTubeStub())
    )

    operations.upload_publish_package(
        {
            "video_uri": "file:///tmp/survival.mp4",
            "title": "Elevador ou escada?",
            "description": "Cenário ficcional.",
            "hashtags": ["#shorts", "#sobrevivencia"],
            "category": "Entertainment",
        },
        "private",
    )

    assert captured["category_id"] == "24"


def test_youtube_upload_keeps_education_category_id_27() -> None:
    captured: dict = {}

    class YouTubeStub:
        def upload_video(self, **kwargs):
            captured.update(kwargs)
            return {"id": "video-27", "status": {"privacyStatus": "private"}}

    operations = YouTubePublicationOperations(
        SimpleNamespace(settings=SimpleNamespace(), youtube=YouTubeStub())
    )

    operations.upload_publish_package(
        {
            "video_uri": "file:///tmp/curiosidade.mp4",
            "title": "Por que os polvos mudam de cor?",
            "category": "Education",
        },
        "private",
    )

    assert captured["category_id"] == "27"


def test_youtube_schedule_maps_entertainment_category_to_id_24() -> None:
    captured: dict = {}

    class YouTubeStub:
        def upload_video(self, **kwargs):
            captured.update(kwargs)
            return {"id": "scheduled-24", "status": {"privacyStatus": "private"}}

    operations = YouTubePublicationOperations(
        SimpleNamespace(settings=SimpleNamespace(), youtube=YouTubeStub())
    )

    operations.schedule_publish_package(
        {
            "video_uri": "file:///tmp/survival.mp4",
            "title": "Elevador ou escada?",
            "category": "Entertainment",
        },
        datetime(2026, 8, 2, 12, tzinfo=UTC),
        "private",
    )

    assert captured["category_id"] == "24"


def test_youtube_schedule_defaults_to_education_category_id_27() -> None:
    captured: dict = {}

    class YouTubeStub:
        def upload_video(self, **kwargs):
            captured.update(kwargs)
            return {"id": "scheduled-27", "status": {"privacyStatus": "private"}}

    operations = YouTubePublicationOperations(
        SimpleNamespace(settings=SimpleNamespace(), youtube=YouTubeStub())
    )

    operations.schedule_publish_package(
        {
            "video_uri": "file:///tmp/curiosidade.mp4",
            "title": "Por que os polvos mudam de cor?",
        },
        datetime(2026, 8, 2, 12, tzinfo=UTC),
        "private",
    )

    assert captured["category_id"] == "27"
