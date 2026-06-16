from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from app.utils import word_tokens


PROTECTED_SHORT_TERMS = {"mel", "pisa"}
GENERIC_RESEARCH_TERMS = {
    "about",
    "ainda",
    "algo",
    "algum",
    "alguma",
    "angle",
    "apenas",
    "auto",
    "causa",
    "causas",
    "como",
    "comportamento",
    "contraintuitivo",
    "curiosidade",
    "curiosidades",
    "dado",
    "dados",
    "detail",
    "detalhe",
    "detalhes",
    "direta",
    "direto",
    "efeito",
    "efeitos",
    "engana",
    "entende",
    "entender",
    "explica",
    "explicar",
    "explicando",
    "explicacao",
    "explicacoes",
    "fact",
    "facts",
    "fenomeno",
    "fenomenos",
    "fica",
    "ficam",
    "fisiologica",
    "fisiologico",
    "fisiologicas",
    "fisiologicos",
    "geral",
    "hook",
    "imagens",
    "mecanismo",
    "mecanismos",
    "muda",
    "nada",
    "olhar",
    "parece",
    "parecem",
    "parecer",
    "percebe",
    "perspectiva",
    "pesquisa",
    "porque",
    "por",
    "promise",
    "promessa",
    "prometido",
    "pelo",
    "query",
    "qual",
    "question",
    "para",
    "real",
    "recorte",
    "reconfigura",
    "research",
    "resultado",
    "review",
    "safe",
    "science",
    "scientific",
    "search",
    "segredo",
    "short",
    "shorts",
    "sobre",
    "forma",
    "intrigante",
    "study",
    "tema",
    "topic",
    "user",
    "video",
    "videos",
}


def _read_field(source: Any, field: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def normalize_research_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def research_tokens(text: str, ignored_terms: set[str] | None = None) -> list[str]:
    ignored = ignored_terms or set()
    tokens: list[str] = []
    seen: set[str] = set()
    for token in word_tokens(normalize_research_text(text)):
        if token in seen:
            continue
        if len(token) < 4 and token not in PROTECTED_SHORT_TERMS:
            continue
        if token in GENERIC_RESEARCH_TERMS or token in ignored:
            continue
        tokens.append(token)
        seen.add(token)
    return tokens


def _infer_claim_scope(seed_theme: str, canonical_topic: str, angle: str, hook_promise: str) -> str:
    scope_text = " ".join([seed_theme, canonical_topic, angle, hook_promise]).lower()
    visual_craft_topic = re.search(
        r"\b(?:diorama|dioramas|maquete|maquetes|miniatura|miniaturas|cidade\s+falsa|cidade\s+em\s+miniatura)\b",
        scope_text,
    )
    visual_craft_context = re.search(
        r"\b(?:visual|cinematografico|cinematográfico|camera|câmera|lente|escala|perspectiva|foto|imagem|"
        r"parece\s+real|engana\s+o\s+olho|mesa|artesanal|sem\s+(?:explicacao|explicação)\s+cientifica|"
        r"sem\s+(?:explicacao|explicação)\s+científica)\b",
        scope_text,
    )
    if visual_craft_topic and visual_craft_context:
        return "visual_craft_observation"
    if re.search(r"\b(?:por que|porque|como|mecanismo|explica|causa|funciona|bloqueia|ativa)\b", scope_text):
        return "explanatory_mechanism"
    if re.search(r"\b(?:origem|historia|história|quando|quem|fundacao|fundação|surgiu|ordem)\b", scope_text):
        return "historical_origin"
    if re.search(r"\b(?:dados|numero|número|estatistica|estatística|crescimento|percentual|taxa)\b", scope_text):
        return "descriptive_evidence"
    return "general_curiosity"


def _infer_evidence_profile(seed_theme: str, canonical_topic: str, angle: str, hook_promise: str, entities: list[str]) -> str:
    scope_text = normalize_research_text(" ".join([seed_theme, canonical_topic, angle, hook_promise, *entities]))
    tokens = set(word_tokens(scope_text))
    if tokens & {"sono", "sleep", "sonolencia", "sleepiness", "vigilia", "wakefulness", "insomnia"}:
        return "saude_biologia"
    if tokens & {"corpo", "cerebro", "brain", "hormonio", "hormone", "molecular", "receptor", "biologia", "biology"}:
        return "saude_biologia"
    if tokens & {"origem", "historia", "historico", "cultura", "cultural", "museu", "arquivo"}:
        return "historia_cultura"
    if tokens & {"preco", "valor", "regra", "lei", "taxa", "dados", "estatistica", "percentual"}:
        return "dados_atuais"
    if tokens & {"celular", "aplicativo", "app", "plataforma", "produto", "marca", "fabricante"}:
        return "produto_plataforma"
    if tokens & {"mecanismo", "funciona", "bloqueia", "ativa", "engenharia", "tecnico", "tecnica"}:
        return "explicacao_tecnica"
    return "cotidiano_observacional"


def _required_evidence_term_groups(seed_theme: str, canonical_topic: str, angle: str, hook_promise: str, entities: list[str], search_terms: list[str]) -> list[dict[str, Any]]:
    scope_tokens = set(research_tokens(" ".join([seed_theme, canonical_topic, angle, hook_promise, *entities, *search_terms])))
    groups: list[dict[str, Any]] = []
    caffeine_terms = {"cafe", "coffee", "cafeina", "caffeine", "adenosina", "adenosine"}
    sleep_terms = {
        "sono",
        "sleep",
        "sleepiness",
        "sonolencia",
        "vigilia",
        "wakefulness",
        "latency",
        "insomnia",
        "cansaco",
        "fatigue",
        "rebound",
        "pressure",
    }
    if scope_tokens & caffeine_terms and scope_tokens & sleep_terms:
        groups.append(
            {
                "name": "coffee_sleep_scope",
                "terms": sorted(sleep_terms),
                "description": "Fonte sobre cafeina/adenosina precisa cobrir sono, vigilia, sonolencia, latencia ou rebote para sustentar esse recorte.",
            }
        )
    return groups


def build_research_brief(topic_plan: Any, request: Any) -> dict[str, Any]:
    canonical_topic = str(_read_field(topic_plan, "canonical_topic", "") or _read_field(request, "seed_theme", "")).strip()
    angle = str(_read_field(topic_plan, "angle", "") or _read_field(request, "requested_angle", "") or "").strip()
    hook_promise = str(_read_field(topic_plan, "hook_promise", "") or "").strip()
    seed_theme = str(_read_field(request, "seed_theme", "") or canonical_topic).strip()
    entities = _read_field(topic_plan, "entities", []) or []
    if isinstance(entities, str):
        entities = [entities]
    entities = [str(entity).strip() for entity in entities if str(entity).strip()]
    search_terms = _read_field(topic_plan, "search_terms", []) or []
    if isinstance(search_terms, str):
        search_terms = [search_terms]
    search_terms = [str(term).strip() for term in search_terms if str(term).strip()][:8]

    primary_terms = _expand_primary_aliases(research_tokens(" ".join([seed_theme, canonical_topic, *entities]))[:8])
    mechanism_seed_terms = research_tokens(" ".join([angle, hook_promise]))
    mechanism_terms: list[str] = []
    seen_mechanism: set[str] = set()
    for token in [*mechanism_seed_terms, *research_tokens(" ".join(search_terms))]:
        if token in primary_terms or token in seen_mechanism:
            continue
        mechanism_terms.append(token)
        seen_mechanism.add(token)
        if len(mechanism_terms) >= 8:
            break

    search_term_groups: list[dict[str, Any]] = []
    for term in search_terms:
        tokens = research_tokens(term)
        if not tokens:
            continue
        non_primary_terms = [token for token in tokens if token not in primary_terms]
        search_term_groups.append(
            {
                "query": term,
                "tokens": tokens[:6],
                "non_primary_terms": non_primary_terms[:4],
            }
        )

    claim_scope = _infer_claim_scope(seed_theme, canonical_topic, angle, hook_promise)
    evidence_profile = _infer_evidence_profile(seed_theme, canonical_topic, angle, hook_promise, entities)
    required_evidence_term_groups = _required_evidence_term_groups(seed_theme, canonical_topic, angle, hook_promise, entities, search_terms)
    require_mechanism_match = claim_scope in {"explanatory_mechanism", "historical_origin", "descriptive_evidence"} and bool(
        mechanism_terms or search_term_groups
    )

    return {
        "focus_topic": canonical_topic,
        "seed_theme": seed_theme,
        "angle": angle,
        "hook_promise": hook_promise,
        "claim_scope": claim_scope,
        "evidence_profile": evidence_profile,
        "primary_entities": entities[:5] or [canonical_topic],
        "primary_terms": primary_terms,
        "mechanism_terms": mechanism_terms,
        "required_evidence_term_groups": required_evidence_term_groups,
        "supporting_search_terms": search_terms,
        "search_term_groups": search_term_groups,
        "require_primary_match": bool(primary_terms),
        "require_mechanism_match": require_mechanism_match,
    }


def _expand_primary_aliases(primary_terms: list[str]) -> list[str]:
    aliases = {
        "cafe": ["coffee", "caffeine"],
        "cafeina": ["caffeine"],
        "mel": ["honey", "honeys"],
        "arrepios": ["arrepio", "goosebumps", "chills", "frisson", "piloerection"],
        "arrepio": ["arrepios", "goosebumps", "chills", "frisson", "piloerection"],
        "musica": ["music", "musical"],
        "musical": ["music", "musica"],
        "dopamina": ["dopamine"],
        "pilomotor": ["piloerection"],
    }
    expanded: list[str] = []
    seen: set[str] = set()
    for term in primary_terms:
        for candidate in [term, *aliases.get(term, [])]:
            if candidate in seen:
                continue
            expanded.append(candidate)
            seen.add(candidate)
    return expanded[:12]


def audit_source_relevance(research_brief: dict[str, Any], title: str, extract: str) -> dict[str, Any]:
    source_tokens = set(research_tokens(f"{title} {extract[:800]}"))
    primary_terms = set(research_brief.get("primary_terms") or [])
    mechanism_terms = set(research_brief.get("mechanism_terms") or [])
    primary_overlap = sorted(primary_terms & source_tokens)
    mechanism_overlap = sorted(mechanism_terms & source_tokens)

    group_hits: list[dict[str, Any]] = []
    strong_group_hits = 0
    group_token_counts: dict[str, int] = {}
    for group in research_brief.get("search_term_groups") or []:
        query = str(group.get("query") or "")
        tokens = [str(token) for token in (group.get("tokens") or []) if str(token)]
        if not tokens:
            continue
        group_token_counts[query] = len(tokens)
        overlap = sorted(set(tokens) & source_tokens)
        if not overlap:
            continue
        non_primary_terms = [str(token) for token in (group.get("non_primary_terms") or []) if str(token)]
        matched_non_primary_terms = sorted(set(non_primary_terms) & source_tokens)
        matched_primary_terms = sorted((set(tokens) & primary_terms) & source_tokens)
        threshold = 1 if len(tokens) <= 1 else (2 if len(tokens) <= 3 else 3)
        is_strong = len(overlap) >= threshold and bool(matched_non_primary_terms or not non_primary_terms)
        if is_strong:
            strong_group_hits += 1
        group_hits.append(
            {
                "query": group.get("query"),
                "matched_terms": overlap,
                "matched_primary_terms": matched_primary_terms,
                "matched_non_primary_terms": matched_non_primary_terms,
                "strong_match": is_strong,
            }
        )

    mechanism_required = bool(research_brief.get("require_mechanism_match"))
    missing_required_groups: list[dict[str, Any]] = []
    for group in research_brief.get("required_evidence_term_groups") or []:
        terms = {str(term) for term in (group.get("terms") or []) if str(term)}
        matched_terms = sorted(terms & source_tokens)
        if not matched_terms:
            missing_required_groups.append({"name": group.get("name"), "terms": sorted(terms)})
    if mechanism_required and research_brief.get("claim_scope") == "explanatory_mechanism":
        mechanism_pass = strong_group_hits > 0
    else:
        mechanism_pass = strong_group_hits > 0 or len(mechanism_overlap) >= (2 if mechanism_required else 1)
    primary_pass = (
        not research_brief.get("require_primary_match")
        or bool(primary_overlap)
        or any(
            bool(hit.get("strong_match"))
            and (
                bool(hit.get("matched_primary_terms"))
                or len(hit.get("matched_terms") or []) >= group_token_counts.get(str(hit.get("query") or ""), 0)
            )
            for hit in group_hits
        )
    )

    required_evidence_pass = not missing_required_groups
    passed = primary_pass and required_evidence_pass and (mechanism_pass or not mechanism_required)
    reason = "matched_research_brief"
    if not primary_pass:
        reason = "missing_primary_topic_terms"
    elif not required_evidence_pass:
        reason = "missing_promised_mechanism_terms"
    elif mechanism_required and not mechanism_pass:
        reason = "missing_promised_mechanism_terms"

    return {
        "passed": passed,
        "reason": reason,
        "claim_scope": research_brief.get("claim_scope"),
        "evidence_profile": research_brief.get("evidence_profile"),
        "primary_terms": sorted(primary_terms),
        "mechanism_terms": sorted(mechanism_terms),
        "required_evidence_term_groups": research_brief.get("required_evidence_term_groups") or [],
        "missing_required_evidence_term_groups": missing_required_groups,
        "primary_overlap": primary_overlap,
        "mechanism_overlap": mechanism_overlap,
        "strong_group_hit_count": strong_group_hits,
        "group_hits": group_hits[:5],
    }
