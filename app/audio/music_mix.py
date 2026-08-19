from __future__ import annotations

import math
import subprocess
import wave
from array import array
from pathlib import Path
from typing import Any

import imageio_ffmpeg


def _wave_rms_db(path: Path) -> float | None:
    """RMS (dBFS) of a 16-bit mono wave, or None if it can't be read."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, OSError):
        return None
    if sample_width != 2 or not frames:
        return None
    samples = array("h")
    samples.frombytes(frames)
    if not samples:
        return None
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    if rms <= 0:
        return None
    return 20 * math.log10(rms / 32767.0)


def calibrate_bed_gain(
    narration_rms_db: float | None,
    music_rms_db: float | None,
    target_ratio: float,
    *,
    min_db: float,
    max_db: float,
    fallback_db: float,
) -> float:
    """Ganho (dB) a aplicar na música para que bed_rms / narration_rms == target_ratio.

    Queremos bed_target_db - narration_db = 20*log10(target_ratio), e o ganho soma
    a difference até o nivel medido da musica. Sem mediacao confiavel, usa fallback.
    """
    if narration_rms_db is None or music_rms_db is None or target_ratio <= 0:
        return fallback_db
    target_relative_db = 20 * math.log10(target_ratio)
    needed_db = (narration_rms_db + target_relative_db) - music_rms_db
    return max(min_db, min(max_db, round(needed_db, 2)))


def mix_background_music(
    narration_path: Path,
    music_path: Path,
    output_path: Path,
    target_duration_ms: int,
    gain_db: float,
    strategy: str = "sidechaincompress+amix+loudnorm",
    *,
    target_ratio: float | None = None,
    gain_min_db: float = -6.0,
    gain_max_db: float = 6.0,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_sec = max(target_duration_ms / 1000, 1.0)
    fade_out_start = max(duration_sec - 1.2, 0.0)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temp_output = output_path.with_suffix(".tmp.wav")
    if target_ratio is not None:
        narration_db = _wave_rms_db(narration_path)
        music_db = _wave_rms_db(music_path)
        gain_db = calibrate_bed_gain(narration_db, music_db, target_ratio, min_db=gain_min_db, max_db=gain_max_db, fallback_db=gain_db)
    if strategy == "sidechaincompress+amix+loudnorm":
        filter_graph = (
            f"[0:a]aresample=24000,volume={gain_db}dB,atrim=0:{duration_sec:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d=1.2[bg];"
            "[bg][1:a]sidechaincompress=threshold=0.025:ratio=10:attack=15:release=300[duck];"
            "[1:a][duck]amix=inputs=2:weights='1 0.8':normalize=0,"
            "loudnorm=I=-16:LRA=11:TP=-1.5[out]"
        )
    else:
        filter_graph = (
            f"[0:a]aresample=24000,volume={gain_db}dB,atrim=0:{duration_sec:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d=1.2[bg];"
            "[1:a]aresample=24000[voc];"
            "[voc][bg]amix=inputs=2:weights='1 0.55':normalize=0,"
            "alimiter=limit=0.93,loudnorm=I=-16:LRA=11:TP=-1.5[out]"
        )
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(music_path),
                "-i",
                str(narration_path),
                "-filter_complex",
                filter_graph,
                "-map",
                "[out]",
                "-t",
                f"{duration_sec:.3f}",
                "-ar",
                "24000",
                "-ac",
                "1",
                str(temp_output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"background music mix failed ({strategy})")
        temp_output.replace(output_path)
    finally:
        temp_output.unlink(missing_ok=True)
    return {
        "mix_filter": strategy,
        "mix_target_lufs": -16.0,
        "mix_true_peak_limit_db": -1.5,
        "gain_db_used": gain_db,
    }
