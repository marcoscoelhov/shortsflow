from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import imageio_ffmpeg


@dataclass(frozen=True)
class BackgroundMusicGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class BackgroundMusicGate:
    def validate(
        self,
        narration_path: Path,
        music_path: Path,
        mixed_audio_path: Path,
        expected_duration_ms: int,
        gain_db: float,
    ) -> BackgroundMusicGateResult:
        reasons: list[str] = []
        metrics: dict[str, Any] = {
            "gain_db": gain_db,
            "expected_duration_ms": int(expected_duration_ms),
            "narration_path": str(narration_path),
            "music_path": str(music_path),
            "mixed_audio_path": str(mixed_audio_path),
        }
        # Faixa segura: o mix calibra o ganho dinamicamente até +6dB para atingir o
        # alvo de ratio audível (ver music_bed_gain_max_db). Aceite essa faixa em vez
        # de um teto rígido de -8 que contradizia a calibração e enterrava a música.
        if gain_db > 6.0 or gain_db < -30.0:
            reasons.append("gain_db_outside_safe_range")

        narration = self._read_wave_stats(narration_path)
        source = self._read_wave_stats(music_path)
        mixed = self._read_wave_stats(mixed_audio_path)
        metrics.update(
            {
                "narration": narration["metrics"],
                "music_source": source["metrics"],
                "mixed": mixed["metrics"],
            }
        )
        if narration["error"]:
            reasons.append(f"narration_{narration['error']}")
        if source["error"]:
            reasons.append(f"music_source_{source['error']}")
        if mixed["error"]:
            reasons.append(f"mixed_{mixed['error']}")
        if reasons:
            return BackgroundMusicGateResult(False, reasons, metrics)

        mixed_metrics = mixed["metrics"]
        source_metrics = source["metrics"]
        if abs(int(mixed_metrics["duration_ms"]) - int(expected_duration_ms)) > 1200:
            reasons.append("mixed_duration_drift_too_high")
        if int(mixed_metrics["sample_rate_hz"]) != 24_000:
            reasons.append("mixed_sample_rate_unexpected")
        if int(mixed_metrics["channels"]) != 1:
            reasons.append("mixed_channels_unexpected")
        if float(mixed_metrics["peak_dbfs"]) > -0.2:
            reasons.append("mixed_peak_too_hot")
        source_rms_dbfs = float(source_metrics["rms_dbfs"])
        if source_rms_dbfs < -55.0:
            reasons.append("music_source_too_quiet")

        bed_ratio = self._bed_relative_rms_ratio(
            narration_rms_dbfs=float(narration["metrics"]["rms_dbfs"]),
            music_source_rms_dbfs=source_rms_dbfs,
            gain_db=gain_db,
        )
        metrics["bed_relative_rms_ratio"] = round(bed_ratio, 4)
        metrics["bed_relative_rms_measurement"] = "music_source_rms_plus_gain_vs_narration_rms"
        raw_residual = self._optimal_gain_residual_ratio(mixed["samples"], narration["samples"])
        loudnorm_reference = self._loudnorm_reference_stats(narration_path)
        if loudnorm_reference["error"]:
            reasons.append("music_mix_reference_generation_failed")
            metrics["observed_mix_contribution_error"] = loudnorm_reference["error"]
            return BackgroundMusicGateResult(False, reasons, metrics)
        loudnorm_residual = self._optimal_gain_residual_ratio(
            mixed["samples"],
            loudnorm_reference["samples"],
        )
        observed_contribution = min(raw_residual, loudnorm_residual)
        observed_reference = "raw_narration" if raw_residual <= loudnorm_residual else "loudnorm_narration"
        metrics["observed_mix_contribution_ratio"] = round(observed_contribution, 6)
        metrics["observed_mix_contribution_reference"] = observed_reference
        metrics["observed_mix_contribution_reference_ratios"] = {
            "raw_narration": round(raw_residual, 6),
            "loudnorm_narration": round(loudnorm_residual, 6),
        }
        metrics["observed_mix_contribution_method"] = "minimum_optimal_gain_residual_vs_raw_and_loudnorm_narration"
        metrics["observed_mix_contribution_min_ratio"] = 0.01
        if observed_contribution < 0.01:
            reasons.append("music_bed_missing_from_mix")
        # Faixas largas de sanidade: o ajuste fino do nível do bed é feito pela
        # calibração dinâmica (music_bed_relative_rms_target). O gate aqui só barra
        # casos absurdos — bed praticamente ausente ou claramente mais alto que a voz —
        # sem rejeitar vídeos legítimos (narração com pausas, sound design, etc.).
        if bed_ratio < 0.02:
            reasons.append("music_bed_inaudible")
        elif bed_ratio > 1.2:
            reasons.append("music_bed_overwhelms_narration")
        return BackgroundMusicGateResult(not reasons, reasons, metrics)

    def _loudnorm_reference_stats(self, narration_path: Path) -> dict[str, Any]:
        reference_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as reference_file:
                reference_path = Path(reference_file.name)
            result = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-i",
                    str(narration_path),
                    "-filter:a",
                    "loudnorm=I=-16:LRA=11:TP=-1.5",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(reference_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return {"error": f"ffmpeg_exit_{result.returncode}", "samples": array("h")}
            stats = self._read_wave_stats(reference_path)
            if stats["error"]:
                return {"error": str(stats["error"]), "samples": array("h")}
            return {"error": None, "samples": stats["samples"]}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}", "samples": array("h")}
        finally:
            if reference_path is not None:
                reference_path.unlink(missing_ok=True)

    def _optimal_gain_residual_ratio(self, mixed: array, reference: array) -> float:
        sample_count = min(len(mixed), len(reference))
        if sample_count <= 0:
            return 0.0
        mixed_values = mixed[:sample_count]
        reference_values = reference[:sample_count]
        reference_energy = sum(float(sample) * float(sample) for sample in reference_values)
        mixed_energy = sum(float(sample) * float(sample) for sample in mixed_values)
        if reference_energy <= 0.0 or mixed_energy <= 0.0:
            return 0.0
        optimal_gain = sum(
            float(mixed_sample) * float(reference_sample)
            for mixed_sample, reference_sample in zip(mixed_values, reference_values, strict=True)
        ) / reference_energy
        residual_energy = sum(
            (float(mixed_sample) - optimal_gain * float(reference_sample)) ** 2
            for mixed_sample, reference_sample in zip(mixed_values, reference_values, strict=True)
        )
        return math.sqrt(residual_energy / mixed_energy)

    def _read_wave_stats(self, path: Path) -> dict[str, Any]:
        metrics: dict[str, Any] = {"path": str(path)}
        if not path.exists():
            return {"error": "missing_file", "metrics": metrics, "samples": array("h")}
        try:
            with wave.open(str(path), "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                raw_frames = wav_file.readframes(frame_count)
        except wave.Error:
            return {"error": "invalid_wave_file", "metrics": metrics, "samples": array("h")}
        if sample_width != 2:
            metrics.update(
                {
                    "sample_width_bytes": sample_width,
                    "sample_rate_hz": sample_rate,
                    "channels": channels,
                }
            )
            return {"error": "unsupported_sample_width", "metrics": metrics, "samples": array("h")}

        samples = array("h")
        samples.frombytes(raw_frames)
        duration_ms = round(frame_count / sample_rate * 1000) if sample_rate else 0
        peak = max((abs(sample) for sample in samples), default=0)
        rms = math.sqrt(sum(sample * sample for sample in samples) / max(len(samples), 1)) if samples else 0.0
        metrics.update(
            {
                "duration_ms": duration_ms,
                "sample_rate_hz": sample_rate,
                "channels": channels,
                "sample_width_bytes": sample_width,
                "frame_count": frame_count,
                "peak_dbfs": self._dbfs(peak),
                "rms_dbfs": self._dbfs(rms),
            }
        )
        return {"error": None, "metrics": metrics, "samples": samples}

    def _bed_relative_rms_ratio(
        self,
        *,
        narration_rms_dbfs: float,
        music_source_rms_dbfs: float,
        gain_db: float,
    ) -> float:
        if narration_rms_dbfs <= -120.0 or music_source_rms_dbfs <= -120.0:
            return 0.0
        relative_db = music_source_rms_dbfs + float(gain_db) - narration_rms_dbfs
        return 10 ** (relative_db / 20)

    def _dbfs(self, amplitude: float) -> float:
        if amplitude <= 0:
            return -120.0
        return round(20 * math.log10(amplitude / 32767.0), 2)
