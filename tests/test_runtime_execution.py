from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime_execution import (
    CapacitySnapshot,
    HeavyJobSlot,
    RuntimeExecutionCoordinator,
    RuntimeExecutionPolicy,
    assess_job_admission,
    assert_real_execution_location,
)


GIB = 1024**3


def test_real_execution_is_rejected_in_development() -> None:
    with pytest.raises(RuntimeError, match="real execution is restricted to the VPS"):
        assert_real_execution_location(environment="development", use_mock_providers=False)


def test_mock_development_and_remote_real_execution_are_allowed() -> None:
    assert_real_execution_location(environment="development", use_mock_providers=True)
    assert_real_execution_location(environment="staging", use_mock_providers=False)
    assert_real_execution_location(environment="production", use_mock_providers=False)


def test_staging_admission_rejects_insufficient_remote_capacity() -> None:
    policy = RuntimeExecutionPolicy(
        environment="staging",
        minimum_free_disk_bytes=15 * GIB,
        minimum_available_memory_bytes=2 * GIB,
        maximum_artifact_bytes=5 * GIB,
    )

    decision = assess_job_admission(
        policy,
        CapacitySnapshot(
            free_disk_bytes=14 * GIB,
            available_memory_bytes=1 * GIB,
            artifact_bytes=6 * GIB,
        ),
        draining=False,
    )

    assert decision.allowed is False
    assert decision.reasons == (
        "staging_disk_below_minimum",
        "staging_memory_below_minimum",
        "staging_artifacts_over_budget",
    )


def test_production_admission_ignores_staging_capacity_thresholds() -> None:
    policy = RuntimeExecutionPolicy(
        environment="production",
        minimum_free_disk_bytes=15 * GIB,
        minimum_available_memory_bytes=2 * GIB,
        maximum_artifact_bytes=5 * GIB,
    )

    decision = assess_job_admission(
        policy,
        CapacitySnapshot(free_disk_bytes=0, available_memory_bytes=0, artifact_bytes=99 * GIB),
        draining=False,
    )

    assert decision.allowed is True
    assert decision.reasons == ()


def test_drain_blocks_new_jobs_in_every_remote_environment() -> None:
    policy = RuntimeExecutionPolicy(environment="production")

    decision = assess_job_admission(
        policy,
        CapacitySnapshot(free_disk_bytes=0, available_memory_bytes=0, artifact_bytes=0),
        draining=True,
    )

    assert decision.allowed is False
    assert decision.reasons == ("runtime_draining",)


def test_global_slot_allows_only_one_heavy_job(tmp_path: Path) -> None:
    lock_path = tmp_path / "heavy-job.lock"
    production = HeavyJobSlot(lock_path=lock_path, environment="production")
    staging = HeavyJobSlot(lock_path=lock_path, environment="staging")

    with production.try_acquire() as production_acquired:
        assert production_acquired is True
        with staging.try_acquire() as staging_acquired:
            assert staging_acquired is False

    with staging.try_acquire() as staging_acquired:
        assert staging_acquired is True


def test_staging_yields_when_production_is_waiting(tmp_path: Path) -> None:
    lock_path = tmp_path / "heavy-job.lock"
    waiting_path = Path(f"{lock_path}.production-waiting")
    waiting_path.write_text("production\n", encoding="utf-8")

    with HeavyJobSlot(lock_path=lock_path, environment="staging").try_acquire() as acquired:
        assert acquired is False


def test_runtime_status_exposes_revision_drain_and_admission(tmp_path: Path) -> None:
    drain_path = tmp_path / "drain"
    drain_path.write_text("deploy\n", encoding="utf-8")
    settings = type(
        "Settings",
        (),
        {
            "runtime_environment": "staging",
            "deployment_revision": "abc123",
            "runtime_drain_path": drain_path,
            "heavy_job_lock_path": tmp_path / "heavy.lock",
            "heavy_job_lock_enabled": True,
            "staging_min_free_disk_gb": 15.0,
            "staging_min_available_memory_gb": 2.0,
            "staging_max_artifacts_gb": 5.0,
            "artifacts_dir": tmp_path / "artifacts",
            "data_dir": tmp_path,
        },
    )()
    coordinator = RuntimeExecutionCoordinator(
        settings,
        capacity_probe=lambda: CapacitySnapshot(20 * GIB, 3 * GIB, 1 * GIB),
    )

    assert coordinator.status() == {
        "environment": "staging",
        "revision": "abc123",
        "draining": True,
        "admission": {"allowed": False, "reasons": ["runtime_draining"]},
        "capacity": {
            "free_disk_bytes": 20 * GIB,
            "available_memory_bytes": 3 * GIB,
            "artifact_bytes": 1 * GIB,
        },
    }
