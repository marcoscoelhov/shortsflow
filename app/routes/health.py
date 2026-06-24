from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.remotion_renderer import RemotionCliRenderer


router = APIRouter()


@router.get("/healthz")
def healthcheck() -> dict[str, Any]:
    settings = get_settings()
    remotion = RemotionCliRenderer(allowed_media_root=settings.artifacts_dir).preflight_environment()
    return {
        "status": "ok",
        "app": settings.app_name,
        "bind": f"{settings.app_host}:{settings.app_port}",
        "tailnet_url": f"https://{settings.tailscale_hostname}.{settings.tailnet_domain}",
        "providers": {
            "mode": "mock" if settings.use_mock_providers else "production",
            "llm_primary": settings.llm_primary_provider,
            "tts_primary": settings.tts_primary_provider,
            "render_backend": settings.render_primary_backend,
        },
        "render": {
            "primary_backend": settings.render_primary_backend,
            "remotion_ready": bool(remotion["ready"]),
            "remotion_missing_items": remotion["missing_items"],
        },
    }
