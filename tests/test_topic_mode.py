from types import SimpleNamespace

from app.editorial.topic_mode import is_viral_space_entertainment_context, resolve_editorial_mode
from app.quality.script_gate import ScriptQualityGate
from app.quality.viral_intensity_gate import ViralIntensityGate


def test_resolve_editorial_mode_astronomy_overrides_factual_strict_stored_mode() -> None:
    topic_plan = {
        "canonical_topic": "Vênus é o planeta mais quente do sistema solar",
        "angle": "contraste visual",
        "hook_promise": "por que o mais perto não é o mais quente",
        "quality_metrics": {"editorial_mode": "factual_strict", "topic_niche": "astronomia"},
    }
    request = SimpleNamespace(
        seed_theme="planeta quente",
        notes="automatic_topic_policy=cosmos_astronomia_universo_first",
        requested_angle=None,
    )

    assert resolve_editorial_mode(topic_plan, request) == "viral_curiosidades"
    assert is_viral_space_entertainment_context(topic_plan, request) is True


def test_script_gate_relaxes_factual_block_for_space_entertainment() -> None:
    gate = ScriptQualityGate()
    topic_plan = {
        "canonical_topic": "Buracos negros e luz",
        "angle": "curiosidade espacial",
        "hook_promise": "o que acontece com a luz",
        "quality_metrics": {"topic_niche": "astronomia"},
    }
    request = SimpleNamespace(seed_theme="buraco negro", notes="cosmos_astronomia_universo_first", requested_angle=None)
    hook = "A gravidade do buraco negro domina tudo ao redor."
    loop = "O que acontece com a luz quando ela se aproxima demais?"
    beats = [
        "A luz viaja em linha reta até a curvatura do espaço mudar o caminho.",
        "Quanto mais perto, mais o tempo parece travar.",
        "No horizonte de eventos, o caminho de volta some.",
    ]
    payoff = "Não é mágica: é gravidade extrema curvando o espaço."
    ending = "E você, já imaginou a luz presa numa armadilha invisível?"
    full = " ".join([hook, loop, *beats, payoff, ending])
    script = {
        "title": "Por que a luz não escapa?",
        "hook": hook,
        "loop": loop,
        "body_beats": beats,
        "payoff": payoff,
        "ending": ending,
        "full_narration": full,
        "language": "pt-BR",
        "claim_trace": [{"text": hook, "grounding": "common_knowledge", "source_fact_ids": []}],
        "retention_map": {
            "visual_hook": {"mapped_text": hook},
            "proof_or_tension": {"mapped_text": loop},
            "escalation": {"mapped_text": beats[0]},
            "turn_or_payoff": {"mapped_text": payoff},
            "loop_close": {"mapped_text": ending},
        },
        "qa_metrics": {
            "hook_score": 0.9,
            "clarity_score": 0.9,
            "information_density_score": 0.9,
            "ending_strength_score": 0.9,
            "repetition_score": 0.2,
        },
    }
    without = gate.validate(script, 45)
    with_ctx = gate.validate(script, 45, topic_plan=topic_plan, request=request)
    if "factual_risk_requires_conservative_rewrite" in without.reasons:
        assert "factual_risk_requires_conservative_rewrite" not in with_ctx.reasons
    assert with_ctx.metrics.get("viral_space_entertainment_relaxed_factual_gate") is True


def test_viral_intensity_accepts_marte_style_closing_question() -> None:
    gate = ViralIntensityGate()
    script = {
        "title": "Aranhas em Marte? A verdade",
        "hook": "Essas marcas no solo de Marte parecem aranhas de verdade. Mas não são.",
        "loop": "O que forma esses desenhos assustadores que cobrem quilômetros?",
        "body_beats": [
            "Elas aparecem perto do polo sul marciano depois do inverno.",
            "O gelo sublima e vira gás de repente.",
            "Esse gás jorra e cavando canais escuros no solo.",
        ],
        "payoff": "Não são animais: são jatos de gás carbônico subterrâneo.",
        "ending": "Aquilo que parecia vivo é só o sopro do gelo marciano. E você, já imaginou um gelo que desenha aranhas?",
        "full_narration": "",
    }
    result = gate.validate(script)
    assert "weak_share_trigger" not in result.reasons