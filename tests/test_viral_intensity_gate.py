import pytest

from app.pipelines.common import RecoverableStepError
from app.pipelines.script_pipeline import ScriptPipeline
from app.quality.viral_intensity_gate import ViralIntensityGate


def test_viral_intensity_gate_blocks_morno_didatico_script() -> None:
    script = {
        "title": "Por que o céu fica laranja no amanhecer",
        "hook": "Quando o sol aparece, a luz muda de cor em poucos segundos.",
        "body_beats": [
            "A luz do sol atravessa uma camada mais espessa da atmosfera.",
            "As partículas menores de poeira e vapor deixam passar mais amarelo e laranja.",
            "A componente azul se espalha primeiro e chega fraca até nós.",
            "O efeito visual cresce no ponto em que o olhar encontra o horizonte.",
        ],
        "ending": "No fim, o céu só muda o filtro e isso ajuda a revelar como o ar muda durante o dia.",
        "full_narration": (
            "Quando o sol aparece, a luz muda de cor em poucos segundos. "
            "A luz do sol atravessa uma camada mais espessa da atmosfera. "
            "As partículas menores de poeira e vapor deixam passar mais amarelo e laranja. "
            "A componente azul se espalha primeiro e chega fraca até nós. "
            "O efeito visual cresce no ponto em que o olhar encontra o horizonte. "
            "No fim, o céu só muda o filtro e isso ajuda a revelar como o ar muda durante o dia."
        ),
    }

    result = ViralIntensityGate().validate(script)

    assert not result.passed
    assert "didactic_or_neutral_tone" in result.reasons
    assert result.metrics["viral_intensity_score"] < 0.88


def test_viral_intensity_gate_accepts_scroll_stopping_script() -> None:
    script = {
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
        "full_narration": (
            "O Sol não fica laranja no amanhecer; o ar rouba o azul antes dele chegar no seu olho. "
            "Se o Sol é o mesmo, por que o horizonte parece pegar fogo? "
            "Quando ele nasce baixo, a luz cruza um corredor gigante de atmosfera. "
            "Nesse caminho, o azul se espalha primeiro e desaparece da linha direta que chega até você. "
            "O que sobra mais forte são tons quentes, como amarelo, laranja e vermelho. "
            "Por isso o céu parece incendiar justo quando a luz está mais filtrada. "
            "O laranja é o resto da viagem da luz depois que o azul foi espalhado pelo ar. "
            "Da próxima vez que o amanhecer parecer fogo, lembra: você está vendo a atmosfera editando o Sol em tempo real."
        ),
    }

    result = ViralIntensityGate().validate(script)

    assert result.passed
    assert result.metrics["viral_intensity_score"] >= 0.88
    assert result.metrics["hook_scroll_stop_score"] >= 0.9
    assert result.metrics["curiosity_gap_score"] >= 0.85


def test_script_pipeline_rejects_generated_script_when_viral_intensity_fails() -> None:
    pipeline = ScriptPipeline.__new__(ScriptPipeline)
    pipeline.owner = type("Owner", (), {"viral_intensity_gate": ViralIntensityGate()})()
    script = {
        "title": "Por que o céu fica laranja no amanhecer",
        "hook": "Quando o sol aparece, a luz muda de cor em poucos segundos.",
        "body_beats": ["A luz atravessa a atmosfera.", "O azul se espalha.", "O laranja fica visível."],
        "ending": "Isso ajuda a revelar como o ar muda durante o dia.",
        "full_narration": "Quando o sol aparece, a luz muda de cor em poucos segundos. A luz atravessa a atmosfera. O azul se espalha. O laranja fica visível. Isso ajuda a revelar como o ar muda durante o dia.",
    }

    with pytest.raises(RecoverableStepError, match="viral intensity gate failed"):
        pipeline._validate_viral_intensity(script, ready_script_mode=False)


def test_script_pipeline_treats_ready_script_bank_viral_failure_as_diagnostic() -> None:
    pipeline = ScriptPipeline.__new__(ScriptPipeline)
    pipeline.owner = type("Owner", (), {"viral_intensity_gate": ViralIntensityGate()})()
    script = {
        "title": "Por que o céu fica laranja no amanhecer",
        "hook": "Quando o sol aparece, a luz muda de cor em poucos segundos.",
        "body_beats": ["A luz atravessa a atmosfera.", "O azul se espalha.", "O laranja fica visível."],
        "ending": "Isso ajuda a revelar como o ar muda durante o dia.",
        "full_narration": "Quando o sol aparece, a luz muda de cor em poucos segundos. A luz atravessa a atmosfera. O azul se espalha. O laranja fica visível. Isso ajuda a revelar como o ar muda durante o dia.",
    }

    returned_script, metrics, repair_file = pipeline._validate_or_repair_viral_intensity(
        script,
        plan_dict={},
        ready_script_mode=True,
        ready_script_bank_mode=True,
        job_id="bank-script-diagnostic",
    )

    assert returned_script is script
    assert repair_file is None
    assert metrics["viral_intensity_gate_pass"] is False
    assert metrics["viral_intensity_hard_block"] is True
    assert metrics["ready_script_bank_policy"] == "viral_intensity_diagnostic_only"


def test_script_pipeline_blocks_ready_script_when_viral_intensity_fails() -> None:
    pipeline = ScriptPipeline.__new__(ScriptPipeline)
    pipeline.owner = type("Owner", (), {"viral_intensity_gate": ViralIntensityGate()})()
    script = {
        "title": "Por que o céu fica laranja no amanhecer",
        "hook": "Quando o sol aparece, a luz muda de cor em poucos segundos.",
        "full_narration": "Quando o sol aparece, a luz muda de cor em poucos segundos. A luz atravessa a atmosfera. O azul se espalha.",
    }

    with pytest.raises(RecoverableStepError, match="viral intensity gate failed"):
        pipeline._validate_viral_intensity(script, ready_script_mode=True)
