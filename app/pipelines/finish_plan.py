from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import BackgroundMusicAsset, Job, NarrationAsset, RenderOutput, SceneAsset, ScenePlan, SubtitleTrack
from app.pipelines.timeline import normalize_scene_timings
from app.utils import path_from_uri, stable_hash


FINISH_PLAN_VERSION = "finish-plan-v1"
PREMIUM_FINISHING_PACKAGE = "Pacote de Acabamento Premium Inicial"


def build_finish_plan(
    *,
    schema_version: str,
    job: Job,
    scene_plan: ScenePlan,
    selected_assets: list[SceneAsset],
    narration: NarrationAsset,
    subtitles: SubtitleTrack,
    background_music: BackgroundMusicAsset | None,
    render: RenderOutput | None,
    visual_contract: dict[str, Any] | None = None,
    media_base_url: str | None = None,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    scene_segments = normalize_scene_timings(scene_plan.scenes, narration.duration_ms)
    assets_by_scene = {asset.scene_id: asset for asset in selected_assets}
    contract = visual_contract if isinstance(visual_contract, dict) else {}
    scenes = []
    for index, scene in enumerate(scene_segments):
        asset = assets_by_scene.get(str(scene.get("scene_id")))
        if asset is None:
            raise ValueError(f"missing selected asset for scene {scene.get('scene_id')}")
        start_ms = int(scene.get("actual_start_ms") or 0)
        end_ms = int(scene.get("actual_end_ms") or start_ms)
        scenes.append(
            {
                "scene_id": str(scene.get("scene_id") or f"scene-{index + 1}"),
                "order": int(scene.get("order") or index + 1),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": max(500, end_ms - start_ms),
                "asset_uri": asset.uri,
                "asset_src": _media_src(asset.uri, media_base_url=media_base_url, artifacts_dir=artifacts_dir),
                "asset_path": str(path_from_uri(asset.uri)),
                "retention_role": str(scene.get("retention_role") or _retention_role_for_index(index, len(scene_segments))),
                "visual_intent": str(scene.get("visual_intent") or ""),
                "primary_subject": str(scene.get("primary_subject") or ""),
                "narration_text": str(scene.get("narration_text") or ""),
                "motion": _motion_for_scene(index, len(scene_segments), scene),
                "transition": _transition_for_scene(index, len(scene_segments), scene),
                "overlays": _overlays_for_scene(index, len(scene_segments), scene, contract),
            }
        )
    audio_uri = (
        background_music.mixed_audio_uri
        if background_music and background_music.mixed_audio_uri
        else narration.normalized_audio_uri or narration.audio_uri
    )
    captions = [_caption_item(item) for item in subtitles.items or []]
    plan = {
        "schema_version": schema_version,
        "finish_plan_version": FINISH_PLAN_VERSION,
        "plan_name": "Plano de Acabamento Editorial",
        "finishing_package": PREMIUM_FINISHING_PACKAGE,
        "job_id": job.job_id,
        "content_hash": stable_hash(
            {
                "job_id": job.job_id,
                "scene_plan": scene_plan.content_hash,
                "narration": narration.content_hash,
                "subtitles": subtitles.content_hash,
                "assets": [asset.content_hash for asset in selected_assets],
            }
        ),
        "canvas": {"width": 1080, "height": 1920, "fps": 30, "duration_ms": narration.duration_ms},
        "audio": {
            "uri": audio_uri,
            "src": _media_src(audio_uri, media_base_url=media_base_url, artifacts_dir=artifacts_dir),
            "path": str(path_from_uri(audio_uri)),
            "duration_ms": narration.duration_ms,
            "source": "mixed_background" if background_music and background_music.mixed_audio_uri else "narration",
        },
        "source_final_video_uri": render.video_uri if render else None,
        "visual_contract_summary": {
            "visual_thesis": str(contract.get("visual_thesis") or ""),
            "visual_domain": str(contract.get("visual_domain") or ""),
            "visual_world": str(contract.get("visual_world") or ""),
        },
        "style": {
            "component_policy": "free_only",
            "caption_style": "one_line_kinetic",
            "font_family": "Inter, system-ui, sans-serif",
            "palette": {
                "background": "oklch(0.13 0.012 25)",
                "text": "oklch(0.96 0.012 35)",
                "muted": "oklch(0.72 0.028 35)",
                "accent": "oklch(0.69 0.19 31)",
                "accent_soft": "oklch(0.84 0.08 31)",
            },
            "safe_area": {"x": 72, "top": 132, "bottom": 250},
        },
        "caption_track": {
            "mode": "one_line_kinetic",
            "max_lines": 1,
            "items": captions,
        },
        "scenes": scenes,
        "summary": {
            "scene_count": len(scenes),
            "caption_count": len(captions),
            "premium_features": [
                "captions_animadas",
                "transicoes_semanticas",
                "enquadramento_estavel_de_cena",
                "sem_texto_superior_editorial",
                "identidade_visual_consistente",
            ],
        },
    }
    return plan


def _media_src(uri: str, *, media_base_url: str | None, artifacts_dir: Path | None) -> str:
    if not media_base_url or not artifacts_dir or not uri.startswith("file://"):
        return uri
    try:
        path = path_from_uri(uri).resolve()
        relative_path = path.relative_to(artifacts_dir.resolve())
    except (OSError, ValueError):
        return uri
    return f"{media_base_url.rstrip('/')}/{relative_path.as_posix()}"


def _caption_item(item: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(item.get("text") or "").split())
    start_ms = max(0, int(item.get("start_ms") or 0))
    end_ms = max(1, int(item.get("end_ms") or 0))
    return {
        "idx": str(item.get("idx") or ""),
        "startMs": start_ms,
        "endMs": end_ms,
        "timestampMs": start_ms,
        "confidence": None,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "text": text,
        "emphasis": _caption_emphasis(text),
    }


def _caption_emphasis(text: str) -> list[str]:
    words = [word.strip(".,:;!?()[]{}").lower() for word in text.split()]
    candidates = [word for word in words if len(word) >= 6]
    return candidates[:2]


def _retention_role_for_index(index: int, scene_count: int) -> str:
    if index == 0:
        return "visual_hook"
    if index == scene_count - 1:
        return "loop_close"
    if index >= max(1, scene_count - 2):
        return "turn_or_payoff"
    return "visual_evidence"


def _motion_for_scene(index: int, scene_count: int, scene: dict[str, Any]) -> dict[str, Any]:
    role = str(scene.get("retention_role") or _retention_role_for_index(index, scene_count))
    if index == 0:
        return {"kind": "subtle_push", "start_scale": 1.04, "end_scale": 1.18, "x_delta": 18, "y_delta": -48}
    if role in {"turn_or_payoff", "loop_close"}:
        direction = -1 if index % 2 else 1
        return {"kind": "payoff_pulse", "start_scale": 1.05, "end_scale": 1.2, "x_delta": 42 * direction, "y_delta": -22}
    direction = -1 if index % 2 else 1
    return {"kind": "slow_drift", "start_scale": 1.06, "end_scale": 1.17, "x_delta": 58 * direction, "y_delta": -26}


def _transition_for_scene(index: int, scene_count: int, scene: dict[str, Any]) -> dict[str, Any]:
    role = str(scene.get("retention_role") or _retention_role_for_index(index, scene_count))
    if index == 0:
        return {"kind": "cold_open", "duration_ms": 0}
    if role in {"turn_or_payoff", "loop_close"}:
        return {"kind": "payoff_reveal", "duration_ms": 240}
    if role == "visual_evidence":
        return {"kind": "evidence_cut", "duration_ms": 180}
    return {"kind": "soft_cut", "duration_ms": 160}


def _overlays_for_scene(
    index: int,
    scene_count: int,
    scene: dict[str, Any],
    visual_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    return []
