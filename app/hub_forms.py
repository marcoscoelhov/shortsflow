from __future__ import annotations

from app.schemas import PerformanceMetricPayload, ReviewActionPayload


def optional_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def optional_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def parse_review_reason_codes(
    reason_codes: list[str] | None,
    confirmation_codes: list[str] | None,
    *,
    rights_confirmed: bool = False,
    ai_disclosure_confirmed: bool = False,
    fact_review_confirmed: bool = False,
    metadata_confirmed: bool = False,
    originality_confirmed: bool = False,
) -> list[str]:
    parsed_reason_codes: list[str] = []

    def append_unique(code: str) -> None:
        normalized = code.strip()
        if normalized and normalized not in parsed_reason_codes:
            parsed_reason_codes.append(normalized)

    for raw_reason in reason_codes or []:
        for item in str(raw_reason).split(","):
            append_unique(item)
    for confirmation_code in confirmation_codes or []:
        append_unique(str(confirmation_code))
    for enabled, code in [
        (rights_confirmed, "rights_confirmed"),
        (ai_disclosure_confirmed, "ai_disclosure_confirmed"),
        (fact_review_confirmed, "fact_review_confirmed"),
        (metadata_confirmed, "metadata_confirmed"),
        (originality_confirmed, "originality_confirmed"),
    ]:
        if enabled:
            append_unique(code)
    return parsed_reason_codes


def build_review_action_payload(
    *,
    reviewer_identity: str,
    action: str,
    reason_codes: list[str] | None = None,
    confirmation_codes: list[str] | None = None,
    rights_confirmed: bool = False,
    ai_disclosure_confirmed: bool = False,
    fact_review_confirmed: bool = False,
    metadata_confirmed: bool = False,
    originality_confirmed: bool = False,
    notes: str | None = None,
) -> ReviewActionPayload:
    return ReviewActionPayload(
        reviewer_identity=reviewer_identity,
        action=action,
        reason_codes=parse_review_reason_codes(
            reason_codes,
            confirmation_codes,
            rights_confirmed=rights_confirmed,
            ai_disclosure_confirmed=ai_disclosure_confirmed,
            fact_review_confirmed=fact_review_confirmed,
            metadata_confirmed=metadata_confirmed,
            originality_confirmed=originality_confirmed,
        ),
        notes=notes,
    )


def build_performance_metric_payload(
    *,
    source: str,
    retention_percent: str | None = None,
    viewed_vs_swiped_away_percent: str | None = None,
    rewatch_rate: str | None = None,
    likes: str | None = None,
    shares: str | None = None,
    comments: str | None = None,
    rpm_usd: str | None = None,
    monetization_status: str | None = None,
    notes: str | None = None,
) -> PerformanceMetricPayload:
    return PerformanceMetricPayload(
        source=source,
        retention_percent=optional_float(retention_percent),
        viewed_vs_swiped_away_percent=optional_float(viewed_vs_swiped_away_percent),
        rewatch_rate=optional_float(rewatch_rate),
        likes=optional_int(likes),
        shares=optional_int(shares),
        comments=optional_int(comments),
        rpm_usd=optional_float(rpm_usd),
        monetization_status=monetization_status,
        notes=notes,
    )
