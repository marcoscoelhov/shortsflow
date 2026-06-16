import pytest

from app.pipelines.common import RecoverableStepError
from app.pipelines.monetization_pipeline import MonetizationPipeline
from app.pipelines.script_pipeline import ScriptPipeline
from app.quality.growth_score_gate import GrowthScoreGate
from app.quality.metadata_ctr_gate import MetadataCTRGate
from app.quality.visual_impact_gate import VisualImpactGate
from app.quality.viral_intensity_gate import ViralIntensityGate


def test_visual_impact_gate_rejects_generic_opening_asset() -> None:
    scenes = [
        {
            "scene_id": "scene-1",
            "order": 1,
            "retention_role": "visual_hook",
            "visual_intent": "macro close-up of octopus skin flashing colors",
            "image_prompt": "generic ocean background, calm blue water, no clear subject",
        },
        {
            "scene_id": "scene-2",
            "order": 2,
            "retention_role": "build_tension",
            "visual_intent": "octopus camouflage against coral",
            "image_prompt": "octopus blending into coral texture, dramatic contrast",
        },
    ]
    assets = [
        {
            "scene_id": "scene-1",
            "provider": "minimax",
            "semantic_match": 0.78,
            "total_score": 0.72,
            "prompt_snapshot": "generic ocean background, calm water, centered stock-photo look",
            "width": 1080,
            "height": 1920,
        },
        {
            "scene_id": "scene-2",
            "provider": "minimax",
            "semantic_match": 0.92,
            "total_score": 0.9,
            "prompt_snapshot": "octopus camouflage against coral, high contrast macro details",
            "width": 1080,
            "height": 1920,
        },
    ]

    result = VisualImpactGate().validate(assets, scenes, visual_contract={})

    assert not result.passed
    assert "opening_frame_not_scroll_stopping" in result.reasons
    assert "generic_stock_visual_penalty" in result.reasons
    assert result.metrics["first_frame_scroll_stop_score"] < 0.82


def test_visual_impact_gate_accepts_strong_vertical_progression() -> None:
    scenes = [
        {
            "scene_id": "scene-1",
            "order": 1,
            "retention_role": "visual_hook",
            "visual_intent": "macro close-up of octopus skin flashing orange and blue",
            "image_prompt": "extreme macro close-up, octopus skin flashing orange blue, dramatic contrast, sharp focus",
        },
        {
            "scene_id": "scene-2",
            "order": 2,
            "retention_role": "turn_or_payoff",
            "visual_intent": "wide reveal of octopus disappearing into coral",
            "image_prompt": "wide reveal, octopus vanishing into coral, high contrast, cinematic light",
        },
    ]
    assets = [
        {
            "scene_id": "scene-1",
            "provider": "minimax",
            "semantic_match": 0.94,
            "total_score": 0.91,
            "prompt_snapshot": "extreme macro close-up, flashing orange blue skin, dramatic contrast, sharp subject",
            "width": 1080,
            "height": 1920,
        },
        {
            "scene_id": "scene-2",
            "provider": "minimax",
            "semantic_match": 0.91,
            "total_score": 0.89,
            "prompt_snapshot": "wide reveal of octopus disappearing into coral, cinematic high contrast",
            "width": 1080,
            "height": 1920,
        },
    ]

    result = VisualImpactGate().validate(assets, scenes, visual_contract={})

    assert result.passed
    assert result.metrics["first_frame_scroll_stop_score"] >= 0.82
    assert result.metrics["scene_progression_score"] >= 0.72


def test_metadata_ctr_gate_rejects_explainer_title_and_weak_hashtags() -> None:
    script = {
        "title": "Por que o polvo muda de cor",
        "full_narration": "Polvos parecem comuns; então uma pista escondida rouba a cena.",
    }
    topic_plan = {"canonical_topic": "polvo muda de cor", "angle": "camuflagem"}

    result = MetadataCTRGate().validate(topic_plan, script, hashtags=["#curiosidades", "#viral"])

    assert not result.passed
    assert "title_too_explanatory" in result.reasons
    assert "weak_hashtags" in result.reasons
    assert result.metrics["title_click_tension_score"] < 0.72


def test_metadata_ctr_gate_accepts_specific_curiosity_title() -> None:
    script = {
        "title": "O polvo rouba a própria cor antes do predador notar",
        "full_narration": "Polvos parecem comuns; então uma pista escondida rouba a cena.",
    }
    topic_plan = {"canonical_topic": "polvo muda de cor", "angle": "camuflagem"}

    result = MetadataCTRGate().validate(topic_plan, script, hashtags=["#polvo", "#camuflagem", "#curiosidades"])

    assert result.passed
    assert result.metrics["title_click_tension_score"] >= 0.72
    assert result.metrics["hashtag_relevance_score"] >= 0.66


def test_growth_score_gate_blocks_when_any_growth_axis_is_low() -> None:
    quality_summary = {
        "script": {"viral_intensity": {"viral_intensity_score": 0.93, "viral_intensity_gate_pass": True}},
        "assets": {"visual_impact": {"visual_impact_score": 0.61, "visual_impact_gate_pass": False}},
        "metadata_ctr": {"metadata_ctr_score": 0.84, "metadata_ctr_gate_pass": True},
        "tts": {"voice_performance_score": 0.78},
        "render": {"render_gate_pass": True},
    }

    result = GrowthScoreGate().evaluate(quality_summary, monetization_report={"hard_blockers": [], "manual_required": []})

    assert not result.passed
    assert result.decision == "repair_required"
    assert "visual_impact_low" in result.reasons
    assert result.metrics["growth_score"] < 0.78


def test_growth_score_gate_accepts_strong_growth_package() -> None:
    quality_summary = {
        "script": {"viral_intensity": {"viral_intensity_score": 0.94, "viral_intensity_gate_pass": True}},
        "assets": {"visual_impact": {"visual_impact_score": 0.88, "visual_impact_gate_pass": True}},
        "metadata_ctr": {"metadata_ctr_score": 0.86, "metadata_ctr_gate_pass": True},
        "tts": {"voice_performance_score": 0.82},
        "render": {"render_gate_pass": True},
    }

    result = GrowthScoreGate().evaluate(quality_summary, monetization_report={"hard_blockers": [], "manual_required": []})

    assert result.passed
    assert result.decision == "ready_for_growth_review"
    assert result.metrics["growth_score"] >= 0.78


def test_growth_score_gate_treats_close_ready_script_viral_failure_as_warning_only() -> None:
    quality_summary = {
        "script": {
            "viral_intensity": {
                "viral_intensity_score": 0.76,
                "viral_intensity_gate_pass": False,
                "viral_intensity_ready_script_warning": True,
            }
        },
        "assets": {"visual_impact": {"visual_impact_score": 0.86, "visual_impact_gate_pass": True}},
        "metadata_ctr": {"metadata_ctr_score": 0.82, "metadata_ctr_gate_pass": True},
        "tts": {"voice_performance_score": 0.74},
        "render": {"render_gate_pass": True},
    }

    result = GrowthScoreGate().evaluate(quality_summary, monetization_report={"hard_blockers": [], "manual_required": []})

    assert result.passed
    assert "script_viral_intensity_low" not in result.reasons
    assert result.metrics["script_viral_intensity_warning_only"] is True


def test_monetization_pipeline_builds_growth_metadata_repair() -> None:
    pipeline = MonetizationPipeline.__new__(MonetizationPipeline)
    topic_plan = type("Topic", (), {"canonical_topic": "O polvo some sem sair do lugar", "angle": "camuflagem"})()
    script = type(
        "Script",
        (),
        {
            "title": "O polvo some sem sair do lugar",
            "hook": "O polvo está na frente do predador. Um segundo depois, o olho perde o alvo.",
            "key_facts": [],
            "qa_metrics": {"declared_hashtags": ["#curiosidades", "#shorts"]},
        },
    )()

    repair = pipeline.build_growth_metadata_repair(
        topic_plan,
        script,
        ["#curiosidades", "#shorts"],
        ["title_click_tension_low", "metadata_ctr_below_threshold"],
    )
    result = MetadataCTRGate().validate(topic_plan, {"title": repair["title"], "full_narration": script.hook}, repair["hashtags"])

    assert repair["applied"] is True
    assert repair["title"] == "O polvo some na sua frente antes do predador notar"
    assert result.passed


class _RepairingProvider:
    def __init__(self, repaired_script: dict) -> None:
        self.repaired_script = repaired_script
        self.calls: list[list[str]] = []

    def repair_script(self, script: dict, reasons: list[str], plan_dict: dict) -> dict:
        self.calls.append(reasons)
        return self.repaired_script


def test_script_pipeline_repairs_generated_script_when_viral_intensity_fails() -> None:
    repaired_script = {
        "title": "O céu laranja não vem do Sol",
        "hook": "O Sol não fica laranja no amanhecer; o ar rouba o azul antes dele chegar no seu olho.",
        "loop": "Se o Sol é o mesmo, por que o horizonte parece pegar fogo?",
        "body_beats": [
            "Quando ele nasce baixo, a luz cruza um corredor gigante de atmosfera.",
            "Nesse caminho, o azul se espalha primeiro e desaparece da linha direta que chega até você.",
            "O que sobra mais forte são tons quentes, como amarelo, laranja e vermelho.",
            "Por isso o céu parece incendiar justo quando a luz está mais filtrada.",
        ],
        "payoff": "O laranja é o resto da viagem da luz depois que o azul foi espalhado pelo ar.",
        "ending": "Da próxima vez que o amanhecer parecer fogo, lembra: você está vendo a atmosfera editando o Sol em tempo real.",
        "full_narration": "O Sol não fica laranja no amanhecer; o ar rouba o azul antes dele chegar no seu olho. Se o Sol é o mesmo, por que o horizonte parece pegar fogo? Quando ele nasce baixo, a luz cruza um corredor gigante de atmosfera. Nesse caminho, o azul se espalha primeiro e desaparece da linha direta que chega até você. O que sobra mais forte são tons quentes, como amarelo, laranja e vermelho. Por isso o céu parece incendiar justo quando a luz está mais filtrada. O laranja é o resto da viagem da luz depois que o azul foi espalhado pelo ar. Da próxima vez que o amanhecer parecer fogo, lembra: você está vendo a atmosfera editando o Sol em tempo real.",
    }
    provider = _RepairingProvider(repaired_script)
    pipeline = ScriptPipeline.__new__(ScriptPipeline)
    pipeline.owner = type(
        "Owner",
        (),
        {"viral_intensity_gate": ViralIntensityGate(), "providers": type("Providers", (), {"creative": provider})()},
    )()
    weak_script = {
        "title": "Por que o céu fica laranja no amanhecer",
        "hook": "Quando o sol aparece, a luz muda de cor em poucos segundos.",
        "full_narration": "Quando o sol aparece, a luz muda de cor em poucos segundos. A luz atravessa a atmosfera. O azul se espalha.",
    }

    script, metrics, repair_file = pipeline._validate_or_repair_viral_intensity(
        weak_script,
        plan_dict={"canonical_topic": "céu laranja"},
        ready_script_mode=False,
        job_id="job-test",
    )

    assert script is repaired_script
    assert metrics["viral_intensity_gate_pass"] is True
    assert repair_file == "viral_intensity_repair.json"
    assert provider.calls


def test_script_pipeline_blocks_generated_script_when_viral_repair_stays_weak() -> None:
    provider = _RepairingProvider({"title": "aula", "hook": "Quando isso ocorre, o processo acontece.", "full_narration": "Quando isso ocorre, o processo acontece."})
    pipeline = ScriptPipeline.__new__(ScriptPipeline)
    pipeline.owner = type(
        "Owner",
        (),
        {"viral_intensity_gate": ViralIntensityGate(), "providers": type("Providers", (), {"creative": provider})()},
    )()

    with pytest.raises(RecoverableStepError, match="viral intensity gate failed"):
        pipeline._validate_or_repair_viral_intensity(
            {"title": "aula", "hook": "Quando isso ocorre, o processo acontece.", "full_narration": "Quando isso ocorre, o processo acontece."},
            plan_dict={},
            ready_script_mode=False,
            job_id="job-test",
        )
