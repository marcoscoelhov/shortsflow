#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


REPOSITORY_URL = "https://github.com/marcoscoelhov/shortsflow.git"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
LEGACY_RUNTIME_UNITS = (
    "shortsflow-hub.service",
    "shortsflow-automation.timer",
    "shortsflow-analytics-sync.timer",
    "shortsflow-hub-reload.path",
)


@dataclass(frozen=True)
class DeploymentLayout:
    install_root: Path
    state_root: Path
    backup_root: Path
    config_root: Path
    runtime_root: Path

    @classmethod
    def system(cls) -> "DeploymentLayout":
        return cls(
            install_root=Path("/opt/shortsflow"),
            state_root=Path("/srv/shortsflow"),
            backup_root=Path("/var/backups/shortsflow"),
            config_root=Path("/etc/shortsflow"),
            runtime_root=Path("/run/shortsflow"),
        )

    @classmethod
    def under(cls, root: Path) -> "DeploymentLayout":
        return cls(
            install_root=root / "opt",
            state_root=root / "srv",
            backup_root=root / "backups",
            config_root=root / "etc",
            runtime_root=root / "run",
        )


@dataclass(frozen=True)
class DeploymentPlan:
    environment: str
    revision: str
    release_dir: Path
    releases_dir: Path
    current_link: Path
    data_dir: Path
    database_path: Path
    backup_dir: Path
    environment_file: Path
    release_environment_file: Path
    drain_path: Path
    service_name: str
    port: int
    health_url: str
    repository_mirror: Path
    deployment_lock: Path

    @classmethod
    def create(cls, environment: str, revision: str, *, layout: DeploymentLayout) -> "DeploymentPlan":
        if environment not in {"staging", "production"}:
            raise ValueError("environment must be staging or production")
        if not REVISION_RE.fullmatch(revision):
            raise ValueError("revision must be a full 40-character lowercase Git SHA")
        port = 8082 if environment == "staging" else 8080
        environment_root = layout.install_root / environment
        releases_dir = environment_root / "releases"
        data_dir = layout.state_root / environment / "data"
        return cls(
            environment=environment,
            revision=revision,
            release_dir=releases_dir / revision,
            releases_dir=releases_dir,
            current_link=environment_root / "current",
            data_dir=data_dir,
            database_path=data_dir / "shortsflow.db",
            backup_dir=layout.backup_root / environment,
            environment_file=layout.config_root / f"{environment}.env",
            release_environment_file=layout.config_root / f"{environment}-release.env",
            drain_path=layout.runtime_root / environment / "drain",
            service_name=f"shortsflow-{environment}.service",
            port=port,
            health_url=f"http://127.0.0.1:{port}/healthz",
            repository_mirror=layout.install_root / "repository.git",
            deployment_lock=layout.runtime_root / "deploy.lock",
        )

    def public_dict(self) -> dict[str, object]:
        return {key: str(value) if isinstance(value, Path) else value for key, value in asdict(self).items()}


@dataclass(frozen=True)
class LegacyHandoff:
    state_copied: bool = False
    active_units: tuple[str, ...] = ()

    @property
    def performed(self) -> bool:
        return self.state_copied


def _run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    if check and completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"command failed: {' '.join(args)}")
    return completed


def atomic_activate(current_link: Path, release_dir: Path) -> Path | None:
    previous = current_link.resolve() if current_link.is_symlink() else None
    current_link.parent.mkdir(parents=True, exist_ok=True)
    temporary_link = current_link.with_name(f".{current_link.name}.{os.getpid()}.new")
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(release_dir)
    os.replace(temporary_link, current_link)
    return previous


def prune_inactive_releases(releases_dir: Path, *, active_release: Path, previous_to_keep: int) -> list[Path]:
    if not releases_dir.exists():
        return []
    candidates = sorted(
        (path for path in releases_dir.iterdir() if path.is_dir() and path.resolve() != active_release.resolve()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    removed: list[Path] = []
    for path in candidates[previous_to_keep:]:
        shutil.rmtree(path)
        removed.append(path)
    return removed


def _available_memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return 0


def _assert_staging_capacity(plan: DeploymentPlan) -> None:
    if plan.environment != "staging":
        return
    plan.data_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(plan.data_dir).free < 15 * 1024**3:
        raise RuntimeError("staging requires at least 15 GiB of free disk")
    if _available_memory_bytes() < 2 * 1024**3:
        raise RuntimeError("staging requires at least 2 GiB of available memory")


def _prepare_repository(plan: DeploymentPlan) -> None:
    plan.repository_mirror.parent.mkdir(parents=True, exist_ok=True)
    if not plan.repository_mirror.exists():
        _run(["git", "clone", "--mirror", REPOSITORY_URL, str(plan.repository_mirror)])
    else:
        _run(["git", "--git-dir", str(plan.repository_mirror), "remote", "update", "--prune"])
    _run(["git", "--git-dir", str(plan.repository_mirror), "cat-file", "-e", f"{plan.revision}^{{commit}}"])
    expected_branch = "staging" if plan.environment == "staging" else "main"
    _run(
        [
            "git",
            "--git-dir",
            str(plan.repository_mirror),
            "merge-base",
            "--is-ancestor",
            plan.revision,
            f"refs/heads/{expected_branch}",
        ]
    )
    if plan.environment == "production":
        _run(
            [
                "git",
                "--git-dir",
                str(plan.repository_mirror),
                "merge-base",
                "--is-ancestor",
                plan.revision,
                "refs/heads/staging",
            ]
        )


def _extract_release(plan: DeploymentPlan) -> None:
    if plan.release_dir.exists():
        marker = plan.release_dir / ".shortsflow-revision"
        if marker.read_text(encoding="utf-8").strip() != plan.revision:
            raise RuntimeError(f"existing release has invalid marker: {plan.release_dir}")
        return
    plan.releases_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{plan.revision}.", dir=plan.releases_dir))
    try:
        archive_path = temporary / "source.tar"
        with archive_path.open("wb") as archive:
            completed = subprocess.run(
                ["git", "--git-dir", str(plan.repository_mirror), "archive", plan.revision],
                check=False,
                stdout=archive,
                stderr=subprocess.PIPE,
            )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        with tarfile.open(archive_path) as bundle:
            bundle.extractall(temporary, filter="data")
        archive_path.unlink()
        (temporary / ".shortsflow-revision").write_text(f"{plan.revision}\n", encoding="utf-8")
        os.replace(temporary, plan.release_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _install_release(plan: DeploymentPlan) -> None:
    python_path = plan.release_dir / ".venv/bin/python"
    if not python_path.exists():
        _run(["python3.12", "-m", "venv", "--without-pip", str(plan.release_dir / ".venv")])
        _run(["python3.12", "-m", "pip", "--python", str(python_path), "install", "-e", str(plan.release_dir)])
    remotion_binary = plan.release_dir / "remotion/node_modules/.bin/remotion"
    if not remotion_binary.exists():
        _run(["npm", "ci"], cwd=plan.release_dir / "remotion")
    _run([str(remotion_binary), "browser", "ensure"], cwd=plan.release_dir / "remotion")
    runtime_media = plan.data_dir / "remotion-runtime"
    runtime_media.mkdir(parents=True, exist_ok=True)
    public_runtime = plan.release_dir / "remotion/public/shortsflow-runtime"
    if public_runtime.is_symlink() or public_runtime.is_file():
        public_runtime.unlink()
    elif public_runtime.exists():
        shutil.rmtree(public_runtime)
    public_runtime.parent.mkdir(parents=True, exist_ok=True)
    public_runtime.symlink_to(runtime_media)
    runtime_user = f"shortsflow-{plan.environment}"
    _run(["chown", "-R", f"root:{runtime_user}", str(plan.release_dir)])
    plan.release_dir.chmod(plan.release_dir.stat().st_mode | 0o050)
    _run(["chown", "-R", f"{runtime_user}:{runtime_user}", str(plan.data_dir)])


def _running_job_count(database_path: Path) -> int:
    if not database_path.exists():
        return 0
    uri = f"file:{database_path}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            row = connection.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error as exc:
        raise RuntimeError(f"cannot inspect running jobs: {exc}") from exc


def _rewrite_legacy_paths(database_path: Path, *, old_root: Path, new_root: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table_name,) in tables:
            escaped_table = str(table_name).replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{escaped_table}")').fetchall()
            for column in columns:
                column_name = str(column[1])
                column_type = str(column[2] or "").upper()
                if column_type and not any(token in column_type for token in ("TEXT", "CHAR", "CLOB", "JSON")):
                    continue
                escaped_column = column_name.replace('"', '""')
                connection.execute(
                    f'UPDATE "{escaped_table}" SET "{escaped_column}" = '
                    f'replace("{escaped_column}", ?, ?) '
                    f'WHERE typeof("{escaped_column}") = \'text\' AND instr("{escaped_column}", ?) > 0',
                    (str(old_root), str(new_root), str(old_root)),
                )


def _handoff_legacy_production(
    plan: DeploymentPlan,
    *,
    legacy_data_dir: Path = Path("/root/shortsflow/data"),
    legacy_units: tuple[str, ...] = LEGACY_RUNTIME_UNITS,
) -> LegacyHandoff:
    if plan.environment != "production" or plan.current_link.exists():
        return LegacyHandoff()
    legacy_database = legacy_data_dir / "shortsflow_render.db"
    if not legacy_database.exists():
        return LegacyHandoff()
    if _running_job_count(legacy_database):
        raise RuntimeError("legacy production still has a running job; retry promotion when it is idle")
    active_units = tuple(
        unit
        for unit in legacy_units
        if _run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
    )
    if active_units:
        _run(["systemctl", "stop", *active_units])
    try:
        plan.data_dir.mkdir(parents=True, exist_ok=True)
        plan.database_path.unlink(missing_ok=True)
        _run(
            [
                "rsync",
                "--archive",
                "--exclude=*.db",
                "--exclude=*.db-wal",
                "--exclude=*.db-shm",
                f"{legacy_data_dir}/",
                f"{plan.data_dir}/",
            ]
        )
        with sqlite3.connect(legacy_database) as source, sqlite3.connect(plan.database_path) as target:
            source.backup(target)
        _rewrite_legacy_paths(plan.database_path, old_root=legacy_data_dir, new_root=plan.data_dir)
        _run(["chown", "-R", "shortsflow-production:shortsflow-production", str(plan.data_dir)])
    except Exception:
        if active_units:
            _run(["systemctl", "start", *active_units], check=False)
        raise
    return LegacyHandoff(state_copied=True, active_units=active_units)


def _drain(plan: DeploymentPlan, *, timeout_seconds: int = 7200) -> None:
    plan.drain_path.parent.mkdir(parents=True, exist_ok=True)
    plan.drain_path.write_text(f"deploy {plan.revision}\n", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    while _running_job_count(plan.database_path):
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for active job to finish")
        time.sleep(5)


def _backup(plan: DeploymentPlan) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = plan.backup_dir / f"predeploy-{timestamp}-{plan.revision[:12]}"
    destination.mkdir(parents=True, mode=0o750)
    if plan.database_path.exists():
        with sqlite3.connect(plan.database_path) as source, sqlite3.connect(destination / "shortsflow.db") as target:
            source.backup(target)
    (destination / "metadata.json").write_text(
        json.dumps({"environment": plan.environment, "revision": plan.revision, "created_at": timestamp}, indent=2),
        encoding="utf-8",
    )
    backups = sorted(plan.backup_dir.glob("predeploy-*"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for expired in backups[3:]:
        shutil.rmtree(expired)
    return destination


def _write_release_environment(plan: DeploymentPlan, *, revision: str | None = None) -> None:
    public_url = "https://srv769897.tailc97b69.ts.net"
    if plan.environment == "staging":
        public_url += ":8443"
    plan.release_environment_file.parent.mkdir(parents=True, exist_ok=True)
    plan.release_environment_file.write_text(
        "\n".join(
            (
                f"SHORTSFLOW_RUNTIME_ENVIRONMENT={plan.environment}",
                f"SHORTSFLOW_APP_NAME=ShortsFlow {plan.environment.title()}",
                f"SHORTSFLOW_APP_URL={public_url}",
                "SHORTSFLOW_APP_HOST=127.0.0.1",
                f"SHORTSFLOW_APP_PORT={plan.port}",
                f"SHORTSFLOW_DATA_DIR={plan.data_dir}",
                f"SHORTSFLOW_DATABASE_URL=sqlite:///{plan.database_path}",
                f"SHORTSFLOW_RUNTIME_DRAIN_PATH={plan.drain_path}",
                f"SHORTSFLOW_DEPLOYMENT_REVISION={revision or plan.revision}",
                "",
            )
        ),
        encoding="utf-8",
    )
    os.chmod(plan.release_environment_file, 0o640)
    shutil.chown(plan.release_environment_file, user="root", group=f"shortsflow-{plan.environment}")


def _wait_for_health(plan: DeploymentPlan, *, timeout_seconds: int = 120) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "health unavailable"
    while time.monotonic() < deadline:
        try:
            with urlopen(plan.health_url, timeout=5) as response:  # noqa: S310
                payload = json.load(response)
            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
            if runtime.get("environment") == plan.environment and runtime.get("revision") == plan.revision:
                return payload
            last_error = f"unexpected runtime identity: {runtime}"
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(last_error)


def deploy(plan: DeploymentPlan) -> dict[str, object]:
    for path in (plan.data_dir, plan.backup_dir, plan.deployment_lock.parent):
        path.mkdir(parents=True, exist_ok=True)
    with plan.deployment_lock.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _assert_staging_capacity(plan)
        _prepare_repository(plan)
        _extract_release(plan)
        _install_release(plan)
        _drain(plan)
        previous = plan.current_link.resolve() if plan.current_link.is_symlink() else None
        previous_revision = None
        if previous:
            marker = previous / ".shortsflow-revision"
            if not marker.exists():
                raise RuntimeError(f"previous release has no revision marker: {previous}")
            previous_revision = marker.read_text(encoding="utf-8").strip()
        legacy_handoff = _handoff_legacy_production(plan)
        try:
            backup = _backup(plan)
            _run(["systemctl", "stop", plan.service_name], check=False)
            _write_release_environment(plan)
            atomic_activate(plan.current_link, plan.release_dir)
            _run(["systemctl", "restart", plan.service_name])
            health = _wait_for_health(plan)
        except Exception:
            if previous and previous.exists():
                atomic_activate(plan.current_link, previous)
                if previous_revision:
                    _write_release_environment(plan, revision=previous_revision)
                _run(["systemctl", "restart", plan.service_name], check=False)
                _wait_for_health(replace(plan, revision=previous_revision, release_dir=previous))
            elif legacy_handoff.performed:
                if plan.current_link.is_symlink():
                    plan.current_link.unlink()
                _run(["systemctl", "stop", plan.service_name], check=False)
                if legacy_handoff.active_units:
                    _run(["systemctl", "start", *legacy_handoff.active_units], check=False)
                    for unit in legacy_handoff.active_units:
                        _run(["systemctl", "is-active", "--quiet", unit])
            raise
        finally:
            plan.drain_path.unlink(missing_ok=True)
        removed = prune_inactive_releases(
            plan.releases_dir,
            active_release=plan.release_dir,
            previous_to_keep=3,
        )
        if legacy_handoff.performed:
            _run(["systemctl", "disable", "--now", *LEGACY_RUNTIME_UNITS], check=False)
            _run(["systemctl", "enable", plan.service_name])
        return {
            "status": "deployed",
            "environment": plan.environment,
            "revision": plan.revision,
            "backup": str(backup),
            "removed_releases": [str(path) for path in removed],
            "health": health,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shortsflow-deploy")
    parser.add_argument("environment", choices=["staging", "production"])
    parser.add_argument("revision")
    parser.add_argument("--plan", action="store_true", help="Print the immutable deployment plan without mutation")
    args = parser.parse_args(argv)
    try:
        plan = DeploymentPlan.create(args.environment, args.revision, layout=DeploymentLayout.system())
        if args.plan:
            print(json.dumps(plan.public_dict(), indent=2))
            return 0
        if os.geteuid() != 0:
            raise RuntimeError("deployment must run as root through the restricted sudo command")
        print(json.dumps(deploy(plan), indent=2))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"deployment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
