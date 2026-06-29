from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

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
    main_module,
    orchestrator,
)

from app.models import ScenePlan
from app.pipelines.common import FatalStepError
from app.pipelines.finish_plan import build_finish_plan, public_finish_plan
from app.premium_finishing import RemotionCliRenderer
from app.quality.premium_finishing_gate import PremiumFinishingGate
from app.quality.render_gate import RenderGateResult
from app.utils import file_sha256, stable_hash, utcnow


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


def _audit_result(score: float) -> dict:
    return {
        "job_id": "test-job",
        "target_score": 9.4,
        "overall_min_score": score,
        "passed_target": score >= 9.4,
        "stages": [
            {
                "stage": "publish_readiness",
                "score": score,
                "target_pass": score >= 9.4,
                "evidence": ["test double audit"],
                "gaps": [] if score >= 9.4 else ["test score below target"],
            }
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


def test_premium_finishing_generates_parallel_artifacts(monkeypatch) -> None:
    job_id = "premium-generation"
    _create_rendered_job(job_id)
    _add_premium_generation_inputs(job_id)
    monkeypatch.setattr(orchestrator.premium_finishing, "renderer", FakePremiumRenderer())
    monkeypatch.setattr(orchestrator.premium_finishing, "gate", FakePremiumGate())

    report = orchestrator.generate_premium_finishing(job_id)

    assert report["passed"] is True
    edit_plan_path = Path(__import__("os").environ["SHORTSFLOW_DATA_DIR"]) / "artifacts" / job_id / "render" / "edit_plan.json"
    premium_path = edit_plan_path.parent / "premium.mp4"
    plan_text = edit_plan_path.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    assert premium_path.exists()
    assert plan["plan_name"] == "Plano de Acabamento Editorial"
    assert plan["style"]["component_policy"] == "free_only"
    assert plan["caption_track"]["max_lines"] == 1
    assert "file://" not in plan_text
    assert str(Path(__import__("os").environ["SHORTSFLOW_DATA_DIR"]).resolve()) not in plan_text
    assert "asset_path" not in plan["scenes"][0]
    assert "path" not in plan["audio"]
    assert report["command"] == ["remotion", "render", "render/premium.mp4"]
    assert {scene["motion"]["kind"] for scene in plan["scenes"]} == {"subtle_push"}
    assert plan["scenes"][0]["overlays"] == []
    assert "sem_texto_superior_editorial" in plan["summary"]["premium_features"]
    assert "transicoes_semanticas" in plan["summary"]["premium_features"]
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job
        assert job.artifact_index["premium_video"] == "render/premium.mp4"
        assert job.quality_summary["premium_finishing"]["premium_finishing_gate_pass"] is True


def test_remotion_primary_render_skips_legacy_ffmpeg(monkeypatch) -> None:
    job_id = "remotion-primary-no-ffmpeg"
    with SessionLocal() as session:
        _create_basic_job(session, job_id=job_id, status="monetization_review", seed_theme="Render primário Remotion")
        session.commit()
    _add_premium_generation_inputs(job_id)
    monkeypatch.setattr(orchestrator.settings, "render_primary_backend", "remotion")
    monkeypatch.setattr(orchestrator.premium_finishing, "renderer", FakePremiumRenderer())
    monkeypatch.setattr(orchestrator.premium_finishing, "gate", FakePremiumGate())

    def fail_if_ffmpeg_is_used(*args, **kwargs):
        raise AssertionError("FFmpeg legacy render should not run when Remotion is primary")

    monkeypatch.setattr(orchestrator.render_pipeline, "render_with_repair", fail_if_ffmpeg_is_used)

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


def test_promote_as_primary_render_uses_premium_file_hash() -> None:
    job_id = "premium-promote-file-hash"
    _create_rendered_job(job_id)
    premium_path = _write_job_artifact(job_id, "render/premium.mp4", "premium-file-bytes")
    orchestrator.storage.persist_json(
        job_id,
        "premium_finishing_report.json",
        {"status": "succeeded", "passed": True, "video_uri": premium_path.as_uri(), "reasons": []},
    )
    orchestrator.storage.persist_json(
        job_id,
        "render_output.json",
        {"content_hash": "old-render-hash", "video_uri": "old-video-uri", "filesize_bytes": 5},
    )

    with SessionLocal() as session:
        orchestrator.premium_finishing.promote_as_primary_render(session, job_id, previous_video_uri="file:///tmp/standard.mp4")
        session.commit()

    with SessionLocal() as session:
        render = session.query(RenderOutput).filter_by(job_id=job_id).one()
        assert render.video_uri == premium_path.as_uri()
        assert render.content_hash == file_sha256(premium_path)

    render_payload = json.loads((Path(__import__("os").environ["SHORTSFLOW_DATA_DIR"]) / "artifacts" / job_id / "render_output.json").read_text(encoding="utf-8"))
    assert render_payload["content_hash"] == file_sha256(premium_path)
    assert render_payload["selected_render"] == "remotion"


def test_premium_finishing_reprocesses_from_tts_when_current_narration_is_not_primary(monkeypatch) -> None:
    job_id = "premium-primary-tts"
    _create_rendered_job(job_id)
    _add_premium_generation_inputs(job_id)
    monkeypatch.setattr(orchestrator.settings, "use_mock_providers", False)
    monkeypatch.setattr(orchestrator.settings, "tts_primary_provider", "gemini_tts")
    monkeypatch.setattr(orchestrator.premium_finishing, "renderer", FakePremiumRenderer())
    monkeypatch.setattr(orchestrator.premium_finishing, "gate", FakePremiumGate())
    called = {}

    with SessionLocal() as session:
        narration = session.query(NarrationAsset).filter(NarrationAsset.job_id == job_id).one()
        narration.provider = "edge_tts"
        session.commit()

    def fake_reprocess(received_job_id: str, step_name: str) -> str:
        called["job_id"] = received_job_id
        called["step_name"] = step_name
        with SessionLocal() as session:
            narration = session.query(NarrationAsset).filter(NarrationAsset.job_id == received_job_id).one()
            narration.provider = "gemini_tts"
            narration.content_hash = "primary-narration-hash"
            job = session.get(Job, received_job_id)
            assert job
            job.status = "monetization_review"
            session.commit()
        return "monetization_review"

    monkeypatch.setattr(orchestrator, "reprocess_job_from_step", fake_reprocess)

    report = orchestrator.generate_premium_finishing(job_id)

    assert report["passed"] is True
    assert called == {"job_id": job_id, "step_name": "tts"}


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


def test_premium_caption_highlight_uses_only_current_word() -> None:
    source = (Path(__file__).resolve().parent.parent / "remotion" / "src" / "PremiumShort.tsx").read_text(encoding="utf-8")

    assert "caption.emphasis.includes" not in source
    assert "index === activeWordIndex" in source
    assert "transition: 'transform" not in source
    assert "wordHighlightProgress" in source


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


def test_job_detail_hides_manual_premium_action() -> None:
    job_id = "premium-action"
    _create_rendered_job(job_id)

    response = TestClient(app).get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert "Comparar acabamento editorial" not in response.text
    assert "Gerar versão premium" not in response.text
    assert f'action="/jobs/{job_id}/premium-finish"' not in response.text
    assert "data-premium-progress" not in response.text


def test_premium_action_route_starts_background_generation(monkeypatch) -> None:
    job_id = "premium-route"
    _create_rendered_job(job_id)
    called = {}

    def fake_generate(received_job_id: str) -> dict:
        called["job_id"] = received_job_id
        return {"passed": True, "created_at": utcnow().isoformat()}

    monkeypatch.setattr(main_module.orchestrator, "generate_premium_finishing", fake_generate)

    response = TestClient(app).post(f"/jobs/{job_id}/premium-finish", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{job_id}?premium_started=1"
    assert called["job_id"] == job_id
    with SessionLocal() as session:
        details = orchestrator.get_job_details(session, job_id)
    assert details["premium_finishing"]["status"] == "running"
    assert details["premium_finishing"]["running"] is True


def test_job_detail_hides_premium_progress_when_generation_is_running() -> None:
    job_id = "premium-progress"
    _create_rendered_job(job_id)
    orchestrator.premium_finishing.mark_running(job_id, phase="rendering", detail="Render premium em andamento")

    response = TestClient(app).get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert 'hx-trigger="every 4s"' not in response.text
    assert "Gerando versão premium" not in response.text
    assert "Render premium em andamento" not in response.text
    assert "data-premium-progress" not in response.text


def test_job_detail_hides_premium_comparison_when_parallel_video_exists() -> None:
    job_id = "premium-comparison"
    _create_rendered_job(job_id)
    premium_path = _write_job_artifact(job_id, "render/premium.mp4", "premium")
    orchestrator.storage.persist_json(job_id, "render/edit_plan.json", {"plan_name": "Plano de Acabamento Editorial"})
    orchestrator.storage.persist_json(
        job_id,
        "premium_finishing_report.json",
        {"passed": True, "video_uri": premium_path.as_uri(), "reasons": []},
    )

    response = TestClient(app).get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert "Versão premium" not in response.text
    assert "Critérios aprovados" not in response.text
    assert "Abrir premium" not in response.text
    assert "Aprovar premium e liberar agenda" not in response.text
    assert f'action="/jobs/{job_id}/premium-approve"' not in response.text


def test_premium_approval_promotes_premium_video_to_publish_package(monkeypatch) -> None:
    job_id = "premium-approval"
    _create_rendered_job(job_id)
    _add_premium_generation_inputs(job_id)
    _set_premium_publish_audit(monkeypatch, 9.4)
    premium_path = _write_job_artifact(job_id, "render/premium.mp4", "premium")
    orchestrator.storage.persist_json(
        job_id,
        "premium_finishing_report.json",
        {"status": "succeeded", "passed": True, "video_uri": premium_path.as_uri(), "reasons": []},
    )

    def fake_monetization_report(session, job, confirmations):
        assert "premium_version_selected" in confirmations
        assert "visual_review_confirmed" in confirmations
        return {
            "passed": True,
            "final_status": "monetization_review",
            "hard_blockers": [],
            "manual_required": [],
            "warnings": [],
        }

    def fake_publish_package(session, job):
        render = session.query(RenderOutput).filter_by(job_id=job.job_id).one()
        return {"schema_version": "1.0.0", "job_id": job.job_id, "video_uri": render.video_uri, "status": "ready_for_publish"}

    monkeypatch.setattr(orchestrator.monetization_pipeline, "build_monetization_report", fake_monetization_report)
    monkeypatch.setattr(orchestrator.monetization_pipeline, "build_publish_package", fake_publish_package)

    response = TestClient(app).post(f"/jobs/{job_id}/premium-approve", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{job_id}"
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        render = session.query(RenderOutput).filter_by(job_id=job_id).one()
        assert job
        assert job.status == "approved_for_publish"
        assert job.review_state == "approved"
        assert render.video_uri == premium_path.as_uri()
        assert render.content_hash == file_sha256(premium_path)
        assert job.artifact_index["render"] == "render/premium.mp4"
        assert job.artifact_index["standard_render"] == "render/final.mp4"
    package_path = Path(__import__("os").environ["SHORTSFLOW_DATA_DIR"]) / "artifacts" / job_id / "publish_package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["video_uri"] == premium_path.as_uri()
    assert package["selected_render"] == "premium"


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
        assert job.quality_summary["premium_publish_gate"]["passed"] is True
        assert job.quality_summary["premium_publish_gate"]["score"] == 9.4
        assert schedule.status == "scheduled"


def test_premium_publish_gate_allows_approval_without_internal_visual_confirmation(monkeypatch) -> None:
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
        assert job.status == "approved_for_publish"
        assert job.review_state == "approved"
        assert job.quality_summary["premium_publish_gate"]["score"] == 9.8
        assert job.quality_summary["premium_publish_gate"]["passed"] is True
        assert job.quality_summary["premium_publish_gate"]["visual_review_required"] is False
        assert "visual_review_required" not in job.quality_summary["premium_publish_gate"]["reasons"]


def test_premium_publish_gate_blocks_schedule_when_score_is_below_threshold(monkeypatch) -> None:
    job_id = "premium-publish-gate-schedule-block"
    _create_rendered_job(job_id)
    _set_premium_publish_audit(monkeypatch, 8.9)
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

    assert response.status_code == 409
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one_or_none()
        assert job
        assert job.status == "blocked_for_monetization"
        assert schedule is None
        assert "premium_publish_score_below_threshold" in job.quality_summary["premium_publish_gate"]["reasons"]


def test_premium_publish_gate_blocks_manual_publish_when_score_is_below_threshold(monkeypatch) -> None:
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
    assert "publish_error=" in response.headers["location"]
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        schedule = session.query(PublicationSchedule).filter_by(job_id=job_id).one_or_none()
        assert job
        assert job.status == "blocked_for_monetization"
        assert schedule is None
        assert job.quality_summary["premium_publish_gate"]["score"] == 9.1
