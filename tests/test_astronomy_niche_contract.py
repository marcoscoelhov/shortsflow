from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from tests.e2e_support import orchestrator
from app.models import TopicRequest


ASTRO_CASES = [
    ("Por que Vênus é mais quente que Mercúrio?", "planetas"),
    ("O universo pode ter galáxias que quase não brilham", "galaxias"),
    ("Buracos negros parecem engolir luz", "buracos_negros"),
    ("Por que a Lua parece mudar de tamanho no céu?", "luas"),
    ("Exoplanetas podem ter céus impossíveis", "exoplanetas"),
    ("Tecnologia espacial: o telescópio James Webb enxerga o passado", "tecnologia_espacial"),
]


def _request(seed_theme: str) -> TopicRequest:
    return cast(TopicRequest, SimpleNamespace(
        seed_theme=seed_theme,
        requested_angle="",
        notes="input_mode=theme\nautomation_source=automatic_topic\nautomatic_topic_policy=cosmos_astronomia_universo_first",
        niche_id="curiosidades",
    ))


def test_automatic_topic_astronomy_niche_contract_covers_core_subniches() -> None:
    for seed_theme, expected_subniche in ASTRO_CASES:
        plan = orchestrator.topic_pipeline.normalize_topic_plan_payload(
            {
                "canonical_topic": seed_theme,
                "angle": "curiosidade astronômica visualmente forte",
                "hook_promise": "revela o detalhe espacial que muda a leitura do céu",
                "entities": [seed_theme],
                "search_terms": [seed_theme],
                "quality_metrics": {},
            },
            _request(seed_theme),
        )

        contract = plan["niche_contract"]
        metrics = plan["quality_metrics"]
        assert contract["niche"] == "astronomia"
        assert contract["subniche"] == expected_subniche
        assert metrics["topic_niche"] == "astronomia"
        assert metrics["topic_subniche"] == expected_subniche
        assert "tecnologia" not in {contract["niche"], contract["subniche"]} or expected_subniche == "tecnologia_espacial"
        forbidden = {str(keyword).casefold() for keyword in contract["forbidden_keywords"]}
        for essential in ["planeta", "estrela", "galáxia", "buraco negro", "nasa", "telescópio"]:
            assert essential.casefold() not in forbidden


def test_structured_viral_contract_exposes_astronomy_niche_keywords() -> None:
    plan = orchestrator.topic_pipeline.normalize_topic_plan_payload(
        {
            "canonical_topic": "Buracos negros parecem engolir luz",
            "angle": "cosmologia visual conservadora",
            "hook_promise": "mostra por que a luz perde a saída",
            "entities": ["buraco negro", "luz", "gravidade"],
            "search_terms": ["buraco negro luz"],
            "quality_metrics": {},
        },
        _request("Buracos negros parecem engolir luz"),
    )

    contract = orchestrator.script_pipeline._structured_viral_contract(plan, 45)
    niche_contract = contract["topic"]["niche_contract"]

    assert niche_contract["niche"] == "astronomia"
    assert niche_contract["subniche"] == "buracos_negros"
    assert "buraco negro" in {str(keyword).casefold() for keyword in niche_contract["allowed_keywords"]}
    assert niche_contract["forbidden_keywords"] == []
