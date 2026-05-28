from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.quality.script_gate import MARKUP_PATTERN
from app.utils import split_caption_chunks, word_tokens


BAD_ENDINGS = {
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "que",
    "e",
    "ao",
    "aos",
    "à",
    "às",
}
BAD_STARTS = {"a", "o", "as", "os", "um", "uma", "uns", "umas"}
BAD_START_HEADS = BAD_ENDINGS | BAD_STARTS
BAD_START_SECOND_TOKENS = {"a", "o", "as", "os", "um", "uma", "uns", "umas", "outro", "outra"}
SEMANTIC_BAD_ENDINGS = BAD_ENDINGS | {"a", "o", "as", "os", "um", "uma", "uns", "umas", "outro", "outra"}
GATE_WEAK_ENDINGS = BAD_ENDINGS | {"outro", "outra"}
SUBTITLE_MAX_CHARS = 32
SUBTITLE_MAX_LINES = 1
SUBTITLE_MAX_WORDS = 8
P95_DRIFT_THRESHOLD_MS = 1200
MAX_DRIFT_THRESHOLD_MS = 1800


@dataclass(frozen=True)
class SubtitleGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class SubtitleGate:
    def validate(self, items: list[dict[str, Any]], coverage_ratio: float, p95_drift_ms: int = 0, max_drift_ms: int = 0) -> SubtitleGateResult:
        reasons: list[str] = []
        item_results: list[dict[str, Any]] = []
        if coverage_ratio < 0.99:
            reasons.append("coverage_below_threshold")
        if p95_drift_ms > P95_DRIFT_THRESHOLD_MS:
            reasons.append("p95_timing_drift_too_high")
        if max_drift_ms > MAX_DRIFT_THRESHOLD_MS:
            reasons.append("max_timing_drift_too_high")
        if not items:
            reasons.append("missing_subtitle_items")
        for item in items:
            idx = str(item.get("idx"))
            text = str(item.get("text") or "").strip()
            item_reasons: list[str] = []
            if not text:
                item_reasons.append("empty_text")
            if MARKUP_PATTERN.search(text):
                item_reasons.append("markup_or_ssml_leaked")
            if re.search(r"\b[a-záàãâéêíóõôúç]$", text, re.IGNORECASE) and text.lower()[-1] not in {"a", "à", "á", "ã", "â", "e", "é", "ê", "o", "ó", "õ", "ô"}:
                item_reasons.append("possible_truncated_word")
            words = word_tokens(text)
            if len(words) > SUBTITLE_MAX_WORDS:
                item_reasons.append("subtitle_too_long")
            if len(split_caption_chunks(text, max_chars=SUBTITLE_MAX_CHARS, max_lines=SUBTITLE_MAX_LINES)) > 1:
                item_reasons.append("subtitle_wraps_multiple_lines")
            if any(len(word) > SUBTITLE_MAX_CHARS for word in text.split()):
                item_reasons.append("subtitle_word_too_wide")
            if self._has_semantic_orphan_start(words):
                item_reasons.append("semantic_orphan_start")
            if words and words[-1].lower() in GATE_WEAK_ENDINGS:
                item_reasons.append("weak_line_ending")
            start_ms = int(item.get("start_ms", 0))
            end_ms = int(item.get("end_ms", 0))
            if end_ms <= start_ms:
                item_reasons.append("invalid_timing")
            item_results.append({"idx": idx, "passed": not item_reasons, "reasons": item_reasons})
            reasons.extend(f"{idx}:{reason}" for reason in item_reasons)
        return SubtitleGateResult(
            passed=not reasons,
            reasons=reasons,
            metrics={
                "coverage_ratio": coverage_ratio,
                "item_count": len(items),
                "p95_drift_ms": int(p95_drift_ms),
                "max_drift_ms": int(max_drift_ms),
                "items": item_results,
            },
        )

    def _has_semantic_orphan_start(self, words: list[str]) -> bool:
        normalized = [word.lower() for word in words]
        if not normalized:
            return False
        if normalized[0] in BAD_STARTS and len(normalized) <= 2:
            return True
        return len(normalized) <= 2 and normalized[0] in BAD_START_HEADS and len(normalized) > 1 and normalized[1] in BAD_START_SECOND_TOKENS
