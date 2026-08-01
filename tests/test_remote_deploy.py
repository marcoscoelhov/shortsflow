from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from scripts.remote_deploy import (
    DeploymentLayout,
    DeploymentPlan,
    LegacyHandoff,
    _handoff_legacy_production,
    _install_release,
    _write_release_environment,
    atomic_activate,
    deploy,
    prune_inactive_releases,
)


def test_staging_plan_uses_isolated_state_and_service(tmp_path: Path) -> None:
    layout = DeploymentLayout(
        install_root=tmp_path / "opt",
        state_root=tmp_path / "srv",
        backup_root=tmp_path / "backups",
        config_root=tmp_path / "etc",
        runtime_root=tmp_path / "run",
    )

    plan = DeploymentPlan.create("staging", "a" * 40, layout=layout)

    assert plan.release_dir == tmp_path / "opt/staging/releases" / ("a" * 40)
    assert plan.data_dir == tmp_path / "srv/staging/data"
    assert plan.database_path == tmp_path / "srv/staging/data/shortsflow.db"
    assert plan.service_name == "shortsflow-staging.service"
    assert plan.port == 8082


def test_deployment_plan_rejects_unresolved_revision(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="40-character"):
        DeploymentPlan.create("production", "main", layout=DeploymentLayout.under(tmp_path))


def test_atomic_activation_can_restore_previous_release(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    first = releases / "first"
    second = releases / "second"
    first.mkdir(parents=True)
    second.mkdir()
    current = tmp_path / "current"
    current.symlink_to(first)

    previous = atomic_activate(current, second)

    assert previous == first
    assert current.resolve() == second
    atomic_activate(current, previous)
    assert current.resolve() == first


def test_release_pruning_preserves_active_and_three_previous(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    releases.mkdir()
    paths = []
    for index in range(6):
        path = releases / f"release-{index}"
        path.mkdir()
        path.touch(exist_ok=True)
        paths.append(path)
    current = tmp_path / "current"
    current.symlink_to(paths[0])

    removed = prune_inactive_releases(releases, active_release=paths[0], previous_to_keep=3)

    assert paths[0].exists()
    assert len([path for path in paths if path.exists()]) == 4
    assert len(removed) == 2


def test_install_release_grants_runtime_group_traversal(tmp_path: Path, monkeypatch) -> None:
    plan = DeploymentPlan.create("staging", "a" * 40, layout=DeploymentLayout.under(tmp_path))
    (plan.release_dir / ".venv/bin").mkdir(parents=True)
    (plan.release_dir / ".venv/bin/python").touch()
    (plan.release_dir / "remotion/node_modules/.bin").mkdir(parents=True)
    (plan.release_dir / "remotion/node_modules/.bin/remotion").touch()
    plan.release_dir.chmod(0o700)
    monkeypatch.setattr("scripts.remote_deploy._run", lambda *_args, **_kwargs: None)

    _install_release(plan)

    assert plan.release_dir.stat().st_mode & 0o050 == 0o050


def test_release_environment_overrides_legacy_runtime_paths(tmp_path: Path, monkeypatch) -> None:
    plan = DeploymentPlan.create("staging", "a" * 40, layout=DeploymentLayout.under(tmp_path))
    monkeypatch.setattr("scripts.remote_deploy.shutil.chown", lambda *_args, **_kwargs: None)

    _write_release_environment(plan)

    values = dict(
        line.split("=", 1)
        for line in plan.release_environment_file.read_text(encoding="utf-8").splitlines()
    )
    assert values["SHORTSFLOW_RUNTIME_ENVIRONMENT"] == "staging"
    assert values["SHORTSFLOW_APP_PORT"] == "8082"
    assert values["SHORTSFLOW_DATA_DIR"] == str(plan.data_dir)
    assert values["SHORTSFLOW_DATABASE_URL"] == f"sqlite:///{plan.database_path}"
    assert values["SHORTSFLOW_DEPLOYMENT_REVISION"] == plan.revision


def test_failed_health_restores_previous_release_and_revision(tmp_path: Path, monkeypatch) -> None:
    previous_revision = "b" * 40
    plan = DeploymentPlan.create("staging", "a" * 40, layout=DeploymentLayout.under(tmp_path))
    previous = plan.releases_dir / previous_revision
    previous.mkdir(parents=True)
    (previous / ".shortsflow-revision").write_text(previous_revision, encoding="utf-8")
    plan.release_dir.mkdir()
    (plan.release_dir / ".shortsflow-revision").write_text(plan.revision, encoding="utf-8")
    plan.current_link.parent.mkdir(parents=True, exist_ok=True)
    plan.current_link.symlink_to(previous)
    events: list[object] = []

    monkeypatch.setattr("scripts.remote_deploy._assert_staging_capacity", lambda _plan: events.append("capacity"))
    monkeypatch.setattr("scripts.remote_deploy._prepare_repository", lambda _plan: events.append("repository"))
    monkeypatch.setattr("scripts.remote_deploy._extract_release", lambda _plan: events.append("release"))
    monkeypatch.setattr("scripts.remote_deploy._install_release", lambda _plan: events.append("install"))
    monkeypatch.setattr("scripts.remote_deploy._drain", lambda _plan: events.append("drain"))
    monkeypatch.setattr("scripts.remote_deploy._backup", lambda _plan: events.append("backup") or tmp_path / "backup")
    monkeypatch.setattr("scripts.remote_deploy._run", lambda *args, **kwargs: events.append(args[0]))
    monkeypatch.setattr(
        "scripts.remote_deploy._write_release_environment",
        lambda _plan, revision=None: events.append(("revision", revision or _plan.revision)),
    )
    monkeypatch.setattr("scripts.remote_deploy._wait_for_health", lambda _plan: (_ for _ in ()).throw(RuntimeError("bad health")))

    with pytest.raises(RuntimeError, match="bad health"):
        deploy(plan)

    assert plan.current_link.resolve() == previous
    assert ("revision", plan.revision) in events
    assert ("revision", previous_revision) in events
    assert events.index("drain") < events.index("backup")


def test_first_production_handoff_copies_state_and_rewrites_paths(tmp_path: Path, monkeypatch) -> None:
    plan = DeploymentPlan.create("production", "a" * 40, layout=DeploymentLayout.under(tmp_path / "new"))
    legacy_data = tmp_path / "legacy-data"
    legacy_data.mkdir()
    legacy_database = legacy_data / "shortsflow_render.db"
    old_video = legacy_data / "artifacts/job-1/render/final.mp4"
    old_video.parent.mkdir(parents=True)
    old_video.write_bytes(b"video")
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("CREATE TABLE jobs (status TEXT, video_uri TEXT)")
        connection.execute("INSERT INTO jobs VALUES ('ready_for_upload', ?)", (old_video.as_uri(),))
    commands: list[list[str]] = []

    def fake_run(args, **_kwargs):
        commands.append(args)
        if args[:3] == ["systemctl", "is-active", "--quiet"]:
            return SimpleNamespace(returncode=0)
        if args[0] == "rsync":
            shutil.copytree(legacy_data / "artifacts", plan.data_dir / "artifacts", dirs_exist_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.remote_deploy._run", fake_run)

    handoff = _handoff_legacy_production(plan, legacy_data_dir=legacy_data)

    assert handoff.performed is True
    assert (plan.data_dir / "artifacts/job-1/render/final.mp4").read_bytes() == b"video"
    with sqlite3.connect(plan.database_path) as connection:
        (video_uri,) = connection.execute("SELECT video_uri FROM jobs").fetchone()
    assert str(plan.data_dir) in video_uri
    stop_command = next(command for command in commands if command[:2] == ["systemctl", "stop"])
    assert "shortsflow-hub.service" in stop_command
    assert "shortsflow-automation.timer" in stop_command


def test_failed_first_production_activation_restores_legacy_and_removes_current(tmp_path: Path, monkeypatch) -> None:
    plan = DeploymentPlan.create("production", "a" * 40, layout=DeploymentLayout.under(tmp_path))
    plan.release_dir.mkdir(parents=True)
    (plan.release_dir / ".shortsflow-revision").write_text(plan.revision, encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr("scripts.remote_deploy._assert_staging_capacity", lambda _plan: None)
    monkeypatch.setattr("scripts.remote_deploy._prepare_repository", lambda _plan: None)
    monkeypatch.setattr("scripts.remote_deploy._extract_release", lambda _plan: None)
    monkeypatch.setattr("scripts.remote_deploy._install_release", lambda _plan: None)
    monkeypatch.setattr("scripts.remote_deploy._drain", lambda _plan: None)
    monkeypatch.setattr(
        "scripts.remote_deploy._handoff_legacy_production",
        lambda _plan: LegacyHandoff(
            state_copied=True,
            active_units=("shortsflow-hub.service", "shortsflow-automation.timer"),
        ),
    )
    monkeypatch.setattr("scripts.remote_deploy._backup", lambda _plan: tmp_path / "backup")
    monkeypatch.setattr("scripts.remote_deploy._write_release_environment", lambda _plan, revision=None: None)
    monkeypatch.setattr(
        "scripts.remote_deploy._run",
        lambda args, **_kwargs: commands.append(args) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr("scripts.remote_deploy._wait_for_health", lambda _plan: (_ for _ in ()).throw(RuntimeError("bad health")))

    with pytest.raises(RuntimeError, match="bad health"):
        deploy(plan)

    assert not plan.current_link.exists()
    assert ["systemctl", "start", "shortsflow-hub.service", "shortsflow-automation.timer"] in commands
