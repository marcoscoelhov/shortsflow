from tests.e2e_support import _base_script

from app.quality.script_gate import ScriptQualityGate


def test_script_gate_accepts_grounded_retention_map_list_items() -> None:
    narration = (
        "HD 189733b parece azul, mas o vento pode levar vidro de lado. "
        "O azul esconde uma atmosfera extrema. "
        "Partículas de silicato podem circular no céu. "
        "Ventos intensos levam esse material pelo horizonte. "
        "Quando você rever o azul, imagine a tempestade lateral."
    )
    script = _base_script(narration)
    retention_map = script["retention_map"]
    assert isinstance(retention_map, dict)
    retention_map["escalation"] = [
        "Partículas de silicato podem circular no céu.",
        "Ventos intensos levam esse material pelo horizonte.",
    ]

    result = ScriptQualityGate().validate(script, target_duration_sec=45)

    assert "retention_map_not_grounded_in_narration" not in result.reasons
    assert result.metrics["structured_viral_gate"]["retention_map_ungrounded_keys"] == []


def test_script_gate_rejects_any_ungrounded_retention_map_list_item() -> None:
    narration = (
        "HD 189733b parece azul, mas o vento pode levar vidro de lado. "
        "O azul esconde uma atmosfera extrema. "
        "Partículas de silicato podem circular no céu. "
        "Ventos intensos levam esse material pelo horizonte. "
        "Quando você rever o azul, imagine a tempestade lateral."
    )
    script = _base_script(narration)
    retention_map = script["retention_map"]
    assert isinstance(retention_map, dict)
    retention_map["escalation"] = [
        "Partículas de silicato podem circular no céu.",
        "Este trecho não existe na narração.",
    ]

    result = ScriptQualityGate().validate(script, target_duration_sec=45)

    assert "retention_map_not_grounded_in_narration" in result.reasons
    assert result.metrics["structured_viral_gate"]["retention_map_ungrounded_keys"] == ["escalation"]
