from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import RenderOutput
from app.utils import file_sha256, file_uri, path_from_uri


def promote_render_output_to_file(
    render: RenderOutput,
    *,
    selected_video_path: Path,
    job_dir: Path,
    artifact_index: dict[str, Any],
    selected_render_ref: str,
    previous_video_uri: str | None = None,
    fallback_standard_ref: str | None = None,
) -> tuple[dict[str, Any], str]:
    original_video_uri = previous_video_uri or str(render.video_uri or "")
    render.video_uri = file_uri(selected_video_path)
    render.filesize_bytes = selected_video_path.stat().st_size
    render.content_hash = file_sha256(selected_video_path)

    updated_index = dict(artifact_index or {})
    try:
        original_render_ref = str(path_from_uri(original_video_uri).resolve().relative_to(job_dir.resolve()))
    except (OSError, ValueError):
        original_render_ref = str(updated_index.get("render") or original_video_uri)
    if original_render_ref and original_render_ref != selected_render_ref:
        updated_index["standard_render"] = str(updated_index.get("standard_render") or original_render_ref)
    elif fallback_standard_ref and not updated_index.get("standard_render"):
        updated_index["standard_render"] = fallback_standard_ref
    updated_index["render"] = selected_render_ref
    updated_index["premium_video"] = selected_render_ref
    return updated_index, original_video_uri
