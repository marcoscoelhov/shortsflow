from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import get_settings
from app.providers.tts import GeminiTTSProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Gemini TTS without printing secrets.")
    parser.add_argument("--text", default="Teste curto de voz Gemini para validar os creditos do projeto.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        return _run_smoke(args.text, args.output_dir, keep_files=True, as_json=args.json)

    with TemporaryDirectory(prefix="yts-gemini-tts-") as tmp:
        return _run_smoke(args.text, Path(tmp), keep_files=False, as_json=args.json)


def _run_smoke(text: str, output_dir: Path, *, keep_files: bool, as_json: bool) -> int:
    settings = get_settings()
    audio_path = output_dir / "gemini_tts_smoke.wav"
    srt_path = output_dir / "gemini_tts_smoke.srt"
    try:
        result = GeminiTTSProvider().synthesize(
            text,
            audio_path,
            srt_path,
            {
                "title": "Teste Gemini TTS",
                "canonical_topic": "teste operacional",
                "hook": "validar voz primaria",
            },
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "passed": False,
            "error": str(exc),
            "gemini_api_key_configured": bool(settings.gemini_api_key),
            "gemini_tts_api_key_configured": bool(settings.gemini_tts_api_key),
            "gemini_tts_model": settings.gemini_tts_model,
        }
        _emit(payload, as_json=as_json)
        return 1

    metadata = dict(result.get("provider_metadata") or {})
    payload: dict[str, Any] = {
        "passed": result.get("provider") == "gemini_tts" and not bool(metadata.get("fallback_used")),
        "provider": result.get("provider"),
        "voice": result.get("voice"),
        "duration_ms": result.get("duration_ms"),
        "audio_exists": audio_path.exists(),
        "audio_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
        "srt_exists": srt_path.exists(),
        "kept_files": keep_files,
        "output_dir": str(output_dir) if keep_files else None,
        "fallback_used": bool(metadata.get("fallback_used")),
        "gemini_api_key_configured": bool(settings.gemini_api_key),
        "gemini_tts_api_key_configured": bool(settings.gemini_tts_api_key),
        "gemini_tts_model": settings.gemini_tts_model,
    }
    if metadata.get("fallback_used"):
        payload.update(
            {
                "fallback_from_provider": metadata.get("fallback_from_provider"),
                "fallback_provider": metadata.get("fallback_provider"),
                "fallback_reason": metadata.get("fallback_reason"),
                "fallback_chain": metadata.get("fallback_chain"),
            }
        )
    _emit(payload, as_json=as_json)
    return 0 if payload["passed"] else 1


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, value in payload.items():
        if value is not None:
            print(f"{key}= {value}")


if __name__ == "__main__":
    raise SystemExit(main())
