from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.utils import clamp01 as _clamp
from app.utils import word_tokens

TENSION_PATTERN = re.compile(r"\b(?:não|nunca|segredo|rouba|esconde|estranho|imposs[ií]vel|antes|por que|muda tudo|ningu[eé]m|predador|fogo|sumir|desaparece|notar)\b", re.I)
EXPLAINER_PATTERN = re.compile(r"^\s*(?:por que|como|entenda|explica(?:ção)?|o que é|a ciência por trás)\b", re.I)
GENERIC_HASHTAGS = {"#viral", "#shorts", "#fyp", "#fy", "#curiosidades", "#curiosidade"}


@dataclass(frozen=True)
class MetadataCTRGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class MetadataCTRGate:
    MIN_METADATA_CTR = 0.74
    MIN_CLICK_TENSION = 0.72
    MIN_HASHTAGS = 0.66

    def validate(self, topic_plan: dict[str, Any] | Any, script: dict[str, Any] | Any, hashtags: list[str]) -> MetadataCTRGateResult:
        title = _get(script, "title")
        narration = _get(script, "full_narration")
        canonical = _get(topic_plan, "canonical_topic")
        angle = _get(topic_plan, "angle")
        words = word_tokens(title)
        title_len_score = _clamp(1.0 - abs(len(title) - 58) / 70) if title else 0.0
        tension_hits = len(TENSION_PATTERN.findall(title))
        specificity_terms = {token for token in word_tokens(" ".join([canonical, angle, narration])) if len(token) >= 5}
        title_terms = {token for token in words if len(token) >= 5}
        specificity_score = _clamp(0.22 + min(0.55, len(title_terms & specificity_terms) * 0.16) + min(0.16, len(title_terms) * 0.025))
        click_tension = _clamp(
            0.20
            + min(0.42, tension_hits * 0.18)
            + (0.16 if not EXPLAINER_PATTERN.search(title) else -0.18)
            + (0.14 if len(words) >= 7 else 0.03)
            + (0.10 if any(token in title.lower() for token in ["antes", "segredo", "notar", "rouba", "sumir"]) else 0.0)
        )
        hashtag_score = self._hashtag_score(hashtags, specificity_terms)
        not_clickbait = 1.0 if not re.search(r"\b(?:chocante|inacredit[aá]vel!!!|100%|garantido)\b", title, re.I) else 0.45
        ctr_score = _clamp(click_tension * 0.38 + specificity_score * 0.24 + hashtag_score * 0.18 + title_len_score * 0.12 + not_clickbait * 0.08)
        reasons: list[str] = []
        if EXPLAINER_PATTERN.search(title):
            reasons.append("title_too_explanatory")
        if click_tension < self.MIN_CLICK_TENSION:
            reasons.append("title_click_tension_low")
        if hashtag_score < self.MIN_HASHTAGS:
            reasons.append("weak_hashtags")
        if ctr_score < self.MIN_METADATA_CTR:
            reasons.append("metadata_ctr_below_threshold")
        metrics = {
            "metadata_ctr_gate_pass": not reasons,
            "metadata_ctr_score": round(ctr_score, 3),
            "title_click_tension_score": round(click_tension, 3),
            "title_specificity_score": round(specificity_score, 3),
            "title_length_score": round(title_len_score, 3),
            "title_not_clickbait_score": round(not_clickbait, 3),
            "hashtag_relevance_score": round(hashtag_score, 3),
        }
        return MetadataCTRGateResult(not reasons, reasons, metrics)

    def _hashtag_score(self, hashtags: list[str], topic_terms: set[str]) -> float:
        clean = [str(tag).strip().lower() for tag in hashtags if str(tag or "").strip()]
        if not clean:
            return 0.0
        specific = 0
        for tag in clean:
            normalized = _normalize(tag.lstrip("#"))
            if tag in GENERIC_HASHTAGS:
                continue
            if any(term in normalized or normalized in term for term in topic_terms):
                specific += 1
            elif len(normalized) >= 5:
                specific += 0.5
        return _clamp(0.15 + min(0.65, specific * 0.26) + min(0.20, len(clean) * 0.05))


def _get(obj: dict[str, Any] | Any, key: str) -> str:
    if isinstance(obj, dict):
        return str(obj.get(key) or "")
    return str(getattr(obj, key, "") or "")


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
