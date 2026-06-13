from __future__ import annotations

import subprocess
from typing import Any

import imageio_ffmpeg
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import BackgroundMusicAsset, Job, NarrationAsset, RenderOutput, SceneAsset, ScenePlan, SubtitleTrack
from app.pipelines.common import RecoverableStepError, model_payload
from app.pipelines.base import BasePipeline
from app.pipelines.timeline import normalize_scene_timings
from app.utils import ensure_dir, file_uri, new_id, path_from_uri, stable_hash, utcnow


RENDER_MOTION_FPS = 30
RENDER_MOTION_MODES = ("stable_hold",)


class RenderPipeline(BasePipeline):
    def step_render(self, session: Session, job: Job, attempt: int) -> list[str]:
        scene_plan = session.scalar(select(ScenePlan).where(ScenePlan.job_id == job.job_id))
        narration = session.scalar(select(NarrationAsset).where(NarrationAsset.job_id == job.job_id))
        subtitles = session.scalar(select(SubtitleTrack).where(SubtitleTrack.job_id == job.job_id))
        background_music = session.scalar(select(BackgroundMusicAsset).where(BackgroundMusicAsset.job_id == job.job_id))
        selected_assets = session.scalars(
            select(SceneAsset).where(SceneAsset.job_id == job.job_id, SceneAsset.selected.is_(True)).order_by(SceneAsset.scene_id)
        ).all()
        assert scene_plan and narration and subtitles and selected_assets
        if str(getattr(self.settings, "render_primary_backend", "ffmpeg") or "ffmpeg").lower() == "remotion":
            report = self.owner.premium_finishing.generate_primary_render(session, job.job_id)
            render_telemetry_file = self._persist_repair_telemetry(
                job.job_id,
                "render",
                {
                    "job_id": job.job_id,
                    "attempt": attempt,
                    "backend": "remotion",
                    "final_passed": True,
                    "attempts": [{"strategy": "remotion_primary", "passed": True}],
                },
            )
            quality_summary = dict(job.quality_summary or {})
            render_metrics = dict(report.get("metrics") or {})
            quality_summary["render"] = {
                **render_metrics,
                "render_gate_pass": True,
                "duration_ms": render_metrics.get("duration_ms") or narration.duration_ms,
                "resolution": "1080x1920",
                "audio_loudness_target_lufs": -16.0,
                "audio_true_peak_limit_db": -1.5,
                "background_music_mixed": bool(background_music and background_music.mixed_audio_uri),
                "render_repair_used": False,
                "backend": "remotion",
            }
            job.quality_summary = quality_summary
            return [
                "render/final.mp4",
                "render/poster.jpg",
                "render/edit_plan.json",
                "render/remotion.log",
                "render_output.json",
                "premium_finishing_report.json",
                render_telemetry_file,
            ]
        final_video = self.storage.job_dir(job.job_id) / "render" / "final.mp4"
        poster = self.storage.job_dir(job.job_id) / "render" / "poster.jpg"
        ffmpeg_log = self.storage.job_dir(job.job_id) / "render" / "ffmpeg.log"
        ensure_dir(final_video.parent)
        total_duration = narration.duration_ms / 1000
        audio_path = path_from_uri(background_music.mixed_audio_uri) if background_music and background_music.mixed_audio_uri else path_from_uri(narration.audio_uri)
        ass_path = path_from_uri(subtitles.ass_uri or "")
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        command = [ffmpeg, "-y"]
        filter_parts: list[str] = []
        concat_inputs: list[str] = []
        scene_segments = normalize_scene_timings(scene_plan.scenes, narration.duration_ms)
        if scene_plan.scenes != scene_segments:
            scene_plan.scenes = scene_segments
            scene_plan.content_hash = stable_hash(scene_segments)
            self.storage.persist_json(
                job.job_id,
                "scene_plan.json",
                self._serialize_for_json(
                    {
                        "schema_version": scene_plan.schema_version,
                        "scene_plan_id": scene_plan.scene_plan_id,
                        "job_id": scene_plan.job_id,
                        "created_at": scene_plan.created_at,
                        "content_hash": scene_plan.content_hash,
                        "scene_count": scene_plan.scene_count,
                        "scenes": scene_segments,
                    }
                ),
            )
        motion_plan = self.build_render_motion_plan(job.job_id, scene_segments)
        motion_artifact = self.storage.persist_json(job.job_id, "render_motion_plan.json", self._serialize_for_json(motion_plan))
        for index, scene in enumerate(scene_segments):
            asset = next(item for item in selected_assets if item.scene_id == scene["scene_id"])
            start = scene["actual_start_ms"] / 1000
            end = scene["actual_end_ms"] / 1000
            duration = max(0.5, end - start)
            command.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(path_from_uri(asset.uri))])
            filter_parts.append(self._scene_motion_filter(index, duration, motion_plan["scenes"][index]))
            concat_inputs.append(f"[v{index}]")
        command.extend(["-i", str(audio_path)])
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(selected_assets)}:v=1:a=0[video]")
        ass_filter_path = ass_path.as_posix().replace("\\", "/").replace(":", "\\\\:")
        filter_parts.append(f"[video]ass={ass_filter_path}[vout]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[vout]",
                "-map",
                f"{len(selected_assets)}:a",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-b:v",
                "2500k",
                "-minrate",
                "800k",
                "-maxrate",
                "4500k",
                "-bufsize",
                "9000k",
                "-x264-params",
                "nal-hrd=cbr:force-cfr=1",
                "-pix_fmt",
                "yuv420p",
                "-af",
                "aresample=async=1:first_pts=0",
                "-ar",
                "48000",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(final_video),
            ]
        )
        render_gate, render_log = self.render_with_repair(job.job_id, command, final_video, ffmpeg_log, narration.duration_ms)
        ffmpeg_log.write_text(render_log, encoding="utf-8")
        Image.open(path_from_uri(selected_assets[0].uri)).resize((540, 960)).save(poster, format="JPEG")
        duration_ms = int(render_gate.metrics.get("duration_ms") or narration.duration_ms)
        created_at = utcnow()
        payload = {
            "schema_version": self.settings.schema_version,
            "render_id": new_id(),
            "job_id": job.job_id,
            "created_at": created_at,
            "content_hash": stable_hash(final_video.read_bytes()),
            "video_uri": file_uri(final_video),
            "poster_uri": file_uri(poster),
            "waveform_uri": None,
            "duration_ms": duration_ms,
            "resolution": "1080x1920",
            "video_codec": "H.264",
            "audio_codec": "AAC",
            "filesize_bytes": final_video.stat().st_size,
            "ffmpeg_log_uri": file_uri(ffmpeg_log),
            "motion_plan_uri": motion_artifact.uri,
            "motion_summary": motion_plan["summary"],
        }
        session.execute(delete(RenderOutput).where(RenderOutput.job_id == job.job_id))
        session.add(RenderOutput(**model_payload(RenderOutput, payload)))
        self.storage.persist_json(job.job_id, "render_output.json", self._serialize_for_json(payload))
        primary_artifacts: list[str] = []
        if str(getattr(self.settings, "render_primary_backend", "ffmpeg") or "ffmpeg").lower() == "remotion":
            session.flush()
            try:
                self.owner.premium_finishing.generate_parallel_version(session, job.job_id)
                self.owner.premium_finishing.promote_as_primary_render(
                    session,
                    job.job_id,
                    previous_video_uri=file_uri(final_video),
                    source="render_pipeline_primary",
                )
                primary_artifacts = ["render/premium.mp4", "render/edit_plan.json", "premium_finishing_report.json", "render/remotion.log"]
            except Exception as exc:  # noqa: BLE001
                raise RecoverableStepError(f"remotion primary render failed: {exc}") from exc
        render_telemetry_file = self._persist_repair_telemetry(
            job.job_id,
            "render",
            {
                "job_id": job.job_id,
                "attempt": attempt,
                "final_passed": True,
                "attempts": render_gate.metrics.get("render_attempts_log", []),
            },
        )
        quality_summary = dict(job.quality_summary or {})
        quality_summary["render"] = {
            **render_gate.metrics,
            "render_gate_pass": True,
            "duration_ms": duration_ms,
            "resolution": "1080x1920",
            "audio_loudness_target_lufs": -16.0,
            "audio_true_peak_limit_db": -1.5,
            "background_music_mixed": bool(background_music and background_music.mixed_audio_uri),
            "render_repair_used": len(render_gate.metrics.get("render_attempts_log", [])) > 1,
            "motion_summary": motion_plan["summary"],
        }
        job.quality_summary = quality_summary
        return [
            "render/final.mp4",
            "render/poster.jpg",
            "render/ffmpeg.log",
            "render_output.json",
            "render_motion_plan.json",
            render_telemetry_file,
            *primary_artifacts,
        ]

    def build_render_motion_plan(self, job_id: str, scene_segments: list[dict[str, Any]]) -> dict[str, Any]:
        scenes: list[dict[str, Any]] = []
        mode_counts = {mode: 0 for mode in RENDER_MOTION_MODES}
        for index, scene in enumerate(scene_segments):
            mode = RENDER_MOTION_MODES[index % len(RENDER_MOTION_MODES)]
            start_zoom, end_zoom = self._zoom_bounds_for_mode(mode)
            mode_counts[mode] += 1
            scenes.append(
                {
                    "scene_id": str(scene.get("scene_id") or f"scene-{index + 1}"),
                    "order": int(scene.get("order") or index + 1),
                    "mode": mode,
                    "start_zoom": start_zoom,
                    "end_zoom": end_zoom,
                    "fps": RENDER_MOTION_FPS,
                    "duration_ms": max(500, int(scene.get("actual_end_ms", 0) or 0) - int(scene.get("actual_start_ms", 0) or 0)),
                }
            )
        return {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "motion_policy": "stable_scene_framing",
            "summary": {
                "enabled": False,
                "fps": RENDER_MOTION_FPS,
                "scene_count": len(scenes),
                "modes": mode_counts,
                "max_zoom_delta": 0.0,
            },
            "scenes": scenes,
        }

    def _zoom_bounds_for_mode(self, mode: str) -> tuple[float, float]:
        return 1.0, 1.0

    def _scene_motion_filter(self, index: int, duration: float, motion: dict[str, Any]) -> str:
        return (
            f"[{index}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,fps={RENDER_MOTION_FPS},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{index}]"
        )

    def render_with_repair(
        self,
        job_id: str,
        base_command: list[str],
        final_video,
        ffmpeg_log,
        expected_duration_ms: int,
    ) -> tuple[Any, str]:
        attempts: list[list[str]] = [
            list(base_command),
            self.mutate_render_command_for_repair(base_command, repair_mode="quality_safe"),
        ]
        collected_logs: list[str] = []
        last_gate = None
        attempts_log: list[dict[str, Any]] = []
        for index, command in enumerate(attempts, start=1):
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            collected_logs.append(f"=== render attempt {index} ===\n{result.stdout}\n{result.stderr}")
            if result.returncode != 0:
                attempts_log.append(
                    {
                        "repair_attempt": index,
                        "strategy": "base" if index == 1 else "quality_safe",
                        "passed": False,
                        "reason_codes": ["ffmpeg_render_failed"],
                    }
                )
                continue
            render_gate = self.render_gate.validate(final_video, expected_duration_ms)
            last_gate = render_gate
            attempts_log.append(
                {
                    "repair_attempt": index,
                    "strategy": "base" if index == 1 else "quality_safe",
                    "passed": render_gate.passed,
                    "reason_codes": render_gate.reasons,
                }
            )
            if render_gate.passed:
                render_gate.metrics["render_attempts_log"] = attempts_log
                return render_gate, "\n".join(collected_logs)
            if index < len(attempts):
                continue
        if last_gate is not None:
            last_gate.metrics["render_attempts_log"] = attempts_log
            self.storage.persist_json(
                job_id,
                "render_quality_report.json",
                {"reasons": last_gate.reasons, "metrics": last_gate.metrics},
            )
            raise RecoverableStepError(f"render quality gate failed: {', '.join(last_gate.reasons[:6])}")
        raise RecoverableStepError("ffmpeg render failed")

    def mutate_render_command_for_repair(self, command: list[str], repair_mode: str) -> list[str]:
        mutated = list(command)
        if repair_mode != "quality_safe":
            return mutated
        replacements = {
            "-preset": "faster",
            "-crf": "21",
            "-b:v": "3200k",
            "-minrate": "1200k",
            "-maxrate": "5200k",
            "-bufsize": "10400k",
            "-af": "aresample=async=1:first_pts=0,alimiter=limit=0.95",
            "-ar": "48000",
        }
        for flag, value in replacements.items():
            if flag in mutated:
                idx = mutated.index(flag)
                if idx + 1 < len(mutated):
                    mutated[idx + 1] = value
        return mutated
