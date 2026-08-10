from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BackgroundMusicAsset, Job, NarrationAsset, RenderOutput, SceneAsset, ScenePlan, SubtitleTrack
from app.pipelines.common import FatalStepError, model_payload
from app.pipelines.finish_plan import build_finish_plan, public_finish_plan
from app.pipelines.timeline import normalize_scene_timings
from app.quality.premium_finishing_gate import PremiumFinishingGate
from app.quality.render_gate import RenderGateResult
from app.remotion_renderer import RemotionCliRenderer
from app.utils import ensure_dir, file_sha256, file_uri, new_id, path_from_uri, read_json, stable_hash, utcnow


class _MockRemotionRenderer:
    def preflight_environment(self) -> dict[str, Any]:
        return {"ready": True, "project_dir": "mock", "missing_items": []}

    def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
        output_path.write_bytes(b"mock-remotion-video")
        log_path.write_text("mock remotion render", encoding="utf-8")
        return ["remotion-mock", "render", str(output_path)]


class _MockPremiumFinishingGate:
    def validate(self, video_path: Path, expected_duration_ms: int, edit_plan: dict[str, Any]) -> RenderGateResult:
        return RenderGateResult(True, [], {"duration_ms": expected_duration_ms})


class PremiumFinishingService:
    def __init__(self, owner: Any, *, renderer: RemotionCliRenderer | None = None, gate: PremiumFinishingGate | None = None) -> None:
        self.owner = owner
        use_mocks = bool(owner.settings.use_mock_providers)
        self.renderer = renderer or (_MockRemotionRenderer() if use_mocks else RemotionCliRenderer(allowed_media_root=owner.settings.artifacts_dir))
        self.gate = gate or (_MockPremiumFinishingGate() if use_mocks else PremiumFinishingGate(owner.render_gate))

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def settings(self) -> Any:
        return self.owner.settings

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
        plan_artifact = self.storage.persist_json(job_id, "render/edit_plan.json", public_finish_plan(plan))
        output_path = render_dir / "final.mp4"
        candidate_path = render_dir / ".final.pending.mp4"
        log_path = render_dir / "remotion.log"
        poster_path = render_dir / "poster.jpg"
        candidate_path.unlink(missing_ok=True)
        self.owner._append_event(job_id, "render.remotion_primary.started", "succeeded", {"finish_plan_hash": plan_artifact.content_hash})
        try:
            command = self._render_with_runtime_plan(job_id, plan, output_path=candidate_path, log_path=log_path)
            command = [str(output_path) if item == str(candidate_path) else item for item in command]
            public_command = self._public_command(command, job_dir)
            gate_result = self.gate.validate(candidate_path, narration.duration_ms, plan)
        except FatalStepError as exc:
            candidate_path.unlink(missing_ok=True)
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
                "video_uri": None,
                "edit_plan_uri": plan_artifact.uri,
                "log_uri": file_uri(log_path),
                "command": public_command,
            }
            self.storage.persist_json(job_id, "premium_finishing_report.json", report)
            self.owner._append_event(job_id, "render.remotion_primary.failed", "failed", {"reasons": gate_result.reasons})
            candidate_path.unlink(missing_ok=True)
            raise FatalStepError(f"gate de render Remotion falhou: {', '.join(gate_result.reasons[:6])}")
        candidate_path.replace(output_path)
        with Image.open(path_from_uri(selected_assets[0].uri)) as poster_source:
            poster_source.resize((540, 960)).save(poster_path, format="JPEG")
        duration_ms = int(gate_result.metrics.get("duration_ms") or narration.duration_ms)
        created_at = utcnow()
        render_payload = {
            "schema_version": self.settings.schema_version,
            "render_id": new_id(),
            "job_id": job_id,
            "created_at": created_at,
            "content_hash": file_sha256(output_path),
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
            "command": public_command,
            "content_hash": file_sha256(output_path),
            "background_music_mixed": bool(background_music and background_music.mixed_audio_uri),
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

    def _render_with_runtime_plan(self, job_id: str, plan: dict[str, Any], *, output_path: Path, log_path: Path) -> list[str]:
        runtime_plan_path: Path | None = None
        runtime_public_dir = self._runtime_public_dir(job_id)
        try:
            runtime_plan = self._stage_runtime_media(job_id, plan)
            with tempfile.NamedTemporaryFile("w", suffix=".json", prefix=f"{job_id}-remotion-", delete=False, encoding="utf-8") as handle:
                runtime_plan_path = Path(handle.name)
                json.dump(self.owner._serialize_for_json(runtime_plan), handle, ensure_ascii=False)
            return self.renderer.render(plan_path=runtime_plan_path, output_path=output_path, log_path=log_path)
        finally:
            if runtime_plan_path is not None:
                runtime_plan_path.unlink(missing_ok=True)
            if runtime_public_dir is not None:
                shutil.rmtree(runtime_public_dir, ignore_errors=True)

    def _stage_runtime_media(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        public_dir = self._runtime_public_dir(job_id)
        if public_dir is None:
            return plan
        shutil.rmtree(public_dir, ignore_errors=True)
        ensure_dir(public_dir)
        staged = json.loads(json.dumps(self.owner._serialize_for_json(plan), ensure_ascii=False))
        used_scene_ids: set[str] = set()
        for index, scene in enumerate(staged.get("scenes") or []):
            if not isinstance(scene, dict):
                continue
            base_stem = self._safe_runtime_component(scene.get("scene_id"), fallback=f"scene-{index + 1}")
            stem = base_stem
            collision_index = 2
            while stem in used_scene_ids:
                stem = f"{base_stem}-{collision_index}"
                collision_index += 1
            used_scene_ids.add(stem)
            scene["scene_id"] = stem
            source = self._local_media_path(scene.get("asset_uri") or scene.get("asset_path"))
            if source is None or not source.exists():
                continue
            candidate = f"{stem}{source.suffix or '.jpg'}"
            target = (public_dir / candidate).resolve()
            if not target.is_relative_to(public_dir.resolve()):
                raise FatalStepError("destino de asset Remotion fora do staging permitido")
            shutil.copy2(source, target)
            scene["asset_src"] = f"shortsflow-runtime/{public_dir.name}/{target.name}"
        audio = staged.get("audio") if isinstance(staged.get("audio"), dict) else {}
        source = self._local_media_path(audio.get("uri") or audio.get("path"))
        if source is not None and source.exists():
            target = public_dir / f"audio{source.suffix or '.wav'}"
            shutil.copy2(source, target)
            audio["src"] = f"shortsflow-runtime/{public_dir.name}/{target.name}"
        return staged

    def _runtime_public_dir(self, job_id: str) -> Path | None:
        project_dir = getattr(self.renderer, "project_dir", None)
        if not project_dir:
            return None
        runtime_root = (Path(project_dir) / "public" / "shortsflow-runtime").resolve()
        safe_job_id = self._safe_runtime_component(job_id, fallback="job")
        public_dir = (runtime_root / safe_job_id).resolve()
        if not public_dir.is_relative_to(runtime_root):
            raise FatalStepError("diretorio de staging Remotion invalido")
        return public_dir

    @staticmethod
    def _safe_runtime_component(value: Any, *, fallback: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-_.")
        return normalized[:96] or fallback

    def _local_media_path(self, value: Any) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if text.startswith("file://"):
                return path_from_uri(text)
        except Exception:  # noqa: BLE001
            return None
        if text.startswith("http://") or text.startswith("https://"):
            parsed = urlparse(text)
            marker = "/artifacts/"
            if marker in parsed.path:
                relative = unquote(parsed.path.split(marker, 1)[1])
                local_path = (self.settings.artifacts_dir / relative).resolve()
                if local_path.exists():
                    return local_path
        path = Path(text)
        return path if path.is_absolute() else None

    def _public_command(self, command: list[str], job_dir: Path) -> list[str]:
        public: list[str] = []
        job_root = job_dir.resolve()
        for item in command:
            value = str(item)
            path = Path(value)
            if path.is_absolute():
                try:
                    public.append(path.resolve().relative_to(job_root).as_posix())
                except (OSError, ValueError):
                    public.append(f"<{path.name}>")
            else:
                public.append(value)
        return public

    def _read_json(self, job_id: str, relative_path: str) -> dict[str, Any]:
        path = self.storage.job_dir(job_id, create=False) / relative_path
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}
