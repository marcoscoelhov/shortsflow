from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.utils import utcnow


GROWTH_MIN_CONFIDENT_VIEWS = 100
GROWTH_STALE_AFTER_HOURS = 48


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def optional_float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def optional_int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _metric_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_int(value: Any) -> int | None:
    number = _metric_float(value)
    if number is None:
        return None
    return int(number)


def build_growth_score(
    summary_metrics: dict[str, Any],
    *,
    fetched_at: datetime | None = None,
    now: datetime | None = None,
    minimum_views: int = GROWTH_MIN_CONFIDENT_VIEWS,
) -> dict[str, Any]:
    views = _metric_int(summary_metrics.get("views")) or 0
    retention_percent = _metric_float(summary_metrics.get("averageViewPercentage"))
    shares = _metric_int(summary_metrics.get("shares")) or 0
    subscribers_gained = _metric_int(summary_metrics.get("subscribersGained")) or 0
    likes = _metric_int(summary_metrics.get("likes")) or 0
    comments = _metric_int(summary_metrics.get("comments")) or 0
    average_view_duration = _metric_float(summary_metrics.get("averageViewDuration"))
    score = round(retention_percent) if retention_percent is not None else None
    fetched_at_utc = as_utc(fetched_at)
    stale = False
    if fetched_at_utc is not None:
        stale = (as_utc(now or utcnow()) or utcnow()) - fetched_at_utc > timedelta(hours=GROWTH_STALE_AFTER_HOURS)
    confidence = "confiavel" if views >= minimum_views else "baixa_confianca"
    return {
        "score": score,
        "confidence": confidence,
        "confidence_label": "confiável" if confidence == "confiavel" else "baixa confiança",
        "minimum_views": minimum_views,
        "stale": stale,
        "views": views,
        "retention_percent": round(retention_percent, 2) if retention_percent is not None else None,
        "average_view_duration": round(average_view_duration, 2) if average_view_duration is not None else None,
        "shares": shares,
        "subscribers_gained": subscribers_gained,
        "likes": likes,
        "comments": comments,
        "sort_key": (
            score if score is not None else -1,
            1 if views >= minimum_views else 0,
            subscribers_gained,
            shares,
            views,
        ),
    }
