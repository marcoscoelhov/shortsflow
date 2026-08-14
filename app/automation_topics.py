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


WINNER_SEED_MIN_SCORE = 0.97


COSMOS_CURIOSITY_POOL: tuple[CosmosCuriositySeed, ...] = (
    CosmosCuriositySeed(
        topic="Por que Vênus é mais quente que Mercúrio?",
        requested_angle="Explicar o paradoxo visual: Mercúrio fica mais perto do Sol, mas Vênus prende calor com uma atmosfera espessa. Linguagem conservadora, sem números precisos.",
        hook_seed="Vênus é o planeta mais quente, mas não é o mais perto do Sol.",
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
        hook_seed="Um buraco negro é um lugar onde até a luz perde a saída.",
        visual_seed="buraco negro com disco de acreção brilhante curvando luz, espaço escuro cinematográfico, sem texto",
        tags=("buraco negro", "luz", "gravidade", "universo"),
        base_score=0.93,
    ),
    CosmosCuriositySeed(
        topic="Por que existem estrelas que piscam no céu?",
        requested_angle="Explicar a cintilação como turbulência da atmosfera da Terra distorcendo a luz das estrelas, visual simples e poético sem exagero.",
        hook_seed="Uma estrela não pisca sozinha: o ar mexe na luz.",
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
        hook_seed="Um meteoro pode riscar o céu inteiro.",
        visual_seed="meteoro brilhante atravessando céu noturno, atmosfera iluminada, paisagem escura embaixo, cinematográfico",
        tags=("meteoro", "atmosfera", "ceu", "espaco"),
        base_score=0.96,
    ),
    CosmosCuriositySeed(
        topic="Por que eclipses solares assustavam tanta gente?",
        requested_angle="Mostrar a cena visual do dia escurecendo quando a Lua cobre o Sol, focando no impacto visual e não em história específica sem fonte.",
        hook_seed="A Lua pode apagar o Sol por alguns minutos.",
        visual_seed="eclipse solar com céu escurecendo, pessoas em silhueta olhando com segurança, atmosfera dramática sem texto",
        tags=("eclipse", "sol", "lua", "ceu"),
        base_score=0.91,
    ),
    CosmosCuriositySeed(
        topic="Como Encélado lança um oceano no espaço?",
        requested_angle="Mostrar o paradoxo visual da lua gelada de Saturno: plumas saem de fraturas no gelo e carregam material ligado ao oceano subterrâneo. Evitar cravar composição ou origem de cada partícula.",
        hook_seed="Encélado parece congelado, mas lança gêiseres no espaço.",
        visual_seed="lua Encélado diante de Saturno, superfície de gelo rachada lançando plumas brilhantes ao espaço, documentário cinematográfico sem texto",
        tags=("encelado", "lua", "geiseres", "saturno"),
        base_score=0.98,
    ),
    CosmosCuriositySeed(
        topic="Como Europa esconde um oceano sob gelo quebrado?",
        requested_angle="Explicar de forma conservadora que evidências apontam para um oceano salgado sob a crosta gelada de Europa, contrastando a superfície congelada com água líquida abaixo.",
        hook_seed="Europa é uma lua congelada que pode esconder um oceano líquido.",
        visual_seed="lua Europa em close, crosta branca rachada e corte visual sugerindo oceano escuro sob o gelo, Júpiter ao fundo, sem texto",
        tags=("europa", "lua", "oceano", "jupiter"),
        base_score=0.97,
    ),
    CosmosCuriositySeed(
        topic="Por que Titã tem rios sem água?",
        requested_angle="Mostrar o paradoxo de Titã: rios, lagos e chuva podem lembrar a Terra, mas são alimentados principalmente por metano e etano líquidos. Sem sugerir água líquida na superfície.",
        hook_seed="Titã tem rios e lagos, mas eles não são de água.",
        visual_seed="lua Titã sob névoa alaranjada, rios e lagos escuros de hidrocarbonetos, Saturno distante, paisagem alienígena realista sem texto",
        tags=("titan", "lua", "metano", "rios"),
        base_score=0.98,
    ),
    CosmosCuriositySeed(
        topic="Como pode chover ferro no exoplaneta WASP-76b?",
        requested_angle="Apresentar como hipótese observacional: no exoplaneta ultraquente WASP-76b, ferro vaporizado no lado diurno pode condensar ao chegar ao lado noturno. Não tratar a chuva de ferro como filmagem direta.",
        hook_seed="No WASP-76b, o dia pode vaporizar ferro e a noite pode fazê-lo chover.",
        visual_seed="exoplaneta WASP-76b dividido entre lado diurno incandescente e lado noturno com gotas metálicas, estrela ao fundo, visual científico sem texto",
        tags=("wasp-76b", "exoplaneta", "ferro", "chuva"),
        base_score=0.99,
    ),
    CosmosCuriositySeed(
        topic="Como Kepler-16b pode ter dois pores do sol?",
        requested_angle="Explicar que Kepler-16b orbita duas estrelas, criando a imagem contraintuitiva de dois sóis no céu. Não afirmar condições vistas de uma superfície sólida.",
        hook_seed="Kepler-16b gira ao redor de dois sóis.",
        visual_seed="exoplaneta Kepler-16b com duas estrelas no horizonte espacial, duas fontes de luz e sombras cruzadas, ilustração científica cinematográfica sem texto",
        tags=("kepler-16b", "exoplaneta", "duas estrelas", "orbita"),
        base_score=0.96,
    ),
    CosmosCuriositySeed(
        topic="Como a Voyager 1 ainda fala com a Terra de tão longe?",
        requested_angle="Contrastar a pequena sonda Voyager 1 com a enorme distância do espaço interestelar e explicar que antenas terrestres muito sensíveis recebem sinais de rádio extremamente fracos. Evitar distância ou potência exatas.",
        hook_seed="A Voyager 1 envia um sussurro de rádio através do espaço interestelar.",
        visual_seed="sonda Voyager 1 minúscula no espaço profundo enviando onda de rádio tênue até grandes antenas na Terra, escala extrema sem texto",
        tags=("voyager", "missao", "radio", "espaco profundo"),
        base_score=0.97,
    ),
    CosmosCuriositySeed(
        topic="Como a missão DART moveu uma lua de asteroide ao bater nela?",
        requested_angle="Mostrar o teste de defesa planetária: a nave DART colidiu com Dimorphos e alterou de forma mensurável sua órbita ao redor de Didymos. Evitar sugerir que o asteroide ameaçava a Terra.",
        hook_seed="A missão DART bateu de propósito em Dimorphos e mudou sua órbita.",
        visual_seed="nave DART colidindo com a pequena lua Dimorphos ao lado do asteroide Didymos, detritos iluminados, visual de missão realista sem texto",
        tags=("dart", "dimorphos", "missao", "asteroide"),
        base_score=0.98,
    ),
    CosmosCuriositySeed(
        topic="Por que um pulsar parece um farol no espaço?",
        requested_angle="Explicar o paradoxo visual: a estrela de nêutrons gira e seus feixes cruzam nossa direção, então os pulsos parecem piscadas regulares sem a estrela realmente ligar e desligar.",
        hook_seed="Um pulsar parece piscar, mas é uma estrela morta girando como um farol.",
        visual_seed="pulsar compacto girando com dois feixes de luz varrendo o espaço como farol, nebulosa escura ao redor, sem texto",
        tags=("pulsar", "estrela de neutrons", "farol", "fenomeno"),
        base_score=0.97,
    ),
    CosmosCuriositySeed(
        topic="Como uma galáxia distante vira um anel de luz?",
        requested_angle="Mostrar uma lente gravitacional: a massa em primeiro plano curva a luz de uma galáxia mais distante e pode formar arcos ou um anel. Evitar dizer que a galáxia mudou de forma fisicamente.",
        hook_seed="Uma galáxia pode parecer um anel porque outra massa dobrou sua luz.",
        visual_seed="galáxia distante formando anel de Einstein ao redor de galáxia em primeiro plano, curvatura de luz visível, imagem astronômica sem texto",
        tags=("lente gravitacional", "galaxia", "anel de einstein", "fenomeno"),
        base_score=0.96,
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
    "encelado": {"encelado", "encélado", "geiser", "geiseres", "gêiser", "gêiseres"},
    "europa": {"europa", "oceano", "gelo"},
    "titan": {"titan", "titã", "metano"},
    "wasp_76b": {"wasp-76b", "wasp", "ferro"},
    "kepler_16b": {"kepler-16b", "kepler", "dois sois", "dois sóis"},
    "voyager": {"voyager", "sonda"},
    "dart": {"dart", "dimorphos", "didymos"},
    "pulsar": {"pulsar", "pulsares", "farol"},
    "lente_gravitacional": {"lente gravitacional", "anel de einstein"},
}

_RECOGNIZABLE_HOOK_OBJECT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("lua", r"\blua\b|\blunar\b"),
    ("marte", r"\bmarte\b|\bmarcian[oa]s?\b"),
    ("saturno", r"\bsaturno\b"),
    ("voyager", r"\bvoyager\b"),
    ("buraco_negro", r"\bburaco\s+negro\b|\bburacos\s+negros\b"),
    ("venus", r"\bvenus\b|\bvenusian[oa]s?\b"),
    ("mercurio", r"\bmercurio\b"),
    ("jupiter", r"\bjupiter\b"),
    ("netuno", r"\bnetuno\b"),
    ("sol", r"\bsol\b|\bsolar\b"),
    ("estrela", r"\bestrela\b|\bestrelas\b"),
    ("meteoro", r"\bmeteoro\b|\bmeteoros\b|\bmeteorito\b|\bmeteoritos\b"),
    ("asteroide", r"\basteroide\b|\basteroides\b"),
    ("cometa", r"\bcometa\b|\bcometas\b"),
    ("eclipse", r"\beclipse\b|\beclipses\b"),
    ("galaxia", r"\bgalaxia\b|\bgalaxias\b|\bvia\s+lactea\b"),
    ("encelado", r"\bencelado\b"),
    ("europa", r"\beuropa\b"),
    ("titan", r"\btitan\b"),
    ("wasp_76b", r"\bwasp[\s-]?76b\b"),
    ("kepler_16b", r"\bkepler[\s-]?16b\b"),
    ("dart", r"\bdart\b|\bdimorphos\b"),
    ("pulsar", r"\bpulsar\b|\bpulsares\b"),
)


def recognizable_hook_object(text: str) -> str | None:
    normalized = _normalize(text)
    for object_name, pattern in _RECOGNIZABLE_HOOK_OBJECT_PATTERNS:
        if re.search(pattern, normalized):
            return object_name
    return None


def has_recognizable_hook_object(text: str) -> bool:
    return recognizable_hook_object(text) is not None


def cosmos_policy_notes() -> list[str]:
    return [
        "input_mode=theme",
        "automation_source=automatic_topic",
        "automatic_topic_policy=cosmos_astronomia_universo_first",
        "automatic_topic_focus=astronomia, universo, planetas, luas, estrelas, buracos negros, meteoros, eclipses e fenomenos espaciais visualmente fortes.",
        "Use curiosidade viral de universo/astronomia com linguagem pt-BR simples, segura e conservadora.",
        "automatic_topic_hook_object_required=true",
        "O hook do automatic_topic deve nomear no primeiro segundo um objeto reconhecivel para leigos, como Lua, Marte, Saturno, Voyager ou buraco negro.",
        "Evite tema cotidiano generico fora de astronomia no automatic_topic; banco de roteiros pode continuar variado.",
        "Evite numeros precisos, datas, descobertas jornalisticas e claims tecnicos sem fonte; prefira formulacoes como 'em geral', 'pode', 'uma das explicacoes'.",
    ]


def select_cosmos_topic(recent_topics: Iterable[str], *, rng: random.Random | None = None) -> TrendCandidate:
    rng = rng or random.Random()
    recent = [str(topic or "") for topic in recent_topics if str(topic or "").strip()]
    eligible_seeds = tuple(seed for seed in COSMOS_CURIOSITY_POOL if seed.base_score >= WINNER_SEED_MIN_SCORE)
    if not eligible_seeds:
        raise RuntimeError("cosmos pool has no seed meeting the winner seed threshold")
    ranked: list[tuple[CosmosCuriositySeed, float]] = []
    for seed in eligible_seeds:
        similarity = max((_cosmos_similarity(seed.topic, topic) for topic in recent), default=0.0)
        if similarity >= 0.62:
            continue
        ranked.append((seed, seed.base_score - similarity * 0.50 + rng.random() * 0.015))
    if not ranked:
        seed = rng.choice(eligible_seeds)
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
