from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.utils import word_tokens

SHOCK_SIGNAL_PATTERN = re.compile(
    r"\b(?:não|nunca|ningu[eé]m|parece|imposs[ií]vel|estranho|segredo|rouba|esconde|fogo|incendia|explode|mata|desaparece|antes|mesmo|s[oó]\s+que|quase|o\s+que\s+sobra|domina|prende|prendeu|persegu\w*|grud\w*|martela|trav[ao]|armadilha|vaza|molha|basta|nunca acaba|briga|luta|some|sumi[ur]|racha|estala|truque|atravessa|invis[ií]vel|pula[rr]?)\b",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(r"[?]|\b(?:por que|porque|como|se\b|o que|qual|quem)\b", re.IGNORECASE)
TENSION_PATTERN = re.compile(
    r"\b(?:mas|s[oó]\s+que|antes|depois|quando|enquanto|por isso|então|segredo|sobra|desaparece|rouba|filtra|revela|parece|fica|vira|mesmo|sem querer|continua|tenta|insiste|nunca|ainda)\b",
    re.IGNORECASE,
)
VISUAL_IMPACT_PATTERN = re.compile(
    r"\b(?:fogo|incendiar|laranja|vermelh[oa]|azul|horizonte|gigante|corredor|luz|brilho|reflexo|reflexos|pixel|tela|celular|sol|olho|c[eé]u|atmosfera|sombra|pele|sangue|cora[cç][aã]o|explod|brilha|escuro|close|detalhe|fone|rua|cozinha|copo|gota|gotas|ch[aã]o|chuva|refr[aã]o|cabe[cç]a|vidro|poeira|gelo|cubo|estalo|rachadura|rachaduras|azulejo|tapete|p[eé]|calor|p[aã]o|bolacha|bocejo|boceja\w*|sof[aá]|rosto|sala|elevador)\b",
    re.IGNORECASE,
)
SHARE_TRIGGER_PATTERN = re.compile(
    r"\b(?:da pr[oó]xima vez|lembra|voc[eê] est[aá] vendo|isso muda|repara|olha de novo|volta para|primeira imagem|segunda olhada|nunca mais|quando voc[eê] vir|em tempo real|vai lembrar|j[aá] deve|manda isso|mostra isso|toda vez que|se amanh[aã]|n[aã]o [eé] falta|nunca acaba|se .*grud)\b",
    re.IGNORECASE,
)
IMPLICIT_GAP_PATTERN = re.compile(
    r"\b(?:basta|persegu\w*|grud\w*|sem parar|sem querer|n[aã]o sai|volta sem pedir|insiste|armadilha|por fora|antes da primeira|briga de luz|luta imposs[ií]vel|parece vazar|n[aã]o [eé].{0,40}batendo|racha por dentro|nunca esteve dentro|sem som nenhum|espalhar t[aã]o r[aá]pido|copia sem|reflexo invis[ií]vel)\b",
    re.IGNORECASE,
)
REWATCH_PAYOFF_PATTERN = re.compile(
    r"\b(?:volta para|primeira imagem|primeira cena|primeira frase|come[cç]o|in[ií]cio|segunda olhada|olha de novo|ver de novo)\b",
    re.IGNORECASE,
)
CONTRAST_GAP_PATTERN = re.compile(
    r"\b(?:n[aã]o [eé]|parece .{0,30}mas|segredo|truque|na verdade)\b",
    re.IGNORECASE,
)
DIDACTIC_PATTERN = re.compile(
    r"\b(?:explica|explicação|explicacao|é causado por|ocorre quando|processo|fen[oô]meno|ajuda a revelar|isso acontece|de forma|componente|part[ií]culas menores|camada mais espessa|efeito visual|observa[cç][aã]o|cient[ií]fica)\b",
    re.IGNORECASE,
)
NEUTRAL_OPENING_PATTERN = re.compile(
    r"^\s*(?:quando|durante|em\s+geral|no\s+caso|na\s+pr[aá]tica|por\s+que\s+o)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ViralIntensityResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class ViralIntensityGate:
    """Reject scripts that are technically clean but too neutral to chase growth.

    This is intentionally heuristic and deterministic: it catches obvious
    didactic/morno scripts before expensive visual/audio steps. Provider audits
    can still add deeper semantic judgment later, but this gate gives the
    pipeline a hard anti-boredom floor.
    """

    MIN_VIRAL_INTENSITY = 0.80
    MIN_HOOK_SCROLL_STOP = 0.90
    MIN_CURIOSITY_GAP = 0.75
    MIN_ESCALATION = 0.70
    MIN_PAYOFF_SURPRISE = 0.55
    MIN_SHARE_TRIGGER = 0.55

    def validate(self, script: dict[str, Any]) -> ViralIntensityResult:
        title = str(script.get("title") or "")
        hook = str(script.get("hook") or "")
        loop = str(script.get("loop") or self._retention_loop_text(script) or "")
        ending = str(script.get("ending") or "")
        payoff = str(script.get("payoff") or "")
        body_beats = [str(item) for item in script.get("body_beats") or [] if str(item).strip()]
        narration = str(script.get("full_narration") or " ".join([hook, loop, *body_beats, payoff, ending]))

        first_sentence = hook or self._first_sentence(narration)
        all_text = " ".join([title, hook, loop, *body_beats, payoff, ending, narration])
        text_words = word_tokens(all_text)
        unique_words = set(text_words)

        shock_hits = self._count_matches(SHOCK_SIGNAL_PATTERN, first_sentence)
        title_shock_hits = self._count_matches(SHOCK_SIGNAL_PATTERN, title)
        tension_hits = self._count_matches(TENSION_PATTERN, all_text)
        visual_hits = self._count_matches(VISUAL_IMPACT_PATTERN, all_text)
        share_hits = self._count_matches(SHARE_TRIGGER_PATTERN, " ".join([payoff, ending, narration]))
        didactic_hits = self._count_matches(DIDACTIC_PATTERN, all_text)
        implicit_gap = bool(IMPLICIT_GAP_PATTERN.search(" ".join([title, first_sentence, loop, narration[:260]])))
        contrast_gap = bool(CONTRAST_GAP_PATTERN.search(" ".join([first_sentence, loop, narration[:220]])))
        question_hits = self._count_matches(QUESTION_PATTERN, " ".join([first_sentence, loop, narration[:220]]))

        hook_word_count = len(word_tokens(first_sentence))
        hook_scroll_stop_score = self._clamp(
            0.22
            + min(0.38, shock_hits * 0.19 + title_shock_hits * 0.08)
            + min(0.22, visual_hits * 0.045)
            + (0.18 if not NEUTRAL_OPENING_PATTERN.search(first_sentence) else -0.18)
            + (0.10 if 7 <= hook_word_count <= 24 else -0.08)
        )
        curiosity_gap_score = self._clamp(
            0.24
            + min(0.35, question_hits * 0.18)
            + min(0.25, tension_hits * 0.035)
            + (0.18 if loop else 0.0)
            + (0.25 if implicit_gap else 0.0)
            + (0.10 if contrast_gap else 0.0)
            + (0.10 if shock_hits else 0.0)
        )
        escalation_score = self._clamp(
            0.22
            + min(0.30, len(body_beats) * 0.075)
            + min(0.24, tension_hits * 0.03)
            + min(0.18, visual_hits * 0.025)
            + (0.08 if len(unique_words) >= 45 else -0.05)
        )
        payoff_text = " ".join([payoff, ending])
        payoff_surprise_score = self._clamp(
            0.18
            + min(0.30, self._count_matches(SHOCK_SIGNAL_PATTERN, payoff_text) * 0.15)
            + min(0.22, self._count_matches(VISUAL_IMPACT_PATTERN, payoff_text) * 0.045)
            + min(0.14, self._count_matches(TENSION_PATTERN, payoff_text) * 0.035)
            + (0.18 if self._shares_salient_terms(first_sentence, ending) else 0.0)
            + (0.14 if SHARE_TRIGGER_PATTERN.search(ending) else 0.0)
            + (0.10 if REWATCH_PAYOFF_PATTERN.search(ending) else 0.0)
        )
        share_trigger_score = self._clamp(0.20 + min(0.45, share_hits * 0.18) + min(0.24, visual_hits * 0.018))
        didactic_penalty = min(0.28, didactic_hits * 0.035)
        neutral_penalty = 0.12 if NEUTRAL_OPENING_PATTERN.search(first_sentence) else 0.0
        viral_intensity_score = self._clamp(
            hook_scroll_stop_score * 0.28
            + curiosity_gap_score * 0.22
            + escalation_score * 0.18
            + payoff_surprise_score * 0.17
            + share_trigger_score * 0.15
            - didactic_penalty
            - neutral_penalty
        )

        reasons: list[str] = []
        if didactic_hits >= 3 or (didactic_hits >= 2 and NEUTRAL_OPENING_PATTERN.search(first_sentence)):
            reasons.append("didactic_or_neutral_tone")
        if hook_scroll_stop_score < self.MIN_HOOK_SCROLL_STOP:
            reasons.append("hook_not_scroll_stopping")
        if curiosity_gap_score < self.MIN_CURIOSITY_GAP:
            reasons.append("weak_curiosity_gap")
        if escalation_score < self.MIN_ESCALATION:
            reasons.append("weak_escalation")
        if payoff_surprise_score < self.MIN_PAYOFF_SURPRISE:
            reasons.append("predictable_payoff")
        if share_trigger_score < self.MIN_SHARE_TRIGGER:
            reasons.append("weak_share_trigger")
        if viral_intensity_score < self.MIN_VIRAL_INTENSITY:
            reasons.append("viral_intensity_below_threshold")

        metrics = {
            "viral_intensity_gate_pass": not reasons,
            "viral_intensity_score": round(viral_intensity_score, 3),
            "hook_scroll_stop_score": round(hook_scroll_stop_score, 3),
            "curiosity_gap_score": round(curiosity_gap_score, 3),
            "escalation_score": round(escalation_score, 3),
            "payoff_surprise_score": round(payoff_surprise_score, 3),
            "share_trigger_score": round(share_trigger_score, 3),
            "didactic_marker_count": didactic_hits,
            "shock_signal_count": shock_hits + title_shock_hits,
            "tension_signal_count": tension_hits,
            "visual_impact_signal_count": visual_hits,
            "implicit_gap_signal": implicit_gap,
            "contrast_gap_signal": contrast_gap,
        }
        return ViralIntensityResult(passed=not reasons, reasons=list(dict.fromkeys(reasons)), metrics=metrics)

    def _retention_loop_text(self, script: dict[str, Any]) -> str:
        retention_map = script.get("retention_map") if isinstance(script.get("retention_map"), dict) else {}
        candidates: list[str] = []
        for key in ("proof_or_tension", "turn_or_payoff"):
            value = retention_map.get(key)
            if isinstance(value, dict):
                candidates.append(str(value.get("mapped_text") or value.get("text") or value.get("narration") or ""))
            elif isinstance(value, str):
                candidates.append(value)
        for segment in retention_map.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            if str(segment.get("code") or "") in {"proof_or_tension", "turn_or_payoff"}:
                candidates.append(str(segment.get("mapped_text") or segment.get("text") or segment.get("narration") or ""))
        return " ".join(item for item in candidates if item).strip()

    def _first_sentence(self, text: str) -> str:
        match = re.search(r"^(.+?[.!?])(?:\s|$)", text.strip())
        return match.group(1) if match else text.strip()

    def _count_matches(self, pattern: re.Pattern[str], text: str) -> int:
        return len(pattern.findall(text or ""))

    def _shares_salient_terms(self, opening: str, ending: str) -> bool:
        opening_terms = {token for token in word_tokens(opening) if len(token) >= 5}
        ending_terms = {token for token in word_tokens(ending) if len(token) >= 5}
        return bool(opening_terms & ending_terms)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))
