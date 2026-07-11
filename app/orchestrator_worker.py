from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import run_transaction_with_lock_retry
from app.models import Job
from app.utils import utcnow

logger = logging.getLogger(__name__)


class OrchestratorWorkerOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    def start_worker(self) -> None:
        if self.owner.worker_thread and self.owner.worker_thread.is_alive():
            return
        self.owner.stop_event = threading.Event()
        self.owner.worker_thread = threading.Thread(target=self.owner._worker_loop, name="shortsflow-worker", daemon=True)
        self.owner.worker_thread.start()

    def stop_worker(self) -> None:
        self.owner.stop_event.set()
        if self.owner.worker_thread and self.owner.worker_thread.is_alive():
            self.owner.worker_thread.join(timeout=2)
        if self.owner.worker_thread and not self.owner.worker_thread.is_alive():
            self.owner.worker_thread = None

    def lease_delta(self) -> timedelta:
        # Real provider steps (image generation, TTS and Remotion/ffmpeg render) can hold
        # a SQLite write transaction open for several minutes. Keep the lease long
        # enough that the worker will not reclaim the same job while the step is still
        # legitimately running if heartbeat refreshes are skipped by SQLite locks.
        return timedelta(seconds=max(3600, self.settings.job_lease_seconds))

    def start_lease_heartbeat(self, job_id: str) -> threading.Event:
        stop_heartbeat = threading.Event()
        # Avoid hammering SQLite while long media steps are running in the same process.
        # The lease floor above is one hour, so a 10-minute heartbeat is sufficient and
        # prevents the noisy self-contention seen with 30-second refreshes.
        interval = max(300.0, min(900.0, max(3600, self.settings.job_lease_seconds) / 6))

        def heartbeat() -> None:
            while not stop_heartbeat.wait(interval):
                def refresh_lease(session: Session) -> bool:
                    job = session.get(Job, job_id)
                    if not job or job.status != "running" or job.lease_owner != self.owner.worker_id:
                        return False
                    job.lease_expires_at = utcnow() + self.owner._lease_delta()
                    return True

                try:
                    if not run_transaction_with_lock_retry(refresh_lease):
                        return
                except OperationalError:
                    logger.warning("lease heartbeat skipped after repeated database lock for job %s", job_id, exc_info=True)

        threading.Thread(target=heartbeat, name=f"shortsflow-lease-{job_id[:8]}", daemon=True).start()
        return stop_heartbeat

    def worker_loop(self) -> None:
        while not self.owner.stop_event.is_set():
            try:
                did_work = self.owner._worker_iteration()
            except OperationalError:
                logger.warning("worker iteration skipped after database operational error", exc_info=True)
                time.sleep(max(1.0, self.settings.worker_poll_seconds))
                continue
            except Exception:
                logger.exception("worker iteration failed unexpectedly")
                time.sleep(max(1.0, self.settings.worker_poll_seconds))
                continue
            if not did_work:
                time.sleep(self.settings.worker_poll_seconds)

    def run_worker_task(self, task_name: str, callback: Callable[[], Any]) -> Any:
        try:
            return callback()
        except OperationalError:
            logger.warning("worker task %s skipped after database operational error", task_name, exc_info=True)
            return None
        except Exception:
            logger.exception("worker task %s failed; worker will continue", task_name)
            return None

    def worker_iteration(self) -> bool:
        if self.settings.artifact_retention_enabled:
            should_sweep = time.monotonic() - self.owner._last_retention_sweep_at >= self.settings.artifact_retention_sweep_seconds
            if should_sweep:
                self.owner._last_retention_sweep_at = time.monotonic()
                self.owner._run_worker_task("retention_sweep", self.owner.publication_ops._run_retention_sweep)
        if self.owner.publication_ops._youtube_api_mode_enabled():
            self.owner._run_worker_task("youtube_publication_recovery", self.owner.publication_ops._recover_stale_publication_schedules)
            self.owner._run_worker_task("youtube_native_schedule_sync", self.owner.publication_ops._sync_native_scheduled_publications)
        if self.owner.publication_ops._tiktok_auto_publish_enabled():
            self.owner._run_worker_task("tiktok_status_sync", self.owner.publication_ops._sync_tiktok_publication_statuses)
            self.owner._run_worker_task("tiktok_crosspost_queue_sync", self.owner.publication_ops._sync_tiktok_crosspost_queue)
        claimed_job_id = self.owner._run_worker_task("job_claim", self.owner._claim_next_job_with_retry)
        if claimed_job_id:
            self.owner._run_worker_task("job_process", lambda: self.owner.process_job(claimed_job_id))
            return True
        claimed_publication_job_id = self.owner._run_worker_task("publication_schedule_claim", self.owner.publication_ops._claim_due_publication_schedule)
        if claimed_publication_job_id:
            self.owner._run_worker_task("publication_schedule_publish", lambda: self.owner.publish_job(claimed_publication_job_id, trigger="schedule_worker"))
            return True
        claimed_tiktok_publication_id = self.owner._run_worker_task("tiktok_publication_claim", self.owner.publication_ops._claim_due_tiktok_publication)
        if claimed_tiktok_publication_id:
            self.owner._run_worker_task(
                "tiktok_publication_publish",
                lambda: self.owner.publication_ops._publish_tiktok_channel_publication(claimed_tiktok_publication_id),
            )
            return True
        return False

    def claim_next_job(self, session: Session) -> str | None:
        now = utcnow()
        lease_expires_at = now + self.owner._lease_delta()
        claimable_job_id = (
            select(Job.job_id)
            .where(
                or_(
                    Job.status == "queued",
                    (Job.status == "running") & (Job.lease_expires_at.is_(None) | (Job.lease_expires_at < now)),
                )
            )
            .order_by(Job.created_at)
            .limit(1)
            .scalar_subquery()
        )
        claim = (
            update(Job)
            .where(Job.job_id == claimable_job_id)
            .values(
                status="running",
                lease_owner=self.owner.worker_id,
                lease_expires_at=lease_expires_at,
            )
            .returning(Job.job_id)
        )
        return session.execute(claim).scalar_one_or_none()
