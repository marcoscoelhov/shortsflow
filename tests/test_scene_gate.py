from app.quality.scene_gate import ScenePlanGate


def test_hook_must_hide_respects_negated_visual_prompt() -> None:
    scenes = [
        {
            "scene_id": "scene-1",
            "order": 1,
            "retention_role": "visual_hook",
            "visual_intent": "subject_in_context",
            "narration_text": "buraco negro que existia antes da própria galáxia",
            "primary_subject": "buraco negro supermassivo solitário",
            "image_prompt": "solitary black hole in empty darkness, no galaxy, no stars, no readable text anywhere",
            "token_start": 0,
            "token_end": 7,
        }
    ]
    contract = {
        "hook_frame": {
            "recommended_visual_intent": "subject in context",
            "must_show": ["buraco negro"],
            "must_hide": ["galáxia"],
        }
    }

    result = ScenePlanGate().validate(scenes, expected_scene_count=1, visual_contract=contract)

    assert result.passed
