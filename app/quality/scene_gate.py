from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.utils import word_tokens


GENERIC_PROMPT_MARKERS = {
    "vertical cinematic scientific image",
    "focused on the described phenomenon",
    "showing subject closeup",
    "showing subject in context",
    "showing process or mechanism",
}

DISALLOWED_VERTICAL_COMPOSITION_MARKERS = {
    "before and after",
    "comparison lines",
    "diptych",
    "grid layout",
    "multi panel",
    "multi-panel",
    "panel layout",
    "sequence",
    "side by side",
    "split screen",
    "split-screen",
    "triptych",
    "two panels",
    "linha de comparacao",
    "linha de comparação",
    "linhas de comparacao",
    "linhas de comparação",
    "montagem",
    "paineis",
    "painéis",
    "sequencia",
    "sequência",
    "tela dividida",
}

NEGATION_TOKENS = {"no", "not", "without", "sem", "nao", "nunca", "avoid", "evitar"}

VISUAL_TERM_ALIASES = {
    "arvore": {"arvore", "arvores", "tree", "trees"},
    "arvores": {"arvore", "arvores", "tree", "trees"},
    "building": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "buildings": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "edificio": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "edificios": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "human": {"human", "humano", "humana", "mao", "maos", "hand", "hands"},
    "humana": {"human", "humano", "humana", "mao", "maos", "hand", "hands"},
    "mao": {"human", "humano", "humana", "mao", "maos", "hand", "hands"},
    "maos": {"human", "humano", "humana", "mao", "maos", "hand", "hands"},
    "predio": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "predios": {"building", "buildings", "predio", "predios", "edificio", "edificios"},
    "quadra": {"quadra", "quadras", "quarteirao", "quarteiroes", "block", "blocks", "cityblock", "cityblocks"},
    "quadras": {"quadra", "quadras", "quarteirao", "quarteiroes", "block", "blocks", "cityblock", "cityblocks"},
    "quarteirao": {"quadra", "quadras", "quarteirao", "quarteiroes", "block", "blocks", "cityblock", "cityblocks"},
    "quarteiroes": {"quadra", "quadras", "quarteirao", "quarteiroes", "block", "blocks", "cityblock", "cityblocks"},
    "rua": {"rua", "ruas", "street", "streets", "road", "roads"},
    "ruas": {"rua", "ruas", "street", "streets", "road", "roads"},
    "street": {"rua", "ruas", "street", "streets", "road", "roads"},
    "streets": {"rua", "ruas", "street", "streets", "road", "roads"},
}


@dataclass(frozen=True)
class SceneGateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class ScenePlanGate:
    def validate(
        self,
        scenes: list[dict[str, Any]],
        expected_scene_count: int,
        visual_contract: dict[str, Any] | None = None,
    ) -> SceneGateResult:
        reasons: list[str] = []
        scene_results: list[dict[str, Any]] = []
        if not scenes:
            reasons.append("missing_scenes")
        if scenes and len(scenes) != expected_scene_count:
            reasons.append("scene_count_mismatch")
        contract_report = self._validate_visual_contract_alignment(scenes, visual_contract or {})
        reasons.extend(contract_report["reasons"])
        for scene in scenes:
            scene_id = str(scene.get("scene_id") or "unknown")
            scene_reasons: list[str] = []
            narration = str(scene.get("narration_text") or "")
            prompt = str(scene.get("image_prompt") or "")
            subject = str(scene.get("primary_subject") or scene.get("topic_hint") or "")
            if not narration.strip():
                scene_reasons.append("missing_narration_text")
            if len(word_tokens(narration)) < 3:
                scene_reasons.append("narration_too_short")
            if not prompt.strip():
                scene_reasons.append("missing_image_prompt")
            if "no readable text" not in prompt.lower():
                scene_reasons.append("missing_no_text_constraint")
            composition_hits = _disallowed_vertical_composition_hits(prompt)
            if composition_hits:
                scene_reasons.append("disallowed_split_or_collage_composition")
            if subject and subject.lower() not in prompt.lower() and subject.lower() not in narration.lower():
                # Provider prompts may translate the subject to English for image models.
                # Treat this as a metric, not a hard failure.
                pass
            generic_hits = [marker for marker in GENERIC_PROMPT_MARKERS if marker in prompt.lower()]
            if generic_hits and len(word_tokens(prompt)) < 22:
                scene_reasons.append("image_prompt_too_generic")
            if not isinstance(scene.get("token_start"), int) or not isinstance(scene.get("token_end"), int):
                scene_reasons.append("missing_token_bounds")
            elif int(scene["token_end"]) < int(scene["token_start"]):
                scene_reasons.append("invalid_token_bounds")
            scene_results.append(
                {
                    "scene_id": scene_id,
                    "passed": not scene_reasons,
                    "reasons": scene_reasons,
                    "disallowed_composition_hits": composition_hits,
                }
            )
            reasons.extend(f"{scene_id}:{reason}" for reason in scene_reasons)
        return SceneGateResult(
            passed=not reasons,
            reasons=reasons,
            metrics={
                "scene_count": len(scenes),
                "expected_scene_count": expected_scene_count,
                "scenes": scene_results,
                "visual_contract_alignment": contract_report,
            },
        )

    def _validate_visual_contract_alignment(self, scenes: list[dict[str, Any]], visual_contract: dict[str, Any]) -> dict[str, Any]:
        if not scenes or not visual_contract:
            return {"checked": False, "reasons": []}
        reasons: list[str] = []
        ordered = sorted(scenes, key=lambda scene: int(scene.get("order", 0) or 0))
        first = ordered[0]
        hook_frame = visual_contract.get("hook_frame") if isinstance(visual_contract.get("hook_frame"), dict) else {}
        loop_policy = visual_contract.get("loop_policy") if isinstance(visual_contract.get("loop_policy"), dict) else {}
        payoff_frame = visual_contract.get("payoff_frame") if isinstance(visual_contract.get("payoff_frame"), dict) else {}
        expected_hook_intent = _normalized_text(hook_frame.get("recommended_visual_intent"))
        first_intent = _normalized_text(first.get("visual_intent"))
        if str(first.get("retention_role") or "").strip().lower() != "visual_hook":
            reasons.append("scene-1:visual_contract_hook_role_mismatch")
        if expected_hook_intent and first_intent != expected_hook_intent:
            reasons.append("scene-1:visual_contract_hook_intent_mismatch")
        first_corpus = _scene_corpus(first)
        first_visual_corpus = _scene_visual_corpus(first)
        must_show = _text_list(hook_frame.get("must_show"))
        if must_show and not any(_contains_required_term(first_corpus, item) for item in must_show):
            reasons.append("scene-1:visual_contract_hook_must_show_missing")
        for item in _text_list(hook_frame.get("must_hide")):
            if _contains_forbidden_term(first_visual_corpus, item):
                reasons.append("scene-1:visual_contract_hook_reveals_hidden_element")
                break
        early_scenes = [scene for scene in ordered[:-1] if str(scene.get("retention_role") or "").strip().lower() not in {"turn_or_payoff", "loop_close"}]
        for item in _text_list(loop_policy.get("forbidden_early_reveal")):
            if any(_contains_forbidden_term(_scene_corpus(scene), item) for scene in early_scenes):
                reasons.append("visual_contract_forbidden_early_reveal")
                break
        expected_payoff_intent = _normalized_text(payoff_frame.get("recommended_visual_intent"))
        if expected_payoff_intent:
            payoff_candidates = [
                scene
                for scene in ordered
                if str(scene.get("retention_role") or "").strip().lower() in {"turn_or_payoff", "loop_close"}
            ]
            if payoff_candidates and not any(_normalized_text(scene.get("visual_intent")) == expected_payoff_intent for scene in payoff_candidates):
                reasons.append("visual_contract_payoff_intent_mismatch")
        return {
            "checked": True,
            "reasons": reasons,
            "hook_expected_visual_intent": expected_hook_intent,
            "hook_actual_visual_intent": first_intent,
            "hook_must_show_count": len(must_show),
            "forbidden_early_reveal_count": len(_text_list(loop_policy.get("forbidden_early_reveal"))),
        }


def _scene_corpus(scene: dict[str, Any]) -> str:
    return _normalized_text(
        " ".join(
            str(scene.get(key) or "")
            for key in ("narration_text", "primary_subject", "topic_hint", "image_prompt", "visual_intent")
        )
    )


def _scene_visual_corpus(scene: dict[str, Any]) -> str:
    return _normalized_text(
        " ".join(
            str(scene.get(key) or "") for key in ("primary_subject", "image_prompt", "visual_intent")
        )
    )


def _disallowed_vertical_composition_hits(prompt: str) -> list[str]:
    normalized = _normalized_text(prompt)
    tokens = normalized.split()
    hits: list[str] = []
    for marker in sorted(DISALLOWED_VERTICAL_COMPOSITION_MARKERS):
        normalized_marker = _normalized_text(marker)
        if not normalized_marker:
            continue
        if _marker_present_unnegated(tokens, normalized_marker.split()):
            hits.append(marker)
    return hits


def _marker_present_unnegated(tokens: list[str], marker_tokens: list[str]) -> bool:
    if not marker_tokens:
        return False
    for index in range(0, len(tokens) - len(marker_tokens) + 1):
        if tokens[index : index + len(marker_tokens)] != marker_tokens:
            continue
        before = tokens[max(0, index - 4) : index]
        if any(token in NEGATION_TOKENS for token in before):
            continue
        return True
    return False


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _contains_required_term(corpus: str, term: str) -> bool:
    normalized = _normalized_text(term)
    if not normalized:
        return False
    if normalized in corpus:
        return True
    parts = [
        part
        for part in re.split(r"\s*(?:,|;|\be\b|\band\b|\bou\b|\bor\b)\s*", normalized)
        if part.strip()
    ]
    if len(parts) > 1:
        matches = sum(1 for part in parts if _contains_simple_term(corpus, part, loose=True))
        return matches >= min(2, len(parts))
    return _contains_simple_term(corpus, normalized, loose=True)


def _contains_forbidden_term(corpus: str, term: str) -> bool:
    normalized = _normalized_text(term)
    if not normalized:
        return False
    tokens = corpus.split()
    marker_tokens = normalized.split()
    if marker_tokens and _marker_present_unnegated(tokens, marker_tokens):
        return True
    return _contains_forbidden_simple_term(corpus, normalized)


def _contains_forbidden_simple_term(corpus: str, term: str) -> bool:
    """Strict containment for visual-contract spoilers.

    Forbidden reveal entries are often natural-language directives such as
    "diagramas de osmose" or "explicação escrita dos mecanismos". Matching a
    single surviving token ("osmose", "mecanismos") creates false positives
    whenever the approved narration itself mentions that concept before the
    payoff. For spoilers, require the complete directive or a near-complete set
    of substantive terms, not just one keyword.
    """
    tokens = [token for token in term.split() if len(token) >= 4]
    if not tokens:
        return False
    corpus_tokens = corpus.split()
    matched = 0
    for token in tokens:
        aliases = VISUAL_TERM_ALIASES.get(token, {token})
        if any(_alias_present_unnegated(corpus_tokens, alias) for alias in aliases):
            matched += 1
    if len(tokens) <= 4:
        return matched == len(tokens)
    return matched >= max(4, len(tokens) - 1)


def _contains_simple_term(corpus: str, term: str, *, loose: bool) -> bool:
    if term in corpus:
        return True
    tokens = [token for token in term.split() if len(token) >= 4]
    if not tokens:
        return False
    matched = 0
    corpus_tokens = corpus.split()
    for token in tokens:
        aliases = VISUAL_TERM_ALIASES.get(token, {token})
        if loose and any(alias in corpus for alias in aliases):
            matched += 1
        elif not loose and any(_alias_present_unnegated(corpus_tokens, alias) for alias in aliases):
            matched += 1
    if loose and len(tokens) >= 4:
        return matched >= 2
    if not loose and len(tokens) <= 2:
        return matched >= len(tokens)
    return matched >= max(1, len(tokens) - 1)


def _contains_term(corpus: str, term: str) -> bool:
    return _contains_required_term(corpus, term)


def _alias_present_unnegated(corpus_tokens: list[str], alias: str) -> bool:
    alias_tokens = alias.split()
    if not alias_tokens:
        return False
    for index in range(0, len(corpus_tokens) - len(alias_tokens) + 1):
        if corpus_tokens[index : index + len(alias_tokens)] != alias_tokens:
            continue
        before = corpus_tokens[max(0, index - 5) : index]
        if any(token in NEGATION_TOKENS for token in before):
            continue
        return True
    return False


def _normalized_text(value: Any) -> str:
    text = str(value or "").replace("_", " ").lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())
