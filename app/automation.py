from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.competitive_scout import CompetitiveScout
from app.db import session_scope
from app.editorial.repetition import build_channel_repetition_report
from app.job_origin import CREATION_VIA_DAILY_CYCLE, JOB_ORIGIN_AUTOMATIC_TOPIC, JOB_ORIGIN_READY_SCRIPT_BANK
from app.manual_script import build_ready_script_notes, normalize_ready_script_text, parse_ready_script
from app.models import (
    AutomationAttempt,
    AutomationRun,
    AutomationSetting,
    Job,
    PublicationSchedule,
    ReadyScriptItem,
    RenderOutput,
    Script,
    SceneAsset,
    TopicRequest,
)
from app.quality.auto_visual_review import AutoVisualReviewService
from app.schemas import TopicRequestCreate
from app.topic_scout import TopicScout
from app.utils import new_id, stable_hash, utcnow


READY_SCRIPT_SPLIT_RE = re.compile(r"(?im)^\s*t[ií]tulo\s*:")
AUTOMATION_ENABLED_KEY = "automation_enabled"
AUTOMATION_SOURCE_READY_SCRIPT = JOB_ORIGIN_READY_SCRIPT_BANK
AUTOMATION_SOURCE_AUTO_TOPIC = JOB_ORIGIN_AUTOMATIC_TOPIC
AUTOMATION_SOURCE_RESUME = "resume_publish"
AUTOMATION_SOURCE_BACKLOG = "publishable_backlog"
ACTIVE_SCHEDULE_STATUSES = {"scheduled", "publishing", "published"}
SECONDARY_AUTOMATION_PUBLISH_TIME = "18:00"
VISUAL_REVIEW_REQUIREMENTS = {"visual_review_required", "asset_visual_review_required"}
TEXTUAL_REPAIR_REASONS = {"unsupported_claim", "invented_source_fact_ids", "off_topic", "weak_ending"}
SCENE_PLAN_REPAIR_REASONS = {"disallowed_split_or_collage_composition"}
SUBTITLE_REPAIR_REASONS = {"p95_timing_drift_too_high", "max_timing_drift_too_high"}
DEFAULT_AUTOMATION_TOPIC_POOL = [
    "Por que o pão fica duro e a bolacha fica mole?",
    "Por que o espelho embaça no banho?",
    "Por que a roupa preta esquenta mais no sol?",
    "Por que sentimos o celular vibrar sem ele vibrar?",
    "Por que o cheiro de chuva aparece antes da chuva?",
    "Por que gelo estala dentro do copo?",
    "Por que algumas músicas grudam na cabeça?",
    "Por que bocejo parece contagioso?",
    "Por que a tela do celular parece pior no sol?",
    "Por que a água gelada sua por fora do copo?",
]


@dataclass(frozen=True)
class ReadyScriptImportResult:
    imported: int
    errors: list[str]


@dataclass(frozen=True)
class PublishSlot:
    local_date: date
    local_time: str
    timezone: str

    @property
    def scheduled_for_local(self) -> str:
        return f"{self.local_date.isoformat()}T{self.local_time}"

    def scheduled_for_utc(self) -> datetime:
        local_tz = ZoneInfo(self.timezone)
        return datetime.fromisoformat(self.scheduled_for_local).replace(tzinfo=local_tz).astimezone(UTC)


@dataclass(frozen=True)
class PublishPlan:
    slot: PublishSlot
    source: str
    fallback_source: str | None = None

    @property
    def sources(self) -> list[str]:
        return list(dict.fromkeys(source for source in [self.source, self.fallback_source] if source))


class AutomationService:
    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator
        self.settings = orchestrator.settings
        self.auto_visual_review = AutoVisualReviewService(orchestrator.storage)

    def automation_enabled(self, session: Session) -> bool:
        row = session.get(AutomationSetting, AUTOMATION_ENABLED_KEY)
        if row is None:
            return bool(self.settings.automation_enabled)
        return bool((row.value or {}).get("enabled"))

    def set_automation_enabled(self, enabled: bool) -> None:
        with session_scope() as session:
            row = session.get(AutomationSetting, AUTOMATION_ENABLED_KEY)
            if row is None:
                row = AutomationSetting(key=AUTOMATION_ENABLED_KEY, value={"enabled": enabled})
                session.add(row)
            else:
                row.value = {"enabled": enabled}

    def import_ready_script_batch(self, raw_text: str, *, fact_check_confirmed: bool, source: str = "batch") -> ReadyScriptImportResult:
        blocks = split_ready_script_batch(raw_text)
        imported = 0
        errors: list[str] = []
        with session_scope() as session:
            for index, block in enumerate(blocks, start=1):
                try:
                    ready_script = parse_ready_script(block, fact_check_confirmed=fact_check_confirmed)
                except ValueError as exc:
                    errors.append(f"bloco {index}: {exc}")
                    continue
                content_hash = stable_hash({"raw_text": ready_script.raw_text, "fact_check_confirmed": fact_check_confirmed})
                existing = session.scalar(select(ReadyScriptItem).where(ReadyScriptItem.content_hash == content_hash))
                if existing:
                    errors.append(f"bloco {index}: roteiro duplicado ignorado")
                    continue
                session.add(
                    ReadyScriptItem(
                        script_item_id=new_id(),
                        schema_version=self.settings.schema_version,
                        content_hash=content_hash,
                        status="available" if fact_check_confirmed else "needs_review",
                        source=source,
                        title=str(ready_script.script["title"]),
                        raw_text=ready_script.raw_text,
                        parsed_script=ready_script.script,
                        hashtags=ready_script.hashtags,
                        fact_check_confirmed=fact_check_confirmed,
                    )
                )
                imported += 1
        return ReadyScriptImportResult(imported=imported, errors=errors)

    def dashboard_context(self) -> dict[str, Any]:
        with session_scope() as session:
            last_run = session.scalar(select(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(1))
            attempts = []
            if last_run:
                attempts = session.scalars(
                    select(AutomationAttempt)
                    .where(AutomationAttempt.run_id == last_run.run_id)
                    .order_by(AutomationAttempt.attempt_number.asc(), AutomationAttempt.created_at.asc())
                ).all()
            metrics = {
                "enabled": self.automation_enabled(session),
                "available_ready_scripts": session.scalar(select(func.count()).select_from(ReadyScriptItem).where(ReadyScriptItem.status == "available")) or 0,
                "needs_review_ready_scripts": session.scalar(select(func.count()).select_from(ReadyScriptItem).where(ReadyScriptItem.status == "needs_review")) or 0,
                "scheduled_ready_scripts": session.scalar(select(func.count()).select_from(ReadyScriptItem).where(ReadyScriptItem.status == "scheduled")) or 0,
            }
            ready_scripts = session.scalars(
                select(ReadyScriptItem).order_by(ReadyScriptItem.created_at.desc(), ReadyScriptItem.title.asc()).limit(50)
            ).all()
            return {
                "metrics": metrics,
                "ready_scripts": [serialize_ready_script_item(item) for item in ready_scripts],
                "last_run": serialize_run(last_run),
                "last_attempts": [serialize_attempt(attempt) for attempt in attempts],
                "settings": {
                    "timezone": self.settings.automation_daily_timezone,
                    "run_time": self.settings.automation_daily_run_time,
                    "publish_time": self.settings.automation_publish_time,
                    "fill_window_days": self.settings.automation_fill_window_days,
                    "max_generation_attempts": self.settings.automation_max_generation_attempts,
                    "score_threshold": self.settings.automation_score_threshold,
                },
            }

    def run_daily_cycle(self, *, force: bool = False) -> dict[str, Any]:
        local_tz = ZoneInfo(self.settings.automation_daily_timezone)
        local_date = datetime.now(local_tz).date().isoformat()
        run = self._acquire_run(local_date, force=force)
        if run.status != "running":
            return serialize_run(run)
        try:
            with session_scope() as session:
                if not self.automation_enabled(session):
                    run = self._finish_run(run.run_id, status="skipped", skipped_reason="automation_disabled")
                    return serialize_run(run)

            scout_result = self._run_competitive_scout_automation()
            self._merge_run_metadata(run.run_id, {"competitive_scout": scout_result})

            preflight = self._youtube_preflight()
            if not preflight["passed"]:
                run = self._finish_run(
                    run.run_id,
                    status="failed",
                    error="; ".join(preflight["missing_items"]),
                    run_metadata={"competitive_scout": scout_result},
                )
                return serialize_run(run)

            target_plan = self._vacant_publish_plan()
            if not target_plan:
                run = self._finish_run(run.run_id, status="skipped", skipped_reason="no_vacant_day")
                return serialize_run(run)
            target_slots = [item.slot for item in target_plan]
            self._set_run_target(run.run_id, target_plan[0].slot.local_date, target_plan[0].slot.scheduled_for_utc())

            scheduled_results: list[dict[str, str]] = []
            backlog_result = self._run_publishable_backlog(run.run_id, target_plan)
            if isinstance(backlog_result, list):
                scheduled_results.extend(backlog_result)
            elif backlog_result:
                return serialize_run(self._get_run(run.run_id))

            scheduled_slot_keys = {str(item.get("scheduled_for_local") or "") for item in scheduled_results}
            remaining_plan = [item for item in target_plan if item.slot.scheduled_for_local not in scheduled_slot_keys]

            generation_attempts = 0
            current_slot_attempts = 0
            while generation_attempts < self.settings.automation_max_generation_attempts:
                if not remaining_plan:
                    break
                plan_item = remaining_plan[0]
                source = self._generation_source_for_attempt(plan_item, current_slot_attempts)
                attempt_result = self._run_generation_attempt(
                    run.run_id,
                    self._next_attempt_number(run.run_id),
                    plan_item.slot,
                    source=source,
                    finish_run=False,
                )
                generation_attempts += 1
                current_slot_attempts += 1
                if attempt_result.get("scheduled"):
                    scheduled_results.append(
                        {
                            "job_id": str(attempt_result.get("job_id") or ""),
                            "schedule_id": str(attempt_result.get("schedule_id") or ""),
                            "scheduled_for_local": plan_item.slot.scheduled_for_local,
                            "source": source,
                        }
                    )
                    remaining_plan = remaining_plan[1:]
                    current_slot_attempts = 0
                    continue
                if attempt_result.get("skip_slot"):
                    if source == plan_item.fallback_source or not plan_item.fallback_source:
                        remaining_plan = remaining_plan[1:]
                        current_slot_attempts = 0
                    continue
                if attempt_result.get("provider_limit"):
                    error = str(attempt_result.get("error") or "provider_limit")
                    if plan_item.fallback_source and source != plan_item.fallback_source:
                        continue
                    if scheduled_results:
                        return serialize_run(self._finish_successful_schedule_run(run.run_id, scheduled_results, target_slots))
                    return serialize_run(
                        self._finish_run(
                            run.run_id,
                            status="failed",
                            error=error,
                            run_metadata=self._automation_failure_metadata(run.run_id, final_reason=error),
                        )
                    )
            if scheduled_results:
                return serialize_run(self._finish_successful_schedule_run(run.run_id, scheduled_results, target_slots))
            return serialize_run(
                self._finish_run(
                    run.run_id,
                    status="failed",
                    error="max_generation_attempts_exhausted",
                    run_metadata=self._automation_failure_metadata(run.run_id, final_reason="max_generation_attempts_exhausted"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return serialize_run(self._finish_run(run.run_id, status="failed", error=str(exc)))

    def _acquire_run(self, local_date: str, *, force: bool) -> AutomationRun:
        with session_scope() as session:
            existing = session.scalar(select(AutomationRun).where(AutomationRun.local_date == local_date))
            now = utcnow()
            if existing:
                started_at = existing.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=UTC)
                stale = existing.status == "running" and started_at < now - timedelta(hours=6)
                incomplete_schedule = existing.status == "succeeded" and (existing.run_metadata or {}).get("schedule_complete") is False
                if not force and existing.status in {"running", "succeeded", "skipped"} and not stale and not incomplete_schedule:
                    return existing
                existing.status = "running"
                existing.started_at = now
                existing.finished_at = None
                existing.error = None
                existing.skipped_reason = None
                existing.attempts_used = 0
                existing.result_job_id = None
                existing.result_schedule_id = None
                existing.run_metadata = {
                    "forced": force,
                    "resumed_stale": stale,
                    "resumed_incomplete_schedule": incomplete_schedule,
                }
                return existing
            run = AutomationRun(
                run_id=new_id(),
                schema_version=self.settings.schema_version,
                content_hash=stable_hash({"local_date": local_date, "created_at": now.isoformat()}),
                local_date=local_date,
                timezone=self.settings.automation_daily_timezone,
                status="running",
                started_at=now,
                run_metadata={"forced": force},
            )
            session.add(run)
            return run

    def _finish_run(
        self,
        run_id: str,
        *,
        status: str,
        skipped_reason: str | None = None,
        error: str | None = None,
        result_job_id: str | None = None,
        result_schedule_id: str | None = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> AutomationRun:
        with session_scope() as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                raise KeyError(run_id)
            run.status = status
            run.finished_at = utcnow()
            run.skipped_reason = skipped_reason
            run.error = error
            if run_metadata:
                merged_metadata = dict(run.run_metadata or {})
                merged_metadata.update(run_metadata)
                run.run_metadata = merged_metadata
            if result_job_id:
                run.result_job_id = result_job_id
            if result_schedule_id:
                run.result_schedule_id = result_schedule_id
            return run

    def _get_run(self, run_id: str) -> AutomationRun:
        with session_scope() as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                raise KeyError(run_id)
            return run

    def _merge_run_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        with session_scope() as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                raise KeyError(run_id)
            run.run_metadata = {**dict(run.run_metadata or {}), **metadata}

    def _set_run_target(self, run_id: str, target_day: date, target_utc: datetime) -> None:
        with session_scope() as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                raise KeyError(run_id)
            run.target_publish_date = target_day.isoformat()
            run.target_publish_at_utc = target_utc

    def _finish_successful_schedule_run(
        self,
        run_id: str,
        scheduled_results: list[dict[str, str]],
        target_slots: list[PublishSlot],
    ) -> AutomationRun:
        last_result = scheduled_results[-1]
        scheduled_slot_keys = {str(item.get("scheduled_for_local") or "") for item in scheduled_results}
        unfilled_slots = [slot.scheduled_for_local for slot in target_slots if slot.scheduled_for_local not in scheduled_slot_keys]
        return self._finish_run(
            run_id,
            status="succeeded",
            result_job_id=last_result.get("job_id") or None,
            result_schedule_id=last_result.get("schedule_id") or None,
            run_metadata={
                "scheduled_count": len(scheduled_results),
                "scheduled_jobs": scheduled_results,
                "vacant_slots_considered": len(target_slots),
                "publish_times": self._automation_publish_times(),
                "schedule_complete": not unfilled_slots,
                "unfilled_slots": unfilled_slots,
                **self._automation_observability_metadata(run_id),
            },
        )

    def _youtube_preflight(self) -> dict[str, Any]:
        missing_items: list[str] = []
        if not self.settings.youtube_api_enabled:
            missing_items.append("YTS_YOUTUBE_API_ENABLED=false")
        if self.settings.youtube_publish_mode != "api":
            missing_items.append("YTS_YOUTUBE_PUBLISH_MODE != api")
        if not self.settings.youtube_channel_id:
            missing_items.append("YTS_YOUTUBE_CHANNEL_ID ausente")
        redirect_uri = self.settings.youtube_oauth_redirect_uri or f"{self.settings.app_url.rstrip('/')}/youtube/oauth/callback"
        status = self.orchestrator.youtube.connection_status(redirect_uri)
        missing_items.extend(item for item in status.missing_items if item not in missing_items)
        return {"passed": not missing_items and status.connected, "missing_items": missing_items, "connected": status.connected}

    def _automation_publish_times(self) -> list[str]:
        times: list[str] = []
        for raw_time in [self.settings.automation_publish_time, SECONDARY_AUTOMATION_PUBLISH_TIME]:
            parsed = datetime.strptime(str(raw_time), "%H:%M")
            normalized = parsed.strftime("%H:%M")
            if normalized not in times:
                times.append(normalized)
        return times

    def _automation_publish_source_for_time(self, publish_time: str) -> str:
        primary_time = datetime.strptime(str(self.settings.automation_publish_time), "%H:%M").strftime("%H:%M")
        secondary_time = datetime.strptime(SECONDARY_AUTOMATION_PUBLISH_TIME, "%H:%M").strftime("%H:%M")
        if publish_time == secondary_time:
            return AUTOMATION_SOURCE_AUTO_TOPIC
        if publish_time == primary_time:
            return AUTOMATION_SOURCE_READY_SCRIPT
        return AUTOMATION_SOURCE_AUTO_TOPIC

    def _automation_fallback_source_for_time(self, publish_time: str) -> str | None:
        secondary_time = datetime.strptime(SECONDARY_AUTOMATION_PUBLISH_TIME, "%H:%M").strftime("%H:%M")
        return AUTOMATION_SOURCE_READY_SCRIPT if publish_time == secondary_time else None

    def _generation_source_for_attempt(
        self,
        plan_item: PublishPlan,
        current_slot_attempts: int,
    ) -> str:
        if not plan_item.fallback_source:
            return plan_item.source
        if current_slot_attempts > 0:
            return plan_item.fallback_source
        return plan_item.source

    def _vacant_publish_slots(self) -> list[PublishSlot]:
        local_tz = ZoneInfo(self.settings.automation_daily_timezone)
        today = datetime.now(local_tz).date()
        with session_scope() as session:
            rows = session.scalars(select(PublicationSchedule).where(PublicationSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES))).all()
        occupied = set()
        for schedule in rows:
            scheduled_at = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
            local_dt = scheduled_at.astimezone(local_tz)
            occupied.add((local_dt.date(), local_dt.strftime("%H:%M")))
        slots: list[PublishSlot] = []
        for offset in range(1, self.settings.automation_fill_window_days + 1):
            for publish_time in self._automation_publish_times():
                candidate = today + timedelta(days=offset)
                if (candidate, publish_time) not in occupied:
                    slots.append(PublishSlot(local_date=candidate, local_time=publish_time, timezone=self.settings.automation_daily_timezone))
        return slots

    def _vacant_publish_plan(self) -> list[PublishPlan]:
        slots = self._vacant_publish_slots()
        if not slots:
            return []
        first_incomplete_date = slots[0].local_date
        return [
            PublishPlan(
                slot=slot,
                source=self._automation_publish_source_for_time(slot.local_time),
                fallback_source=self._automation_fallback_source_for_time(slot.local_time),
            )
            for slot in slots
            if slot.local_date == first_incomplete_date
        ]

    def _first_vacant_day(self) -> date | None:
        slot = next(iter(self._vacant_publish_slots()), None)
        return slot.local_date if slot else None

    def _resume_publishable_job(self, run_id: str, target_day: date) -> bool:
        with session_scope() as session:
            rows = session.scalars(
                select(AutomationAttempt)
                .where(AutomationAttempt.status == "publish_failed")
                .where(AutomationAttempt.job_id.is_not(None))
                .order_by(AutomationAttempt.updated_at.desc())
                .limit(10)
            ).all()
            for row in rows:
                failures = session.scalar(
                    select(func.count())
                    .select_from(AutomationAttempt)
                    .where(AutomationAttempt.job_id == row.job_id)
                    .where(AutomationAttempt.status == "publish_failed")
                ) or 0
                if failures < self.settings.automation_max_publish_attempts_per_job:
                    job_id = str(row.job_id)
                    break
            else:
                return False
        attempt = self._create_attempt(run_id, 1, AUTOMATION_SOURCE_RESUME, job_id=job_id)
        try:
            schedule_id = self._approve_and_schedule(job_id, target_day)
        except Exception as exc:  # noqa: BLE001
            self._finish_attempt(attempt.attempt_id, status="publish_failed", error=str(exc))
            self._finish_run(run_id, status="failed", error=str(exc), result_job_id=job_id)
            return True
        self._finish_attempt(attempt.attempt_id, status="scheduled")
        self._finish_run(run_id, status="succeeded", result_job_id=job_id, result_schedule_id=schedule_id)
        return True

    def _run_publishable_backlog(self, run_id: str, target_slots: list[PublishPlan] | list[PublishSlot] | date) -> list[dict[str, str]]:
        plan = self._coerce_publish_plan(target_slots)
        if not plan:
            return []
        candidates = self._publishable_backlog_candidates()
        scheduled_results: list[dict[str, str]] = []
        used_job_ids: set[str] = set()
        for plan_item in plan:
            target_slot = plan_item.slot
            slot_scheduled = False
            for source in plan_item.sources:
                for candidate in candidates:
                    if str(candidate["job_id"]) in used_job_ids or not self._backlog_candidate_matches_source(candidate, source):
                        continue
                    job_id = candidate["job_id"]
                    used_job_ids.add(str(job_id))
                    classification = candidate["classification"]
                    attempt = self._create_attempt(run_id, self._next_attempt_number(run_id), AUTOMATION_SOURCE_BACKLOG, job_id=job_id)
                    self._merge_attempt_report(
                        attempt.attempt_id,
                        {
                            **classification,
                            "slot": {
                                "scheduled_for_local": target_slot.scheduled_for_local,
                                "timezone": target_slot.timezone,
                                "source": source,
                            },
                            "candidate": {
                                "status_before": candidate["status"],
                                "job_origin": candidate.get("job_origin"),
                            },
                            "decision": "evaluating_backlog_candidate",
                        },
                    )
                    try:
                        status = candidate["status"]
                        confirmation_codes: list[str] = []
                        if status == "monetization_review":
                            before_report = self._monetization_report_for_job_id(job_id)
                            self._merge_attempt_report(attempt.attempt_id, {"monetization_before": self._automation_report_summary(before_report)})
                            visual_result = self._run_auto_visual_review(job_id)
                            self._merge_attempt_report(attempt.attempt_id, {"visual_review": visual_result})
                            if not visual_result["passed"]:
                                self._merge_attempt_report(
                                    attempt.attempt_id,
                                    {"decision": "skip_visual_review_failed", "eligible_after_visual_review": False},
                                )
                                self._finish_attempt(
                                    attempt.attempt_id,
                                    status="not_eligible",
                                    error="automatic_visual_review_failed: " + ", ".join(visual_result["reasons"]),
                                )
                                continue
                            refreshed_report = self._refresh_monetization_after_visual_review(job_id)
                            refreshed_summary = self._automation_report_summary(refreshed_report)
                            self._merge_attempt_report(
                                attempt.attempt_id,
                                {
                                    "monetization_after": refreshed_summary,
                                    "eligible_after_visual_review": refreshed_summary["final_status"] == "ready_for_upload",
                                },
                            )
                            status = self._job_status(job_id)
                            confirmation_codes.append("visual_review_confirmed")

                        if status == "ready_for_upload":
                            self._merge_attempt_report(attempt.attempt_id, {"decision": "score_autoapproval"})
                            score_report = self.evaluate_autoapproval(job_id)
                            self._set_attempt_score(attempt.attempt_id, score_report)
                            if not score_report["eligible"]:
                                self._merge_attempt_report(
                                    attempt.attempt_id,
                                    {"decision": "skip_score_failed", "eligible_after_visual_review": False},
                                )
                                self._finish_attempt(
                                    attempt.attempt_id,
                                    status="score_failed",
                                    error=self._automation_score_error(AUTOMATION_SOURCE_BACKLOG, score_report["reasons"]),
                                )
                                continue
                        elif status != "approved_for_publish":
                            current_report = self._monetization_report_for_job_id(job_id)
                            self._merge_attempt_report(
                                attempt.attempt_id,
                                {
                                    "decision": "skip_remaining_blockers",
                                    "eligible_after_visual_review": False,
                                    "monetization_after": self._automation_report_summary(current_report),
                                },
                            )
                            self._finish_attempt(attempt.attempt_id, status="not_eligible", error=f"job_status={status}")
                            continue

                        self._merge_attempt_report(attempt.attempt_id, {"decision": "schedule_candidate"})
                        schedule_id = self._approve_and_schedule(job_id, target_slot, confirmation_codes=confirmation_codes)
                    except Exception as exc:  # noqa: BLE001
                        self._merge_attempt_report(attempt.attempt_id, {"decision": "publish_attempt_failed"})
                        self._finish_attempt(attempt.attempt_id, status="publish_failed", error=str(exc))
                        continue
                    self._finish_attempt(attempt.attempt_id, status="scheduled")
                    scheduled_results.append(
                        {
                            "job_id": job_id,
                            "schedule_id": schedule_id,
                            "scheduled_for_local": target_slot.scheduled_for_local,
                            "source": str(candidate.get("job_origin") or source),
                        }
                    )
                    slot_scheduled = True
                    break
                if slot_scheduled:
                    break
        return scheduled_results

    def _backlog_candidate_matches_source(self, candidate: dict[str, Any], source: str) -> bool:
        return str(candidate.get("job_origin") or "") == source

    def _publishable_backlog_candidates(self) -> list[dict[str, Any]]:
        with session_scope() as session:
            jobs = session.scalars(
                select(Job)
                .where(Job.status.in_(["monetization_review", "ready_for_upload", "approved_for_publish"]))
                .order_by(Job.updated_at.desc(), Job.created_at.desc())
                .limit(25)
            ).all()
            candidates: list[dict[str, Any]] = []
            for job in jobs:
                active_schedule = session.scalar(
                    select(PublicationSchedule.schedule_id)
                    .where(PublicationSchedule.job_id == job.job_id)
                    .where(PublicationSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES))
                )
                render_exists = session.scalar(select(RenderOutput.render_id).where(RenderOutput.job_id == job.job_id))
                package_exists = bool((job.artifact_index or {}).get("publish_package")) or (
                    self.orchestrator.storage.job_dir(job.job_id, create=False) / "publish_package.json"
                ).exists()
                if active_schedule or not render_exists or not package_exists:
                    continue

                report = self._monetization_report(job)
                classification = self.classify_failure(job.status, job.failure_reason, report)
                if job.status == "approved_for_publish":
                    candidates.append({"job_id": job.job_id, "status": job.status, "job_origin": job.job_origin, "classification": classification})
                    continue
                if job.status == "ready_for_upload":
                    if not report.get("hard_blockers"):
                        candidates.append({"job_id": job.job_id, "status": job.status, "job_origin": job.job_origin, "classification": classification})
                    continue
                if self._visual_review_can_be_attempted(report):
                    candidates.append({"job_id": job.job_id, "status": job.status, "job_origin": job.job_origin, "classification": classification})
            return candidates

    def _visual_review_can_be_attempted(self, report: dict[str, Any]) -> bool:
        """Return True when local vision can remove visual-review debt safely.

        This is intentionally broader than publish eligibility: a job may also need
        fact/metadata/publish-audit review, but we should still run the automated
        vision check and rebuild monetization so the visual blocker does not stay
        stale in backlog. Scheduling still requires the refreshed report to reach
        ready_for_upload.
        """
        manual_required = {str(item) for item in report.get("manual_required") or []}
        return not report.get("hard_blockers") and bool(manual_required & VISUAL_REVIEW_REQUIREMENTS)

    def _only_safe_visual_review_remains(self, report: dict[str, Any]) -> bool:
        manual_required = {str(item) for item in report.get("manual_required") or []}
        return self._visual_review_can_be_attempted(report) and manual_required.issubset(VISUAL_REVIEW_REQUIREMENTS)

    def _run_auto_visual_review(self, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            return self.auto_visual_review.review(session, job)

    def _refresh_monetization_after_visual_review(self, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            report = self.orchestrator.monetization_pipeline.build_monetization_report(
                session,
                job,
                {"visual_review_confirmed"},
            )
            self.orchestrator.storage.persist_json(
                job_id,
                "monetization_report.json",
                self.orchestrator._serialize_for_json(report),
            )
            quality_summary = dict(job.quality_summary or {})
            quality_summary["monetization"] = {
                "passed": report["passed"],
                "final_status": report["final_status"],
                "hard_blockers": report["hard_blockers"],
                "manual_required": report["manual_required"],
                "warnings": report.get("warnings", []),
                "content_hash": stable_hash(report),
            }
            job.quality_summary = quality_summary
            job.status = str(report["final_status"])
            return report

    def _run_generation_attempt(
        self,
        run_id: str,
        attempt_number: int,
        target_slot: PublishSlot | date,
        *,
        source: str | None = None,
        finish_run: bool = True,
    ) -> dict[str, Any]:
        selected_script = None if source == AUTOMATION_SOURCE_AUTO_TOPIC else self._select_ready_script_item()
        source = source or (AUTOMATION_SOURCE_READY_SCRIPT if selected_script else AUTOMATION_SOURCE_AUTO_TOPIC)
        if source not in {AUTOMATION_SOURCE_READY_SCRIPT, AUTOMATION_SOURCE_AUTO_TOPIC}:
            raise ValueError(f"automation_source_not_supported={source}")
        attempt = self._create_attempt(run_id, attempt_number, source, ready_script_item_id=selected_script.script_item_id if selected_script else None)
        if source == AUTOMATION_SOURCE_READY_SCRIPT and not selected_script:
            error = "Banco de roteiros: não há roteiro disponível para o slot diário."
            self._finish_attempt(attempt.attempt_id, status="not_eligible", error=error)
            return {"scheduled": False, "skip_slot": True, "error": error}
        job_id: str | None = None
        try:
            payload = self._job_payload_from_ready_script(selected_script) if selected_script else self._automatic_topic_payload()
            job_id = self.orchestrator.create_job(payload)
            self._attach_job_to_attempt(attempt.attempt_id, job_id)
            retention_experiment_assignment = self._attach_job_to_active_retention_experiment(job_id) if source == AUTOMATION_SOURCE_AUTO_TOPIC else None
            if retention_experiment_assignment:
                self._merge_attempt_report(attempt.attempt_id, {"retention_experiment": retention_experiment_assignment})
            if selected_script:
                self._mark_ready_script_in_progress(selected_script.script_item_id)
            status = self.orchestrator.process_job(job_id)
            classification = self._classify_job_failure(job_id, status)
            retry_report = {"attempted": False}
            if classification.get("retry_from_step"):
                retry_report = {
                    "attempted": True,
                    "from_step": classification["retry_from_step"],
                    "initial_status": status,
                }
                status = self.orchestrator.reprocess_job_from_step(job_id, classification["retry_from_step"])
                retry_report["result_status"] = status
                classification = self._classify_job_failure(job_id, status)
            self._merge_attempt_report(
                attempt.attempt_id,
                {
                    **classification,
                    "retry": retry_report,
                },
            )
            if status == "monetization_review" and classification["classification"] in {
                "visual_review_repairable",
                "visual_review_partial_repairable",
            }:
                visual_result = self._run_auto_visual_review(job_id)
                self._merge_attempt_report(attempt.attempt_id, {"visual_review": visual_result})
                if visual_result["passed"]:
                    self._refresh_monetization_after_visual_review(job_id)
                    status = self._job_status(job_id)
            if status != "ready_for_upload":
                error = self._automation_attempt_error(job_id, status, source)
                self._finish_attempt(attempt.attempt_id, status="not_eligible", error=error)
                if selected_script:
                    self._finalize_ready_script_failure(selected_script.script_item_id, classification, error)
                return {"scheduled": False, "provider_limit": self._is_provider_limit_error(error), "error": error}
            score_report = self.evaluate_autoapproval(job_id)
            self._set_attempt_score(attempt.attempt_id, score_report)
            if not score_report["eligible"]:
                error = self._automation_score_error(source, score_report["reasons"])
                self._finish_attempt(attempt.attempt_id, status="score_failed", error=error)
                if selected_script:
                    self._finalize_ready_script_failure(
                        selected_script.script_item_id,
                        {"classification": "editorial_review_required"},
                        error,
                    )
                return {"scheduled": False}
            confirmation_codes: list[str] = []
            if status == "ready_for_upload" and classification["classification"] in {
                "visual_review_repairable",
                "visual_review_partial_repairable",
            }:
                confirmation_codes.append("visual_review_confirmed")
            schedule_id = self._approve_and_schedule(job_id, target_slot, confirmation_codes=confirmation_codes)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            self._finish_attempt(attempt.attempt_id, status="failed", error=error)
            if selected_script:
                self._finalize_ready_script_failure(
                    selected_script.script_item_id,
                    {"classification": "technical_retry_pending"},
                    error,
                )
            return {"scheduled": False, "provider_limit": self._is_provider_limit_error(error), "error": error}
        self._finish_attempt(attempt.attempt_id, status="scheduled")
        if selected_script:
            self._mark_ready_script_scheduled(selected_script.script_item_id, job_id)
        if finish_run:
            self._finish_run(run_id, status="succeeded", result_job_id=job_id, result_schedule_id=schedule_id)
        return {"scheduled": True, "job_id": job_id, "schedule_id": schedule_id}

    def _job_status_error(self, job_id: str, status: str) -> str:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job and job.failure_reason:
                return f"job_status={status}; {job.failure_reason}"
        return f"job_status={status}"

    def _automation_attempt_error(self, job_id: str, status: str, source: str) -> str:
        base_error = self._job_status_error(job_id, status)
        if source == AUTOMATION_SOURCE_READY_SCRIPT:
            return (
                "Banco de roteiros: roteiro validado pelo usuário. Não houve publish porque o job "
                f"não ficou tecnicamente publicável ({base_error})"
            )
        return f"Tema automático: bloqueado antes do publish ({base_error})"

    def _automation_score_error(self, source: str, reasons: list[str]) -> str:
        base_error = "; ".join(reasons) or "autoapproval_score_failed"
        if source == AUTOMATION_SOURCE_READY_SCRIPT:
            return (
                "Banco de roteiros: score registrado como diagnóstico. Não houve publish porque "
                f"restaram bloqueios técnicos ({base_error})"
            )
        return f"Tema automático: bloqueado antes do publish pelo score de autoaprovação ({base_error})"

    def _monetization_report(self, job: Job) -> dict[str, Any]:
        report = self.orchestrator._read_job_json(job.job_id, "monetization_report.json") or {}
        if report:
            return report
        summary = dict((job.quality_summary or {}).get("monetization") or {})
        return {
            "passed": summary.get("passed"),
            "final_status": summary.get("final_status"),
            "hard_blockers": list(summary.get("hard_blockers") or []),
            "manual_required": list(summary.get("manual_required") or []),
            "publish_readiness": dict(summary.get("publish_readiness") or {}),
        }

    def _monetization_report_for_job_id(self, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            return self._monetization_report(job)

    def _automation_report_summary(self, report: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": bool(report.get("passed")),
            "final_status": report.get("final_status"),
            "hard_blockers": [str(item) for item in report.get("hard_blockers") or []],
            "manual_required": [str(item) for item in report.get("manual_required") or []],
            "publish_readiness_reasons": [
                str(item)
                for item in (report.get("publish_readiness") or {}).get("reasons")
                or []
            ],
        }

    def _classify_job_failure(self, job_id: str, status: str) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            return self.classify_failure(status, job.failure_reason, self._monetization_report(job))

    def classify_failure(
        self,
        status: str,
        failure_reason: str | None,
        monetization_report: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = " ".join(
            [
                str(failure_reason or ""),
                " ".join(str(item) for item in monetization_report.get("hard_blockers") or []),
                " ".join(str(item) for item in monetization_report.get("manual_required") or []),
                " ".join(str(item) for item in (monetization_report.get("publish_readiness") or {}).get("reasons") or []),
            ]
        ).lower()
        matched_reasons: list[str] = []
        for reason in sorted(TEXTUAL_REPAIR_REASONS | SCENE_PLAN_REPAIR_REASONS | SUBTITLE_REPAIR_REASONS):
            if reason in evidence:
                matched_reasons.append(reason)

        hard_blockers = [str(item) for item in monetization_report.get("hard_blockers") or []]
        if status == "blocked_for_monetization" or hard_blockers:
            return {
                "classification": "hard_blocker",
                "matched_reasons": matched_reasons or hard_blockers,
                "retry_from_step": None,
            }
        if status == "monetization_review" and self._visual_review_can_be_attempted(monetization_report):
            manual_required = {str(item) for item in monetization_report.get("manual_required") or []}
            return {
                "classification": "visual_review_repairable"
                if manual_required.issubset(VISUAL_REVIEW_REQUIREMENTS)
                else "visual_review_partial_repairable",
                "matched_reasons": list(monetization_report.get("manual_required") or []),
                "retry_from_step": None,
            }
        if status == "script_quality_failed" and any(reason in TEXTUAL_REPAIR_REASONS for reason in matched_reasons):
            return {
                "classification": "textual_repairable",
                "matched_reasons": matched_reasons,
                "retry_from_step": "script",
            }
        if status == "scene_plan_quality_failed" and any(reason in SCENE_PLAN_REPAIR_REASONS for reason in matched_reasons):
            return {
                "classification": "scene_plan_repairable",
                "matched_reasons": matched_reasons,
                "retry_from_step": "scene_plan",
            }
        if status == "subtitle_quality_failed" and any(reason in SUBTITLE_REPAIR_REASONS for reason in matched_reasons):
            return {
                "classification": "subtitle_repairable",
                "matched_reasons": matched_reasons,
                "retry_from_step": "subtitle_alignment",
            }
        if status in {"ready_for_upload", "approved_for_publish"}:
            return {"classification": "publishable", "matched_reasons": [], "retry_from_step": None}
        return {"classification": "unclassified_failure", "matched_reasons": matched_reasons, "retry_from_step": None}

    def _automation_failure_metadata(self, run_id: str, *, final_reason: str) -> dict[str, Any]:
        observability = self._automation_observability_metadata(run_id)
        return {
            "final_reason": final_reason,
            **observability,
            "ready_script_publish_policy": (
                "Roteiros do banco preservam a aprovação humana do texto. Editorial, factualidade, metadados, "
                "retenção narrativa, similaridade e score viram diagnóstico; publicação automática só pode parar "
                "por bloqueios técnicos, visuais, direitos, disclosure, duração, áudio, render ou YouTube."
            ),
        }

    def _automation_observability_metadata(self, run_id: str) -> dict[str, Any]:
        with session_scope() as session:
            attempts = session.scalars(
                select(AutomationAttempt)
                .where(AutomationAttempt.run_id == run_id)
                .order_by(AutomationAttempt.attempt_number.asc(), AutomationAttempt.created_at.asc())
            ).all()
            partial_repairs = []
            for attempt in attempts:
                report = dict(attempt.score_report or {})
                visual_review = dict(report.get("visual_review") or {})
                monetization_after = dict(report.get("monetization_after") or {})
                if report.get("classification") != "visual_review_partial_repairable" or not visual_review.get("passed"):
                    continue
                partial_repairs.append(
                    {
                        "attempt_number": attempt.attempt_number,
                        "source": attempt.source,
                        "source_label": self._automation_source_label(attempt.source),
                        "job_id": attempt.job_id,
                        "status": attempt.status,
                        "reason": attempt.error or "Revisão visual automática aprovada, mas ainda há bloqueios manuais.",
                        "decision": report.get("decision"),
                        "remaining_manual_required": list(monetization_after.get("manual_required") or []),
                        "remaining_hard_blockers": list(monetization_after.get("hard_blockers") or []),
                        "scheduled_for_local": (report.get("slot") or {}).get("scheduled_for_local"),
                    }
                )
            blockers = [
                {
                    "attempt_number": attempt.attempt_number,
                    "source": attempt.source,
                    "source_label": self._automation_source_label(attempt.source),
                    "job_id": attempt.job_id,
                    "status": attempt.status,
                    "reason": attempt.error,
                }
                for attempt in attempts
                if attempt.status not in {"scheduled"} or attempt.error
            ]
        partial_attempt_numbers = {repair["attempt_number"] for repair in partial_repairs}
        notifications = [
            {
                "kind": "partial_repair",
                "title": "Candidato reparado parcialmente",
                **repair,
            }
            for repair in partial_repairs
        ]
        notifications.extend(
            {
                "kind": "publish_blocker",
                "title": "Candidato não agendado",
                **blocker,
            }
            for blocker in blockers
            if blocker.get("reason") and blocker.get("attempt_number") not in partial_attempt_numbers
        )
        return {
            "publish_blockers": blockers,
            "partial_repairs": partial_repairs,
            "automation_notifications": notifications[:10],
        }

    def _automation_source_label(self, source: str | None) -> str:
        if source == AUTOMATION_SOURCE_READY_SCRIPT:
            return "Banco de roteiros"
        if source == AUTOMATION_SOURCE_BACKLOG:
            return "Backlog"
        if source == AUTOMATION_SOURCE_RESUME:
            return "Retomada de publish"
        return "Tema automático"

    def _is_provider_limit_error(self, message: str) -> bool:
        normalized = message.lower()
        return any(
            marker in normalized
            for marker in [
                "provider limit",
                "usage limit",
                "quota",
                "rate limit",
                "too many requests",
                "insufficient",
                "balance",
                "credit",
            ]
        )

    def _create_attempt(
        self,
        run_id: str,
        attempt_number: int,
        source: str,
        *,
        ready_script_item_id: str | None = None,
        job_id: str | None = None,
    ) -> AutomationAttempt:
        with session_scope() as session:
            attempt = AutomationAttempt(
                attempt_id=new_id(),
                run_id=run_id,
                schema_version=self.settings.schema_version,
                content_hash=stable_hash({"run_id": run_id, "attempt_number": attempt_number, "source": source, "created_at": utcnow().isoformat()}),
                attempt_number=attempt_number,
                source=source,
                status="running",
                ready_script_item_id=ready_script_item_id,
                job_id=job_id,
            )
            session.add(attempt)
            run = session.get(AutomationRun, run_id)
            if run:
                run.attempts_used = max(run.attempts_used or 0, attempt_number)
            return attempt

    def _next_attempt_number(self, run_id: str) -> int:
        with session_scope() as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                raise KeyError(run_id)
            return int(run.attempts_used or 0) + 1

    def _attach_job_to_attempt(self, attempt_id: str, job_id: str) -> None:
        with session_scope() as session:
            attempt = session.get(AutomationAttempt, attempt_id)
            if attempt:
                attempt.job_id = job_id

    def _set_attempt_score(self, attempt_id: str, score_report: dict[str, Any]) -> None:
        with session_scope() as session:
            attempt = session.get(AutomationAttempt, attempt_id)
            if attempt:
                attempt.score = float(score_report.get("score") or 0.0)
                merged_report = dict(attempt.score_report or {})
                merged_report.update(score_report)
                attempt.score_report = merged_report

    def _merge_attempt_report(self, attempt_id: str, metadata: dict[str, Any]) -> None:
        with session_scope() as session:
            attempt = session.get(AutomationAttempt, attempt_id)
            if attempt:
                report = dict(attempt.score_report or {})
                report.update(metadata)
                attempt.score_report = report

    def _finish_attempt(self, attempt_id: str, *, status: str, error: str | None = None) -> AutomationAttempt:
        with session_scope() as session:
            attempt = session.get(AutomationAttempt, attempt_id)
            if not attempt:
                raise KeyError(attempt_id)
            attempt.status = status
            attempt.error = error
            attempt.finished_at = utcnow()
            return attempt

    def _select_ready_script_item(self) -> ReadyScriptItem | None:
        with session_scope() as session:
            items = session.scalars(select(ReadyScriptItem).where(ReadyScriptItem.status == "available")).all()
            random.shuffle(items)
            for item in items:
                report = self._ready_script_repetition_report(session, item)
                if report.get("repetition_risk") == "high":
                    item.last_skip_reason = "high_narrative_similarity_warning"
                    item.last_similarity_score = float(report.get("max_similarity") or 0.0)
                    return item
                item.last_skip_reason = None
                item.last_similarity_score = None
                return item
        return None

    def _ready_script_repetition_report(self, session: Session, item: ReadyScriptItem) -> dict[str, Any]:
        rows = session.execute(
            select(Job.job_id, Job.topic_summary, Script.title, Script.hook, Script.ending, Script.estimated_duration_sec, Script.body_beats)
            .join(Script, Script.job_id == Job.job_id)
            .join(PublicationSchedule, PublicationSchedule.job_id == Job.job_id, isouter=True)
            .where(or_(PublicationSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES), Job.status.in_(["approved_for_publish", "published"])))
            .order_by(Job.created_at.desc())
            .limit(30)
        ).all()
        recent_rows = [
            {
                "job_id": job_id,
                "topic_summary": topic_summary,
                "title": title,
                "hook": hook,
                "ending": ending,
                "estimated_duration_sec": estimated_duration_sec,
                "body_beats": body_beats,
            }
            for job_id, topic_summary, title, hook, ending, estimated_duration_sec, body_beats in rows
        ]
        return build_channel_repetition_report(
            current={
                "canonical_topic": item.title,
                "angle": "roteiro pronto",
                "script": item.parsed_script,
            },
            recent_rows=recent_rows,
        )

    def _mark_ready_script_in_progress(self, script_item_id: str) -> None:
        with session_scope() as session:
            item = session.get(ReadyScriptItem, script_item_id)
            if item:
                item.status = "in_progress"
                # Preserve diagnostic selection notes such as high narrative similarity.
                # The final lifecycle transition decides whether the script was scheduled,
                # released for retry, or needs human review.

    def _mark_ready_script_needs_review(self, script_item_id: str) -> None:
        with session_scope() as session:
            item = session.get(ReadyScriptItem, script_item_id)
            if item and item.status != "scheduled":
                item.status = "needs_review"

    def _finalize_ready_script_failure(
        self,
        script_item_id: str,
        classification: dict[str, Any],
        error: str,
    ) -> None:
        failure_class = str(classification.get("classification") or "unclassified_failure")
        with session_scope() as session:
            item = session.get(ReadyScriptItem, script_item_id)
            if not item or item.status == "scheduled":
                return
            if failure_class in {"hard_blocker", "textual_repairable", "editorial_review_required"}:
                item.status = "needs_review"
            else:
                item.status = "available"
            item.last_skip_reason = failure_class
            item.consumed_job_id = None
            item.consumed_at = None

    def _mark_ready_script_scheduled(self, script_item_id: str, job_id: str) -> None:
        with session_scope() as session:
            item = session.get(ReadyScriptItem, script_item_id)
            if item:
                item.status = "scheduled"
                item.consumed_job_id = job_id
                item.consumed_at = utcnow()

    def _job_payload_from_ready_script(self, item: ReadyScriptItem) -> dict[str, Any]:
        return TopicRequestCreate(
            seed_theme=item.title,
            niche_id=self.settings.niche_id,
            language=self.settings.language,
            target_duration_sec=self.settings.target_duration_sec,
            tone="intrigante_direto",
            cta_style="none",
            notes=build_ready_script_notes(None, item.raw_text, item.fact_check_confirmed),
            requested_angle=None,
            job_origin=JOB_ORIGIN_READY_SCRIPT_BANK,
            creation_via=CREATION_VIA_DAILY_CYCLE,
        ).model_dump()

    def _run_competitive_scout_automation(self) -> dict[str, Any]:
        try:
            return CompetitiveScout(settings=self.settings).run_automation_cycle(niche_id=self.settings.niche_id)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "reason": str(exc)}

    def _attach_job_to_active_retention_experiment(self, job_id: str) -> dict[str, Any] | None:
        try:
            return CompetitiveScout(settings=self.settings).attach_job_to_active_experiment(job_id, niche_id=self.settings.niche_id)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "reason": str(exc)}

    def _active_retention_guidance_notes(self) -> str | None:
        try:
            guidance = CompetitiveScout(settings=self.settings).active_retention_guidance(niche_id=self.settings.niche_id)
        except Exception:
            return None
        if not guidance:
            return None
        text = str(guidance.get("guidance_text") or "").strip()
        if not text:
            return None
        return (
            "Aprendizado competitivo ativo no ciclo diario. Use como diretriz estrutural de retencao, "
            "sem copiar palavras, roteiro literal ou exemplos de Shorts de referencia.\n"
            f"{text}"
        )

    def _automatic_topic_payload(self) -> dict[str, Any]:
        with session_scope() as session:
            recent_topics = session.scalars(
                select(TopicRequest.seed_theme)
                .where(TopicRequest.niche_id == self.settings.niche_id)
                .order_by(TopicRequest.created_at.desc())
                .limit(40)
            ).all()
        scout_result = TopicScout().find_topic(self.settings.niche_id, recent_topics=recent_topics)
        if scout_result:
            trend = scout_result.candidate
            seed_theme = trend.topic
            requested_angle = trend.requested_angle
            notes = "\n".join(["input_mode=theme", "automation_source=automatic_topic", trend.as_notes(), f"topic_scout_considered={scout_result.considered_count}", f"topic_scout_rejected_recent={scout_result.rejected_recent_count}"])
        else:
            seed_theme = random.choice(DEFAULT_AUTOMATION_TOPIC_POOL)
            requested_angle = None
            notes = "input_mode=theme\nautomation_source=automatic_topic\ntrend_research=unavailable\ntrend_source=fallback_pool"
        retention_guidance = self._active_retention_guidance_notes()
        if retention_guidance:
            notes = "\n".join([notes, retention_guidance])
        return TopicRequestCreate(
            seed_theme=seed_theme,
            niche_id=self.settings.niche_id,
            language=self.settings.language,
            target_duration_sec=self.settings.target_duration_sec,
            tone="intrigante_direto",
            cta_style="none",
            notes=notes,
            requested_angle=requested_angle,
            job_origin=JOB_ORIGIN_AUTOMATIC_TOPIC,
            creation_via=CREATION_VIA_DAILY_CYCLE,
        ).model_dump()

    def evaluate_autoapproval(self, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            script = session.scalar(select(Script).where(Script.job_id == job_id))
            monetization_report = self.orchestrator._read_job_json(job_id, "monetization_report.json")
            repetition_report = monetization_report.get("channel_repetition_report") or {}
            manual_confirmations = {str(item) for item in monetization_report.get("manual_confirmations") or []}
            metadata_review = monetization_report.get("metadata_review") or {}
            fact_claims_report = monetization_report.get("fact_claims_report") or {}
            publish_readiness = monetization_report.get("publish_readiness") or {}
            audit = publish_readiness.get("minimax_audit") or {}
            quality_summary = dict(job.quality_summary or {})
            asset_summary = dict(quality_summary.get("assets") or {})
            qa_metrics = dict(script.qa_metrics or {}) if script else {}
            ready_script_bank_job = job.job_origin == JOB_ORIGIN_READY_SCRIPT_BANK

        reasons: list[str] = []
        if job.status != "ready_for_upload":
            reasons.append("job_not_ready_for_upload")
        if not monetization_report.get("passed"):
            reasons.append("monetization_not_passed")
        repetition_risk = str(repetition_report.get("repetition_risk") or "unknown")
        originality_confirmed = "originality_confirmed" in manual_confirmations
        if repetition_risk == "high" and not originality_confirmed:
            reasons.append("high_narrative_similarity")

        factual_score = as_score(audit.get("factual_score"))
        if factual_score is None:
            factual_score = 1.0 if not fact_claims_report.get("requires_fact_review") else 0.0
        retention_score = as_score(audit.get("retention_score"))
        if retention_score is None:
            candidates = [as_score(qa_metrics.get("hook_score")), as_score(qa_metrics.get("information_density_score"))]
            values = [value for value in candidates if value is not None]
            retention_score = sum(values) / len(values) if values else 0.85
        metadata_score = as_score(audit.get("metadata_score"))
        if metadata_score is None:
            metadata_score = 1.0 if not metadata_review.get("requires_metadata_review") else 0.7
        asset_score = as_score(asset_summary.get("asset_semantic_score_avg"))
        asset_score_missing = asset_score is None
        if asset_score_missing:
            asset_score = 0.0

        if factual_score < 0.80:
            reasons.append("factual_score_below_threshold")
        if retention_score < 0.75:
            reasons.append("retention_score_below_threshold")
        if metadata_score < 0.75:
            reasons.append("metadata_score_below_threshold")
        if asset_score < 0.80:
            reasons.append("asset_semantic_score_below_threshold")
        if asset_score_missing:
            reasons.append("asset_semantic_score_missing")

        component_scores = [factual_score, retention_score, metadata_score, asset_score]
        composite = sum(component_scores) / len(component_scores)
        penalty = 0.10 if repetition_risk == "medium" and not originality_confirmed else 0.0
        score = max(0.0, round(composite - penalty, 3))
        if score < self.settings.automation_score_threshold:
            reasons.append("automation_score_below_threshold")
        diagnostic_reasons: list[str] = []
        if ready_script_bank_job:
            editorial_diagnostic_reasons = {
                "high_narrative_similarity",
                "factual_score_below_threshold",
                "retention_score_below_threshold",
                "metadata_score_below_threshold",
                "automation_score_below_threshold",
            }
            diagnostic_reasons = [reason for reason in reasons if reason in editorial_diagnostic_reasons]
            reasons = [reason for reason in reasons if reason not in editorial_diagnostic_reasons]
        report = {
            "eligible": not reasons,
            "score": score,
            "threshold": self.settings.automation_score_threshold,
            "reasons": list(dict.fromkeys(reasons)),
            "diagnostic_reasons": list(dict.fromkeys(diagnostic_reasons)),
            "ready_script_bank_policy": (
                "score_diagnostic_only"
                if ready_script_bank_job
                else "score_blocks_automatic_publication"
            ),
            "components": {
                "factual_score": round(factual_score, 3),
                "retention_score": round(retention_score, 3),
                "metadata_score": round(metadata_score, 3),
                "asset_semantic_score": round(asset_score, 3),
                "repetition_risk": repetition_risk,
                "repetition_penalty": penalty,
                "originality_confirmed": originality_confirmed,
            },
        }
        self.orchestrator.storage.persist_json(job_id, "autoapproval_score.json", self.orchestrator._serialize_for_json(report))
        return report

    def _approve_and_schedule(
        self,
        job_id: str,
        target_slot: PublishSlot | date,
        *,
        confirmation_codes: list[str] | None = None,
    ) -> str:
        slot = self._coerce_publish_slot(target_slot)
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            if job.status == "ready_for_upload":
                pass
            elif job.status != "approved_for_publish":
                raise RuntimeError(f"job_status_not_publishable={job.status}")
        if self._job_status(job_id) == "ready_for_upload":
            reason_codes = ["automation_score_confirmed", *(confirmation_codes or [])]
            self.orchestrator.review_job(
                {
                    "reviewer_identity": "automation:daily-cycle",
                    "action": "approve",
                    "reason_codes": list(dict.fromkeys(reason_codes)),
                    "notes": "Aprovado automaticamente por Score de Autoaprovacao.",
                },
                job_id,
            )
        payload = {
            "scheduled_for_local": slot.scheduled_for_local,
            "timezone": slot.timezone,
            "youtube_visibility": "public",
            "notes": "Agendado automaticamente pelo Ciclo Diario de Automacao.",
        }
        last_error: Exception | None = None
        for _ in range(self.settings.automation_max_publish_attempts_per_job):
            try:
                self.orchestrator.schedule_publication(job_id, payload)
                schedule_id = self._publication_schedule_id(job_id)
                if schedule_id:
                    return schedule_id
                raise RuntimeError("publication_schedule_missing_after_success")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error:
            raise last_error
        raise RuntimeError("publication_schedule_failed")

    def _coerce_publish_slot(self, target_slot: PublishSlot | date) -> PublishSlot:
        if isinstance(target_slot, PublishSlot):
            return target_slot
        return PublishSlot(
            local_date=target_slot,
            local_time=datetime.strptime(str(self.settings.automation_publish_time), "%H:%M").strftime("%H:%M"),
            timezone=self.settings.automation_daily_timezone,
        )

    def _coerce_publish_slots(self, target_slots: list[PublishSlot] | date) -> list[PublishSlot]:
        if isinstance(target_slots, date):
            return [self._coerce_publish_slot(target_slots)]
        return [self._coerce_publish_slot(slot) for slot in target_slots]

    def _coerce_publish_plan(self, target_slots: list[PublishPlan] | list[PublishSlot] | date) -> list[PublishPlan]:
        if isinstance(target_slots, date):
            slot = self._coerce_publish_slot(target_slots)
            return [
                PublishPlan(
                    slot=slot,
                    source=self._automation_publish_source_for_time(slot.local_time),
                    fallback_source=self._automation_fallback_source_for_time(slot.local_time),
                )
            ]
        plan: list[PublishPlan] = []
        for target_slot in target_slots:
            if isinstance(target_slot, PublishPlan):
                plan.append(target_slot)
                continue
            slot = self._coerce_publish_slot(target_slot)
            plan.append(
                PublishPlan(
                    slot=slot,
                    source=self._automation_publish_source_for_time(slot.local_time),
                    fallback_source=self._automation_fallback_source_for_time(slot.local_time),
                )
            )
        return plan

    def _publication_schedule_id(self, job_id: str) -> str | None:
        with session_scope() as session:
            schedule = session.scalar(select(PublicationSchedule).where(PublicationSchedule.job_id == job_id))
            return str(schedule.schedule_id) if schedule else None

    def _job_status(self, job_id: str) -> str:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                raise KeyError(job_id)
            return str(job.status)


def split_ready_script_batch(raw_text: str) -> list[str]:
    text = normalize_ready_script_text(raw_text)
    if not text:
        return []
    starts = [match.start() for match in READY_SCRIPT_SPLIT_RE.finditer(text)]
    if not starts:
        return [text]
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def as_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


def serialize_run(run: AutomationRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "run_id": run.run_id,
        "local_date": run.local_date,
        "timezone": run.timezone,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "target_publish_date": run.target_publish_date,
        "target_publish_at_utc": run.target_publish_at_utc.isoformat() if run.target_publish_at_utc else None,
        "attempts_used": run.attempts_used,
        "result_job_id": run.result_job_id,
        "result_schedule_id": run.result_schedule_id,
        "skipped_reason": run.skipped_reason,
        "error": run.error,
        "metadata": run.run_metadata or {},
    }


def serialize_ready_script_item(item: ReadyScriptItem) -> dict[str, Any]:
    return {
        "script_item_id": item.script_item_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "status": item.status,
        "source": item.source,
        "title": item.title,
        "fact_check_confirmed": item.fact_check_confirmed,
        "consumed_job_id": item.consumed_job_id,
        "last_skip_reason": item.last_skip_reason,
        "last_similarity_score": item.last_similarity_score,
    }


def serialize_attempt(attempt: AutomationAttempt) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "run_id": attempt.run_id,
        "attempt_number": attempt.attempt_number,
        "source": attempt.source,
        "status": attempt.status,
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "ready_script_item_id": attempt.ready_script_item_id,
        "job_id": attempt.job_id,
        "score": attempt.score,
        "score_report": attempt.score_report or {},
        "error": attempt.error,
    }
