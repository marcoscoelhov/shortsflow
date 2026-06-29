from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


ASTRONOMY_NICHE = "astronomia"
ASTRONOMY_ALLOWED_KEYWORDS = (
    "astronomia",
    "universo",
    "cosmos",
    "espaço",
    "sistema solar",
    "planeta",
    "planetas",
    "estrela",
    "estrelas",
    "galáxia",
    "galáxias",
    "buraco negro",
    "buracos negros",
    "lua",
    "luas",
    "exoplaneta",
    "exoplanetas",
    "sol",
    "meteoro",
    "meteorito",
    "asteroide",
    "cometa",
    "nebulosa",
    "supernova",
    "eclipse",
    "NASA",
    "telescópio",
    "telescópios",
    "sonda",
    "foguete",
    "satélite",
    "órbita",
    "cosmologia",
    "ciência espacial",
    "tecnologia espacial",
)
ESSENTIAL_ASTRONOMY_KEYWORDS = {keyword.casefold() for keyword in ASTRONOMY_ALLOWED_KEYWORDS}

_ASTRONOMY_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("buracos_negros", r"\b(?:buraco\s+negro|buracos\s+negros|singularidade|horizonte\s+de\s+eventos|disco\s+de\s+acrecao)\b", "buracos negros"),
    ("exoplanetas", r"\b(?:exoplaneta|exoplanetas|planeta\s+fora\s+do\s+sistema\s+solar|mundos?\s+distantes?)\b", "exoplanetas"),
    ("luas", r"\b(?:lua|luas|lunar|europa|ganimedes|tita|encelado|io)\b", "luas"),
    ("planetas", r"\b(?:planeta|planetas|mercurio|venus|terra|marte|jupiter|saturno|urano|netuno|sistema\s+solar)\b", "planetas"),
    ("estrelas", r"\b(?:estrela|estrelas|sol|solar|supernova|ana\s+branca|gigante\s+vermelha|nebulosa)\b", "estrelas"),
    ("galaxias", r"\b(?:galaxia|galaxias|via\s+lactea|andromeda)\b", "galáxias"),
    ("fenomenos_espaciais", r"\b(?:meteoro|meteorito|asteroide|cometa|eclipse|aurora|orbita|gravidade|atmosfera\s+terrestre)\b", "fenômenos espaciais"),
    ("tecnologia_espacial", r"\b(?:nasa|esa|spacex|telescopio|telescopios|james\s+webb|hubble|sonda|satelite|satelites|foguete|foguetes|missao\s+espacial|tecnologia\s+espacial)\b", "tecnologia espacial"),
    ("cosmologia", r"\b(?:universo|cosmos|cosmologia|big\s+bang|materia\s+escura|energia\s+escura|espaco\s+profundo|espacial)\b", "cosmologia"),
)

_INCOMPATIBLE_FORBIDDEN_BY_NICHE: dict[str, tuple[str, ...]] = {
    ASTRONOMY_NICHE: (),
}


@dataclass(frozen=True)
class NicheClassification:
    niche: str
    subniche: str
    allowed_keywords: tuple[str, ...]
    forbidden_keywords: tuple[str, ...]
    matched_terms: tuple[str, ...]
    source: str

    def as_quality_metrics(self) -> dict[str, object]:
        return {
            "topic_niche": self.niche,
            "topic_subniche": self.subniche,
            "allowed_keywords": list(self.allowed_keywords),
            "forbidden_keywords": list(self.forbidden_keywords),
            "niche_matched_terms": list(self.matched_terms),
            "niche_source": self.source,
        }

    def as_contract(self) -> dict[str, object]:
        return {
            "niche": self.niche,
            "subniche": self.subniche,
            "allowed_keywords": list(self.allowed_keywords),
            "forbidden_keywords": list(self.forbidden_keywords),
            "matched_terms": list(self.matched_terms),
            "source": self.source,
        }


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _dedupe_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.casefold().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value.strip())
    return tuple(result)


def classify_niche_contract(*texts: object, fallback_niche: str = "curiosidades") -> NicheClassification:
    source_text = " ".join(str(text or "") for text in texts if text is not None)
    normalized = _normalize_text(source_text)
    matched_subniches: list[str] = []
    matched_terms: list[str] = []
    for subniche, pattern, label in _ASTRONOMY_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            matched_subniches.append(subniche)
            matched_terms.append(label)

    cosmos_policy = "cosmos_astronomia_universo_first" in normalized or "automatic_topic_focus=astronomia" in normalized
    if matched_subniches or cosmos_policy:
        if "tecnologia_espacial" in matched_subniches:
            subniche = "tecnologia_espacial"
        elif matched_subniches:
            subniche = matched_subniches[0]
        else:
            subniche = "astronomia_geral"
        allowed = _dedupe_preserve_order([*ASTRONOMY_ALLOWED_KEYWORDS, *matched_terms])
        forbidden = tuple(
            keyword
            for keyword in _INCOMPATIBLE_FORBIDDEN_BY_NICHE.get(ASTRONOMY_NICHE, ())
            if keyword.casefold() not in ESSENTIAL_ASTRONOMY_KEYWORDS
        )
        return NicheClassification(
            niche=ASTRONOMY_NICHE,
            subniche=subniche,
            allowed_keywords=allowed,
            forbidden_keywords=forbidden,
            matched_terms=_dedupe_preserve_order(matched_terms or ["astronomia"]),
            source="astronomy_keyword_contract",
        )

    return NicheClassification(
        niche=(fallback_niche or "curiosidades").strip() or "curiosidades",
        subniche="geral",
        allowed_keywords=(),
        forbidden_keywords=(),
        matched_terms=(),
        source="fallback_niche",
    )
