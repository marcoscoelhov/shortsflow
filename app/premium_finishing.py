from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BackgroundMusicAsset, Job, NarrationAsset, RenderOutput, SceneAsset, ScenePlan, SubtitleTrack
from app.pipelines.common import FatalStepError, model_payload
from app.pipelines.finish_plan import build_finish_plan
from app.pipelines.timeline import normalize_scene_timings
from app.quality.premium_finishing_gate import PremiumFinishingGate
from app.utils import ensure_dir, file_uri, new_id, path_from_uri, read_json, stable_hash, utcnow


PREMIUM_COMPOSITION_ID = "YtsPremiumShort"


class RemotionCliRenderer:
    def __init__(self, project_dir: Path | None = None, timeout_sec: int = 900) -> None:
        self.project_dir = project_dir or Path(__file__).resolve().parent.parent / "remotion"
        self.timeout_sec = timeout_sec

    def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
        remotion_bin = self.project_dir / "node_modules" / ".bin" / "remotion"
        entrypoint = self.project_dir / "src" / "index.ts"
        resolved_plan_path = plan_path.resolve()
        resolved_output_path = output_path.resolve()
        resolved_log_path = log_path.resolve()
        if not remotion_bin.exists():
            raise FatalStepError("dependencias do Remotion nao instaladas; rode npm install em remotion/")
        if not entrypoint.exists():
            raise FatalStepError("entrypoint do Remotion nao encontrado em remotion/src/index.ts")
        command = [
            str(remotion_bin),
            "render",
            str(entrypoint),
            PREMIUM_COMPOSITION_ID,
            str(resolved_output_path),
            "--props",
            str(resolved_plan_path),
            "--codec",
            "h264",
            "--audio-codec",
            "aac",
            "--pixel-format",
            "yuv420p",
            "--crf",
            "20",
            "--x264-preset",
            "veryfast",
            "--overwrite",
            "--concurrency",
            "2",
            "--disable-web-security",
            "--log",
            "info",
        ]
        self._preflight_local_media(resolved_plan_path)
        ensure_dir(resolved_output_path.parent)
        try:
            result = subprocess.run(
                command,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            resolved_log_path.write_text(self._process_text(exc.stdout) + "\n" + self._process_text(exc.stderr), encoding="utf-8")
            raise FatalStepError("render premium excedeu o tempo limite") from exc
        resolved_log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise FatalStepError("render premium falhou no Remotion CLI")
        return command

    def _preflight_local_media(self, plan_path: Path) -> None:
        try:
            plan = read_json(plan_path)
        except Exception as exc:  # noqa: BLE001
            raise FatalStepError("plano de acabamento Remotion invalido ou ilegivel") from exc
        if not isinstance(plan, dict):
            raise FatalStepError("plano de acabamento Remotion invalido")
        missing: list[str] = []
        for scene in plan.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            media_path = self._local_media_path(str(scene.get("asset_uri") or scene.get("asset_path") or ""))
            if media_path and not media_path.exists():
                missing.append(str(media_path))
        audio = plan.get("audio") if isinstance(plan.get("audio"), dict) else {}
        media_path = self._local_media_path(str(audio.get("uri") or audio.get("path") or ""))
        if media_path and not media_path.exists():
            missing.append(str(media_path))
        if missing:
            preview = ", ".join(missing[:4])
            suffix = f" e mais {len(missing) - 4}" if len(missing) > 4 else ""
            raise FatalStepError(f"assets locais do Remotion ausentes: {preview}{suffix}")

    def _local_media_path(self, value: str) -> Path | None:
        if not value:
            return None
        if value.startswith("file://"):
            return path_from_uri(value)
        path = Path(value)
        return path if path.is_absolute() else None

    def _process_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value


class PremiumFinishingService:
    def __init__(self, owner: Any, *, renderer: RemotionCliRenderer | None = None, gate: PremiumFinishingGate | None = None) -> None:
        self.owner = owner
        self.renderer = renderer or RemotionCliRenderer()
        self.gate = gate or PremiumFinishingGate(owner.render_gate)

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def settings(self) -> Any:
        return self.owner.settings

    def context(self, job_id: str) -> dict[str, Any]:
        job_dir = self.storage.job_dir(job_id, create=False)
        video_path = job_dir / "render" / "premium.mp4"
        edit_plan = self._read_json(job_id, "render/edit_plan.json")
        report = self._read_json(job_id, "premium_finishing_report.json")
        log_path = job_dir / "render" / "remotion.log"
        status = str(report.get("status") or ("succeeded" if video_path.exists() else "not_started"))
        return {
            "available": video_path.exists(),
            "video_uri": file_uri(video_path) if video_path.exists() else None,
            "edit_plan_uri": file_uri(job_dir / "render" / "edit_plan.json") if edit_plan else None,
            "log_uri": file_uri(log_path) if log_path.exists() else None,
            "edit_plan": edit_plan,
            "report": report,
            "status": status,
            "running": status == "running",
            "gate_pass": bool(report.get("passed")),
            "error": report.get("error"),
        }

    def generate_parallel_version(self, session: Session, job_id: str) -> dict[str, Any]:
        job = session.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        scene_plan = session.scalar(select(ScenePlan).where(ScenePlan.job_id == job_id))
        narration = session.scalar(select(NarrationAsset).where(NarrationAsset.job_id == job_id))
        subtitles = session.scalar(select(SubtitleTrack).where(SubtitleTrack.job_id == job_id))
        render = session.scalar(select(RenderOutput).where(RenderOutput.job_id == job_id))
        background_music = session.scalar(select(BackgroundMusicAsset).where(BackgroundMusicAsset.job_id == job_id))
        selected_assets = session.scalars(
            select(SceneAsset).where(SceneAsset.job_id == job_id, SceneAsset.selected.is_(True)).order_by(SceneAsset.scene_id)
        ).all()
        if not scene_plan or not narration or not subtitles or not selected_assets:
            raise FatalStepError("job ainda nao tem cenas, narracao, legendas e assets selecionados para prova premium")
        visual_contract = self._read_json(job_id, "visual_contract.json")
        plan = build_finish_plan(
            schema_version=self.settings.schema_version,
            job=job,
            scene_plan=scene_plan,
            selected_assets=list(selected_assets),
            narration=narration,
            subtitles=subtitles,
            background_music=background_music,
            render=render,
            visual_contract=visual_contract,
            media_base_url=f"{str(self.settings.app_url).rstrip('/')}/artifacts",
            artifacts_dir=self.settings.artifacts_dir,
        )
        job_dir = self.storage.job_dir(job_id)
        plan_artifact = self.storage.persist_json(job_id, "render/edit_plan.json", plan)
        output_path = job_dir / "render" / "premium.mp4"
        log_path = job_dir / "render" / "remotion.log"
        self.mark_running(job_id, phase="rendering", detail="Render premium em andamento")
        self.owner._append_event(job_id, "premium_finishing.started", "succeeded", {"finish_plan_hash": plan_artifact.content_hash})
        try:
            command = self.renderer.render(plan_path=job_dir / "render" / "edit_plan.json", output_path=output_path, log_path=log_path)
            gate_result = self.gate.validate(output_path, narration.duration_ms, plan)
        except FatalStepError as exc:
            report = self._failure_report(job_id, plan, str(exc))
            self.storage.persist_json(job_id, "premium_finishing_report.json", report)
            self.owner._append_event(job_id, "premium_finishing.failed", "failed", {"message": str(exc)})
            raise
        report = {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "created_at": utcnow().isoformat(),
            "status": "succeeded" if gate_result.passed else "failed",
            "passed": gate_result.passed,
            "reasons": gate_result.reasons,
            "metrics": gate_result.metrics,
            "video_uri": file_uri(output_path),
            "edit_plan_uri": plan_artifact.uri,
            "log_uri": file_uri(log_path),
            "command": command,
            "content_hash": stable_hash(output_path.read_bytes()) if output_path.exists() else None,
        }
        self.storage.persist_json(job_id, "premium_finishing_report.json", report)
        if not gate_result.passed:
            self.owner._append_event(job_id, "premium_finishing.failed", "failed", {"reasons": gate_result.reasons})
            raise FatalStepError(f"gate de acabamento premium falhou: {', '.join(gate_result.reasons[:6])}")
        artifact_index = dict(job.artifact_index or {})
        artifact_index.update(
            {
                "premium_video": "render/premium.mp4",
                "premium_edit_plan": "render/edit_plan.json",
                "premium_finishing_report": "premium_finishing_report.json",
                "premium_remotion_log": "render/remotion.log",
            }
        )
        job.artifact_index = artifact_index
        quality_summary = dict(job.quality_summary or {})
        quality_summary["premium_finishing"] = {
            "premium_finishing_gate_pass": True,
            "duration_ms": gate_result.metrics.get("duration_ms"),
            "scene_count": len(plan["scenes"]),
            "caption_count": len(plan["caption_track"]["items"]),
            "component_policy": plan["style"]["component_policy"],
        }
        job.quality_summary = quality_summary
        self.owner._append_event(job_id, "premium_finishing.completed", "succeeded", quality_summary["premium_finishing"])
        return report

    def generate_primary_render(self, session: Session, job_id: str) -> dict[str, Any]:
        job = session.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        scene_plan = session.scalar(select(ScenePlan).where(ScenePlan.job_id == job_id))
        narration = session.scalar(select(NarrationAsset).where(NarrationAsset.job_id == job_id))
        subtitles = session.scalar(select(SubtitleTrack).where(SubtitleTrack.job_id == job_id))
        background_music = session.scalar(select(BackgroundMusicAsset).where(BackgroundMusicAsset.job_id == job_id))
        selected_assets = session.scalars(
            select(SceneAsset).where(SceneAsset.job_id == job_id, SceneAsset.selected.is_(True)).order_by(SceneAsset.scene_id)
        ).all()
        if not scene_plan or not narration or not subtitles or not selected_assets:
            raise FatalStepError("job ainda nao tem cenas, narracao, legendas e assets selecionados para render Remotion")
        scene_segments = normalize_scene_timings(scene_plan.scenes, narration.duration_ms)
        if scene_plan.scenes != scene_segments:
            scene_plan.scenes = scene_segments
            scene_plan.content_hash = stable_hash(scene_segments)
            self.storage.persist_json(
                job_id,
                "scene_plan.json",
                {
                    "schema_version": scene_plan.schema_version,
                    "scene_plan_id": scene_plan.scene_plan_id,
                    "job_id": scene_plan.job_id,
                    "created_at": scene_plan.created_at.isoformat() if scene_plan.created_at else None,
                    "content_hash": scene_plan.content_hash,
                    "scene_count": scene_plan.scene_count,
                    "scenes": scene_segments,
                },
            )
        visual_contract = self._read_json(job_id, "visual_contract.json")
        plan = build_finish_plan(
            schema_version=self.settings.schema_version,
            job=job,
            scene_plan=scene_plan,
            selected_assets=list(selected_assets),
            narration=narration,
            subtitles=subtitles,
            background_music=background_music,
            render=None,
            visual_contract=visual_contract,
            media_base_url=f"{str(self.settings.app_url).rstrip('/')}/artifacts",
            artifacts_dir=self.settings.artifacts_dir,
        )
        job_dir = self.storage.job_dir(job_id)
        render_dir = job_dir / "render"
        ensure_dir(render_dir)
        plan_artifact = self.storage.persist_json(job_id, "render/edit_plan.json", plan)
        output_path = render_dir / "final.mp4"
        log_path = render_dir / "remotion.log"
        poster_path = render_dir / "poster.jpg"
        self.mark_running(job_id, phase="rendering", detail="Render principal Remotion em andamento")
        self.owner._append_event(job_id, "render.remotion_primary.started", "succeeded", {"finish_plan_hash": plan_artifact.content_hash})
        try:
            command = self.renderer.render(plan_path=render_dir / "edit_plan.json", output_path=output_path, log_path=log_path)
            gate_result = self.gate.validate(output_path, narration.duration_ms, plan)
        except FatalStepError as exc:
            report = self._failure_report(job_id, plan, str(exc))
            report["source"] = "remotion_primary"
            self.storage.persist_json(job_id, "premium_finishing_report.json", report)
            self.owner._append_event(job_id, "render.remotion_primary.failed", "failed", {"message": str(exc)})
            raise
        if not gate_result.passed:
            report = {
                "schema_version": self.settings.schema_version,
                "job_id": job_id,
                "created_at": utcnow().isoformat(),
                "status": "failed",
                "source": "remotion_primary",
                "passed": False,
                "reasons": gate_result.reasons,
                "metrics": gate_result.metrics,
                "video_uri": file_uri(output_path) if output_path.exists() else None,
                "edit_plan_uri": plan_artifact.uri,
                "log_uri": file_uri(log_path),
                "command": command,
            }
            self.storage.persist_json(job_id, "premium_finishing_report.json", report)
            self.owner._append_event(job_id, "render.remotion_primary.failed", "failed", {"reasons": gate_result.reasons})
            raise FatalStepError(f"gate de render Remotion falhou: {', '.join(gate_result.reasons[:6])}")
        Image.open(path_from_uri(selected_assets[0].uri)).resize((540, 960)).save(poster_path, format="JPEG")
        duration_ms = int(gate_result.metrics.get("duration_ms") or narration.duration_ms)
        created_at = utcnow()
        render_payload = {
            "schema_version": self.settings.schema_version,
            "render_id": new_id(),
            "job_id": job_id,
            "created_at": created_at,
            "content_hash": stable_hash(output_path.read_bytes()),
            "video_uri": file_uri(output_path),
            "poster_uri": file_uri(poster_path),
            "waveform_uri": None,
            "duration_ms": duration_ms,
            "resolution": "1080x1920",
            "video_codec": "H.264",
            "audio_codec": "AAC",
            "filesize_bytes": output_path.stat().st_size,
            "ffmpeg_log_uri": file_uri(log_path),
            "motion_plan_uri": plan_artifact.uri,
            "motion_summary": {"backend": "remotion", "scene_count": len(plan["scenes"])},
            "selected_render": "remotion",
        }
        session.execute(delete(RenderOutput).where(RenderOutput.job_id == job_id))
        session.add(RenderOutput(**model_payload(RenderOutput, render_payload)))
        self.storage.persist_json(job_id, "render_output.json", self.owner._serialize_for_json(render_payload))
        report = {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "created_at": utcnow().isoformat(),
            "status": "succeeded",
            "source": "remotion_primary",
            "passed": True,
            "reasons": [],
            "metrics": gate_result.metrics,
            "video_uri": file_uri(output_path),
            "edit_plan_uri": plan_artifact.uri,
            "log_uri": file_uri(log_path),
            "command": command,
            "content_hash": stable_hash(output_path.read_bytes()),
        }
        self.storage.persist_json(job_id, "premium_finishing_report.json", report)
        artifact_index = dict(job.artifact_index or {})
        artifact_index.update(
            {
                "render": "render/final.mp4",
                "poster": "render/poster.jpg",
                "remotion_edit_plan": "render/edit_plan.json",
                "remotion_log": "render/remotion.log",
                "premium_finishing_report": "premium_finishing_report.json",
            }
        )
        job.artifact_index = artifact_index
        quality_summary = dict(job.quality_summary or {})
        quality_summary["premium_finishing"] = {
            "premium_finishing_gate_pass": True,
            "duration_ms": duration_ms,
            "scene_count": len(plan["scenes"]),
            "caption_count": len(plan["caption_track"]["items"]),
            "component_policy": plan["style"]["component_policy"],
            "source": "remotion_primary",
        }
        quality_summary["selected_render"] = {
            "variant": "remotion",
            "video_uri": file_uri(output_path),
            "source": "render_pipeline_primary",
        }
        job.quality_summary = quality_summary
        self.owner._append_event(job_id, "render.remotion_primary.completed", "succeeded", quality_summary["selected_render"])
        return report

    def promote_as_primary_render(
        self,
        session: Session,
        job_id: str,
        *,
        previous_video_uri: str | None = None,
        source: str = "remotion_primary",
    ) -> None:
        job = session.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        render = session.scalar(select(RenderOutput).where(RenderOutput.job_id == job_id))
        if not render:
            raise FatalStepError("job nao tem render final para promover Remotion como primario")
        premium_report = self._read_json(job_id, "premium_finishing_report.json")
        premium_video_uri = str(premium_report.get("video_uri") or "").strip()
        premium_path = path_from_uri(premium_video_uri) if premium_video_uri else self.storage.job_dir(job_id, create=False) / "render" / "premium.mp4"
        if not premium_path.exists():
            raise FatalStepError("versao Remotion ainda nao foi gerada")
        if not premium_report or not bool(premium_report.get("passed")):
            raise FatalStepError("versao Remotion nao passou no gate de acabamento")
        original_video_uri = previous_video_uri or str(render.video_uri or "")
        render.video_uri = file_uri(premium_path)
        render.filesize_bytes = premium_path.stat().st_size
        render.content_hash = stable_hash({
            "primary_video_uri": render.video_uri,
            "previous_video_uri": original_video_uri,
            "source": source,
        })
        artifact_index = dict(job.artifact_index or {})
        job_dir = self.storage.job_dir(job_id, create=False)
        try:
            original_render_ref = str(path_from_uri(original_video_uri).resolve().relative_to(job_dir.resolve()))
        except (OSError, ValueError):
            original_render_ref = str(artifact_index.get("render") or original_video_uri)
        if original_render_ref and original_render_ref != "render/premium.mp4":
            artifact_index["standard_render"] = str(artifact_index.get("standard_render") or original_render_ref)
        artifact_index["render"] = "render/premium.mp4"
        artifact_index["premium_video"] = "render/premium.mp4"
        job.artifact_index = artifact_index
        render_payload = self._read_json(job_id, "render_output.json")
        if render_payload:
            render_payload.update(
                {
                    "content_hash": render.content_hash,
                    "video_uri": render.video_uri,
                    "filesize_bytes": render.filesize_bytes,
                    "selected_render": "remotion",
                    "standard_video_uri": original_video_uri,
                }
            )
            self.storage.persist_json(job_id, "render_output.json", render_payload)
        quality_summary = dict(job.quality_summary or {})
        quality_summary["selected_render"] = {
            "variant": "remotion",
            "previous_video_uri": original_video_uri,
            "video_uri": render.video_uri,
            "source": source,
        }
        job.quality_summary = quality_summary
        self.owner._append_event(job_id, "render.primary_promoted", "succeeded", quality_summary["selected_render"])

    def narration_uses_primary_tts(self, narration: NarrationAsset | None) -> bool:
        if narration is None:
            return False
        return str(narration.provider or "").lower() in self.primary_tts_provider_names()

    def primary_tts_provider_names(self) -> set[str]:
        if self.settings.use_mock_providers:
            return {"espeak_ng", "synthetic_wav"}
        configured = str(self.settings.tts_primary_provider or "elevenlabs").strip().lower()
        return {configured or "elevenlabs"}

    def primary_tts_refresh_needed(self, session: Session, job_id: str) -> bool:
        job = session.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        narration = session.scalar(select(NarrationAsset).where(NarrationAsset.job_id == job_id))
        return narration is not None and not self.narration_uses_primary_tts(narration)

    def require_primary_tts(self, session: Session, job_id: str) -> None:
        narration = session.scalar(select(NarrationAsset).where(NarrationAsset.job_id == job_id))
        if self.narration_uses_primary_tts(narration):
            return
        current_provider = str(narration.provider) if narration else "ausente"
        expected = ", ".join(sorted(self.primary_tts_provider_names()))
        raise FatalStepError(f"versao premium exige TTS primario ({expected}); provider atual: {current_provider}")

    def mark_running(self, job_id: str, *, phase: str = "queued", detail: str = "Acabamento premium iniciado") -> dict[str, Any]:
        report = {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "created_at": utcnow().isoformat(),
            "status": "running",
            "phase": phase,
            "detail": detail,
            "passed": False,
            "reasons": ["premium_finishing_running"],
        }
        self.storage.persist_json(job_id, "premium_finishing_report.json", report)
        return report

    def mark_failed(self, job_id: str, error: str) -> dict[str, Any]:
        report = {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "created_at": utcnow().isoformat(),
            "status": "failed",
            "passed": False,
            "error": error,
            "reasons": ["premium_render_failed"],
        }
        self.storage.persist_json(job_id, "premium_finishing_report.json", report)
        return report

    def _failure_report(self, job_id: str, plan: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "schema_version": self.settings.schema_version,
            "job_id": job_id,
            "created_at": utcnow().isoformat(),
            "status": "failed",
            "passed": False,
            "error": error,
            "reasons": ["premium_render_failed"],
            "edit_plan_hash": stable_hash(plan),
        }

    def _read_json(self, job_id: str, relative_path: str) -> dict[str, Any]:
        path = self.storage.job_dir(job_id, create=False) / relative_path
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}
