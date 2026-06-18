from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean, median
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


def _rate(numerator: float, denominator: float, multiplier: float = 100.0) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * multiplier, 2)


def _summary_number(summary: dict[str, Any], key: str) -> float:
    return _metric_float(summary.get(key)) or 0.0


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(mean(values), 2),
        "median": round(median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def build_channel_growth_report(
    snapshots: list[dict[str, Any]],
    *,
    minimum_views: int = GROWTH_MIN_CONFIDENT_VIEWS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = as_utc(generated_at or utcnow()) or utcnow()
    videos: list[dict[str, Any]] = []
    for snapshot in snapshots:
        summary = dict(snapshot.get("summary_metrics") or {})
        views = _summary_number(summary, "views")
        likes = _summary_number(summary, "likes")
        comments = _summary_number(summary, "comments")
        shares = _summary_number(summary, "shares")
        subscribers_gained = _summary_number(summary, "subscribersGained")
        subscribers_lost = _summary_number(summary, "subscribersLost")
        watch_minutes = _summary_number(summary, "estimatedMinutesWatched")
        retention_percent = _metric_float(summary.get("averageViewPercentage"))
        average_view_duration = _metric_float(summary.get("averageViewDuration"))
        engaged_views = _summary_number(summary, "engagedViews")
        video = {
            "job_id": snapshot.get("job_id"),
            "youtube_video_id": snapshot.get("youtube_video_id"),
            "title": snapshot.get("title") or snapshot.get("topic") or "sem título",
            "topic": snapshot.get("topic"),
            "canonical_topic": snapshot.get("canonical_topic"),
            "hook": snapshot.get("hook"),
            "published_at": snapshot.get("published_at"),
            "fetched_at": snapshot.get("fetched_at"),
            "views": int(views),
            "engaged_views": int(engaged_views),
            "watch_minutes": round(watch_minutes, 2),
            "retention_percent": _round_or_none(retention_percent),
            "average_view_duration": _round_or_none(average_view_duration),
            "likes": int(likes),
            "comments": int(comments),
            "shares": int(shares),
            "subscribers_gained": int(subscribers_gained),
            "subscribers_lost": int(subscribers_lost),
            "subscribers_net": int(subscribers_gained - subscribers_lost),
            "like_rate": _rate(likes, views),
            "engagement_rate": _rate(likes + comments + shares, views),
            "share_rate": _rate(shares, views),
            "comment_rate": _rate(comments, views),
            "subscribers_per_1000_views": _rate(subscribers_gained - subscribers_lost, views, 1000.0),
            "engaged_view_rate": _rate(engaged_views, views),
            "confidence": "confiavel" if views >= minimum_views else "baixa_confianca",
        }
        videos.append(video)

    nonzero_videos = [video for video in videos if int(video["views"]) > 0]
    reliable_videos = [video for video in videos if video["confidence"] == "confiavel"]
    total_views = sum(int(video["views"]) for video in videos)
    total_likes = sum(int(video["likes"]) for video in videos)
    total_comments = sum(int(video["comments"]) for video in videos)
    total_shares = sum(int(video["shares"]) for video in videos)
    total_subscribers_gained = sum(int(video["subscribers_gained"]) for video in videos)
    total_subscribers_lost = sum(int(video["subscribers_lost"]) for video in videos)
    total_watch_minutes = sum(float(video["watch_minutes"]) for video in videos)
    reliable_retention_values = [float(video["retention_percent"]) for video in reliable_videos if video["retention_percent"] is not None]
    nonzero_retention_values = [float(video["retention_percent"]) for video in nonzero_videos if video["retention_percent"] is not None]
    views_values = [float(video["views"]) for video in videos]
    median_views = median([float(video["views"]) for video in nonzero_videos]) if nonzero_videos else 0

    top_views = sorted(nonzero_videos, key=lambda item: (int(item["views"]), float(item["retention_percent"] or 0)), reverse=True)[:10]
    top_retention = sorted(
        reliable_videos,
        key=lambda item: (float(item["retention_percent"] or -1), int(item["views"])),
        reverse=True,
    )[:10]
    bottom_retention = sorted(
        [video for video in reliable_videos if video["retention_percent"] is not None],
        key=lambda item: (float(item["retention_percent"] or 0), -int(item["views"])),
    )[:10]
    top_sub_conversion = sorted(
        [video for video in reliable_videos if video["subscribers_per_1000_views"] is not None],
        key=lambda item: (float(item["subscribers_per_1000_views"] or 0), int(item["views"])),
        reverse=True,
    )[:10]
    top_like_rate = sorted(
        [video for video in reliable_videos if video["like_rate"] is not None],
        key=lambda item: (float(item["like_rate"] or 0), int(item["views"])),
        reverse=True,
    )[:10]
    distribution_gap = [
        video
        for video in reliable_videos
        if float(video["retention_percent"] or 0) >= 75 and int(video["views"]) < median_views
    ]
    retention_gap = [
        video
        for video in reliable_videos
        if int(video["views"]) >= median_views and float(video["retention_percent"] or 0) < 55
    ]
    share_gap = total_views >= minimum_views and (total_shares == 0 or (total_shares / total_views) < 0.002)
    comment_gap = total_views >= minimum_views and (total_comments == 0 or (total_comments / total_views) < 0.002)

    gaps: list[dict[str, Any]] = []
    if distribution_gap:
        gaps.append(
            {
                "kind": "distribution_gap",
                "title": "Retenção alta com pouca distribuição",
                "impact": "Bons vídeos podem estar perdendo no primeiro swipe, embalagem ou teste inicial do algoritmo.",
                "count": len(distribution_gap),
                "examples": [video["title"] for video in distribution_gap[:3]],
            }
        )
    if retention_gap:
        gaps.append(
            {
                "kind": "retention_gap",
                "title": "Distribuição razoável com retenção fraca",
                "impact": "O tema recebeu teste, mas a abertura ou o meio não sustentaram atenção.",
                "count": len(retention_gap),
                "examples": [video["title"] for video in retention_gap[:3]],
            }
        )
    if share_gap:
        gaps.append(
            {
                "kind": "share_gap",
                "title": "Compartilhamento baixo",
                "impact": "Os vídeos são assistíveis, mas ainda geram pouco impulso social.",
                "count": total_shares,
                "examples": [],
            }
        )
    if comment_gap:
        gaps.append(
            {
                "kind": "comment_gap",
                "title": "Conversação quase inexistente",
                "impact": "Falta uma pergunta, tensão ou discordância natural que convide resposta.",
                "count": total_comments,
                "examples": [],
            }
        )
    if any(int(video["views"]) == 0 for video in videos):
        gaps.append(
            {
                "kind": "zero_view_snapshot",
                "title": "Snapshots zerados",
                "impact": "Vídeos recentes ou sem dados maduros não devem pesar como fracasso editorial.",
                "count": sum(1 for video in videos if int(video["views"]) == 0),
                "examples": [video["title"] for video in videos if int(video["views"]) == 0][:3],
            }
        )

    recommendations: list[dict[str, Any]] = []
    if top_retention:
        recommendations.append(
            {
                "kind": "repeat_winners",
                "title": "Replicar estruturas vencedoras",
                "body": "Priorize pautas com imagem mental imediata, fenômeno estranho e consequência concreta.",
                "examples": [video["title"] for video in top_retention[:3]],
            }
        )
    if retention_gap:
        recommendations.append(
            {
                "kind": "tighten_openings",
                "title": "Reescrever hooks abstratos",
                "body": "Quando o tema exige contexto, transforme o primeiro segundo em cena física ou risco humano.",
                "examples": [video["title"] for video in retention_gap[:3]],
            }
        )
    if share_gap or comment_gap:
        recommendations.append(
            {
                "kind": "add_social_trigger",
                "title": "Adicionar gatilho de resposta",
                "body": "Inclua finais que abram dúvida específica ou uma comparação fácil de mandar para outra pessoa.",
                "examples": [],
            }
        )

    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at.isoformat(),
        "minimum_views": minimum_views,
        "coverage": {
            "videos": len(videos),
            "nonzero_videos": len(nonzero_videos),
            "reliable_videos": len(reliable_videos),
            "zero_view_videos": len(videos) - len(nonzero_videos),
        },
        "totals": {
            "views": total_views,
            "watch_minutes": round(total_watch_minutes, 2),
            "likes": total_likes,
            "comments": total_comments,
            "shares": total_shares,
            "subscribers_gained": total_subscribers_gained,
            "subscribers_lost": total_subscribers_lost,
            "subscribers_net": total_subscribers_gained - total_subscribers_lost,
            "like_rate": _rate(total_likes, total_views),
            "engagement_rate": _rate(total_likes + total_comments + total_shares, total_views),
            "share_rate": _rate(total_shares, total_views),
            "comment_rate": _rate(total_comments, total_views),
            "subscribers_per_1000_views": _rate(total_subscribers_gained - total_subscribers_lost, total_views, 1000.0),
        },
        "stats": {
            "views": _stats(views_values),
            "retention_percent_nonzero": _stats(nonzero_retention_values),
            "retention_percent_reliable": _stats(reliable_retention_values),
        },
        "rankings": {
            "top_views": top_views,
            "top_retention": top_retention,
            "bottom_retention": bottom_retention,
            "top_sub_conversion": top_sub_conversion,
            "top_like_rate": top_like_rate,
        },
        "gaps": gaps,
        "recommendations": recommendations,
        "videos": videos,
    }
