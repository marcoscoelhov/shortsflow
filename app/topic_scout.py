from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.schemas import SUPPORTED_NICHES
from app.trends import TrendCandidate, TrendResearcher


@dataclass(frozen=True)
class EverydayCuriositySeed:
    topic: str
    requested_angle: str
    hook_seed: str
    visual_seed: str
    everyday_tags: tuple[str, ...]
    base_score: float = 0.84


EVERYDAY_CURIOSITY_POOL: tuple[EverydayCuriositySeed, ...] = (
    EverydayCuriositySeed(
        topic="Por que o pão fica duro e a bolacha fica mole?",
        requested_angle="Explicar, com visual de cozinha, que pão perde umidade enquanto bolacha absorve umidade do ar. Sem tom de aula; abrir com a contradição.",
        hook_seed="Pão e bolacha envelhecem ao contrário.",
        visual_seed="pão duro quebrando, bolacha mole dobrando, mesa de cozinha comum, close macro de textura",
        everyday_tags=("comida", "cozinha", "pão", "bolacha"),
        base_score=0.96,
    ),
    EverydayCuriositySeed(
        topic="Por que o espelho embaça no banho?",
        requested_angle="Conectar vapor quente, vidro frio e gotículas minúsculas em uma situação de banheiro familiar.",
        hook_seed="O espelho não fica sujo: ele vira uma tela de gotículas.",
        visual_seed="espelho embaçando no banheiro, vapor subindo, dedo abrindo faixa limpa no vidro",
        everyday_tags=("casa", "banho", "espelho", "vapor"),
        base_score=0.94,
    ),
    EverydayCuriositySeed(
        topic="Por que a roupa preta esquenta mais no sol?",
        requested_angle="Mostrar absorção de luz como sensação cotidiana: camiseta preta no sol versus roupa clara, sem virar aula de física.",
        hook_seed="A camiseta preta não só parece mais quente; ela captura mais luz.",
        visual_seed="duas camisetas no varal sob sol forte, mão tocando tecido preto quente, termômetro simples",
        everyday_tags=("roupa", "sol", "calor", "casa"),
        base_score=0.93,
    ),
    EverydayCuriositySeed(
        topic="Por que sentimos o celular vibrar sem ele vibrar?",
        requested_angle="Tratar a vibração fantasma como erro de expectativa do cérebro no bolso, visual e cotidiano.",
        hook_seed="Seu bolso pode mentir para o seu cérebro.",
        visual_seed="mão pegando celular no bolso, tela sem notificação, expressão de dúvida, close no bolso da calça",
        everyday_tags=("celular", "cérebro", "bolso", "notificação"),
        base_score=0.95,
    ),
    EverydayCuriositySeed(
        topic="Por que o cheiro de chuva aparece antes da chuva?",
        requested_angle="Explicar o cheiro familiar antes da chuva por poeira, solo e gotas chegando, com visual de rua/casa.",
        hook_seed="Às vezes seu nariz percebe a chuva antes da janela.",
        visual_seed="rua seca escurecendo, primeiras gotas no chão, pessoa na janela sentindo cheiro de chuva",
        everyday_tags=("chuva", "rua", "cheiro", "casa"),
        base_score=0.95,
    ),
    EverydayCuriositySeed(
        topic="Por que gelo estala dentro do copo?",
        requested_angle="Abrir com o estalo familiar do gelo no copo e explicar contração/choque térmico em linguagem simples.",
        hook_seed="O gelo no copo faz barulho porque está rachando por dentro.",
        visual_seed="cubo de gelo caindo em copo, rachaduras aparecendo, bebida gelada em close",
        everyday_tags=("gelo", "copo", "cozinha", "bebida"),
        base_score=0.92,
    ),
    EverydayCuriositySeed(
        topic="Por que algumas músicas grudam na cabeça?",
        requested_angle="Mostrar repetição, expectativa e loop mental com situação de rua/fone/cozinha, sem neurociência pesada.",
        hook_seed="Uma música pode prender sua cabeça com só um pedaço repetido.",
        visual_seed="pessoa com fone repetindo refrão, notas musicais abstratas discretas, rotina urbana",
        everyday_tags=("música", "memória", "fone", "rotina"),
        base_score=0.90,
    ),
    EverydayCuriositySeed(
        topic="Por que bocejo parece contagioso?",
        requested_angle="Usar cena cotidiana de uma pessoa bocejando e outra copiando, tratando como reflexo social sem prometer certeza absoluta.",
        hook_seed="Um bocejo pode atravessar a sala sem som nenhum.",
        visual_seed="duas pessoas no sofá, uma boceja e outra começa a bocejar, ambiente doméstico",
        everyday_tags=("sono", "corpo", "casa", "bocejo"),
        base_score=0.91,
    ),
    EverydayCuriositySeed(
        topic="Por que a tela do celular parece pior no sol?",
        requested_angle="Conectar brilho da tela, reflexo e luz ambiente numa cena comum de rua, com solução visual rápida.",
        hook_seed="No sol, seu celular perde uma briga de luz.",
        visual_seed="pessoa tentando ler celular sob sol forte, reflexo na tela, sombra feita com a mão",
        everyday_tags=("celular", "sol", "rua", "tela"),
        base_score=0.92,
    ),
    EverydayCuriositySeed(
        topic="Por que a água gelada sua por fora do copo?",
        requested_angle="Mostrar que a água do lado de fora veio do ar, não de dentro do copo, com visual de condensação.",
        hook_seed="O copo gelado parece vazar, mas a água vem do ar.",
        visual_seed="copo gelado com gotículas por fora, mesa de cozinha, dedo passando pelas gotas",
        everyday_tags=("água", "copo", "cozinha", "frio"),
        base_score=0.94,
    ),
)


@dataclass(frozen=True)
class TopicScoutResult:
    candidate: TrendCandidate
    considered_count: int
    rejected_recent_count: int


class TopicScout:
    """Pick viral curiosity topics for empty requests, favoring everyday familiarity.

    This intentionally does not rely only on live trends. Google Trends is noisy
    for Shorts; the curated everyday pool provides reliable day-to-day hooks
    whenever live trends are too newsy, sports-heavy, obscure, or repetitive.
    """

    def __init__(self, trend_researcher: Any | None = None, *, rng: random.Random | None = None) -> None:
        self.trend_researcher = trend_researcher or TrendResearcher()
        self.rng = rng or random.Random()

    def find_topic(self, niche_id: str = "curiosidades", recent_topics: Iterable[str] = ()) -> TopicScoutResult | None:
        if niche_id not in SUPPORTED_NICHES:
            return None
        recent = [topic for topic in recent_topics if str(topic or "").strip()]
        candidates = [self._candidate_from_seed(seed) for seed in EVERYDAY_CURIOSITY_POOL]
        trend = self.trend_researcher.find_topic(niche_id)
        if trend is not None:
            candidates.append(self._rescore_trend(trend))
        ranked: list[tuple[TrendCandidate, float]] = []
        rejected_recent = 0
        for candidate in candidates:
            similarity = max((_similarity(candidate.topic, topic) for topic in recent), default=0.0)
            if similarity >= 0.62:
                rejected_recent += 1
                continue
            recency_penalty = similarity * 0.55
            source_bonus = 0.05 if candidate.source == "everyday_curiosity_pool" else 0.0
            jitter = self.rng.random() * 0.015
            ranked.append((candidate, candidate.score + source_bonus + jitter - recency_penalty))
        if not ranked:
            ranked = [(self._candidate_from_seed(seed), seed.base_score) for seed in EVERYDAY_CURIOSITY_POOL]
        best = max(ranked, key=lambda item: item[1])[0]
        return TopicScoutResult(best, considered_count=len(candidates), rejected_recent_count=rejected_recent)

    def _candidate_from_seed(self, seed: EverydayCuriositySeed) -> TrendCandidate:
        return TrendCandidate(
            topic=seed.topic,
            requested_angle=seed.requested_angle,
            source="everyday_curiosity_pool",
            source_url="local://everyday-curiosity-pool",
            score=seed.base_score,
            raw_title=seed.topic,
            familiarity_score=1.0,
            source_title=seed.topic,
            hook_seed=seed.hook_seed,
            visual_seed=seed.visual_seed,
            why=["cotidiano", "visual_simples", "baixo_risco_factual", *seed.everyday_tags[:2]],
        )

    def _rescore_trend(self, trend: TrendCandidate) -> TrendCandidate:
        normalized = _normalize(trend.source_title or trend.raw_title or trend.topic)
        everyday_bonus = 0.16 if any(term in normalized for term in ["agua", "chuva", "calor", "sono", "cafe", "celular", "casa", "comida", "olho", "pele"]) else 0.0
        science_penalty = 0.18 if any(term in normalized for term in ["buraco negro", "planeta", "nasa", "asteroide", "quantico", "quantica"]) else 0.0
        score = min(0.97, max(0.20, 0.58 + trend.familiarity_score * 0.22 + everyday_bonus - science_penalty))
        return TrendCandidate(
            topic=trend.topic,
            requested_angle=(
                f"Usar a tendência real '{trend.source_title or trend.raw_title}' só como gancho se ela conectar com algo cotidiano. "
                "Evitar tom científico abstrato; transformar em pergunta familiar, visual e verificável."
            ),
            source=trend.source,
            source_url=trend.source_url,
            score=score,
            raw_title=trend.raw_title,
            familiarity_score=trend.familiarity_score,
            source_title=trend.source_title,
            hook_seed=getattr(trend, "hook_seed", None),
            visual_seed=getattr(trend, "visual_seed", None),
            why=["tendencia_real", "filtrada_para_cotidiano"],
        )


def _normalize(text: str) -> str:
    replacements = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return str(text or "").lower().translate(replacements)


def _tokens(text: str) -> set[str]:
    blocked = {"por", "que", "como", "para", "com", "uma", "umas", "uns", "dos", "das", "sem", "antes", "depois", "voce", "você"}
    return {token for token in re.findall(r"[a-z0-9à-ÿ]+", _normalize(text)) if len(token) >= 4 and token not in blocked}


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
