from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain_contracts import (
    ACTIVE_SCHEDULE_STATUSES,
    AUTOMATION_SOURCE_AUTO_TOPIC,
    AUTOMATION_SOURCE_BACKLOG,
    AUTOMATION_SOURCE_READY_SCRIPT,
    AUTOMATION_SOURCE_RESUME,
)


SECONDARY_AUTOMATION_PUBLISH_TIME = "18:00"


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


def automation_publish_times(primary_publish_time: str) -> list[str]:
    times: list[str] = []
    for raw_time in [primary_publish_time, SECONDARY_AUTOMATION_PUBLISH_TIME]:
        parsed = datetime.strptime(str(raw_time), "%H:%M")
        normalized = parsed.strftime("%H:%M")
        if normalized not in times:
            times.append(normalized)
    return times


def automation_publish_source_for_time(primary_publish_time: str, publish_time: str) -> str:
    primary_time = datetime.strptime(str(primary_publish_time), "%H:%M").strftime("%H:%M")
    secondary_time = datetime.strptime(SECONDARY_AUTOMATION_PUBLISH_TIME, "%H:%M").strftime("%H:%M")
    if publish_time == secondary_time:
        return AUTOMATION_SOURCE_AUTO_TOPIC
    if publish_time == primary_time:
        return AUTOMATION_SOURCE_READY_SCRIPT
    return AUTOMATION_SOURCE_AUTO_TOPIC


def automation_fallback_source_for_time(publish_time: str) -> str | None:
    # Keep daily lanes honest: ready-script bank and automatic-topic failures
    # must stay visible instead of silently filling one lane from the other.
    return None


def generation_source_for_attempt(
    plan_item: PublishPlan,
    current_slot_attempts: int,
    max_primary_attempts_per_slot: int,
) -> str:
    if not plan_item.fallback_source:
        return plan_item.source
    if current_slot_attempts >= max_primary_attempts_per_slot:
        return plan_item.fallback_source
    return plan_item.source


def build_vacant_publish_slots(
    *,
    today: date,
    fill_window_days: int,
    publish_times: list[str],
    timezone: str,
    occupied: set[tuple[date, str]],
) -> list[PublishSlot]:
    slots: list[PublishSlot] = []
    for offset in range(1, fill_window_days + 1):
        candidate = today + timedelta(days=offset)
        for publish_time in publish_times:
            if (candidate, publish_time) not in occupied:
                slots.append(PublishSlot(local_date=candidate, local_time=publish_time, timezone=timezone))
    return slots


def build_publish_plan(slots: list[PublishSlot], *, primary_publish_time: str) -> list[PublishPlan]:
    if not slots:
        return []
    first_incomplete_date = slots[0].local_date
    return [
        PublishPlan(
            slot=slot,
            source=automation_publish_source_for_time(primary_publish_time, slot.local_time),
            fallback_source=automation_fallback_source_for_time(slot.local_time),
        )
        for slot in slots
        if slot.local_date == first_incomplete_date
    ]
