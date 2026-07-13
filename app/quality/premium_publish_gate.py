from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.models import Job
from app.utils import iso_now, stable_hash
from scripts.audit_system_quality import audit


PREMIUM_PUBLISH_AUDIT_ARTIFACT = "premium_publish_audit.json"


@dataclass(frozen=True)
class PremiumPublishGateResult:
    passed: bool
    score: float
    target_score: float
    reasons: list[str]
    audit: dict[str, Any]
    visual_review_required: bool
    visual_review_confirmed: bool

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "target_score": self.target_score,
            "reasons": self.reasons,
            "visual_review_required": self.visual_review_required,
            "visual_review_confirmed": self.visual_review_confirmed,
            "content_hash": stable_hash(self.audit),
        }


class PremiumPublishGate:
    def __init__(
        self,
        *,
        settings: Any,
        storage: Any,
        audit_func: Callable[[Path], dict[str, Any]] = audit,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.audit_func = audit_func

    def evaluate(
        self,
        job: Job,
        *,
        confirmations: set[str] | None = None,
        visual_review_required: bool = False,
    ) -> PremiumPublishGateResult:
        confirmations = confirmations or set()
        visual_review_confirmed = "visual_review_confirmed" in confirmations
        target_score = 0.0
        root = self.storage.job_dir(job.job_id, create=False)
        audit_payload: dict[str, Any]
        reasons: list[str] = []
        if not root.exists():
            audit_payload = {
                "job_id": job.job_id,
                "target_score": target_score,
                "overall_min_score": 0.0,
                "passed_target": False,
                "stages": [],
            }
            reasons.append("premium_publish_artifacts_missing")
        else:
            try:
                audit_payload = self.audit_func(root)
            except Exception as exc:  # noqa: BLE001
                audit_payload = {
                    "job_id": job.job_id,
                    "target_score": target_score,
                    "overall_min_score": 0.0,
                    "passed_target": False,
                    "stages": [],
                    "error": str(exc),
                }
                reasons.append("premium_publish_audit_failed")
        score = _float(audit_payload.get("overall_min_score"), 0.0)
        target_score = _float(audit_payload.get("target_score"), 0.0)
        # ponytail: audit score is diagnostic; publication blocks only on real review requirements.
        if visual_review_required and not visual_review_confirmed:
            reasons.append("visual_review_required")
        reasons = list(dict.fromkeys(reason for reason in reasons if reason))
        passed = not reasons
        return PremiumPublishGateResult(
            passed=passed,
            score=score,
            target_score=target_score,
            reasons=reasons,
            audit=audit_payload,
            visual_review_required=visual_review_required,
            visual_review_confirmed=visual_review_confirmed,
        )

    def persist(self, job: Job, result: PremiumPublishGateResult, *, context: str) -> dict[str, Any]:
        payload = {
            "schema_version": self.settings.schema_version,
            "job_id": job.job_id,
            "created_at": iso_now(),
            "context": context,
            "status": "passed" if result.passed else "failed",
            "passed": result.passed,
            "score": result.score,
            "target_score": result.target_score,
            "reasons": result.reasons,
            "visual_review_required": result.visual_review_required,
            "visual_review_confirmed": result.visual_review_confirmed,
            "audit": result.audit,
            "content_hash": stable_hash(result.audit),
        }
        self.storage.persist_json(job.job_id, PREMIUM_PUBLISH_AUDIT_ARTIFACT, payload)
        artifact_index = dict(job.artifact_index or {})
        artifact_index["premium_publish_audit"] = PREMIUM_PUBLISH_AUDIT_ARTIFACT
        job.artifact_index = artifact_index
        quality_summary = dict(job.quality_summary or {})
        quality_summary["premium_publish_gate"] = result.summary()
        job.quality_summary = quality_summary
        return payload

def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
