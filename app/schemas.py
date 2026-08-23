from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_NICHES = {"curiosidades", "survival_decisions", "fiction_microdrama"}
SUPPORTED_LANGUAGES = {"pt-BR"}


class TopicRequestCreate(BaseModel):
    seed_theme: str = Field(min_length=3)
    niche_id: str = "curiosidades"
    language: str = "pt-BR"
    target_duration_sec: int = 45
    tone: str = "intrigante_direto"
    cta_style: Literal["none", "soft"] = "soft"
    notes: str | None = None
    requested_angle: str | None = None
    job_origin: Literal["ready_script_bank", "manual_ready_script", "automatic_topic", "manual_theme", "manual_title", "unknown"] | None = None
    creation_via: Literal["hub", "daily_cycle", "cli", "api", "recreation", "unknown"] | None = None

    @model_validator(mode="after")
    def preserve_experiment_markers(self) -> TopicRequestCreate:
        if self.niche_id == "fiction_microdrama":
            if self.job_origin in {"automatic_topic", "ready_script_bank"} or self.creation_via == "daily_cycle":
                raise ValueError("fiction_microdrama is manual-only and cannot enter automated creation lanes")
            from app.microdrama_pilot import microdrama_policy_notes

            protected_keys = {
                "fictional_scenario",
                "fiction_format",
                "automatic_publication_allowed",
                "human_review_required",
                "originality_review_required",
                "twist_required",
                "twist_must_reinterpret_story",
                "shock_without_graphic_violence",
            }
            existing_notes = "\n".join(
                line
                for line in str(self.notes or "").strip().splitlines()
                if line.strip().partition("=")[0].strip() not in protected_keys
            ).strip()
            required_notes = list(microdrama_policy_notes())
            existing_lines = set(existing_notes.splitlines())
            self.notes = "\n".join(
                part for part in [existing_notes, *(note for note in required_notes if note not in existing_lines)] if part
            )
            return self
        if self.niche_id != "survival_decisions":
            return self
        if self.job_origin == "automatic_topic":
            raise ValueError(
                "survival_decisions must be explicitly invoked and cannot enter the automatic_topic lane"
            )
        if self.job_origin == "ready_script_bank" or self.creation_via == "daily_cycle":
            raise ValueError(
                "survival_decisions cannot enter automated creation or publication lanes"
            )
        from app.survival_experiment import survival_policy_notes

        existing_notes = "\n".join(
            line
            for line in str(self.notes or "").strip().splitlines()
            if not (
                line.startswith("human_review_required=")
                or line == "pilot_qwen_autoapproval=true"
                or line.startswith("visual_review_authority=qwen")
            )
        ).strip()
        policy_notes = survival_policy_notes()
        existing_lines = set(existing_notes.splitlines())
        required_notes = [note for note in policy_notes if note not in existing_lines]
        self.notes = "\n".join(part for part in [existing_notes, *required_notes] if part)
        return self

    @field_validator("seed_theme")
    @classmethod
    def validate_seed_theme(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("seed_theme must have at least 3 non-space characters")
        return normalized

    @field_validator("target_duration_sec")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if not 35 <= value <= 150:
            raise ValueError("target_duration_sec must be between 35 and 150")
        return value

    @field_validator("niche_id")
    @classmethod
    def validate_niche_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_NICHES:
            raise ValueError(
                "unsupported niche_id: supported values are 'curiosidades', 'survival_decisions', and 'fiction_microdrama'"
            )
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.strip().lower().replace("_", "-")
        alias_map = {
            "pt-br": "pt-BR",
            "portuguese-br": "pt-BR",
            "ptbr": "pt-BR",
        }
        resolved = alias_map.get(normalized)
        if resolved not in SUPPORTED_LANGUAGES:
            raise ValueError("unsupported language: only 'pt-BR' is currently supported")
        return resolved


class ReviewActionPayload(BaseModel):
    reviewer_identity: str = "tailscale:local-reviewer"
    action: Literal["approve", "reject", "retry"]
    reason_codes: list[str] = Field(default_factory=list)
    notes: str | None = None


class PerformanceMetricPayload(BaseModel):
    source: str = "youtube_studio_manual"
    retention_percent: float | None = None
    viewed_vs_swiped_away_percent: float | None = None
    rewatch_rate: float | None = None
    likes: int | None = None
    shares: int | None = None
    comments: int | None = None
    rpm_usd: float | None = None
    monetization_status: str | None = None
    notes: str | None = None

    @field_validator("retention_percent", "viewed_vs_swiped_away_percent")
    @classmethod
    def validate_percent(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 100:
            raise ValueError("percent metrics must be between 0 and 100")
        return value

    @field_validator("rewatch_rate", "rpm_usd")
    @classmethod
    def validate_non_negative_float(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("metric must be non-negative")
        return value

    @field_validator("likes", "shares", "comments")
    @classmethod
    def validate_non_negative_int(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("metric must be non-negative")
        return value


class PublicationSchedulePayload(BaseModel):
    scheduled_for_local: str
    timezone: str = "UTC"
    youtube_visibility: Literal["private", "unlisted", "public"] = "private"
    notes: str | None = None

    @field_validator("scheduled_for_local")
    @classmethod
    def validate_scheduled_for_local(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("scheduled_for_local is required")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("scheduled_for_local must be a valid datetime-local value") from exc
        if parsed.tzinfo is not None:
            raise ValueError("scheduled_for_local must not include timezone offset")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = str(value or "").strip() or "UTC"
        try:
            ZoneInfo(normalized)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized
