from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TARGET_SCORE = 9.2


@dataclass
class StageScore:
    stage: str
    score: float
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _score_from_ratio(value: float, *, floor: float = 6.0, ceiling: float = 10.0) -> float:
    return round(max(floor, min(ceiling, floor + (ceiling - floor) * value)), 1)


def _bool_score(value: Any, good: float = 9.4, bad: float = 5.0) -> float:
    return good if bool(value) else bad


def _cap(score: float, cap: float, gaps: list[str], reason: str) -> float:
    if score > cap:
        gaps.append(reason)
        return cap
    return score


def score_topic(root: Path) -> StageScore:
    data = _load_json(root / "topic_plan.json")
    metrics = data.get("quality_metrics") if isinstance(data.get("quality_metrics"), dict) else {}
    evidence: list[str] = []
    gaps: list[str] = []
    required_groups = [
        ("loop", "loop_sustentavel", "loop_sustained"),
        ("payoff", "payoff_tardio"),
        ("replay_trigger", "replay_mental", "provoca_replay"),
        ("promessa_verificável", "promessa_verificavel"),
        ("beats", "escalada_de_impacto", "retencao_esperada"),
    ]
    passed = sum(1 for group in required_groups if any(metrics.get(key) for key in group))
    score = _score_from_ratio(passed / max(len(required_groups), 1), floor=6.2)
    if metrics.get("topic_uniqueness_pass"):
        score += 0.3
        evidence.append("topic_uniqueness_pass")
    else:
        gaps.append("topic uniqueness missing or failed")
    if metrics.get("fallback_used"):
        score -= 0.2
        gaps.append("topic provider fallback used")
    evidence.append(f"{passed}/{len(required_groups)} topic quality fields passed")
    return StageScore("topic_plan", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_script(root: Path) -> StageScore:
    script = _load_json(root / "script.json")
    audit = _load_json(root / "text_publish_audit.json")
    metrics = script.get("qa_metrics") if isinstance(script.get("qa_metrics"), dict) else {}
    audit_payload = audit.get("audit") if isinstance(audit.get("audit"), dict) else audit
    evidence: list[str] = []
    gaps: list[str] = []
    component_values = [
        float(metrics.get("hook_score") or 0),
        float(metrics.get("clarity_score") or 0),
        float(metrics.get("information_density_score") or 0),
        float(metrics.get("ending_strength_score") or 0),
        1.0 - min(float(metrics.get("repetition_score") or 1), 1.0),
    ]
    score = round(sum(component_values) / max(len(component_values), 1) * 10, 1)
    if metrics.get("script_quality_gate_pass"):
        evidence.append("script_quality_gate_pass")
        score = max(score, 8.8)
    else:
        gaps.append("script quality gate not proven")
    if audit and not audit_payload.get("passed", False):
        score = min(score, 8.5)
        gaps.append("text publish audit did not pass")
    elif audit:
        evidence.append("text_publish_audit present")
        if audit_payload.get("skipped"):
            score = _cap(score, 9.0, gaps, "text publish audit was skipped by simple mode")
    else:
        score = min(score, 8.6)
        gaps.append("text publish audit missing")
    if metrics.get("script_generation_fallback_used"):
        score -= 0.2
        gaps.append("script provider fallback used")
    if metrics.get("fact_pack_consistency_pass"):
        score += 0.1
        evidence.append("fact_pack_consistency_pass")
    structured_gate = metrics.get("structured_viral_gate") if isinstance(metrics.get("structured_viral_gate"), dict) else {}
    if structured_gate.get("retention_map_complete") and structured_gate.get("body_beat_count_valid"):
        score += 0.2
        evidence.append("structured viral gate complete")
    claim_trace = metrics.get("claim_trace") if isinstance(metrics.get("claim_trace"), dict) else {}
    if claim_trace.get("missing_risky_claim_trace") is False:
        score += 0.1
        evidence.append("risky claim trace covered")
    return StageScore("script", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_visual_contract(root: Path) -> StageScore:
    contract = _load_json(root / "visual_contract.json")
    gaps: list[str] = []
    evidence: list[str] = []
    required = ["visual_thesis", "hook_frame", "loop_policy", "payoff_frame", "visual_domain"]
    present = sum(1 for key in required if contract.get(key))
    score = _score_from_ratio(present / max(len(required), 1), floor=5.8)
    if present == len(required):
        evidence.append("visual contract has hook, loop, payoff and domain")
    else:
        gaps.append("visual contract incomplete")
    return StageScore("visual_contract", score, evidence, gaps)


def score_scene_plan(root: Path) -> StageScore:
    scene_plan = _load_json(root / "scene_plan.json")
    scenes = scene_plan.get("scenes") if isinstance(scene_plan.get("scenes"), list) else []
    gaps: list[str] = []
    evidence: list[str] = []
    score = 5.0
    if scenes:
        score = 8.2
        evidence.append(f"{len(scenes)} scenes present")
    if len(scenes) >= 5:
        score += 0.5
    roles = {str(scene.get("retention_role") or "") for scene in scenes}
    required_roles = {"visual_hook", "proof_or_tension", "escalation", "turn_or_payoff", "loop_close"}
    role_ratio = len(roles & required_roles) / len(required_roles)
    score += role_ratio
    if role_ratio < 0.8:
        gaps.append("retention roles incomplete")
    prompts = [str(scene.get("image_prompt") or "") for scene in scenes]
    if prompts and all("no readable text" in prompt.lower() for prompt in prompts):
        score += 0.3
        evidence.append("all scene prompts include no-text constraint")
    else:
        gaps.append("scene prompt no-text constraint missing")
    if any(len(prompt) > 1500 for prompt in prompts):
        score = min(score, 8.8)
        gaps.append("one or more image prompts exceed MiniMax limit")
    return StageScore("scene_plan", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_image_semantics(root: Path) -> StageScore:
    gate = _load_json(root / "asset_visual_gate.json")
    visual_review = _load_json(root / "visual_review_report.json")
    metrics = gate.get("metrics") if isinstance(gate.get("metrics"), dict) else {}
    selected = gate.get("selected_assets") if isinstance(gate.get("selected_assets"), list) else []
    gaps: list[str] = []
    evidence: list[str] = []
    if not gate:
        return StageScore("image_semantics", 0.0, [], ["asset_visual_gate.json missing"])
    scene_reports = metrics.get("scenes") if isinstance(metrics.get("scenes"), list) else []
    scores = [float(item.get("total_score") or 0) for item in scene_reports]
    mean_score = sum(scores) / len(scores) if scores else 0.0
    score = round(mean_score * 10, 1)
    if metrics.get("asset_visual_gate_pass") and metrics.get("checked"):
        score = max(score, 8.4)
        evidence.append("asset visual gate checked and passed")
    else:
        gaps.append("asset visual gate missing or failed")
    verification_modes = {
        str((asset.get("scores") or {}).get("verification_mode") or asset.get("verification_mode") or "")
        for asset in selected
        if isinstance(asset, dict)
    }
    if "prompt_heuristic" in verification_modes or not selected:
        if visual_review.get("passed") and str(visual_review.get("reviewer") or "").lower() in {"codex_vision", "human_vision"}:
            score = max(score, 9.4)
            evidence.append(f"visual review passed by {visual_review.get('reviewer')}")
        else:
            score = _cap(score, 8.2, gaps, "image semantics used prompt heuristic instead of real vision")
    if any(str(asset.get("provider") or "") == "local_semantic" for asset in selected if isinstance(asset, dict)):
        score = _cap(score, 8.0, gaps, "selected image used local semantic fallback")
    return StageScore("image_semantics", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_tts(root: Path) -> StageScore:
    narration = _load_json(root / "narration_asset.json")
    metadata = narration.get("provider_metadata") if isinstance(narration.get("provider_metadata"), dict) else {}
    gaps: list[str] = []
    evidence: list[str] = []
    score = 0.0
    provider = str(narration.get("provider") or "")
    if provider == "gemini_tts" and not metadata.get("fallback_used"):
        score = 8.8
        evidence.append("Gemini TTS used without fallback")
    elif provider:
        score = 7.2
        gaps.append(f"TTS provider is {provider}")
    else:
        gaps.append("narration asset missing")
    duration_ms = int(narration.get("duration_ms") or 0)
    if 35_000 <= duration_ms <= 55_000:
        score += 0.4
        evidence.append("narration duration inside 35-55s")
    else:
        gaps.append("narration duration outside target window")
    if metadata.get("voice_direction_used"):
        score += 0.2
        evidence.append("voice direction used")
    else:
        gaps.append("voice direction missing")
    if metadata.get("voice_profile"):
        score += 0.5
        evidence.append(f"voice profile: {metadata.get('voice_profile')}")
    else:
        score = _cap(score, 8.9, gaps, "Gemini voice profile selection not recorded")
    return StageScore("tts_narrator", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_subtitles(root: Path) -> StageScore:
    track = _load_json(root / "subtitle_track.json")
    gaps: list[str] = []
    evidence: list[str] = []
    coverage = float(track.get("coverage_ratio") or 0)
    p95 = int(track.get("p95_drift_ms") or 0)
    max_drift = int(track.get("max_drift_ms") or 0)
    score = 5.0
    if coverage >= 0.99:
        score += 2.0
        evidence.append(f"coverage={coverage}")
    else:
        gaps.append(f"coverage below 0.99: {coverage}")
    if p95 <= 800:
        score += 1.4
        evidence.append(f"p95_drift_ms={p95}")
    elif p95 <= 1200:
        score += 0.9
        gaps.append(f"p95 drift acceptable but not strong: {p95}ms")
    else:
        gaps.append(f"p95 drift high: {p95}ms")
    if max_drift <= 1200:
        score += 1.0
        evidence.append(f"max_drift_ms={max_drift}")
    elif max_drift <= 1800:
        score += 0.6
        gaps.append(f"max drift acceptable but not strong: {max_drift}ms")
    else:
        gaps.append(f"max drift high: {max_drift}ms")
    if track.get("items"):
        score += 0.4
    else:
        gaps.append("subtitle items missing")
    return StageScore("subtitle_timing", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_background_music(root: Path) -> StageScore:
    report = _load_json(root / "background_music_quality_report.json")
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    gaps: list[str] = []
    evidence: list[str] = []
    if not report:
        return StageScore("background_music", 0.0, [], ["background_music_quality_report.json missing"])
    score = _bool_score(report.get("passed"), good=9.0, bad=5.5)
    if report.get("passed"):
        evidence.append("background music quality gate passed")
    else:
        gaps.extend(str(item) for item in report.get("reasons") or [])
    expected = int(metrics.get("expected_duration_ms") or 0)
    mixed = metrics.get("mixed") if isinstance(metrics.get("mixed"), dict) else {}
    mixed_duration = int(mixed.get("duration_ms") or 0)
    if expected and abs(expected - mixed_duration) <= 800:
        score += 0.5
        evidence.append("mixed audio duration drift <=800ms")
    bed_ratio = float(metrics.get("bed_relative_rms_ratio") or 0)
    if 0.015 <= bed_ratio <= 0.45:
        score += 0.3
        evidence.append("music bed audible and controlled")
    return StageScore("background_music", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_render(root: Path) -> StageScore:
    render = _load_json(root / "render_output.json")
    gaps: list[str] = []
    evidence: list[str] = []
    if not render:
        return StageScore("render", 0.0, [], ["render_output.json missing"])
    score = 8.0
    duration = int(render.get("duration_ms") or 0)
    if 35_000 <= duration <= 55_000:
        score += 0.8
        evidence.append("render duration inside 35-55s")
    else:
        gaps.append("render duration outside publish window")
    if (root / "render" / "final.mp4").exists():
        score += 0.7
        evidence.append("final.mp4 exists")
    else:
        gaps.append("final.mp4 missing")
    if (root / "render" / "poster.jpg").exists():
        score += 0.2
    return StageScore("render", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def score_publish(root: Path) -> StageScore:
    report = _load_json(root / "monetization_report.json")
    package = _load_json(root / "publish_package.json")
    gaps: list[str] = []
    evidence: list[str] = []
    if not report:
        return StageScore("publish_readiness", 0.0, [], ["monetization_report.json missing"])
    score = _bool_score(report.get("passed"), good=9.0, bad=4.5)
    if report.get("final_status") == "ready_for_upload":
        score += 0.5
        evidence.append("final_status=ready_for_upload")
    else:
        gaps.append(f"final_status={report.get('final_status')}")
    blockers = list(report.get("hard_blockers") or [])
    if blockers:
        score = min(score, 7.0)
        gaps.extend(str(item) for item in blockers[:5])
    else:
        evidence.append("no hard blockers")
    manual_required = list(report.get("manual_required") or [])
    if manual_required:
        score = min(score, 8.9)
        gaps.append(f"manual confirmations required: {', '.join(map(str, manual_required[:5]))}")
    if package.get("status") == "ready_for_upload":
        score += 0.2
    elif package.get("status"):
        gaps.append(f"publish_package status={package.get('status')}")
    return StageScore("publish_readiness", round(max(0.0, min(10.0, score)), 1), evidence, gaps)


def audit(root: Path) -> dict[str, Any]:
    scorers = [
        score_topic,
        score_script,
        score_visual_contract,
        score_scene_plan,
        score_image_semantics,
        score_tts,
        score_subtitles,
        score_background_music,
        score_render,
        score_publish,
    ]
    stages = [scorer(root) for scorer in scorers]
    overall = round(min(stage.score for stage in stages), 1) if stages else 0.0
    return {
        "job_id": root.name,
        "target_score": TARGET_SCORE,
        "overall_min_score": overall,
        "passed_target": all(stage.score >= TARGET_SCORE for stage in stages),
        "stages": [
            {
                "stage": stage.stage,
                "score": stage.score,
                "target_pass": stage.score >= TARGET_SCORE,
                "evidence": stage.evidence,
                "gaps": stage.gaps,
            }
            for stage in stages
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit YTS Render job quality scores from persisted artifacts.")
    parser.add_argument("job_id")
    parser.add_argument("--artifacts-dir", default="data/artifacts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.artifacts_dir) / args.job_id
    result = audit(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"Job: {result['job_id']}")
    print(f"Target: {TARGET_SCORE:.1f}+")
    print(f"Overall min score: {result['overall_min_score']:.1f}")
    print("")
    for stage in result["stages"]:
        status = "PASS" if stage["target_pass"] else "FAIL"
        print(f"{stage['stage']:<22} {stage['score']:>4.1f}  {status}")
        if stage["evidence"]:
            print(f"  evidence: {'; '.join(stage['evidence'])}")
        if stage["gaps"]:
            print(f"  gaps: {'; '.join(stage['gaps'])}")


if __name__ == "__main__":
    main()
