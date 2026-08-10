from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.remotion_renderer import RemotionCliRenderer
from app.runtime_execution import RuntimeExecutionCoordinator


router = APIRouter()


@router.get("/healthz")
def healthcheck() -> dict[str, Any]:
    settings = get_settings()
    remotion = RemotionCliRenderer(allowed_media_root=settings.artifacts_dir).preflight_environment()
    runtime = RuntimeExecutionCoordinator(settings).status()
    runtime["worker_enabled"] = settings.worker_enabled
    return {
        "status": "ok",
        "app": settings.app_name,
        "bind": f"{settings.app_host}:{settings.app_port}",
        "runtime": runtime,
        "tailnet_url": f"https://{settings.tailscale_hostname}.{settings.tailnet_domain}",
        "providers": {
            "mode": "mock" if settings.use_mock_providers else "production",
            "llm_primary": settings.llm_primary_provider,
            "llm_gate_judge": settings.llm_gate_judge_provider,
            "llm_gate_judge_model": settings.llm_gate_judge_model,
            "tts_primary": settings.tts_primary_provider,
            "render_backend": "remotion",
        },
        "render": {
            "primary_backend": "remotion",
            "remotion_ready": bool(remotion["ready"]),
            "remotion_missing_items": remotion["missing_items"],
        },
    }
