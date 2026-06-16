from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db import session_scope
from app.job_origin import CREATION_VIA_RECREATION, JOB_ORIGIN_UNKNOWN, infer_job_origin_from_notes, normalize_job_origin
from app.models import Job, RenderOutput, ReviewRecord, TopicRequest
from app.pipelines.common import FatalStepError
from app.render_selection import promote_render_output_to_file
from app.utils import iso_now, new_id, path_from_uri, stable_hash, utcnow


class ReviewOperations:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def monetization_pipeline(self) -> Any:
        return self.owner.monetization_pipeline

    @property
    def topic_pipeline(self) -> Any:
        return self.owner.topic_pipeline

    def review_job(self, payload: dict[str, Any], job_id: str) -> str | None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            self.validate_review_action(job, payload["action"])
            review = ReviewRecord(
                review_id=new_id(),
                job_id=job_id,
                schema_version=self.settings.schema_version,
                content_hash=stable_hash(payload),
                created_at=utcnow(),
                reviewer_identity=payload["reviewer_identity"],
                action=payload["action"],
                reason_codes=payload.get("reason_codes", []),
                notes=payload.get("notes"),
                retry_step=None,
            )
            review_id = review.review_id
            session.add(review)
            if payload["action"] == "approve":
                report = self.monetization_pipeline.build_monetization_report(session, job, set(payload.get("reason_codes") or []))
                if not report["passed"]:
                    self.storage.persist_json(job.job_id, "monetization_report.json", self.owner._serialize_for_json(report))
                    quality_summary = dict(job.quality_summary or {})
                    quality_summary["monetization"] = {
                        "passed": report["passed"],
                        "final_status": report["final_status"],
                        "hard_blockers": report["hard_blockers"],
                        "manual_required": report["manual_required"],
                        "warnings": report["warnings"],
                        "content_hash": stable_hash(report),
                    }
                    job.quality_summary = quality_summary
                    job.status = report["final_status"]
                    self.owner._refresh_retention_state(session, job)
                    session.commit()
                    raise FatalStepError(f"monetization readiness incomplete: {', '.join(report['hard_blockers'] + report['manual_required'])}")
                self.storage.persist_json(job.job_id, "monetization_report.json", self.owner._serialize_for_json(report))
                quality_summary = dict(job.quality_summary or {})
                quality_summary["monetization"] = {
                    "passed": report["passed"],
                    "final_status": report["final_status"],
                    "hard_blockers": report["hard_blockers"],
                    "manual_required": report["manual_required"],
                    "warnings": report["warnings"],
                    "content_hash": stable_hash(report),
                }
                job.quality_summary = quality_summary
                gate_result = self.owner._run_premium_publish_gate(
                    session,
                    job,
                    context="review_approve",
                    extra_confirmations=set(payload.get("reason_codes") or []),
                )
                if not gate_result.passed:
                    message = self.owner._block_job_for_premium_publish_gate(job, gate_result)
                    self.owner._refresh_retention_state(session, job)
                    session.commit()
                    raise FatalStepError(message)
                job.status = "approved_for_publish"
                job.review_state = "approved"
                job.failure_reason = None
                self.topic_pipeline.upsert_topic_registry(session, job_id, approved=True)
                self.owner._refresh_retention_state(session, job)
                self.persist_human_review_artifact(job_id, payload, action="approve", review_id=review.review_id)
                self.owner._append_event(job_id, "review.approved", "succeeded", payload)
                return None
            if payload["action"] == "reject":
                job.status = "rejected"
                job.review_state = "rejected"
                self.owner._refresh_retention_state(session, job)
                self.persist_human_review_artifact(job_id, payload, action="reject", review_id=review.review_id)
                self.owner._append_event(job_id, "review.rejected", "succeeded", payload)
                return None
            request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == job_id))
            if not request:
                raise KeyError("missing topic request")
            retry_origin = normalize_job_origin(job.job_origin)
            if retry_origin == JOB_ORIGIN_UNKNOWN:
                retry_origin = infer_job_origin_from_notes(request.notes)
            clone_payload = {
                "seed_theme": request.seed_theme,
                "niche_id": request.niche_id,
                "language": request.language,
                "target_duration_sec": request.target_duration_sec,
                "tone": request.tone or "intrigante_direto",
                "cta_style": request.cta_style or "none",
                "notes": request.notes,
                "requested_angle": request.requested_angle,
                "job_origin": retry_origin,
                "creation_via": CREATION_VIA_RECREATION,
            }
        new_job_id = self.owner.owner.create_job(clone_payload, retry_of_job_id=job_id)
        self.owner._append_event(
            job_id,
            "review.retry_requested",
            "succeeded",
            {"new_job_id": new_job_id, "retry_mode": "full_clone"},
        )
        self.persist_human_review_artifact(
            job_id,
            {**payload, "new_job_id": new_job_id, "retry_mode": "full_clone"},
            action="retry",
            review_id=review_id,
        )
        return new_job_id

    def persist_human_review_artifact(self, job_id: str, payload: dict[str, Any], *, action: str, review_id: str) -> None:
        self.storage.persist_json(
            job_id,
            "human_review.json",
            self.owner._serialize_for_json(
                {
                    "schema_version": self.settings.schema_version,
                    "job_id": job_id,
                    "review_id": review_id,
                    "created_at": iso_now(),
                    "action": action,
                    "reviewer_identity": payload.get("reviewer_identity"),
                    "reason_codes": payload.get("reason_codes", []),
                    "notes": payload.get("notes"),
                    "new_job_id": payload.get("new_job_id"),
                    "retry_mode": payload.get("retry_mode"),
                    "content_hash": stable_hash(payload),
                }
            ),
        )

    def validate_review_action(self, job: Job, action: str) -> None:
        reviewable_statuses = {"monetization_review", "blocked_for_monetization", "ready_for_upload"}
        retryable_statuses = {
            "monetization_review",
            "blocked_for_monetization",
            "rejected",
            "failed",
            "script_quality_failed",
            "scene_plan_quality_failed",
            "asset_quality_failed",
            "subtitle_quality_failed",
            "render_quality_failed",
        }
        rejectable_statuses = reviewable_statuses | retryable_statuses
        if action == "approve" and job.status not in reviewable_statuses:
            raise FatalStepError(f"job status {job.status} cannot be approved")
        if action == "reject" and job.status not in rejectable_statuses:
            raise FatalStepError(f"job status {job.status} cannot be rejected")
        if action == "retry" and job.status not in retryable_statuses:
            raise FatalStepError(f"job status {job.status} cannot be retried")

    def approve_premium_for_publish(
        self,
        job_id: str,
        reviewer_identity: str = "tailscale:local-reviewer",
        *,
        score_override_confirmed: bool = False,
    ) -> None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            self.validate_review_action(job, "approve")
            render = session.scalar(select(RenderOutput).where(RenderOutput.job_id == job_id))
            if not render:
                raise FatalStepError("job nao tem render final para substituir pela versao premium")
            premium_report = self.owner._read_job_json(job_id, "premium_finishing_report.json")
            premium_video_uri = str(premium_report.get("video_uri") or "").strip()
            premium_path = path_from_uri(premium_video_uri) if premium_video_uri else self.storage.job_dir(job_id, create=False) / "render" / "premium.mp4"
            if not premium_path.exists():
                raise FatalStepError("versao premium ainda nao foi gerada")
            if not premium_report or not bool(premium_report.get("passed")):
                raise FatalStepError("versao premium nao passou no gate de acabamento")
            confirmations = {"premium_version_selected", "visual_review_confirmed"}
            if score_override_confirmed:
                confirmations.add("premium_publish_score_accepted")
            payload = {
                "reviewer_identity": reviewer_identity,
                "action": "approve_premium",
                "reason_codes": sorted(confirmations),
                "notes": (
                    "Versao premium selecionada como arquivo final para publicacao; "
                    "score premium abaixo do alvo aceito por revisao humana explicita."
                    if score_override_confirmed
                    else "Versao premium selecionada como arquivo final para publicacao."
                ),
            }
            job_dir = self.storage.job_dir(job_id, create=False)
            artifact_index, original_video_uri = promote_render_output_to_file(
                render,
                selected_video_path=premium_path,
                job_dir=job_dir,
                artifact_index=dict(job.artifact_index or {}),
                selected_render_ref="render/premium.mp4",
                fallback_standard_ref="render/final.mp4",
            )
            job.artifact_index = artifact_index
            report = self.monetization_pipeline.build_monetization_report(session, job, confirmations)
            if not report["passed"]:
                self.storage.persist_json(job.job_id, "monetization_report.json", self.owner._serialize_for_json(report))
                job.status = report["final_status"]
                self.owner._refresh_retention_state(session, job)
                raise FatalStepError(f"monetization readiness incomplete: {', '.join(report['hard_blockers'] + report['manual_required'])}")
            self.storage.persist_json(job.job_id, "monetization_report.json", self.owner._serialize_for_json(report))
            gate_result = self.owner._run_premium_publish_gate(
                session,
                job,
                context="premium_review_approve",
                extra_confirmations=confirmations,
            )
            if not gate_result.passed:
                message = self.owner._block_job_for_premium_publish_gate(job, gate_result)
                self.owner._refresh_retention_state(session, job)
                session.commit()
                raise FatalStepError(message)
            quality_summary = dict(job.quality_summary or {})
            quality_summary["monetization"] = {
                "passed": report["passed"],
                "final_status": report["final_status"],
                "hard_blockers": report["hard_blockers"],
                "manual_required": report["manual_required"],
                "warnings": report["warnings"],
                "content_hash": stable_hash(report),
            }
            quality_summary["selected_render"] = {"variant": "premium", "previous_video_uri": original_video_uri, "video_uri": render.video_uri}
            job.quality_summary = quality_summary
            package = self.monetization_pipeline.build_publish_package(session, job)
            package["selected_render"] = "premium"
            package["standard_video_uri"] = original_video_uri
            self.storage.persist_json(job.job_id, "publish_package.json", self.owner._serialize_for_json(package))
            job.status = "approved_for_publish"
            job.review_state = "approved"
            review = ReviewRecord(
                review_id=new_id(),
                job_id=job_id,
                schema_version=self.settings.schema_version,
                content_hash=stable_hash(payload),
                created_at=utcnow(),
                reviewer_identity=reviewer_identity,
                action="approve_premium",
                reason_codes=payload["reason_codes"],
                notes=payload["notes"],
                retry_step=None,
            )
            session.add(review)
            self.topic_pipeline.upsert_topic_registry(session, job_id, approved=True)
            self.owner._refresh_retention_state(session, job)
            self.persist_human_review_artifact(job_id, payload, action="approve_premium", review_id=review.review_id)
            self.owner._append_event(job_id, "review.premium_approved", "succeeded", {"video_uri": render.video_uri, "previous_video_uri": original_video_uri})
