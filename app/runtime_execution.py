from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import shutil
import time
from typing import Iterator


@dataclass(frozen=True)
class CapacitySnapshot:
    free_disk_bytes: int
    available_memory_bytes: int
    artifact_bytes: int


@dataclass(frozen=True)
class RuntimeExecutionPolicy:
    environment: str
    minimum_free_disk_bytes: int = 0
    minimum_available_memory_bytes: int = 0
    maximum_artifact_bytes: int = 0


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def assert_real_execution_location(*, environment: str, use_mock_providers: bool) -> None:
    if environment == "development" and not use_mock_providers:
        raise RuntimeError(
            "real execution is restricted to the VPS; use `shortsflow job` or "
            "`shortsflow validate`, or enable mock providers for local development"
        )


def assess_job_admission(
    policy: RuntimeExecutionPolicy,
    snapshot: CapacitySnapshot,
    *,
    draining: bool,
) -> AdmissionDecision:
    if draining:
        return AdmissionDecision(allowed=False, reasons=("runtime_draining",))
    if policy.environment != "staging":
        return AdmissionDecision(allowed=True, reasons=())

    reasons: list[str] = []
    if snapshot.free_disk_bytes < policy.minimum_free_disk_bytes:
        reasons.append("staging_disk_below_minimum")
    if snapshot.available_memory_bytes < policy.minimum_available_memory_bytes:
        reasons.append("staging_memory_below_minimum")
    if policy.maximum_artifact_bytes and snapshot.artifact_bytes > policy.maximum_artifact_bytes:
        reasons.append("staging_artifacts_over_budget")
    return AdmissionDecision(allowed=not reasons, reasons=tuple(reasons))


class HeavyJobSlot:
    """Cross-process, non-blocking admission to the single heavy-job slot."""

    def __init__(self, *, lock_path: Path, environment: str) -> None:
        self.lock_path = lock_path
        self.environment = environment
        self.production_waiting_path = Path(f"{lock_path}.production-waiting")

    def _production_is_waiting(self) -> bool:
        if not self.production_waiting_path.exists():
            return False
        try:
            marker = self.production_waiting_path.read_text(encoding="utf-8").strip()
            if marker.isdigit() and not Path(f"/proc/{marker}").exists():
                self.production_waiting_path.unlink(missing_ok=True)
                return False
        except OSError:
            return True
        return True

    @contextmanager
    def try_acquire(self) -> Iterator[bool]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        is_production = self.environment == "production"
        if not is_production and self._production_is_waiting():
            yield False
            return

        if is_production:
            self.production_waiting_path.write_text("production\n", encoding="utf-8")

        lock_file = self.lock_path.open("a+", encoding="utf-8")
        acquired = False
        try:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
            if acquired and not is_production and self._production_is_waiting():
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                acquired = False
            yield acquired
        finally:
            if acquired:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            if is_production:
                self.production_waiting_path.unlink(missing_ok=True)

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Wait for the slot while keeping a production-priority marker."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        is_production = self.environment == "production"
        if is_production:
            self.production_waiting_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            while not is_production and self._production_is_waiting():
                time.sleep(0.25)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if not is_production and self._production_is_waiting():
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                while self._production_is_waiting():
                    time.sleep(0.25)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            if is_production:
                self.production_waiting_path.unlink(missing_ok=True)


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def _available_memory_bytes() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


class RuntimeExecutionCoordinator:
    def __init__(self, settings, *, capacity_probe=None) -> None:  # noqa: ANN001
        self.settings = settings
        self._capacity_probe = capacity_probe or self._system_capacity
        self._cached_snapshot: CapacitySnapshot | None = None
        self._cached_at = 0.0

    @property
    def policy(self) -> RuntimeExecutionPolicy:
        gib = 1024**3
        return RuntimeExecutionPolicy(
            environment=self.settings.runtime_environment,
            minimum_free_disk_bytes=round(self.settings.staging_min_free_disk_gb * gib),
            minimum_available_memory_bytes=round(self.settings.staging_min_available_memory_gb * gib),
            maximum_artifact_bytes=round(self.settings.staging_max_artifacts_gb * gib),
        )

    @property
    def draining(self) -> bool:
        return Path(self.settings.runtime_drain_path).exists()

    def _system_capacity(self) -> CapacitySnapshot:
        data_dir = Path(self.settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        return CapacitySnapshot(
            free_disk_bytes=shutil.disk_usage(data_dir).free,
            available_memory_bytes=_available_memory_bytes(),
            artifact_bytes=_directory_size(Path(self.settings.artifacts_dir)),
        )

    def capacity(self, *, fresh: bool = False) -> CapacitySnapshot:
        now = time.monotonic()
        if fresh or self._cached_snapshot is None or now - self._cached_at >= 30.0:
            self._cached_snapshot = self._capacity_probe()
            self._cached_at = now
        return self._cached_snapshot

    def admission(self, *, fresh: bool = False) -> AdmissionDecision:
        return assess_job_admission(self.policy, self.capacity(fresh=fresh), draining=self.draining)

    @contextmanager
    def job_slot(self) -> Iterator[None]:
        if not self.settings.heavy_job_lock_enabled:
            yield
            return
        slot = HeavyJobSlot(
            lock_path=Path(self.settings.heavy_job_lock_path),
            environment=self.settings.runtime_environment,
        )
        with slot.acquire():
            yield

    def status(self) -> dict[str, object]:
        snapshot = self.capacity(fresh=True)
        decision = assess_job_admission(self.policy, snapshot, draining=self.draining)
        return {
            "environment": self.settings.runtime_environment,
            "revision": self.settings.deployment_revision,
            "draining": self.draining,
            "admission": {"allowed": decision.allowed, "reasons": list(decision.reasons)},
            "capacity": {
                "free_disk_bytes": snapshot.free_disk_bytes,
                "available_memory_bytes": snapshot.available_memory_bytes,
                "artifact_bytes": snapshot.artifact_bytes,
            },
        }
