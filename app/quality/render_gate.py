from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import imageio_ffmpeg


@dataclass(frozen=True)
class RenderGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class RenderGate:
    def __init__(self, min_bitrate: int = 250_000) -> None:
        self.min_bitrate = min_bitrate

    def validate(self, video_path: Path, expected_duration_ms: int) -> RenderGateResult:
        reasons: list[str] = []
        metrics: dict[str, Any] = {"path": str(video_path)}
        if not video_path.exists() or video_path.stat().st_size <= 0:
            return RenderGateResult(False, ["missing_render_file"], metrics)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            return RenderGateResult(False, ["ffprobe_failed"], {"stderr": probe.stderr})
        data = json.loads(probe.stdout or "{}")
        streams = data.get("streams") or []
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt = data.get("format") or {}
        duration_ms = round(float(fmt.get("duration") or 0) * 1000)
        size = int(fmt.get("size") or video_path.stat().st_size)
        bitrate = int(fmt.get("bit_rate") or 0)
        metrics.update(
            {
                "duration_ms": duration_ms,
                "size_bytes": size,
                "bit_rate": bitrate,
                "video": video_stream,
                "audio": audio_stream,
            }
        )
        if not video_stream:
            reasons.append("missing_video_stream")
        else:
            if int(video_stream.get("width") or 0) != 1080 or int(video_stream.get("height") or 0) != 1920:
                reasons.append("invalid_resolution")
        if not audio_stream:
            reasons.append("missing_audio_stream")
        elif int(audio_stream.get("sample_rate") or 0) not in {24000, 44100, 48000, 96000}:
            reasons.append("unexpected_audio_sample_rate")
        if abs(duration_ms - int(expected_duration_ms)) > 1200:
            reasons.append("duration_drift_too_high")
        if not 24_000 <= duration_ms <= 46_500:
            reasons.append("duration_outside_publish_range")
        if size < 250_000:
            reasons.append("render_file_too_small")
        if bitrate and bitrate < self.min_bitrate:
            reasons.append("bitrate_below_minimum")
        decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(video_path), "-f", "null", "-"], capture_output=True, text=True, check=False)
        if decode.returncode != 0:
            reasons.append("ffmpeg_decode_failed")
            metrics["decode_stderr"] = decode.stderr[-1000:]
        return RenderGateResult(passed=not reasons, reasons=reasons, metrics=metrics)
