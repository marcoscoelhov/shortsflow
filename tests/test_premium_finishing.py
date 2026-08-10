from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.e2e_support import (
    BackgroundMusicAsset,
    Job,
    NarrationAsset,
    PublicationSchedule,
    RenderOutput,
    SceneAsset,
    SessionLocal,
    SubtitleTrack,
    TestClient,
    _create_basic_job,
    _write_job_artifact,
    app,
    orchestrator,
)

from app.models import ScenePlan
from app.pipelines.common import FatalStepError
from app.pipelines.finish_plan import build_finish_plan, public_finish_plan
from app.premium_finishing import RemotionCliRenderer
from app.quality.premium_finishing_gate import PremiumFinishingGate
from app.quality.premium_publish_gate import PREMIUM_PUBLISH_AUDIT_STAGES
from app.quality.render_gate import RenderGateResult
from app.utils import stable_hash


class FakePremiumRenderer:
    def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
        assert plan_path.exists()
        runtime_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert runtime_plan["scenes"][0]["asset_uri"].startswith("file://")
        assert "asset_path" in runtime_plan["scenes"][0]
        assert runtime_plan["audio"]["uri"].startswith("file://")
        assert "path" in runtime_plan["audio"]
        output_path.write_bytes(b"premium-video")
        log_path.write_text("fake remotion log", encoding="utf-8")
        return ["remotion", "render", str(output_path)]


class FakePremiumGate:
    def validate(self, video_path: Path, expected_duration_ms: int, edit_plan: dict) -> RenderGateResult:
        assert video_path.exists()
        assert expected_duration_ms == 35_000
        assert edit_plan["style"]["component_policy"] == "free_only"
        return RenderGateResult(True, [], {"duration_ms": expected_duration_ms})


class RejectingPremiumGate:
    def validate(self, video_path: Path, expected_duration_ms: int, edit_plan: dict) -> RenderGateResult:
        assert video_path.exists()
        return RenderGateResult(False, ["invalid_render"], {"duration_ms": expected_duration_ms})


def _audit_result(score: float) -> dict:
    return {
        "job_id": "test-job",
        "target_score": 9.4,
        "overall_min_score": score,
        "passed_target": score >= 9.4,
        "stages": [
            {
                "stage": stage,
                "score": score,
                "target_pass": score >= 9.4,
                "evidence": ["test double audit"],
                "gaps": [] if score >= 9.4 else ["test score below target"],
            }
            for stage in PREMIUM_PUBLISH_AUDIT_STAGES
        ],
    }


def _set_premium_publish_audit(monkeypatch, score: float) -> None:
    monkeypatch.setattr(orchestrator.publication_ops.premium_publish_gate, "audit_func", lambda root: _audit_result(score))


def _stub_monetization_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        orchestrator.monetization_pipeline,
        "build_monetization_report",
        lambda session, job, confirmations=None: {
            "passed": True,
            "final_status": "ready_for_upload",
            "hard_blockers": [],
            "manual_required": [],
            "warnings": [],
        },
    )


def _create_rendered_job(job_id: str) -> None:
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Prova premium")
        video_path = _write_job_artifact(job_id, "render/final.mp4", "video")
        poster_path = _write_job_artifact(job_id, "render/poster.jpg", "poster")
        session.add(
            RenderOutput(
                render_id=f"{job_id}-render",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash="render-hash",
                video_uri=video_path.as_uri(),
                poster_uri=poster_path.as_uri(),
                duration_ms=35_000,
                resolution="1080x1920",
                video_codec="H.264",
                audio_codec="AAC",
                filesize_bytes=1234,
                ffmpeg_log_uri=_write_job_artifact(job_id, "render/ffmpeg.log", "log").as_uri(),
            )
        )
        session.commit()


def _add_premium_generation_inputs(job_id: str) -> None:
    image_path = _write_job_artifact(job_id, "assets/scene-1.jpg", "image")
    Image.new("RGB", (1080, 1920), color=(24, 22, 21)).save(image_path, format="JPEG")
    audio_path = _write_job_artifact(job_id, "audio/mixed.wav", "audio")
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        session.add(
            ScenePlan(
                scene_plan_id=f"{job_id}-scene-plan",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash="scene-plan-hash",
                scene_count=1,
                scenes=[
                    {
                        "scene_id": "scene-1",
                        "order": 1,
                        "actual_start_ms": 0,
                        "actual_end_ms": 35_000,
                        "retention_role": "visual_hook",
                        "visual_intent": "deceptive_establishing",
                        "primary_subject": "polvo",
                        "narration_text": "Um polvo parece simples ate voce olhar de perto.",
                    }
                ],
            )
        )
        session.add(
            SceneAsset(
                asset_id=f"{job_id}-asset",
                job_id=job_id,
                scene_id="scene-1",
                schema_version="1.0.0",
                content_hash="asset-hash",
                provider="test",
                kind="image",
                uri=image_path.as_uri(),
                width=1080,
                height=1920,
                selected=True,
                scores={},
            )
        )
        session.add(
            NarrationAsset(
                narration_id=f"{job_id}-narration",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash="narration-hash",
                provider="synthetic_wav",
                voice="test",
                audio_uri=audio_path.as_uri(),
                duration_ms=35_000,
                sample_rate_hz=24000,
                channels=1,
            )
        )
        session.add(
            SubtitleTrack(
                subtitle_id=f"{job_id}-subtitles",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash="subtitle-hash",
                format="internal",
                items=[
                    {
                        "idx": "1",
                        "start_ms": 0,
                        "end_ms": 35_000,
                        "text": "Um polvo parece simples",
                        "token_start": 0,
                        "token_end": 3,
                    }
                ],
                coverage_ratio=1.0,
                p95_drift_ms=0,
                max_drift_ms=0,
            )
        )
        session.add(
            BackgroundMusicAsset(
                music_id=f"{job_id}-music",
                job_id=job_id,
                schema_version="1.0.0",
                content_hash=stable_hash("music"),
                provider="local_bank",
                audio_uri=audio_path.as_uri(),
                mixed_audio_uri=audio_path.as_uri(),
                duration_ms=35_000,
                gain_db=-17.0,
            )
        )
        session.commit()
    orchestrator.storage.persist_json(
        job_id,
        "visual_contract.json",
        {
            "visual_thesis": "Mostrar a virada visual do polvo.",
            "visual_domain": "documentary realism",
            "hook_frame": {"positive_read": "parece simples"},
            "payoff_frame": {"reveal": "nao era simples"},
        },
    )


def test_render_pipeline_produces_primary_remotion_artifacts(monkeypatch) -> None:
    job_id = "remotion-primary-no-ffmpeg"
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Render primário Remotion")
        session.commit()
    _add_premium_generation_inputs(job_id)
    monkeypatch.setattr(orchestrator.premium_finishing, "renderer", FakePremiumRenderer())
    monkeypatch.setattr(orchestrator.premium_finishing, "gate", FakePremiumGate())

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        artifacts = orchestrator.render_pipeline.step_render(session, job, attempt=1)
        session.commit()

    assert "render/final.mp4" in artifacts
    assert "render/remotion.log" in artifacts
    assert "render/ffmpeg.log" not in artifacts
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        render = session.query(RenderOutput).filter_by(job_id=job_id).one()
        assert job is not None
        assert job.artifact_index["render"] == "render/final.mp4"
        assert job.quality_summary["render"]["backend"] == "remotion"
        assert job.quality_summary["selected_render"]["variant"] == "remotion"
        assert render.video_uri.endswith("/render/final.mp4")
        assert render.ffmpeg_log_uri.endswith("/render/remotion.log")


def test_failed_primary_render_gate_preserves_previous_final(monkeypatch) -> None:
    job_id = "remotion-primary-gate-failure"
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Render anterior")
        session.commit()
    _add_premium_generation_inputs(job_id)
    final_path = _write_job_artifact(job_id, "render/final.mp4", "previous-valid-video")
    monkeypatch.setattr(orchestrator.premium_finishing, "renderer", FakePremiumRenderer())
    monkeypatch.setattr(orchestrator.premium_finishing, "gate", RejectingPremiumGate())

    with SessionLocal() as session, pytest.raises(FatalStepError, match="gate de render Remotion falhou"):
        orchestrator.premium_finishing.generate_primary_render(session, job_id)

    assert final_path.read_text(encoding="utf-8") == "previous-valid-video"

def test_remotion_cli_renderer_uses_absolute_artifact_paths(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    plan_path = tmp_path / "data" / "artifacts" / "job" / "render" / "edit_plan.json"
    output_path = tmp_path / "data" / "artifacts" / "job" / "render" / "premium.mp4"
    log_path = tmp_path / "data" / "artifacts" / "job" / "render" / "remotion.log"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        Path(command[4]).write_bytes(b"complete-file")
        return SimpleNamespace(
            returncode=0,
            stdout=f"ok project={project_dir} props={plan_path}",
            stderr=f"output={output_path} entry={entrypoint}",
        )

    monkeypatch.setattr("app.remotion_renderer.subprocess.run", fake_run)

    command = RemotionCliRenderer(project_dir=project_dir).render(plan_path=plan_path, output_path=output_path, log_path=log_path)

    props_index = command.index("--props") + 1
    assert Path(command[props_index]).is_absolute()
    assert Path(command[4]).is_absolute()
    assert command[command.index("--concurrency") + 1] == "2"
    assert captured["cwd"] == project_dir
    log_text = log_path.read_text(encoding="utf-8")
    assert str(project_dir) not in log_text
    assert str(plan_path) not in log_text
    assert str(output_path) not in log_text
    assert str(entrypoint) not in log_text
    assert "<remotion>" in log_text
    assert "<edit_plan.json>" in log_text
    assert "<premium.mp4>" in log_text


def test_remotion_cli_renderer_promotes_a_complete_file_atomically(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    plan_path = tmp_path / "edit_plan.json"
    output_path = tmp_path / "final.mp4"
    log_path = tmp_path / "remotion.log"
    plan_path.write_text("{}", encoding="utf-8")
    output_path.write_bytes(b"previous-complete-file")
    captured = {}

    def fake_run(command, **_kwargs):
        render_target = Path(command[4])
        captured["render_target"] = render_target
        assert render_target != output_path
        assert output_path.read_bytes() == b"previous-complete-file"
        render_target.write_bytes(b"new-complete-file")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("app.remotion_renderer.subprocess.run", fake_run)

    command = RemotionCliRenderer(project_dir=project_dir).render(
        plan_path=plan_path,
        output_path=output_path,
        log_path=log_path,
    )

    assert output_path.read_bytes() == b"new-complete-file"
    assert not captured["render_target"].exists()
    assert "--disable-web-security" not in command


def test_remotion_cli_renderer_preserves_previous_file_when_render_fails(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    plan_path = tmp_path / "edit_plan.json"
    output_path = tmp_path / "final.mp4"
    log_path = tmp_path / "remotion.log"
    plan_path.write_text("{}", encoding="utf-8")
    output_path.write_bytes(b"previous-complete-file")
    captured = {}

    def fake_run(command, **_kwargs):
        render_target = Path(command[4])
        captured["render_target"] = render_target
        render_target.write_bytes(b"partial-file")
        return SimpleNamespace(returncode=1, stdout="", stderr="failed")

    monkeypatch.setattr("app.remotion_renderer.subprocess.run", fake_run)

    with pytest.raises(FatalStepError, match="render premium falhou"):
        RemotionCliRenderer(project_dir=project_dir).render(
            plan_path=plan_path,
            output_path=output_path,
            log_path=log_path,
        )

    assert output_path.read_bytes() == b"previous-complete-file"
    assert not captured["render_target"].exists()


def test_remotion_cli_renderer_preflight_reports_missing_runtime(tmp_path) -> None:
    renderer = RemotionCliRenderer(project_dir=tmp_path / "remotion")

    status = renderer.preflight_environment()

    assert status["ready"] is False
    assert "remotion/node_modules/.bin/remotion ausente; rode npm install em remotion/" in status["missing_items"]
    with pytest.raises(FatalStepError, match="rode npm install em remotion"):
        renderer.assert_environment_ready()


def test_remotion_cli_renderer_preflight_accepts_installed_runtime(tmp_path) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")

    status = RemotionCliRenderer(project_dir=project_dir).preflight_environment()

    assert status["ready"] is True
    assert status["missing_items"] == []


def test_remotion_cli_renderer_rejects_missing_local_media_before_render(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    plan_path = tmp_path / "data" / "artifacts" / "job" / "render" / "edit_plan.json"
    output_path = tmp_path / "data" / "artifacts" / "job" / "render" / "premium.mp4"
    log_path = tmp_path / "data" / "artifacts" / "job" / "render" / "remotion.log"
    missing_asset = tmp_path / "data" / "artifacts" / "job" / "assets" / "missing.png"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(
            {
                "scenes": [{"asset_uri": missing_asset.as_uri()}],
                "audio": {"uri": "https://example.test/audio.mp3"},
            }
        ),
        encoding="utf-8",
    )

    def fake_run(*_args, **_kwargs):
        raise AssertionError("remotion render should not be called")

    monkeypatch.setattr("app.remotion_renderer.subprocess.run", fake_run)

    with pytest.raises(FatalStepError, match="assets locais do Remotion ausentes") as exc_info:
        RemotionCliRenderer(project_dir=project_dir).render(plan_path=plan_path, output_path=output_path, log_path=log_path)
    assert str(missing_asset.parent) not in str(exc_info.value)
    assert "missing.png" in str(exc_info.value)


def test_remotion_cli_renderer_rejects_local_media_outside_allowed_root(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "remotion"
    remotion_bin = project_dir / "node_modules" / ".bin" / "remotion"
    entrypoint = project_dir / "src" / "index.ts"
    remotion_bin.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    remotion_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.write_text("export {};\n", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    allowed_root = tmp_path / "data" / "artifacts"
    outside_asset = tmp_path / "private" / "secret.png"
    outside_asset.parent.mkdir(parents=True)
    outside_asset.write_bytes(b"secret")
    plan_path = allowed_root / "job" / "render" / "edit_plan.json"
    output_path = allowed_root / "job" / "render" / "premium.mp4"
    log_path = allowed_root / "job" / "render" / "remotion.log"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps({"scenes": [{"asset_uri": outside_asset.as_uri()}], "audio": {"uri": "https://example.test/audio.mp3"}}),
        encoding="utf-8",
    )

    def fake_run(*_args, **_kwargs):
        raise AssertionError("remotion render should not be called")

    monkeypatch.setattr("app.remotion_renderer.subprocess.run", fake_run)

    with pytest.raises(FatalStepError, match="assets locais do Remotion ausentes") as exc_info:
        RemotionCliRenderer(project_dir=project_dir, allowed_media_root=allowed_root).render(
            plan_path=plan_path,
            output_path=output_path,
            log_path=log_path,
        )
    assert str(outside_asset.parent) not in str(exc_info.value)
    assert "secret.png fora da raiz permitida" in str(exc_info.value)


def test_public_finish_plan_removes_unsafe_local_media_uris(tmp_path: Path) -> None:
    outside_asset = tmp_path / "private" / "scene.png"
    outside_audio = tmp_path / "private" / "voice.wav"
    plan = {
        "source_final_video_uri": outside_asset.as_uri(),
        "scenes": [
            {
                "asset_uri": outside_asset.as_uri(),
                "asset_src": outside_asset.as_uri(),
                "asset_path": str(outside_asset),
            }
        ],
        "audio": {"uri": outside_audio.as_uri(), "src": outside_audio.as_uri(), "path": str(outside_audio)},
    }

    public_plan_text = json.dumps(public_finish_plan(plan))

    assert "file://" not in public_plan_text
    assert str(tmp_path) not in public_plan_text


def test_premium_finishing_gate_accepts_controlled_editorial_motion(tmp_path: Path) -> None:
    class PassingRenderGate:
        def validate(self, video_path: Path, expected_duration_ms: int) -> RenderGateResult:
            return RenderGateResult(True, [], {"duration_ms": expected_duration_ms})

    video_path = tmp_path / "premium.mp4"
    video_path.write_bytes(b"video")
    plan = {
        "style": {"component_policy": "free_only"},
        "caption_track": {"max_lines": 1, "items": [{"text": "Legenda curta"}]},
        "scenes": [
            {
                "scene_id": "scene-1",
                "transition": {"kind": "soft_cut"},
                "motion": {"kind": "subtle_push", "start_scale": 1.02, "end_scale": 1.09, "x_delta": 6, "y_delta": 0},
                "overlays": [{"kind": "hook_tag", "text": "Detalhe", "start_ms": 100, "duration_ms": 900}],
            }
        ],
    }

    result = PremiumFinishingGate(PassingRenderGate()).validate(video_path, 35_000, plan)

    assert result.passed is True
    assert result.reasons == []


def test_premium_finishing_gate_rejects_excessive_motion(tmp_path: Path) -> None:
    class PassingRenderGate:
        def validate(self, video_path: Path, expected_duration_ms: int) -> RenderGateResult:
            return RenderGateResult(True, [], {"duration_ms": expected_duration_ms})

    video_path = tmp_path / "premium.mp4"
    video_path.write_bytes(b"video")
    plan = {
        "style": {"component_policy": "free_only"},
        "caption_track": {"max_lines": 1, "items": [{"text": "Legenda curta"}]},
        "scenes": [
            {
                "scene_id": "scene-1",
                "transition": {"kind": "soft_cut"},
                "motion": {"kind": "subtle_push", "start_scale": 1.0, "end_scale": 1.22, "x_delta": 60, "y_delta": 0},
                "overlays": [],
            }
        ],
    }

    result = PremiumFinishingGate(PassingRenderGate()).validate(video_path, 35_000, plan)

    assert result.passed is False
    assert "scene-1:excessive_motion" in result.reasons


def test_premium_finishing_gate_rejects_excessive_visual_event_motion(tmp_path: Path) -> None:
    class PassingRenderGate:
        def validate(self, video_path: Path, expected_duration_ms: int) -> RenderGateResult:
            return RenderGateResult(True, [], {"duration_ms": expected_duration_ms})

    video_path = tmp_path / "premium.mp4"
    video_path.write_bytes(b"video")
    plan = {
        "style": {"component_policy": "free_only"},
        "caption_track": {"max_lines": 1, "items": [{"text": "Legenda curta"}]},
        "scenes": [
            {
                "scene_id": "scene-1",
                "transition": {"kind": "soft_cut"},
                "motion": {"kind": "subtle_push", "start_scale": 1.02, "end_scale": 1.1, "x_delta": 6, "y_delta": 0},
                "overlays": [],
                "visual_events": [
                    {
                        "kind": "punch_in",
                        "start_ms": 1000,
                        "duration_ms": 500,
                        "scale_delta": 0.2,
                        "x_delta": 0,
                        "y_delta": 0,
                    }
                ],
            }
        ],
    }

    result = PremiumFinishingGate(PassingRenderGate()).validate(video_path, 35_000, plan)

    assert result.passed is False
    assert "scene-1:excessive_visual_event_motion" in result.reasons


def test_finish_plan_limits_caption_emphasis_to_data_only() -> None:
    job_id = "premium-caption-emphasis"
    _create_rendered_job(job_id)
    _add_premium_generation_inputs(job_id)

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        scene_plan = session.query(ScenePlan).filter_by(job_id=job_id).one()
        assets = session.query(SceneAsset).filter_by(job_id=job_id, selected=True).all()
        narration = session.query(NarrationAsset).filter_by(job_id=job_id).one()
        subtitles = session.query(SubtitleTrack).filter_by(job_id=job_id).one()
        render = session.query(RenderOutput).filter_by(job_id=job_id).one()
        assert job
        plan = build_finish_plan(
            schema_version="1.0.0",
            job=job,
            scene_plan=scene_plan,
            selected_assets=assets,
            narration=narration,
            subtitles=subtitles,
            background_music=None,
            render=render,
            visual_contract={},
        )

    caption = plan["caption_track"]["items"][0]
    assert caption["emphasis"]
    assert caption["startMs"] == 0
    assert caption["endMs"] == 35_000
    assert caption["timestampMs"] == 0
    assert caption["confidence"] is None
    assert "\n" not in caption["text"]


def test_finish_plan_repairs_invalid_caption_end_after_start() -> None:
    job_id = "premium-caption-timing"
    _create_rendered_job(job_id)
    _add_premium_generation_inputs(job_id)

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        scene_plan = session.query(ScenePlan).filter_by(job_id=job_id).one()
        assets = session.query(SceneAsset).filter_by(job_id=job_id, selected=True).all()
        narration = session.query(NarrationAsset).filter_by(job_id=job_id).one()
        subtitles = session.query(SubtitleTrack).filter_by(job_id=job_id).one()
        subtitles.items = [{"idx": "1", "start_ms": 1200, "end_ms": 0, "text": "Legenda com fim ausente"}]
        render = session.query(RenderOutput).filter_by(job_id=job_id).one()
        assert job
        plan = build_finish_plan(
            schema_version="1.0.0",
            job=job,
            scene_plan=scene_plan,
            selected_assets=assets,
            narration=narration,
            subtitles=subtitles,
            background_music=None,
            render=render,
            visual_contract={},
        )

    caption = plan["caption_track"]["items"][0]
    assert caption["startMs"] == 1200
    assert caption["endMs"] == 1201


def test_finish_plan_exposes_versioned_style_and_dense_deterministic_visual_events() -> None:
    roles = [
        "visual_hook",
        "visual_evidence",
        "visual_evidence",
        "visual_evidence",
        "turn_or_payoff",
        "loop_close",
    ]
    scenes = [
        {
            "scene_id": f"scene-{index + 1}",
            "order": index + 1,
            "token_start": index * 10,
            "token_end": index * 10 + 9,
            "retention_role": role,
            "visual_intent": "visual_evidence",
            "primary_subject": "octopus",
            "narration_text": f"Scene {index + 1}",
        }
        for index, role in enumerate(roles)
    ]
    assets = [
        SimpleNamespace(
            scene_id=scene["scene_id"],
            uri=f"file:///tmp/{scene['scene_id']}.png",
            content_hash=f"asset-{index}",
        )
        for index, scene in enumerate(scenes)
    ]
    kwargs = {
        "schema_version": "1.0.0",
        "job": SimpleNamespace(job_id="visual-events-job"),
        "scene_plan": SimpleNamespace(scenes=scenes, content_hash="scene-plan"),
        "selected_assets": assets,
        "narration": SimpleNamespace(
            duration_ms=36_000,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="file:///tmp/narration.wav",
        ),
        "subtitles": SimpleNamespace(items=[], content_hash="subtitles"),
        "background_music": None,
        "render": None,
        "visual_contract": {"visual_style_profile": "scientific_watercolor"},
    }

    first = public_finish_plan(build_finish_plan(**kwargs))
    second = public_finish_plan(build_finish_plan(**kwargs))

    assert first["style"]["visual_style_profile"]["id"] == "scientific_watercolor"
    assert first["style"]["visual_style_profile"]["version"] == "visual-style-v1"
    assert sum(len(scene["visual_events"]) for scene in first["scenes"]) >= 12
    assert [scene["visual_events"] for scene in first["scenes"]] == [
        scene["visual_events"] for scene in second["scenes"]
    ]
    assert all(
        scene["visual_style_profile"] == {"id": "scientific_watercolor", "version": "visual-style-v1"}
        for scene in first["scenes"]
    )


def test_survival_finish_plan_tells_the_binary_choice_through_scene_overlays() -> None:
    roles = ["visual_hook", "proof_or_tension", "escalation", "turn_or_payoff", "loop_close"]
    narrations = [
        "Areia invade a biblioteca: você leva a chave ou o livro?",
        "A areia já cobre o primeiro degrau.",
        "As estantes somem e a saída parece fechar.",
        "Sua escolha agora está travada.",
        "A chave abre a porta errada, mas o livro revela a saída real.",
    ]
    scenes = [
        {
            "scene_id": f"scene-{index + 1}",
            "order": index + 1,
            "actual_start_ms": index * 4_000,
            "actual_end_ms": (index + 1) * 4_000,
            "retention_role": role,
            "narration_text": narrations[index],
        }
        for index, role in enumerate(roles)
    ]
    kwargs = {
        "schema_version": "1.0.0",
        "job": SimpleNamespace(
            job_id="survival-overlay-job",
            niche_id="survival_decisions",
            topic_summary="Na biblioteca enchendo de areia, você leva a chave ou o livro?",
        ),
        "scene_plan": SimpleNamespace(scenes=scenes, content_hash="scene-plan"),
        "selected_assets": [
            SimpleNamespace(scene_id=scene["scene_id"], uri=f"scene-{index}.png", content_hash=f"asset-{index}")
            for index, scene in enumerate(scenes)
        ],
        "narration": SimpleNamespace(
            duration_ms=20_000,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        "subtitles": SimpleNamespace(items=[], content_hash="subtitles"),
        "background_music": None,
        "render": None,
        "visual_contract": {},
    }

    first = build_finish_plan(**kwargs)
    second = build_finish_plan(**kwargs)

    assert first["scenes"][0]["overlays"] == [
        {
            "kind": "hook_tag",
            "variant": "choice_label",
            "side": "left",
            "text": "CHAVE",
            "start_ms": 0,
            "duration_ms": 4_000,
        },
        {
            "kind": "hook_tag",
            "variant": "choice_label",
            "side": "right",
            "text": "LIVRO",
            "start_ms": 0,
            "duration_ms": 4_000,
        },
        {
            "kind": "evidence_marker",
            "variant": "sand_progress",
            "text": "AREIA SUBINDO",
            "progress": 0.25,
            "start_ms": 0,
            "duration_ms": 4_000,
        },
    ]
    assert first["scenes"][1]["overlays"][0] == {
        "kind": "evidence_marker",
        "variant": "sand_progress",
        "text": "AREIA SUBINDO",
        "progress": 0.5,
        "start_ms": 160,
        "duration_ms": 3_440,
    }
    assert first["scenes"][2]["overlays"][0]["progress"] == 1.0
    assert first["scenes"][3]["overlays"][0]["variant"] == "choice_state"
    assert first["scenes"][3]["overlays"][0]["text"] == "ESCOLHA TRAVADA"
    assert first["scenes"][4]["overlays"] == [
        {
            "kind": "payoff_tag",
            "variant": "outcome_comparison",
            "side": "left",
            "text": "ESCOLHA ERRADA",
            "secondary_text": "CHAVE",
            "start_ms": 120,
            "duration_ms": 1_380,
        },
        {
            "kind": "payoff_tag",
            "variant": "outcome_comparison",
            "side": "right",
            "text": "SAÍDA REAL",
            "secondary_text": "LIVRO",
            "start_ms": 120,
            "duration_ms": 1_380,
        },
        {
            "kind": "payoff_tag",
            "variant": "comment_prompt",
            "text": "VOCÊ ESCOLHEU QUAL?",
            "secondary_text": "CHAVE OU LIVRO?",
            "start_ms": 1_500,
            "duration_ms": 2_300,
        },
    ]
    assert [scene["overlays"] for scene in first["scenes"]] == [scene["overlays"] for scene in second["scenes"]]


@pytest.mark.parametrize(
    ("topic_summary", "expected_marker"),
    [
        ("No observatório, você fecha a cúpula ou mantém o sinal?", "SINAL ANÔMALO"),
        ("No hotel submerso, você sela o corredor ou libera a cápsula?", "PRESSÃO AUMENTANDO"),
        ("No farol isolado, você usa a bateria no rádio ou na luz?", "TEMPESTADE AUMENTANDO"),
        ("No museu parado no tempo, você gira o relógio para frente ou para trás?", "TEMPO CONGELADO"),
    ],
)
def test_survival_finish_plan_uses_scenario_specific_hazard_marker(
    topic_summary: str,
    expected_marker: str,
) -> None:
    scene = {
        "scene_id": "scene-1",
        "order": 1,
        "actual_start_ms": 0,
        "actual_end_ms": 4_000,
        "retention_role": "visual_hook",
        "narration_text": topic_summary,
    }

    plan = build_finish_plan(
        schema_version="1.0.0",
        job=SimpleNamespace(
            job_id="scenario-specific-hazard",
            niche_id="survival_decisions",
            topic_summary=topic_summary,
        ),
        scene_plan=SimpleNamespace(scenes=[scene], content_hash="scene-plan"),
        selected_assets=[SimpleNamespace(scene_id="scene-1", uri="scene.png", content_hash="asset")],
        narration=SimpleNamespace(
            duration_ms=4_000,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        subtitles=SimpleNamespace(items=[], content_hash="subtitles"),
        background_music=None,
        render=None,
        visual_contract={},
    )

    hazard_marker = plan["scenes"][0]["overlays"][-1]
    assert hazard_marker["variant"] == "hazard_progress"
    assert hazard_marker["text"] == expected_marker


def test_survival_finish_plan_completes_binary_payoff_from_one_confident_outcome() -> None:
    payoff_narration = (
        "então o teto se ilumina o livro desenha a planta e a chave abre a porta errada quando seu amigo escolher a "
        "chave lembre do teto a fechadura era distração"
    )
    scenes = [
        {
            "scene_id": "scene-1",
            "order": 1,
            "actual_start_ms": 0,
            "actual_end_ms": 4_000,
            "retention_role": "visual_hook",
            "narration_text": "Você precisa escolher a chave metálica ou o livro luminoso.",
        },
        {
            "scene_id": "scene-2",
            "order": 2,
            "actual_start_ms": 4_000,
            "actual_end_ms": 8_000,
            "retention_role": "loop_close",
            "narration_text": payoff_narration,
        },
    ]

    plan = build_finish_plan(
        schema_version="1.0.0",
        job=SimpleNamespace(
            job_id="survival-binary-payoff-fallback",
            niche_id="survival_decisions",
            topic_summary="Biblioteca subterrânea invadida por areia: escolher a chave metálica ou o livro luminoso",
        ),
        scene_plan=SimpleNamespace(scenes=scenes, content_hash="scene-plan"),
        selected_assets=[
            SimpleNamespace(scene_id=scene["scene_id"], uri=f"scene-{index}.png", content_hash=f"asset-{index}")
            for index, scene in enumerate(scenes)
        ],
        narration=SimpleNamespace(
            duration_ms=8_000,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        subtitles=SimpleNamespace(items=[], content_hash="subtitles"),
        background_music=None,
        render=None,
        visual_contract={},
    )

    opening_overlays = plan["scenes"][0]["overlays"]
    payoff_overlays = plan["scenes"][-1]["overlays"]
    assert [overlay["text"] for overlay in opening_overlays] == ["CHAVE", "LIVRO", "AREIA SUBINDO"]
    assert next(overlay for overlay in payoff_overlays if overlay["text"] == "ESCOLHA ERRADA")["secondary_text"] == "CHAVE"
    assert next(overlay for overlay in payoff_overlays if overlay["text"] == "SAÍDA REAL")["secondary_text"] == "LIVRO"


@pytest.mark.parametrize("scene_duration_ms", [500, 2_620])
def test_survival_finish_plan_keeps_short_overlay_windows_frame_visible(scene_duration_ms: int) -> None:
    narrations = [
        "Você escolhe a corda ou a semente?",
        "O perigo se aproxima.",
        "A escolha precisa acontecer.",
        "A escolha está travada.",
        "A corda dá errado, mas a semente revela a saída.",
    ]
    scenes = [
        {
            "scene_id": f"scene-{index + 1}",
            "order": index + 1,
            "actual_start_ms": index * scene_duration_ms,
            "actual_end_ms": (index + 1) * scene_duration_ms,
            "retention_role": "loop_close" if index == 4 else "visual_evidence",
            "narration_text": narration,
        }
        for index, narration in enumerate(narrations)
    ]
    plan = build_finish_plan(
        schema_version="1.0.0",
        job=SimpleNamespace(
            job_id="short-survival-overlays",
            niche_id="survival_decisions",
            topic_summary="No jardim sem gravidade, você prende a corda ou segura a semente?",
        ),
        scene_plan=SimpleNamespace(scenes=scenes, content_hash="scene-plan"),
        selected_assets=[
            SimpleNamespace(scene_id=scene["scene_id"], uri=f"scene-{index}.png", content_hash=f"asset-{index}")
            for index, scene in enumerate(scenes)
        ],
        narration=SimpleNamespace(
            duration_ms=scene_duration_ms * len(scenes),
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        subtitles=SimpleNamespace(items=[], content_hash="subtitles"),
        background_music=None,
        render=None,
        visual_contract={},
    )

    for scene in plan["scenes"][1:4]:
        assert all(overlay["duration_ms"] >= 34 for overlay in scene["overlays"])
        assert all(overlay["start_ms"] + overlay["duration_ms"] <= scene_duration_ms for overlay in scene["overlays"])
    payoff = plan["scenes"][-1]["overlays"]
    outcomes = [overlay for overlay in payoff if overlay["variant"] == "outcome_comparison"]
    comment = next(overlay for overlay in payoff if overlay["variant"] == "comment_prompt")
    assert len(outcomes) == 2
    assert all(overlay["duration_ms"] >= 34 for overlay in outcomes)
    assert all(overlay["start_ms"] + overlay["duration_ms"] <= comment["start_ms"] for overlay in outcomes)
    assert comment["duration_ms"] >= 34
    assert comment["secondary_text"] == "CORDA OU SEMENTE?"
    assert comment["start_ms"] + comment["duration_ms"] <= scene_duration_ms


def test_survival_finish_plan_preserves_long_payoff_overlay_timing() -> None:
    duration_ms = 10_305
    scenes = [
        {
            "scene_id": f"scene-{index + 1}",
            "order": index + 1,
            "actual_start_ms": index * duration_ms,
            "actual_end_ms": (index + 1) * duration_ms,
            "retention_role": "loop_close" if index == 1 else "visual_hook",
            "narration_text": (
                "A chave abre a porta errada, mas o livro revela a saída real."
                if index == 1
                else "Escolha a chave metálica ou o livro luminoso."
            ),
        }
        for index in range(2)
    ]
    plan = build_finish_plan(
        schema_version="1.0.0",
        job=SimpleNamespace(
            job_id="long-survival-overlays",
            niche_id="survival_decisions",
            topic_summary="a chave metálica ou o livro luminoso",
        ),
        scene_plan=SimpleNamespace(scenes=scenes, content_hash="scene-plan"),
        selected_assets=[
            SimpleNamespace(scene_id=scene["scene_id"], uri=f"scene-{index}.png", content_hash=f"asset-{index}")
            for index, scene in enumerate(scenes)
        ],
        narration=SimpleNamespace(
            duration_ms=duration_ms * 2,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        subtitles=SimpleNamespace(items=[], content_hash="subtitles"),
        background_music=None,
        render=None,
        visual_contract={},
    )

    payoff = plan["scenes"][-1]["overlays"]
    assert [(overlay["start_ms"], overlay["duration_ms"]) for overlay in payoff] == [
        (120, 7_685),
        (120, 7_685),
        (7_805, 2_300),
    ]


def test_remotion_survival_overlay_variants_are_frame_driven() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumShort.tsx").read_text(encoding="utf-8")

    assert "<SceneOverlays" in source
    assert "overlay.variant === 'choice_label'" in source
    assert "overlay.variant === 'sand_progress' || overlay.variant === 'hazard_progress'" in source
    assert "overlay.variant === 'choice_state'" in source
    assert "overlay.variant === 'outcome_comparison'" in source
    assert "overlay.variant === 'comment_prompt'" in source
    overlay_source = source[source.index("const SceneOverlays"):source.index("const eventCameraOffset")]
    assert "useCurrentFrame()" in overlay_source
    assert "interpolate(" in overlay_source
    assert "spring({" in overlay_source
    assert "const choiceCardTop" in overlay_source
    assert "const sandProgressTop = choiceCardTop +" in overlay_source
    assert "top: sandProgressTop" in overlay_source
    assert "const outcomeIndicatorProgress = interpolate(" in overlay_source
    assert "wrong ? '×' : '✓'" in overlay_source
    assert "color: wrong ? 'oklch(0.72 0.22 28)' : 'oklch(0.82 0.2 145)'" in overlay_source
    assert "const emphasizedChoiceIndex" in overlay_source
    assert "bottom: safeArea.bottom + 240" in overlay_source
    assert "left: Math.max(108, safeArea.x)" in overlay_source
    assert "right: Math.max(108, safeArea.x)" in overlay_source
    assert "transition:" not in overlay_source
    assert "animation:" not in overlay_source
    assert "@keyframes" not in source


def test_survival_overlay_labels_fall_back_neutrally_without_changing_generic_plans() -> None:
    scene = {
        "scene_id": "scene-1",
        "order": 1,
        "actual_start_ms": 0,
        "actual_end_ms": 4_000,
        "retention_role": "visual_hook",
        "narration_text": "Uma decisão precisa ser tomada agora.",
    }
    base_kwargs = {
        "schema_version": "1.0.0",
        "scene_plan": SimpleNamespace(scenes=[scene], content_hash="scene-plan"),
        "selected_assets": [SimpleNamespace(scene_id="scene-1", uri="scene.png", content_hash="asset")],
        "narration": SimpleNamespace(
            duration_ms=4_000,
            content_hash="narration",
            normalized_audio_uri=None,
            audio_uri="narration.wav",
        ),
        "subtitles": SimpleNamespace(items=[], content_hash="subtitles"),
        "background_music": None,
        "render": None,
        "visual_contract": {},
    }

    survival = build_finish_plan(
        **base_kwargs,
        job=SimpleNamespace(job_id="survival-fallback", niche_id="survival_decisions", topic_summary="Decisão impossível"),
    )
    generic = build_finish_plan(
        **base_kwargs,
        job=SimpleNamespace(job_id="generic-overlay", niche_id="curiosidades", topic_summary="Curiosidade"),
    )

    assert [overlay["text"] for overlay in survival["scenes"][0]["overlays"]] == [
        "OPÇÃO A",
        "OPÇÃO B",
        "PERIGO AUMENTANDO",
    ]
    assert generic["scenes"][0]["overlays"] == []


def test_premium_caption_highlight_uses_only_current_word() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumCaption.tsx").read_text(encoding="utf-8")

    assert "caption.emphasis.includes" not in source
    assert "index === activeWordIndex" in source
    assert "transition: 'transform" not in source
    assert "wordHighlightProgress" in source


def test_premium_scene_crossfade_never_fades_both_scenes_to_black() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumShort.tsx").read_text(encoding="utf-8")
    scene_layer = source[source.index("const SceneLayer"):source.index("const SceneOverlays")]

    assert "const opacityOut" not in scene_layer
    assert "const opacity = opacityIn" in scene_layer
    assert "durationInFrames={durationFrames + transitionFrames}" in scene_layer


def test_premium_caption_component_keeps_lateral_breathing_room() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumCaption.tsx").read_text(encoding="utf-8")

    assert "Math.max(108" in source
    assert "maxWidth: 840" in source
    assert "padding: '8px 28px 10px'" in source
    assert "WebkitTextStroke: '8px" in source


def test_premium_component_prefers_local_media_for_cli_render() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumShort.tsx").read_text(encoding="utf-8")

    assert "scene.asset_src || scene.asset_uri" in source
    assert "plan.audio.src || plan.audio.uri" in source
    assert "staticFile(value.replace" in source


def test_premium_runtime_plan_stages_local_media_for_remotion_public(tmp_path: Path) -> None:
    project_dir = tmp_path / "remotion"
    service = orchestrator.premium_finishing
    original_renderer = service.renderer
    service.renderer = RemotionCliRenderer(project_dir=project_dir)
    image_path = tmp_path / "source.jpg"
    audio_path = tmp_path / "source.wav"
    Image.new("RGB", (16, 16), color=(1, 2, 3)).save(image_path, format="JPEG")
    audio_path.write_bytes(b"wav")
    try:
        staged = service._stage_runtime_media(
            "stage-job",
            {
                "scenes": [{"scene_id": "scene-1", "asset_uri": image_path.as_uri(), "asset_path": str(image_path)}],
                "audio": {"uri": audio_path.as_uri(), "path": str(audio_path)},
            },
        )
    finally:
        service.renderer = original_renderer

    assert staged["scenes"][0]["asset_src"] == "shortsflow-runtime/stage-job/scene-1.jpg"
    assert staged["audio"]["src"] == "shortsflow-runtime/stage-job/audio.wav"
    assert (project_dir / "public" / "shortsflow-runtime" / "stage-job" / "scene-1.jpg").exists()
    assert (project_dir / "public" / "shortsflow-runtime" / "stage-job" / "audio.wav").exists()


def test_primary_render_contains_staged_scene_paths_and_cleans_runtime_media(tmp_path: Path) -> None:
    job_id = "remotion-safe-runtime-media"
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Staging seguro")
        session.commit()
    _add_premium_generation_inputs(job_id)
    project_dir = tmp_path / "remotion"
    observed = {}

    class InspectingRenderer:
        def __init__(self) -> None:
            self.project_dir = project_dir

        def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
            runtime_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            assert [scene["scene_id"] for scene in runtime_plan["scenes"]] == ["escape", "escape-2"]
            asset_src = runtime_plan["scenes"][0]["asset_src"]
            staged_path = (project_dir / "public" / asset_src).resolve()
            runtime_job_dir = (project_dir / "public" / "shortsflow-runtime" / job_id).resolve()
            assert staged_path.is_relative_to(runtime_job_dir)
            assert staged_path.exists()
            observed["runtime_job_dir"] = runtime_job_dir
            output_path.write_bytes(b"premium-video")
            log_path.write_text("fake remotion log", encoding="utf-8")
            return ["remotion", "render", str(output_path)]

    with SessionLocal() as session:
        scene_plan = session.query(ScenePlan).filter_by(job_id=job_id).one()
        scenes = [dict(scene) for scene in scene_plan.scenes]
        scenes[0]["scene_id"] = "../escape"
        scenes[0]["actual_end_ms"] = 17_500
        scenes.append({**scenes[0], "scene_id": "..?escape", "order": 2, "actual_start_ms": 17_500, "actual_end_ms": 35_000})
        scene_plan.scenes = scenes
        existing_asset = session.query(SceneAsset).filter_by(job_id=job_id).one()
        existing_asset.scene_id = "../escape"
        session.add(
            SceneAsset(
                asset_id=f"{job_id}-asset-2",
                job_id=job_id,
                scene_id="..?escape",
                schema_version="1.0.0",
                content_hash="asset-hash-2",
                provider="test",
                kind="image",
                uri=existing_asset.uri,
                width=1080,
                height=1920,
                selected=True,
                scores={},
            )
        )
        session.commit()

    service = orchestrator.premium_finishing
    original_renderer = service.renderer
    original_gate = service.gate
    service.renderer = InspectingRenderer()
    service.gate = FakePremiumGate()
    try:
        with SessionLocal() as session:
            report = service.generate_primary_render(session, job_id)
    finally:
        service.renderer = original_renderer
        service.gate = original_gate

    assert report["passed"] is True
    assert not observed["runtime_job_dir"].exists()
    assert not (project_dir / "public" / "shortsflow-runtime" / "escape.jpg").exists()


def test_primary_render_preserves_caption_token_timing() -> None:
    job_id = "remotion-caption-token-timing"
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Sincronia da legenda")
        session.commit()
    _add_premium_generation_inputs(job_id)
    expected_tokens = [
        {"text": "Um", "fromMs": 0, "toMs": 240},
        {"text": " polvo", "fromMs": 240, "toMs": 710},
    ]
    observed = {}

    class InspectingCaptionRenderer:
        def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
            runtime_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            observed["tokens"] = runtime_plan["caption_track"]["items"][0].get("tokens")
            output_path.write_bytes(b"premium-video")
            log_path.write_text("fake remotion log", encoding="utf-8")
            return ["remotion", "render", str(output_path)]

    with SessionLocal() as session:
        subtitles = session.query(SubtitleTrack).filter_by(job_id=job_id).one()
        items = [dict(item) for item in subtitles.items]
        items[0]["tokens"] = expected_tokens
        subtitles.items = items
        session.commit()

    service = orchestrator.premium_finishing
    original_renderer = service.renderer
    original_gate = service.gate
    service.renderer = InspectingCaptionRenderer()
    service.gate = FakePremiumGate()
    try:
        with SessionLocal() as session:
            report = service.generate_primary_render(session, job_id)
    finally:
        service.renderer = original_renderer
        service.gate = original_gate

    assert report["passed"] is True
    assert observed["tokens"] == expected_tokens


def test_premium_publish_gate_allows_approval_and_schedule_with_visual_confirmation(monkeypatch) -> None:
    job_id = "premium-publish-gate-pass"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 9.4)
    _stub_monetization_pass(monkeypatch)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "ready_for_upload"
        job.quality_summary = {
            "assets": {
                "semantic_threshold_pass": True,
                "asset_visual_gate_checked": True,
                "asset_visual_verification_modes": ["prompt_heuristic"],
            }
        }
        session.commit()

    orchestrator.review_job(
        {
            "reviewer_identity": "test",
            "action": "approve",
            "reason_codes": ["visual_review_confirmed"],
            "notes": None,
        },
        job_id,
    )
    orchestrator.schedule_publication(
        job_id,
        {
            "scheduled_for_local": "2099-06-10T14:30",
            "timezone": "America/Sao_Paulo",
            "youtube_visibility": "private",
            "notes": "",
        },
    )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one()
        assert job
        assert job.status == "approved_for_publish"
        assert schedule.status == "scheduled"


def test_premium_publish_gate_blocks_approval_without_visual_confirmation(monkeypatch) -> None:
    job_id = "premium-publish-gate-visual-block"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 9.8)
    _stub_monetization_pass(monkeypatch)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "ready_for_upload"
        job.quality_summary = {
            "assets": {
                "semantic_threshold_pass": True,
                "asset_visual_gate_checked": True,
                "asset_visual_verification_modes": ["prompt_heuristic"],
            }
        }
        session.commit()

    with pytest.raises(FatalStepError, match="visual_review_required"):
        orchestrator.review_job(
            {
                "reviewer_identity": "test",
                "action": "approve",
                "reason_codes": [],
                "notes": None,
            },
            job_id,
        )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        assert job.status == "blocked_for_monetization"
        assert job.review_state == "blocked"


def test_ready_job_approves_when_premium_audit_is_below_threshold(monkeypatch) -> None:
    job_id = "premium-publish-gate-approval-below-threshold"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 8.9)
    _stub_monetization_pass(monkeypatch)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "ready_for_upload"
        session.commit()

    orchestrator.review_job(
        {"reviewer_identity": "test", "action": "approve", "reason_codes": [], "notes": None},
        job_id,
    )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job and job.status == "approved_for_publish"


def test_ready_job_schedules_when_premium_audit_is_below_threshold(monkeypatch) -> None:
    job_id = "premium-publish-gate-schedule-block"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 8.9)
    orchestrator.storage.persist_json(
        job_id,
        "monetization_report.json",
        {"passed": True, "final_status": "ready_for_upload", "hard_blockers": [], "manual_required": []},
    )
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "approved_for_publish"
        job.review_state = "approved"
        session.commit()

    response = TestClient(app).post(
        f"/jobs/{job_id}/schedule",
        data={
            "scheduled_for_local": "2099-06-10T14:30",
            "timezone": "America/Sao_Paulo",
            "youtube_visibility": "private",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one_or_none()
        assert job
        assert job.status == "approved_for_publish"
        assert schedule is not None
        assert schedule.status == "scheduled"


def test_ready_job_manual_publishes_when_premium_audit_is_below_threshold(monkeypatch) -> None:
    job_id = "premium-publish-gate-manual-publish-block"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 9.1)
    orchestrator.storage.persist_json(
        job_id,
        "monetization_report.json",
        {"passed": True, "final_status": "ready_for_upload", "hard_blockers": [], "manual_required": []},
    )
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "approved_for_publish"
        job.review_state = "approved"
        job.quality_summary = {
            "monetization": {"passed": True, "final_status": "ready_for_upload", "hard_blockers": [], "manual_required": []}
        }
        session.commit()

    response = TestClient(app).post(
        f"/jobs/{job_id}/publish",
        data={"youtube_video_id": "yt-low-score"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{job_id}"
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one_or_none()
        assert job
        assert job.status == "published"
        assert schedule is not None
        assert schedule.status == "published"


@pytest.mark.parametrize("flow", ["immediate", "scheduled", "recovery"])
def test_every_youtube_flow_fails_preflight_for_non_publishable_final_status(monkeypatch, flow: str) -> None:
    job_id = f"youtube-semantic-preflight-{flow}"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 10.0)
    orchestrator.storage.persist_json(
        job_id,
        "monetization_report.json",
        {"passed": True, "final_status": "monetization_review", "hard_blockers": [], "manual_required": []},
    )
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        job.status = "approved_for_publish"
        job.review_state = "approved"
        session.commit()

    if flow == "scheduled":
        response = TestClient(app).post(
            f"/jobs/{job_id}/schedule",
            data={
                "scheduled_for_local": "2099-06-10T14:30",
                "timezone": "America/Sao_Paulo",
                "youtube_visibility": "private",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 409
    else:
        with pytest.raises(FatalStepError, match="premium_publish_final_status_not_publishable"):
            orchestrator.publish_job(
                job_id,
                youtube_video_id="yt-preflight",
                trigger="schedule_worker" if flow == "recovery" else "manual",
            )

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one_or_none()
        assert job and job.status == "blocked_for_monetization"
        assert schedule is None
