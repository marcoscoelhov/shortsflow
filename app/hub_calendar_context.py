from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Job, PublicationSchedule, Script, TopicRequest

COMMON_SCHEDULE_TIMEZONES = [
    "UTC",
    "America/Sao_Paulo",
    "America/New_York",
    "Europe/London",
]

MONTH_NAMES_PT_BR = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


class HubCalendarContext:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    def parse_month(self, month: str | None) -> date:
        normalized = str(month or "").strip()
        if not normalized:
            now = datetime.now(UTC)
            return date(now.year, now.month, 1)
        try:
            parsed = datetime.strptime(normalized, "%Y-%m")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="month must use YYYY-MM") from exc
        return date(parsed.year, parsed.month, 1)

    def shift_month(self, month_start: date, delta: int) -> date:
        month_index = month_start.month - 1 + delta
        year = month_start.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, 1)

    def context(self, month: str | None) -> dict[str, object]:
        month_start = self.parse_month(month)
        previous_month = self.shift_month(month_start, -1)
        next_month = self.shift_month(month_start, 1)
        month_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
        with SessionLocal() as session:
            ready_to_schedule = self.owner._ready_to_schedule_entries(session)
            schedule_rows = session.execute(
                select(PublicationSchedule, Job, TopicRequest, Script)
                .join(Job, Job.job_id == PublicationSchedule.job_id)
                .join(TopicRequest, TopicRequest.job_id == PublicationSchedule.job_id)
                .join(Script, Script.job_id == PublicationSchedule.job_id, isouter=True)
                .where(PublicationSchedule.status.in_(["scheduled", "publishing", "publish_failed", "published"]))
                .order_by(PublicationSchedule.scheduled_for_utc)
            ).all()

        entries_by_day: dict[date, list[dict[str, object]]] = {}
        scheduled_count = 0
        published_count = 0
        for schedule, job, topic_request, script in schedule_rows:
            scheduled_for_utc = schedule.scheduled_for_utc if schedule.scheduled_for_utc.tzinfo else schedule.scheduled_for_utc.replace(tzinfo=UTC)
            local_dt = scheduled_for_utc.astimezone(ZoneInfo(schedule.timezone))
            local_day = local_dt.date()
            if local_day.year != month_start.year or local_day.month != month_start.month:
                continue
            title = script.title if script else (job.topic_summary or topic_request.seed_theme)
            entry = {
                "job_id": job.job_id,
                "title": title,
                "seed_theme": topic_request.seed_theme,
                "job_status": job.status,
                "review_state": job.review_state,
                "schedule_status": schedule.status,
                "local_time": local_dt.strftime("%H:%M"),
                "timezone": schedule.timezone,
                "youtube_visibility": schedule.youtube_visibility,
                "youtube_url": schedule.youtube_url,
            }
            entries_by_day.setdefault(local_day, []).append(entry)
            if schedule.status == "scheduled":
                scheduled_count += 1
            if schedule.status == "published":
                published_count += 1

        weeks: list[list[dict[str, object]]] = []
        for week in month_weeks:
            week_cells = []
            for day in week:
                week_cells.append(
                    {
                        "date": day,
                        "iso_date": day.isoformat(),
                        "day_number": day.day,
                        "is_current_month": day.month == month_start.month,
                        "entries": entries_by_day.get(day, []),
                    }
                )
            weeks.append(week_cells)

        return {
            "month_value": month_start.strftime("%Y-%m"),
            "month_label": f"{MONTH_NAMES_PT_BR[month_start.month - 1]} {month_start.year}",
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "weeks": weeks,
            "scheduled_count": scheduled_count,
            "published_count": published_count,
            "ready_to_schedule": ready_to_schedule,
            "common_schedule_timezones": COMMON_SCHEDULE_TIMEZONES,
            "default_schedule_timezone": "America/Sao_Paulo",
            "default_schedule_time": "15:00",
            "default_youtube_visibility": "public" if self.settings.youtube_publish_mode == "api" else "private",
        }
