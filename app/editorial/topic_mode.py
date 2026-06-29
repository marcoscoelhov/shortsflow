from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


STRICT_OVERRIDE_PATTERN = re.compile(
    r"\b(?:factual[_\s-]*strict|strict[_\s-]*fact|research[_\s-]*strict|com\s+fontes|lastro\s+factual|grounded)\b",
    re.IGNORECASE,
)

HIGH_RISK_TOPIC_PATTERN = re.compile(
    r"\b(?:sa[uú]de|m[eé]dico|medicina|doen[cç]a|doen[cç]as|tratamento|tratamentos|rem[eé]dio|remedios|medicamento|"
    r"medicamentos|suplemento|suplementos|dosagem|gravidez|gesta[cç][aã]o|c[aâ]ncer|diabetes|ansiedade|depress[aã]o|"
    r"cirurgia|sintoma|sintomas|anatomia\s+humana|corpo\s+humano|investimento|investimentos|a[cç][oõ]es|cripto|"
    r"criptomoeda|criptomoedas|imposto|impostos|lei|leis|legal|jur[ií]dico|crime|crimes|pol[ií]tica|elei[cç][aã]o|"
    r"elei[cç][oõ]es|seguran[cç]a|risco|perigo|morte|mortes|morto|mortos|acidente|acidentes|queda|ferido|feridos)\b",
    re.IGNORECASE,
)

SCIENCE_TOPIC_PATTERN = re.compile(
    r"\b(?:biologia|biol[oó]gic[oa]s?|cient[ií]fic[oa]s?|anatomia|fisiologia|esp[eé]cie|esp[eé]cies|evolu[cç][aã]o|"
    r"animal|animais|polvo|polvos|octopus|cora[cç][aã]o|cora[cç][oõ]es|br[aâ]nquias?|hemocianina|sangue\s+azul|"
    r"oxig[eê]nio|c[eé]lulas?|neur[oô]nios?|c[eé]rebro|dna|gene|bact[eé]ria|v[ií]rus)\b",
    re.IGNORECASE,
)

NEGATED_SCIENCE_CONTEXT_PATTERN = re.compile(
    r"\b(?:sem|nao|não)\s+(?:parecer\s+)?(?:explica[cç][aã]o\s+)?cient[ií]fic[oa]s?\b",
    re.IGNORECASE,
)

VISUAL_CRAFT_TOPIC_PATTERN = re.compile(
    r"\b(?:diorama|dioramas|maquete|maquetes|miniatura|miniaturas|model\s+city|miniature\s+city|"
    r"cidade\s+falsa|cidades\s+falsas|cidade\s+em\s+miniatura|cidades\s+em\s+miniatura)\b",
    re.IGNORECASE,
)

VISUAL_CRAFT_CONTEXT_PATTERN = re.compile(
    r"\b(?:visual|cinematogr[aá]fic[oa]|c[aâ]mera|camera|lente|escala|perspectiva|foto|imagem|"
    r"parece\s+real|parecem\s+reais|engana\s+o\s+olho|mesa|artesanal|craft)\b",
    re.IGNORECASE,
)

VISUAL_PERCEPTION_TERMS_PATTERN = re.compile(
    r"\b(?:c[eé]rebro|percep[cç][aã]o|olho|ilus[aã]o|[oó]tica)\b",
    re.IGNORECASE,
)


def _read_field(source: Any, field: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _is_visual_craft_context(source_text: str, requested_angle: str) -> bool:
    visual_text = " ".join(part for part in [source_text, requested_angle] if part)
    return bool(
        VISUAL_CRAFT_TOPIC_PATTERN.search(visual_text)
        and (
            NEGATED_SCIENCE_CONTEXT_PATTERN.search(visual_text)
            or VISUAL_CRAFT_CONTEXT_PATTERN.search(visual_text)
        )
    )


def resolve_editorial_mode(topic_plan: Any | None = None, request: Any | None = None) -> str:
    notes = str(_read_field(request, "notes", "") or "")
    requested_angle = str(_read_field(request, "requested_angle", "") or "")
    seed_theme = str(_read_field(request, "seed_theme", "") or "")
    canonical_topic = str(_read_field(topic_plan, "canonical_topic", "") or "")
    angle = str(_read_field(topic_plan, "angle", "") or "")
    hook_promise = str(_read_field(topic_plan, "hook_promise", "") or "")
    quality_metrics = _read_field(topic_plan, "quality_metrics", {}) or {}
    override_text = " ".join(part for part in [notes, requested_angle] if part).strip()
    if override_text and STRICT_OVERRIDE_PATTERN.search(override_text):
        return "factual_strict"
    source_text = " ".join(part for part in [seed_theme, canonical_topic, angle, hook_promise] if part).strip()
    source_text_for_risk = NEGATED_SCIENCE_CONTEXT_PATTERN.sub(" ", source_text)
    if source_text_for_risk and HIGH_RISK_TOPIC_PATTERN.search(source_text_for_risk):
        return "factual_strict"
    visual_craft_context = _is_visual_craft_context(source_text, requested_angle)
    source_text_for_science = source_text_for_risk
    if visual_craft_context:
        source_text_for_science = VISUAL_PERCEPTION_TERMS_PATTERN.sub(" ", source_text_for_science)
    if source_text_for_science and SCIENCE_TOPIC_PATTERN.search(source_text_for_science):
        return "factual_strict"
    if isinstance(quality_metrics, Mapping):
        existing_mode = str(quality_metrics.get("editorial_mode") or "").strip()
        if existing_mode == "factual_strict" and visual_craft_context:
            return "viral_curiosidades"
        if existing_mode in {"viral_curiosidades", "factual_strict"}:
            return existing_mode
    return "viral_curiosidades"
