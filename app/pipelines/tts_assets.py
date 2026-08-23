from __future__ import annotations

import subprocess
import wave
from pathlib import Path
from typing import Any

import imageio_ffmpeg

from app.utils import ms_to_srt, parse_srt


def tts_duration_bounds_ms(target_duration_sec: int) -> tuple[int, int]:
    if target_duration_sec <= 55:
        return 35_000, 55_000
    minimum = max(35_000, round(target_duration_sec * 0.80 * 1000))
    maximum = min(175_000, (target_duration_sec + 25) * 1000)
    return minimum, maximum


class TTSDomain:
    def __init__(self, pipeline: Any) -> None:
        self.pipeline = pipeline

    def fit_tts_duration(
        self,
        audio_path: Path,
        srt_path: Path,
        result: dict[str, Any],
        *,
        target_duration_sec: int,
    ) -> dict[str, Any]:
        if target_duration_sec > 55:
            return result
        duration_ms = int(result["duration_ms"])
        target_ms: int | None = None
        if duration_ms > 55_000:
            target_ms = 54_000
        # Do not expand (slow down) short audio <35s; let the range check in caller fail the step.
        if target_ms is None:
            return result
        speed = duration_ms / target_ms
        if not 0.5 <= speed <= 1.12:  # tighten: only mild compress <=1.12; no expand at all
            return result
        temp_audio = audio_path.with_suffix(".fit.wav")
        try:
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-i",
                    str(audio_path),
                    "-filter:a",
                    f"atempo={speed:.6f},loudnorm=I=-16:LRA=11:TP=-1.5",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    str(temp_audio),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            temp_audio.replace(audio_path)
            self.scale_srt_timings(srt_path, speed)
        finally:
            temp_audio.unlink(missing_ok=True)
        adjusted = dict(result)
        adjusted["duration_ms"] = self.measure_audio_ms(audio_path)
        provider_metadata = dict(adjusted.get("provider_metadata") or {})
        provider_metadata.update(
            {
                "duration_fit_applied": True,
                "duration_fit_original_ms": duration_ms,
                "duration_fit_target_ms": target_ms,
                "duration_fit_speed": round(speed, 6),
            }
        )
        adjusted["provider_metadata"] = provider_metadata
        return adjusted

    def scale_srt_timings(self, srt_path: Path, speed: float) -> None:
        cues = parse_srt(srt_path.read_text(encoding="utf-8"))
        blocks = []
        for cue in cues:
            start_ms = max(0, round(int(cue["start_ms"]) / speed))
            end_ms = max(start_ms + 1, round(int(cue["end_ms"]) / speed))
            blocks.append(f"{cue['idx']}\n{ms_to_srt(start_ms)} --> {ms_to_srt(end_ms)}\n{cue['text']}")
        srt_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    def measure_audio_ms(self, audio_path: Path) -> int:
        with wave.open(str(audio_path), "rb") as wav_file:
            return int(wav_file.getnframes() / wav_file.getframerate() * 1000)
