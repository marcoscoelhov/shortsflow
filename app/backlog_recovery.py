from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.db import session_scope
from app.domain_contracts import (
    ACTIVE_SCHEDULE_STATUSES,
    ARTIFACT_PUBLISH_PACKAGE,
    JOB_STATUS_APPROVED_FOR_PUBLISH,
    JOB_STATUS_BLOCKED_FOR_MONETIZATION,
    JOB_STATUS_MONETIZATION_REVIEW,
    JOB_STATUS_READY_FOR_UPLOAD,
    JOB_STATUS_SCRIPT_QUALITY_FAILED,
    JOB_STATUS_SUBTITLE_QUALITY_FAILED,
    REASON_ASSET_VISUAL_REVIEW_REQUIRED,
    REASON_INVENTED_SOURCE_FACT_IDS,
    REASON_UNSUPPORTED_CLAIM,
    REASON_VISUAL_REVIEW_REQUIRED,
)
from app.models import BacklogRecoveryAttempt, Job, PublicationSchedule, RenderOutput, SceneAsset, NarrationAsset
from app.utils import new_id, path_from_uri, stable_hash, utcnow

CANDIDATE_STATUSES = {
    JOB_STATUS_MONETIZATION_REVIEW,
    JOB_STATUS_READY_FOR_UPLOAD,
    JOB_STATUS_APPROVED_FOR_PUBLISH,
    JOB_STATUS_BLOCKED_FOR_MONETIZATION,
    JOB_STATUS_SCRIPT_QUALITY_FAILED,
    "render_quality_failed",
    "asset_quality_failed",
    JOB_STATUS_SUBTITLE_QUALITY_FAILED,
}
FACTUAL_OR_RIGHTS_MARKERS = {
    REASON_UNSUPPORTED_CLAIM,
    REASON_INVENTED_SOURCE_FACT_IDS,
    "rights",
    "copyright",
    "youtube_policy",
    "policy_risk",
    "factual",
}
CORRECTABLE_MARKERS = {
    REASON_VISUAL_REVIEW_REQUIRED,
    REASON_ASSET_VISUAL_REVIEW_REQUIRED,
    "metadata",
    "text publish audit missing",
    "image_semantics_score_below_threshold",
    "topic quality metrics incomplete",
    "duration",
    "render failed",
    "asset",
    "tts",
    "subtitle",
    "monetization_readiness_gate",
    "premium_publish_score_below_threshold",
}


@dataclass(frozen=True)
class BacklogCandidate:
    job_id: str
    status: str
    classification: str
    reasons: list[str]
    allowed_repairs: list[str]
    risk: str
    job_origin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacklogRecoveryReport:
    status: str
    mode: str
    dry_run: bool
    candidates: list[BacklogCandidate]
    actions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        summary: dict[str, int] = {}
        for candidate in self.candidates:
            summary[candidate.classification] = summary.get(candidate.classification, 0) + 1
        return {
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "summary": summary,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "actions": self.actions,
        }


class BacklogRecoveryService:
    def __init__(self, settings: Any, orchestrator: Any) -> None:
        self.settings = settings
        self.orchestrator = orchestrator

    def scan(self, *, limit: int = 50) -> BacklogRecoveryReport:
        candidates = self._scan_candidates(limit=limit)
        return BacklogRecoveryReport(status="ok", mode="scan", dry_run=True, candidates=candidates, actions=[])

    def run(self, *, mode: str = "reactive", dry_run: bool = False, job_id: str | None = None, limit: int = 50) -> BacklogRecoveryReport:
        candidates = self._scan_candidates(limit=limit, job_id=job_id)
        actions: list[dict[str, Any]] = []
        if dry_run:
            return BacklogRecoveryReport(status="ok", mode=mode, dry_run=True, candidates=candidates, actions=[])
        for candidate in candidates:
            if candidate.classification != "near_publishable":
                continue
            action = self._repair_candidate(candidate)
            actions.append(action)
        return BacklogRecoveryReport(status="ok", mode=mode, dry_run=False, candidates=candidates, actions=actions)

    def _scan_candidates(self, *, limit: int, job_id: str | None = None) -> list[BacklogCandidate]:
        with session_scope() as session:
            query = select(Job).where(Job.status.in_(CANDIDATE_STATUSES)).order_by(Job.updated_at.desc(), Job.created_at.desc()).limit(limit)
            if job_id:
                query = select(Job).where(Job.job_id == job_id)
            jobs = session.scalars(query).all()
            result = [self._classify_job(session, job) for job in jobs]
        return result

    def _classify_job(self, session: Any, job: Job) -> BacklogCandidate:
        reasons: list[str] = []
        allowed_repairs: list[str] = []
        risk = "low"
        active_schedule = session.scalar(
            select(PublicationSchedule.schedule_id)
            .where(PublicationSchedule.job_id == job.job_id)
            .where(PublicationSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES))
        )
        if active_schedule:
            return BacklogCandidate(job.job_id, job.status, "already_scheduled", ["active_schedule_exists"], [], "low", job.job_origin)

        evidence = self._job_evidence(session, job)
        if evidence["duplicate_risk"]:
            return BacklogCandidate(job.job_id, job.status, "needs_checkpoint", ["duplicate_or_already_published_risk"], [], "medium", job.job_origin)
        if any(marker in evidence["text"] for marker in FACTUAL_OR_RIGHTS_MARKERS):
            return BacklogCandidate(job.job_id, job.status, "needs_checkpoint", ["factual_or_rights_risk"], [], "high", job.job_origin)
        if self._failed_same_repair_twice(session, job.job_id):
            return BacklogCandidate(job.job_id, job.status, "not_worth_recovering", ["same_repair_failed_twice"], [], "high", job.job_origin)

        has_render = bool(evidence["render_uri"] and evidence["render_exists"])
        has_publish_package = bool(evidence["publish_package_exists"])
        has_assets = bool(evidence["asset_count"])
        has_audio = bool(evidence["audio_count"])

        if job.status in {JOB_STATUS_APPROVED_FOR_PUBLISH, JOB_STATUS_READY_FOR_UPLOAD} and (has_render or has_publish_package):
            return BacklogCandidate(job.job_id, job.status, "near_publishable", ["already_publishable_path"], ["monetization_readiness_gate"], "low", job.job_origin)

        if job.status == JOB_STATUS_MONETIZATION_REVIEW and has_render:
            allowed_repairs.extend(["monetization_readiness_gate", "derived_audits"])
            reasons.append("rendered_but_waiting_final_gate")

        if job.status == JOB_STATUS_BLOCKED_FOR_MONETIZATION and has_render and any(marker in evidence["text"] for marker in CORRECTABLE_MARKERS):
            allowed_repairs.extend(["metadata", "monetization_readiness_gate", "derived_audits"])
            reasons.append("correctable_gate_or_score_blocker")
            risk = "medium"

        if job.status == "render_quality_failed" and has_assets and has_audio:
            allowed_repairs.append("render")
            reasons.append("render_failed_with_assets_and_audio_present")

        if job.status == "asset_quality_failed" and has_audio:
            allowed_repairs.append("asset_generation")
            reasons.append("asset_problem_with_audio_present")
            risk = "medium"

        if job.status == JOB_STATUS_SUBTITLE_QUALITY_FAILED and has_audio:
            allowed_repairs.append("subtitle_alignment")
            reasons.append("subtitle_problem_with_audio_present")

        if job.status == JOB_STATUS_SCRIPT_QUALITY_FAILED and any(marker in evidence["text"] for marker in ["word_count_too_low", "narration_pace", "weak_ending"]):
            allowed_repairs.append("tts" if has_audio else "script")
            reasons.append("localized_script_or_pacing_issue")
            risk = "medium"

        allowed_repairs = list(dict.fromkeys(allowed_repairs))
        if allowed_repairs:
            return BacklogCandidate(job.job_id, job.status, "near_publishable", reasons or ["correctable_localized_blocker"], allowed_repairs, risk, job.job_origin)

        if not has_render and not has_assets and not has_audio:
            return BacklogCandidate(job.job_id, job.status, "not_worth_recovering", ["no_useful_artifacts"], [], "high", job.job_origin)
        if "full rewrite" in evidence["text"] or "rewrite_from_zero" in evidence["text"]:
            return BacklogCandidate(job.job_id, job.status, "not_worth_recovering", ["requires_full_rewrite"], [], "high", job.job_origin)
        return BacklogCandidate(job.job_id, job.status, "needs_checkpoint", ["uncertain_recovery_value"], [], "medium", job.job_origin)

    def _job_evidence(self, session: Any, job: Job) -> dict[str, Any]:
        render = session.scalar(select(RenderOutput).where(RenderOutput.job_id == job.job_id))
        render_uri = render.video_uri if render else None
        render_exists = _uri_exists(render_uri)
        asset_count = session.scalar(select(func.count()).select_from(SceneAsset).where(SceneAsset.job_id == job.job_id)) or 0
        audio_count = session.scalar(select(func.count()).select_from(NarrationAsset).where(NarrationAsset.job_id == job.job_id)) or 0
        package_path = self.orchestrator.storage.job_dir(job.job_id, create=False) / ARTIFACT_PUBLISH_PACKAGE
        publish_package = bool((job.artifact_index or {}).get("publish_package")) or package_path.exists()
        text = " ".join(
            [
                str(job.failure_reason or ""),
                json.dumps(job.quality_summary or {}, ensure_ascii=False),
                json.dumps(job.artifact_index or {}, ensure_ascii=False),
            ]
        ).lower()
        duplicate_risk = any(marker in text for marker in ["duplicate", "already published", "too similar", "near_duplicate"])
        return {
            "render_uri": render_uri,
            "render_exists": render_exists,
            "asset_count": asset_count,
            "audio_count": audio_count,
            "publish_package_exists": publish_package,
            "text": text,
            "duplicate_risk": duplicate_risk,
        }

    def _failed_same_repair_twice(self, session: Any, job_id: str) -> bool:
        rows = session.execute(
            select(BacklogRecoveryAttempt.repair_kind, func.count())
            .where(BacklogRecoveryAttempt.job_id == job_id)
            .where(BacklogRecoveryAttempt.status == "failed")
            .group_by(BacklogRecoveryAttempt.repair_kind)
        ).all()
        return any(count >= 2 for _, count in rows)

    def _repair_candidate(self, candidate: BacklogCandidate) -> dict[str, Any]:
        repair_kind = candidate.allowed_repairs[0] if candidate.allowed_repairs else "none"
        before_status = candidate.status
        attempt_id = new_id()
        try:
            if repair_kind in {"render", "asset_generation", "tts", "subtitle_alignment"}:
                after_status = self.orchestrator.reprocess_job_from_step(candidate.job_id, repair_kind)
            elif repair_kind in {"monetization_readiness_gate", "derived_audits", "metadata"}:
                after_status = self.orchestrator.reprocess_job_from_step(candidate.job_id, "monetization_readiness_gate")
            else:
                after_status = before_status
            status = "recovered" if after_status in {JOB_STATUS_READY_FOR_UPLOAD, JOB_STATUS_APPROVED_FOR_PUBLISH, JOB_STATUS_MONETIZATION_REVIEW} else "attempted"
            result = {"after_status": after_status}
            error = None
        except Exception as exc:  # noqa: BLE001
            after_status = None
            status = "failed"
            result = None
            error = str(exc)
        self._record_attempt(
            attempt_id=attempt_id,
            candidate=candidate,
            repair_kind=repair_kind,
            before_status=before_status,
            after_status=after_status,
            status=status,
            result=result,
            error=error,
        )
        return {
            "recovery_attempt_id": attempt_id,
            "job_id": candidate.job_id,
            "repair_kind": repair_kind,
            "before_status": before_status,
            "after_status": after_status,
            "status": status,
            "error": error,
        }

    def _record_attempt(
        self,
        *,
        attempt_id: str,
        candidate: BacklogCandidate,
        repair_kind: str,
        before_status: str,
        after_status: str | None,
        status: str,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        with session_scope() as session:
            payload = {
                "job_id": candidate.job_id,
                "repair_kind": repair_kind,
                "before_status": before_status,
                "after_status": after_status,
                "status": status,
                "reasons": candidate.reasons,
                "created_at": utcnow().isoformat(),
            }
            session.add(
                BacklogRecoveryAttempt(
                    recovery_attempt_id=attempt_id,
                    job_id=candidate.job_id,
                    schema_version=str(self.settings.schema_version),
                    content_hash=stable_hash(payload),
                    status=status,
                    repair_kind=repair_kind,
                    before_status=before_status,
                    after_status=after_status,
                    reasons=candidate.reasons,
                    result=result,
                    error=error,
                )
            )


def _uri_exists(uri: str | None) -> bool:
    if not uri:
        return False
    try:
        return Path(path_from_uri(uri)).exists()
    except Exception:  # noqa: BLE001
        return False
