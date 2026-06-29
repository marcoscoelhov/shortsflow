from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Iterable

from app.trends import TrendCandidate


@dataclass(frozen=True)
class CosmosCuriositySeed:
    topic: str
    requested_angle: str
    hook_seed: str
    visual_seed: str
    tags: tuple[str, ...]
    base_score: float = 0.90


COSMOS_CURIOSITY_POOL: tuple[CosmosCuriositySeed, ...] = (
    CosmosCuriositySeed(
        topic="Por que Vênus é mais quente que Mercúrio?",
        requested_angle="Explicar o paradoxo visual: Mercúrio fica mais perto do Sol, mas Vênus prende calor com uma atmosfera espessa. Linguagem conservadora, sem números precisos.",
        hook_seed="O planeta mais quente não é o mais perto do Sol.",
        visual_seed="Vênus brilhando coberto por nuvens densas, Mercúrio perto do Sol, comparação cinematográfica sem texto",
        tags=("venus", "mercurio", "planetas", "atmosfera"),
        base_score=0.97,
    ),
    CosmosCuriositySeed(
        topic="Por que a Lua parece mudar de tamanho no céu?",
        requested_angle="Tratar a ilusão da Lua no horizonte: ela parece gigante perto de prédios e árvores, mas o tamanho real quase não muda naquela noite.",
        hook_seed="A Lua pode parecer gigante sem crescer nada.",
        visual_seed="Lua enorme no horizonte atrás de prédios e árvores, depois alta no céu parecendo menor, realismo cinematográfico",
        tags=("lua", "ilusao", "ceu", "horizonte"),
        base_score=0.96,
    ),
    CosmosCuriositySeed(
        topic="Por que Saturno tem anéis tão visíveis?",
        requested_angle="Mostrar que os anéis são feitos de incontáveis pedaços gelados e poeira refletindo luz, sem virar aula técnica.",
        hook_seed="Saturno parece usar um disco quebrado ao redor dele.",
        visual_seed="Saturno com anéis de gelo e poeira em close cinematográfico, pequenos fragmentos orbitando sem texto",
        tags=("saturno", "aneis", "planeta", "gelo"),
        base_score=0.95,
    ),
    CosmosCuriositySeed(
        topic="Por que Marte é chamado de planeta vermelho?",
        requested_angle="Explicar a poeira rica em óxidos de ferro como ferrugem visual cobrindo a paisagem marciana, com wording seguro.",
        hook_seed="Marte parece enferrujado visto de longe.",
        visual_seed="solo vermelho de Marte, poeira levantando, planeta avermelhado no espaço, documentário realista",
        tags=("marte", "vermelho", "poeira", "planeta"),
        base_score=0.94,
    ),
    CosmosCuriositySeed(
        topic="Por que buracos negros parecem engolir luz?",
        requested_angle="Usar metáfora visual segura: perto de um buraco negro, a gravidade curva caminhos da luz de modo extremo. Evitar números e certezas exageradas.",
        hook_seed="Existe um lugar onde até a luz perde a saída.",
        visual_seed="buraco negro com disco de acreção brilhante curvando luz, espaço escuro cinematográfico, sem texto",
        tags=("buraco negro", "luz", "gravidade", "universo"),
        base_score=0.93,
    ),
    CosmosCuriositySeed(
        topic="Por que existem estrelas que piscam no céu?",
        requested_angle="Explicar a cintilação como turbulência da atmosfera da Terra distorcendo a luz das estrelas, visual simples e poético sem exagero.",
        hook_seed="A estrela não pisca sozinha: o ar mexe na luz.",
        visual_seed="estrela tremulando no céu noturno através de camadas de ar quente, atmosfera terrestre sutil, realismo",
        tags=("estrelas", "atmosfera", "ceu", "luz"),
        base_score=0.94,
    ),
    CosmosCuriositySeed(
        topic="Por que Júpiter tem uma tempestade gigante?",
        requested_angle="Mostrar a Grande Mancha Vermelha como uma tempestade persistente vista nas nuvens de Júpiter, sem prometer duração exata.",
        hook_seed="Júpiter carrega uma tempestade maior que planetas inteiros.",
        visual_seed="Júpiter em close com grande mancha vermelha girando em nuvens, espaço cinematográfico, sem texto",
        tags=("jupiter", "tempestade", "mancha vermelha", "planeta"),
        base_score=0.95,
    ),
    CosmosCuriositySeed(
        topic="Por que Netuno parece azul?",
        requested_angle="Explicar de forma conservadora que gases na atmosfera ajudam a filtrar/refletir luz, criando aparência azul profunda.",
        hook_seed="Netuno parece um oceano, mas não é água.",
        visual_seed="Netuno azul profundo no espaço, atmosfera gasosa com nuvens sutis, realismo documental, sem texto",
        tags=("netuno", "azul", "atmosfera", "planeta"),
        base_score=0.92,
    ),
    CosmosCuriositySeed(
        topic="Por que meteoros viram riscos de luz no céu?",
        requested_angle="Explicar o brilho do meteoro entrando rápido na atmosfera e aquecendo o ar ao redor, sem números precisos.",
        hook_seed="Uma pedrinha espacial pode riscar o céu inteiro.",
        visual_seed="meteoro brilhante atravessando céu noturno, atmosfera iluminada, paisagem escura embaixo, cinematográfico",
        tags=("meteoro", "atmosfera", "ceu", "espaco"),
        base_score=0.96,
    ),
    CosmosCuriositySeed(
        topic="Por que eclipses solares assustavam tanta gente?",
        requested_angle="Mostrar a cena visual do dia escurecendo quando a Lua cobre o Sol, focando no impacto visual e não em história específica sem fonte.",
        hook_seed="O dia pode escurecer como se alguém apagasse o Sol.",
        visual_seed="eclipse solar com céu escurecendo, pessoas em silhueta olhando com segurança, atmosfera dramática sem texto",
        tags=("eclipse", "sol", "lua", "ceu"),
        base_score=0.91,
    ),
)

_CANONICAL_GROUPS: dict[str, set[str]] = {
    "venus": {"venus", "vênus"},
    "mercurio": {"mercurio", "mercúrio"},
    "lua": {"lua", "lunar"},
    "saturno": {"saturno", "aneis", "anéis"},
    "marte": {"marte", "vermelho", "ferrugem"},
    "buraco_negro": {"buraco", "negro", "buracos", "negros"},
    "estrela": {"estrela", "estrelas", "pisca", "piscam", "cintila"},
    "jupiter": {"jupiter", "júpiter", "mancha", "tempestade"},
    "netuno": {"netuno", "azul"},
    "meteoro": {"meteoro", "meteoros", "meteorito", "rastro"},
    "eclipse": {"eclipse", "eclipses"},
}


def cosmos_policy_notes() -> list[str]:
    return [
        "input_mode=theme",
        "automation_source=automatic_topic",
        "automatic_topic_policy=cosmos_astronomia_universo_first",
        "automatic_topic_focus=astronomia, universo, planetas, luas, estrelas, buracos negros, meteoros, eclipses e fenomenos espaciais visualmente fortes.",
        "Use curiosidade viral de universo/astronomia com linguagem pt-BR simples, segura e conservadora.",
        "Evite tema cotidiano generico fora de astronomia no automatic_topic; banco de roteiros pode continuar variado.",
        "Evite numeros precisos, datas, descobertas jornalisticas e claims tecnicos sem fonte; prefira formulacoes como 'em geral', 'pode', 'uma das explicacoes'.",
    ]


def select_cosmos_topic(recent_topics: Iterable[str], *, rng: random.Random | None = None) -> TrendCandidate:
    rng = rng or random.Random()
    recent = [str(topic or "") for topic in recent_topics if str(topic or "").strip()]
    ranked: list[tuple[CosmosCuriositySeed, float]] = []
    for seed in COSMOS_CURIOSITY_POOL:
        similarity = max((_cosmos_similarity(seed.topic, topic) for topic in recent), default=0.0)
        if similarity >= 0.62:
            continue
        ranked.append((seed, seed.base_score - similarity * 0.50 + rng.random() * 0.015))
    if not ranked:
        seed = rng.choice(COSMOS_CURIOSITY_POOL)
    else:
        seed = max(ranked, key=lambda item: item[1])[0]
    return TrendCandidate(
        topic=seed.topic,
        requested_angle=seed.requested_angle,
        source="cosmos_curiosity_pool",
        source_url="local://cosmos-curiosity-pool",
        score=seed.base_score,
        raw_title=seed.topic,
        familiarity_score=0.95,
        source_title=seed.topic,
        hook_seed=seed.hook_seed,
        visual_seed=seed.visual_seed,
        why=["astronomia", "universo", "visual_forte", *seed.tags[:2]],
    )


def _normalize(text: str) -> str:
    replacements = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return str(text or "").lower().translate(replacements)


def _tokens(text: str) -> set[str]:
    blocked = {"por", "que", "como", "para", "com", "uma", "umas", "uns", "dos", "das", "sem", "antes", "depois", "voce", "você", "porque"}
    raw = {token for token in re.findall(r"[a-z0-9à-ÿ]+", _normalize(text)) if len(token) >= 4 and token not in blocked}
    canonical = set(raw)
    for group, synonyms in _CANONICAL_GROUPS.items():
        if raw & {_normalize(item) for item in synonyms}:
            canonical.add(group)
    return canonical


def _cosmos_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
