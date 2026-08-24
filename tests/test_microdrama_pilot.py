from __future__ import annotations

from datetime import date
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import cli
from app.automation import AutomationService
from app.db import SessionLocal
from app.hub_job_request import build_hub_job_request
from app.editorial.retention import build_retention_map
from app.hub_prompt import DEFAULT_VIRAL_PROMPT_TEMPLATE, extract_viral_prompt_contract
from app.microdrama_pilot import (
    MICRODRAMA_NICHE_ID,
    MICRODRAMA_PILOT_DURATION_SEC,
    build_microdrama_pilot_plan,
    get_microdrama_pilot,
)
from app.niche_classification import classify_niche_contract
from app.editorial.topic_mode import resolve_editorial_mode
from app.models import ChannelPublication, Job, PublicationSchedule, RetentionExperiment, RetentionExperimentAssignment, TopicRequest
from app.orchestrator import JobOrchestrator, RecoverableStepError
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
            "originality_review_required=false\n"
            "twist_required=false\n"
            "twist_must_reinterpret_story=false\n"
            "shock_without_graphic_violence=false"
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
    assert notes.count("twist_required=true") == 1
    assert notes.count("twist_must_reinterpret_story=true") == 1
    assert notes.count("shock_without_graphic_violence=true") == 1
    assert not any(line.endswith("=false") for line in notes if line.split("=", 1)[0] in {
        "fictional_scenario",
        "human_review_required",
        "originality_review_required",
        "twist_required",
        "twist_must_reinterpret_story",
        "shock_without_graphic_violence",
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
    assert classification.subniche == "drama_chocante_reviravolta"
    assert classification.source == "explicit_request_niche"
    assert classification.allowed_keywords == ("microdrama", "ficção", "drama", "reviravolta", "segredo")


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

    assert resolve_editorial_mode(None, request) == "fiction_microdrama"
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
    ) == "fiction_microdrama"


def test_microdrama_editorial_mode_uses_explicit_niche_without_policy_notes() -> None:
    request = type(
        "Request",
        (),
        {
            "niche_id": MICRODRAMA_NICHE_ID,
            "notes": "",
            "requested_angle": "Uma filha encontra uma carta escondida.",
            "seed_theme": "A carta atrasada",
        },
    )()

    assert resolve_editorial_mode(None, request) == "fiction_microdrama"


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
            tone="drama_chocante_reviravolta",
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


def test_microdrama_hub_replaces_astronomy_default_with_editorial_contract() -> None:
    result = build_hub_job_request(
        seed_theme="A chave da casa vazia no buquê da noiva",
        input_mode="theme",
        niche_id=MICRODRAMA_NICHE_ID,
        language="pt-BR",
        target_duration_sec=40,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes=None,
        requested_angle="No casamento, a chave revela um segredo familiar.",
        custom_angle=None,
        ready_script_text=None,
        default_niche_id="curiosidades",
        retention_optimized_duration_sec=40,
        viral_prompt_template=DEFAULT_VIRAL_PROMPT_TEMPLATE,
        trend_seed_resolver=lambda _: (_ for _ in ()).throw(AssertionError("unexpected trend resolution")),
    )

    notes = result.payload.notes or ""
    assert "MICRODRAMAS DE SUSPENSE EMOCIONAL UNIVERSAL" in notes
    assert "universos variados" in notes
    assert "mistérios brasileiros" not in notes
    assert "Folclore brasileiro" not in notes
    assert "Escreva trama, personagens, situações e falas do zero" in notes
    assert "Hook em até 8 palavras" in notes
    assert "espaço/astronomia" not in notes
    assert "SISTEMA SOLAR" not in notes
    assert "Modelos de hook para astronomia" not in notes
    assert extract_viral_prompt_contract(notes)["source"] == "niche_default"


def test_microdrama_create_job_injects_editorial_contract_without_prompt_marker() -> None:
    job_id = JobOrchestrator().create_job(
        TopicRequestCreate(
            seed_theme="A chave da casa vazia no buquê da noiva",
            niche_id=MICRODRAMA_NICHE_ID,
            target_duration_sec=40,
            requested_angle="No casamento, a chave revela um segredo familiar.",
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )

    with SessionLocal() as session:
        request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job_id))
        job = session.get(Job, job_id)
        assert request is not None
        assert "MICRODRAMAS DE SUSPENSE EMOCIONAL UNIVERSAL" in (request.notes or "")
        assert "universos variados" in (request.notes or "")
        assert "espaço/astronomia" not in (request.notes or "")
        assert job is not None
        job.status = "cancelled"
        session.commit()


def test_microdrama_topic_drift_repairs_then_fails_before_downstream_work(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    calls = 0

    def saturn_plan(*_args, **_kwargs) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "canonical_topic": "Saturno e seus anéis de gelo",
            "angle": "A colisão de luas criou os anéis do planeta",
            "hook_promise": "Saturno não usa joia, usa destroços em órbita",
            "title_candidates": ["Saturno não usa joia"],
            "entities": ["Saturno"],
            "search_terms": ["anéis de Saturno"],
            "quality_metrics": {},
        }

    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", saturn_plan)
    request = TopicRequest(
        job_id="microdrama-topic-drift",
        topic_request_id="microdrama-topic-drift-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A chave da casa vazia no buquê da noiva",
        requested_angle="No casamento, a chave revela um segredo familiar.",
        language="pt-BR",
        target_duration_sec=40,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    with pytest.raises(RecoverableStepError, match="microdrama_topic_alignment_failed"):
        orchestrator.topic_pipeline.generate_topic_plan_with_repair(request, history=[], attempt=1)

    assert calls == orchestrator.settings.llm_topic_repair_attempts + 1


def test_microdrama_topic_alignment_accepts_a_valid_paraphrase_after_repair(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    plans = iter(
        [
            {
                "canonical_topic": "Saturno e seus anéis de gelo",
                "angle": "A colisão de luas criou os anéis do planeta",
                "hook_promise": "Saturno não usa joia, usa destroços em órbita",
                "title_candidates": ["Saturno não usa joia"],
                "entities": ["Saturno"],
                "search_terms": ["anéis de Saturno"],
                "quality_metrics": {},
            },
            {
                "canonical_topic": "A chave escondida no buquê leva a noiva à casa vazia",
                "angle": "O objeto interrompe o casamento e expõe o segredo da família",
                "hook_promise": "Antes do sim, a noiva precisa decidir se abre a casa abandonada",
                "title_candidates": ["A chave antes do sim"],
                "entities": ["noiva", "chave", "casa vazia"],
                "search_terms": ["microdrama chave noiva"],
                "quality_metrics": {},
            },
        ]
    )
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: next(plans))
    request = TopicRequest(
        job_id="microdrama-topic-repaired",
        topic_request_id="microdrama-topic-repaired-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A chave da casa vazia no buquê da noiva",
        requested_angle="No casamento, a chave revela um segredo familiar.",
        language="pt-BR",
        target_duration_sec=40,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    plan, metrics = orchestrator.topic_pipeline.generate_topic_plan_with_repair(request, history=[], attempt=1)

    assert plan["canonical_topic"].startswith("A chave escondida")
    assert metrics["microdrama_topic_alignment_pass"] is True
    assert metrics["microdrama_topic_alignment_similarity"] >= metrics["microdrama_topic_alignment_min_similarity"]
    assert metrics["topic_repair_used"] is True
    assert metrics["topic_repair_attempts_log"][0]["reason_codes"] == ["microdrama_topic_alignment_failed"]
    assert metrics["topic_repair_attempts_log"][1]["reason_codes"] == []


def test_microdrama_topic_alignment_accepts_identical_short_request_without_central_terms(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    plan = {
        "canonical_topic": "Eu ou ele?",
        "angle": "Eu ou ele?",
        "hook_promise": "Eu ou ele?",
        "title_candidates": ["Eu ou ele?"],
        "entities": [],
        "search_terms": ["eu ou ele"],
        "quality_metrics": {},
    }
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: plan)
    request = TopicRequest(
        job_id="microdrama-short-identical",
        topic_request_id="microdrama-short-identical-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="Eu ou ele?",
        requested_angle=None,
        language="pt-BR",
        target_duration_sec=120,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    _accepted_plan, metrics = orchestrator.topic_pipeline.generate_topic_plan_with_repair(
        request,
        history=[],
        attempt=1,
    )

    assert metrics["microdrama_topic_alignment_pass"] is True
    assert metrics["microdrama_central_term_coverage"] == 1.0


def test_microdrama_topic_alignment_accepts_conservative_photographer_paraphrase_without_angle(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    plan = {
        "canonical_topic": "A fotógrafa com fotografias queimadas",
        "angle": "A fotógrafa com imagens destruídas descobre quem tentou apagar a prova",
        "hook_promise": "A fotógrafa revela quem ateou fogo às imagens",
        "title_candidates": ["As imagens que sobreviveram ao fogo"],
        "entities": ["fotógrafa", "fotografias queimadas"],
        "search_terms": ["microdrama fotógrafa fotografias queimadas"],
        "quality_metrics": {},
    }
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: plan)
    request = TopicRequest(
        job_id="microdrama-photographer-paraphrase",
        topic_request_id="microdrama-photographer-paraphrase-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A fotógrafa com retratos carbonizados",
        requested_angle=None,
        language="pt-BR",
        target_duration_sec=120,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    _accepted_plan, metrics = orchestrator.topic_pipeline.generate_topic_plan_with_repair(
        request,
        history=[],
        attempt=1,
    )

    assert metrics["microdrama_topic_alignment_pass"] is True
    assert metrics["microdrama_topic_alignment_similarity"] >= 0.35
    assert metrics["microdrama_central_term_coverage"] == pytest.approx(1 / 3, abs=0.001)


def test_microdrama_topic_alignment_rejects_object_substitution_without_angle(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    replacement = {
        "canonical_topic": "Um músico encontra cartas rasgadas",
        "angle": "As cartas revelam uma dívida escondida antes do concerto",
        "hook_promise": "O músico precisa decidir se abandona o palco",
        "title_candidates": ["As cartas antes do concerto"],
        "entities": ["músico", "cartas", "concerto"],
        "search_terms": ["microdrama músico cartas"],
        "quality_metrics": {},
    }
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: replacement)
    request = TopicRequest(
        job_id="microdrama-object-substitution-no-angle",
        topic_request_id="microdrama-object-substitution-no-angle-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A fotógrafa com retratos carbonizados",
        requested_angle=None,
        language="pt-BR",
        target_duration_sec=120,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    with pytest.raises(RecoverableStepError, match="microdrama_topic_alignment_failed"):
        orchestrator.topic_pipeline.generate_topic_plan_with_repair(request, history=[], attempt=1)


def test_microdrama_topic_alignment_rejects_lexical_match_that_replaces_central_objects(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    replacement = {
        "canonical_topic": "Uma carta antes do casamento",
        "angle": "A noiva recebe uma carta e descobre um segredo familiar antes do sim",
        "hook_promise": "Antes do casamento, ela precisa decidir se lê a carta",
        "title_candidates": ["A carta antes do sim"],
        "entities": ["noiva", "carta", "casamento"],
        "search_terms": ["microdrama carta casamento"],
        "quality_metrics": {},
    }
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: replacement)
    request = TopicRequest(
        job_id="microdrama-object-substitution",
        topic_request_id="microdrama-object-substitution-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A chave da casa vazia no buquê da noiva",
        requested_angle="No casamento, a chave revela um segredo familiar.",
        language="pt-BR",
        target_duration_sec=120,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    with pytest.raises(RecoverableStepError, match="microdrama_topic_alignment_failed"):
        orchestrator.topic_pipeline.generate_topic_plan_with_repair(request, history=[], attempt=1)


def test_microdrama_topic_alignment_rejects_preserved_objects_with_replaced_conflict(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    replacement = {
        "canonical_topic": "A chave da casa vazia no buquê da noiva",
        "angle": "Os objetos decoram o casamento enquanto uma carta antiga cancela a cerimônia",
        "hook_promise": "A noiva precisa descobrir quem escreveu a carta",
        "title_candidates": ["A carta antes do sim"],
        "entities": ["noiva", "carta", "casamento"],
        "search_terms": ["microdrama carta casamento"],
        "quality_metrics": {},
    }
    monkeypatch.setattr(orchestrator.providers.creative, "plan_topic", lambda *_args, **_kwargs: replacement)
    request = TopicRequest(
        job_id="microdrama-conflict-substitution",
        topic_request_id="microdrama-conflict-substitution-request",
        schema_version="1.0.0",
        content_hash="test",
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A chave da casa vazia no buquê da noiva",
        requested_angle="No casamento, a chave revela um segredo familiar.",
        language="pt-BR",
        target_duration_sec=120,
        tone="drama_chocante_reviravolta",
        cta_style="soft",
        notes="fictional_scenario=true",
    )

    with pytest.raises(RecoverableStepError, match="microdrama_topic_alignment_failed"):
        orchestrator.topic_pipeline.generate_topic_plan_with_repair(request, history=[], attempt=1)


def test_microdrama_originality_is_required_even_when_repetition_risk_is_low() -> None:
    pipeline = JobOrchestrator().monetization_pipeline
    checklist = pipeline.build_human_review_checklist(
        rights_registry={"all_commercial_rights_confirmed": True},
        ai_disclosure={"youtube_disclosure_required": False},
        fact_claims_report={"requires_fact_review": False},
        metadata_review={"requires_metadata_review": False},
        channel_repetition_report={"repetition_risk": "low"},
        publish_audit_required=False,
        confirmations={"visual_review_confirmed"},
        visual_review_required=True,
        originality_review_required=True,
    )

    originality = next(item for item in checklist["items"] if item["code"] == "originality_review_required")
    assert originality["required"] is True
    assert originality["completed"] is False
    assert originality["source"] == "microdrama_policy"
    assert "originality_review_required" in checklist["pending_codes"]


def test_non_microdrama_originality_diagnostic_preserves_ready_status() -> None:
    pipeline = JobOrchestrator().monetization_pipeline

    assert pipeline.resolve_monetization_status(
        hard_blockers=[], manual_required=["originality_review_required"]
    ) == (True, "ready_for_upload")


def test_microdrama_viral_truth_policy_never_allows_automatic_publish() -> None:
    orchestrator = JobOrchestrator()
    request = TopicRequest(
        niche_id=MICRODRAMA_NICHE_ID,
        seed_theme="A chave da casa vazia no buquê da noiva",
        requested_angle="No casamento, a chave revela um segredo familiar.",
        notes="fictional_scenario=true",
    )
    topic_plan = type(
        "TopicPlanStub",
        (),
        {
            "canonical_topic": "A chave escondida no buquê leva a noiva à casa vazia",
            "angle": "O segredo familiar interrompe o casamento",
            "hook_promise": "A chave obriga a noiva a escolher antes do sim",
            "quality_metrics": {"editorial_mode": "viral_curiosidades", "topic_niche": MICRODRAMA_NICHE_ID},
        },
    )()

    policy = orchestrator.script_pipeline.fact_pack_domain._viral_truth_policy(
        topic_plan,
        request,
        {
            "claim_scope": "general_curiosity",
            "evidence_profile": "cotidiano_observacional",
            "required_evidence_term_groups": [],
        },
        source_status="verified",
    )

    assert policy["automatic_publish_allowed"] is False


def test_microdrama_monetization_report_normalizes_legacy_automatic_publish_flag(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    job_id = orchestrator.create_job(
        TopicRequestCreate(
            seed_theme="A chave da casa vazia no buquê da noiva",
            niche_id=MICRODRAMA_NICHE_ID,
            requested_angle="No casamento, a chave revela um segredo familiar.",
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )
    orchestrator.storage.persist_json(
        job_id,
        "fact_pack.json",
        {
            "status": "verified",
            "provider": "legacy_canary",
            "viral_truth_policy": {"automatic_publish_allowed": True},
        },
    )
    pipeline = orchestrator.monetization_pipeline
    observed: dict[str, object] = {}

    monkeypatch.setattr(pipeline, "build_rights_registry", lambda *_args: {"all_commercial_rights_confirmed": True})
    monkeypatch.setattr(
        pipeline,
        "build_ai_disclosure_report",
        lambda *_args: {"youtube_disclosure_required": False, "contains_synthetic_visuals": False},
    )

    def fact_claims(*args) -> dict[str, object]:
        fact_pack = args[2]
        observed.update(fact_pack["viral_truth_policy"])
        return {
            "requires_fact_review": False,
            "viral_truth_policy": fact_pack["viral_truth_policy"],
        }

    monkeypatch.setattr(pipeline, "build_fact_claims_report", fact_claims)
    monkeypatch.setattr(
        pipeline,
        "build_channel_repetition_report",
        lambda *_args: {"repetition_risk": "low", "matches": []},
    )
    monkeypatch.setattr(pipeline, "build_metadata_review", lambda *_args: {"requires_metadata_review": False})
    monkeypatch.setattr(pipeline, "build_growth_metadata_repair", lambda *_args, **_kwargs: {"applied": False})
    monkeypatch.setattr(
        pipeline.metadata_ctr_gate,
        "validate",
        lambda *_args: SimpleNamespace(passed=True, reasons=[], metrics={"metadata_ctr_gate_pass": True}),
    )
    monkeypatch.setattr(pipeline, "build_quality_checklist", lambda *_args: {"script": True})
    monkeypatch.setattr(pipeline, "provider_publish_audit", lambda *_args, **_kwargs: {"passed": True, "reasons": []})
    monkeypatch.setattr(
        pipeline,
        "publish_readiness_report",
        lambda *_args, **_kwargs: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(pipeline, "visual_review_required_for_assets", lambda *_args: False)
    monkeypatch.setattr(pipeline, "narration_publishability_blockers", lambda *_args: [])
    monkeypatch.setattr(pipeline, "automatic_publish_blockers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        pipeline.growth_score_gate,
        "evaluate",
        lambda *_args: SimpleNamespace(
            passed=True,
            decision="ready_for_growth_review",
            reasons=[],
            metrics={"growth_score": 1.0, "growth_score_gate_pass": True},
        ),
    )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        report = pipeline.build_monetization_report(session, job, extra_confirmations={"visual_review_confirmed"})
        job.status = "cancelled"
        session.commit()

    assert observed["automatic_publish_allowed"] is False
    assert report["fact_claims_report"]["viral_truth_policy"]["automatic_publish_allowed"] is False
    assert report["manual_required"] == ["originality_review_required"]
    assert report["final_status"] == "monetization_review"


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
    assert all(item["target_duration_sec"] == MICRODRAMA_PILOT_DURATION_SEC for item in first["items"])
    assert all(item["language"] == "pt-BR" for item in first["items"])
    assert all(item["human_review_required"] is True for item in first["items"])
    assert all(item["automatic_publication_allowed"] is False for item in first["items"])
    assert all(item["twist_required"] is True for item in first["items"])
    assert all(item["positioning"] == "dramas_chocantes_com_reviravolta" for item in first["items"])
    assert all(item["requested_angle"] for item in first["items"])
    assert all(item["story_format"] in {"standalone", "arc_2_parts", "arc_3_parts", "arc_4_parts"} for item in first["items"])
    assert all(item["fictional_universe"] == "universos_variados" for item in first["items"])
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "A"} == {
        "betrayal_family_secret_shocking_twist"
    }
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "B"} == {
        "injustice_impossible_choice_consequence_twist"
    }
    assert {item["arm_focus"] for item in first["items"] if item["arm"] == "C"} == {
        "dark_mystery_supernatural_twist_no_gore"
    }
    assert first["experiment_id"].startswith("jarvis_shocking_twist_drama_pilot_v2_")
    combined_text = json.dumps(first, ensure_ascii=False).casefold()
    assert "ceo" not in combined_text
    assert "bilionário" not in combined_text
    assert not any(term in combined_text for term in ("saci", "curupira", "iara", "matinta", "boto"))


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


def test_microdrama_script_pipeline_generates_three_tracks_and_selects_winner_before_media(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    job_id = orchestrator.create_job(
        TopicRequestCreate(
            seed_theme="A carta escondida no paletó do pai",
            niche_id=MICRODRAMA_NICHE_ID,
            target_duration_sec=120,
            requested_angle="A filha encontra a carta antes do discurso do sócio.",
            job_origin="manual_theme",
            creation_via="api",
        ).model_dump()
    )
    pipeline = orchestrator.script_pipeline
    monkeypatch.setattr(
        pipeline,
        "_validate_or_repair_script",
        lambda script, *_args, **_kwargs: (script, {"script_quality_gate_pass": True}),
    )
    plan_dict = {
        "canonical_topic": "A carta escondida no paletó do pai",
        "angle": "A filha encontra a carta antes do discurso do sócio.",
        "hook_promise": "A carta revela que o sócio esconde a identidade do pai.",
        "title_candidates": ["A carta que ninguém devia ler"],
        "tone": "drama_chocante_reviravolta",
        "cta_style": "soft",
        "hub_notes": "fictional_scenario=true",
        "original_input": "A carta escondida no paletó do pai",
        "editorial_mode": "viral_curiosidades",
        "retention_map": build_retention_map(120),
        "fact_pack": {
            "status": "disabled",
            "facts": [],
            "viral_truth_policy": {"automatic_publish_allowed": True},
        },
    }
    script, metrics = pipeline._generate_script_with_track_selection(
        job_id=job_id,
        plan_dict=plan_dict,
        attempt=1,
    )
    assert str(script.get("full_narration") or "").strip()
    assert metrics["script_track_draft_count"] == 3
    assert metrics["script_track_selected_judge_score"] > 0
    artifact_dir = orchestrator.storage.job_dir(job_id, create=False)
    assert (artifact_dir / "script_tracks.json").exists()


def test_microdrama_track_diversity_ignores_title_variant_suffixes(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    pipeline = orchestrator.script_pipeline
    duplicate_tracks = [
        {
            "title": f"A carta escondida (variante {index + 1})",
            "hook": "Ninguém viu a carta desaparecer.",
            "body_beats": ["A filha abriu o mesmo paletó."],
            "full_narration": "Ninguém viu a carta desaparecer. A filha abriu o mesmo paletó.",
        }
        for index in range(3)
    ]
    monkeypatch.setattr(
        pipeline.providers.creative,
        "generate_script_batch",
        lambda _plan, _count: {"tracks": duplicate_tracks},
    )

    with pytest.raises(RecoverableStepError, match="invalid or repeating track"):
        pipeline._generate_script_with_track_selection(
            job_id="duplicate-narrative-tracks",
            plan_dict={"niche_id": MICRODRAMA_NICHE_ID},
            attempt=1,
        )

    audit = json.loads(
        (orchestrator.storage.job_dir("duplicate-narrative-tracks", create=False) / "script_tracks.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["drafts"][1]["rejection_reason"] == "script_track_not_distinct"


def test_microdrama_reuses_next_ranked_track_when_judge_winner_fails_quality(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    pipeline = orchestrator.script_pipeline
    ranked_tracks = [
        {"_track_index": 6, "title": "Primeira", "full_narration": "Primeira candidata."},
        {"_track_index": 8, "title": "Segunda", "full_narration": "Segunda candidata."},
    ]
    locally_validated_indices: list[int] = []
    repaired_indices: list[int] = []

    def fake_local_validate(script, *_args, **_kwargs):
        locally_validated_indices.append(int(script["_track_index"]))
        if script["_track_index"] == 6:
            raise RecoverableStepError("final script quality gate failed: weak_loop_closure")
        return script, {"script_quality_gate_pass": True}

    monkeypatch.setattr(
        pipeline.repair_domain,
        "validate_final_script_candidate_without_repair",
        fake_local_validate,
    )
    monkeypatch.setattr(
        pipeline,
        "_validate_or_repair_script",
        lambda script, *_args, **_kwargs: repaired_indices.append(int(script["_track_index"])),
    )

    script, metrics, attempts = pipeline._select_ranked_script_candidate(
        ranked_tracks,
        plan_dict={"niche_id": MICRODRAMA_NICHE_ID},
        target_duration_sec=120,
        cta_style="soft",
        job_id="ranked-quality-fallback",
    )

    assert script["_track_index"] == 8
    assert locally_validated_indices == [6, 8]
    assert repaired_indices == []
    assert metrics["script_quality_gate_pass"] is True
    assert attempts == [
        {"rank": 1, "index": 6, "passed": False, "reason": "final script quality gate failed: weak_loop_closure"},
        {"rank": 2, "index": 8, "passed": True, "reason": None},
    ]


def test_microdrama_repairs_only_judge_winner_when_all_ranked_tracks_fail_locally(monkeypatch) -> None:
    pipeline = JobOrchestrator().script_pipeline
    ranked_tracks = [
        {"_track_index": 6, "title": "Primeira", "full_narration": "Primeira candidata."},
        {"_track_index": 8, "title": "Segunda", "full_narration": "Segunda candidata."},
    ]
    repaired_indices: list[int] = []

    def fail_local(script, *_args, **_kwargs):
        raise RecoverableStepError(f"final script quality gate failed: invalid_{script['_track_index']}")

    def repair_winner(script, *_args, **_kwargs):
        repaired_indices.append(int(script["_track_index"]))
        return script, {"script_quality_gate_pass": True, "script_repair_used": True}

    monkeypatch.setattr(
        pipeline.repair_domain,
        "validate_final_script_candidate_without_repair",
        fail_local,
    )
    monkeypatch.setattr(pipeline, "_validate_or_repair_script", repair_winner)

    script, metrics, attempts = pipeline._select_ranked_script_candidate(
        ranked_tracks,
        plan_dict={"niche_id": MICRODRAMA_NICHE_ID},
        target_duration_sec=120,
        cta_style="soft",
        job_id="single-ranked-repair",
    )

    assert script["_track_index"] == 6
    assert repaired_indices == [6]
    assert metrics["script_track_quality_repair_used"] is True
    assert attempts[-1] == {"rank": 1, "index": 6, "passed": True, "reason": None, "repair_used": True}


def test_microdrama_track_diversity_rejects_isolated_pista_numbers_in_narration(monkeypatch) -> None:
    orchestrator = JobOrchestrator()
    pipeline = orchestrator.script_pipeline
    tracks = [
        {
            "title": f"A carta escondida {index + 1}",
            "hook": "Ninguém viu a carta desaparecer.",
            "body_beats": ["A filha abriu o paletó e encontrou a mesma prova."],
            "full_narration": (
                f"Pista {index + 1}. Ninguém viu a carta desaparecer. "
                "A filha abriu o paletó e encontrou a mesma prova."
            ),
        }
        for index in range(3)
    ]
    monkeypatch.setattr(
        pipeline.providers.creative,
        "generate_script_batch",
        lambda _plan, _count: {"tracks": tracks},
    )

    with pytest.raises(RecoverableStepError, match="invalid or repeating track"):
        pipeline._generate_script_with_track_selection(
            job_id="pista-number-narrative-tracks",
            plan_dict={"niche_id": MICRODRAMA_NICHE_ID},
            attempt=1,
        )

    audit = json.loads(
        (orchestrator.storage.job_dir("pista-number-narrative-tracks", create=False) / "script_tracks.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["drafts"][1]["rejection_reason"] == "script_track_not_distinct"
    assert audit["drafts"][1]["normalized_narrative_hash"] == audit["drafts"][0]["normalized_narrative_hash"]
    assert audit["drafts"][1]["max_lexical_similarity"] == 1.0
