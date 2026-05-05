from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SUPPORTED_NICHES = {"curiosidades"}


class TopicRequestCreate(BaseModel):
    seed_theme: str = Field(min_length=3)
    niche_id: str = "curiosidades"
    language: str = "pt-BR"
    target_duration_sec: int = 32
    tone: str = "intrigante_direto"
    cta_style: Literal["none", "soft"] = "none"
    notes: str | None = None
    requested_angle: str | None = None

    @field_validator("target_duration_sec")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if not 25 <= value <= 45:
            raise ValueError("target_duration_sec must be between 25 and 45")
        return value

    @field_validator("niche_id")
    @classmethod
    def validate_niche_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_NICHES:
            raise ValueError("unsupported niche_id: only 'curiosidades' is currently supported")
        return normalized


class ReviewActionPayload(BaseModel):
    reviewer_identity: str = "tailscale:local-reviewer"
    action: Literal["approve", "reject", "retry"]
    reason_codes: list[str] = Field(default_factory=list)
    notes: str | None = None
