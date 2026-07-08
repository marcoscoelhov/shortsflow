from app.quality.asset_visual_gate import AssetVisualGate


def test_hook_must_hide_respects_negated_visual_prompt() -> None:
    scenes = [
        {
            "scene_id": "1",
            "order": 1,
            "retention_role": "visual_hook",
            "visual_intent": "subject_in_context",
            "narration_text": "buraco negro que existia antes da própria galáxia",
            "primary_subject": "buraco negro supermassivo solitário",
            "topic_hint": "O buraco negro que nasceu antes da própria galáxia",
            "image_prompt": "solitary black hole in empty darkness, no galaxy, no stars, no readable text anywhere",
        }
    ]
    assets = [
        {
            "scene_id": "1",
            "provider": "minimax",
            "prompt_snapshot": "solitary black hole in empty darkness, no galaxy, no stars, no readable text anywhere",
            "semantic_match": 0.95,
            "total_score": 0.9,
        }
    ]
    contract = {
        "hook_frame": {
            "recommended_visual_intent": "subject in context",
            "must_show": ["buraco negro"],
            "must_hide": ["galáxia"],
        }
    }

    result = AssetVisualGate().validate(assets, scenes, visual_contract=contract)

    assert result.passed
