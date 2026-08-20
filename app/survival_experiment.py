from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass

from app.automation_topics import COSMOS_CURIOSITY_POOL, cosmos_policy_notes

DEFAULT_NICHE_ID = "curiosidades"
SURVIVAL_NICHE_ID = "survival_decisions"
SURVIVAL_EXPERIMENT_ID = "survival_vs_astronomy_20260730"
SURVIVAL_COHORT_ID = "survival_decisions_v1"
SURVIVAL_LABEL_PT_BR = "Sobrevivência e decisões impossíveis"

_SAFETY_FRAMING = (
    "Cenário ficcional e hipotético para entretenimento; não é relato de evento real nem instrução "
    "de segurança, médica, ilegal, sobre armas ou para replicação."
)


@dataclass(frozen=True)
class SurvivalScenarioSeed:
    scenario_id: str
    title_seed: str
    hook_seed: str
    scenario_family: str
    hazard: str
    decision_mechanic: str
    escalation_seed: str
    visual_seed: str
    safety_framing: str = _SAFETY_FRAMING


@dataclass(frozen=True)
class NichePolicy:
    niche_id: str
    label_pt_br: str
    seed_pool: tuple[object, ...]
    policy_notes: tuple[str, ...]
    experimental: bool
    hypothetical: bool


SURVIVAL_SCENARIO_POOL: tuple[SurvivalScenarioSeed, ...] = (
    SurvivalScenarioSeed(
        scenario_id="elevador_botoes",
        title_seed="No elevador apagado, você aperta LUZ ou PORTA?",
        hook_seed="O painel do elevador apaga e só dois botões continuam acesos: LUZ ou PORTA.",
        scenario_family="confinamento_vertical",
        hazard="falha_de_energia",
        decision_mechanic="escolha_binaria_de_recurso",
        escalation_seed="Cada escolha apaga a outra enquanto o visor começa uma contagem regressiva fictícia.",
        visual_seed="painel de elevador escuro com apenas os botões LUZ e PORTA acesos, visor vermelho em contagem, sem pessoas feridas",
    ),
    SurvivalScenarioSeed(
        scenario_id="ponte_mochila",
        title_seed="Na ponte rachando, você salva a mochila ou o mapa?",
        hook_seed="Uma ponte de vidro começa a rachar e você só consegue segurar a mochila ou o mapa luminoso.",
        scenario_family="travessia_suspensa",
        hazard="estrutura_instavel",
        decision_mechanic="abandono_de_um_item",
        escalation_seed="As placas atrás desaparecem e o item abandonado muda qual saída fica visível.",
        visual_seed="ponte de vidro fictícia sobre névoa, mochila numa mão e mapa holográfico na outra, rachaduras luminosas não gráficas",
    ),
    SurvivalScenarioSeed(
        scenario_id="trem_vagoes",
        title_seed="No trem sem freio, vagão azul ou vermelho?",
        hook_seed="O mapa do trem pisca: o vagão azul tem energia, o vermelho tem a única saída.",
        scenario_family="transporte_em_movimento",
        hazard="rota_sem_parada",
        decision_mechanic="escolha_de_compartimento",
        escalation_seed="As portas entre os vagões fecham uma a uma enquanto a cidade termina nos trilhos.",
        visual_seed="interior de trem futurista, duas portas marcadas apenas por luz azul e vermelha, mapa piscando, tensão sem colisão",
    ),
    SurvivalScenarioSeed(
        scenario_id="farol_bateria",
        title_seed="No farol isolado, você usa a última bateria no rádio ou na luz?",
        hook_seed="A bateria do farol marca 1%: ela liga o rádio ou mantém a luz acesa.",
        scenario_family="isolamento_costeiro",
        hazard="tempestade_ficcional",
        decision_mechanic="alocacao_de_energia",
        escalation_seed="Uma sombra de navio aparece na névoa ao mesmo tempo que o rádio recebe um sinal incompleto.",
        visual_seed="farol cinematográfico sob tempestade claramente ficcional, bateria em 1%, rádio antigo e lâmpada apagando",
    ),
    SurvivalScenarioSeed(
        scenario_id="estufa_portais",
        title_seed="Na estufa congelando, você abre o portal quente ou o iluminado?",
        hook_seed="O termômetro da estufa cai e dois portais aparecem: um solta calor, o outro mostra luz.",
        scenario_family="habitat_botanico",
        hazard="frio_impossivel",
        decision_mechanic="escolha_por_sinal_incompleto",
        escalation_seed="As plantas viram cristal e cada portal revela uma consequência visual diferente.",
        visual_seed="estufa fantástica congelando, plantas de cristal, um portal laranja com calor e outro branco luminoso, sem dano",
    ),
    SurvivalScenarioSeed(
        scenario_id="biblioteca_areia",
        title_seed="Na biblioteca enchendo de areia, você leva a chave ou o livro?",
        hook_seed="Areia invade a biblioteca e o pedestal oferece uma chave de metal ou um livro que brilha.",
        scenario_family="arquivo_subterraneo",
        hazard="areia_crescente",
        decision_mechanic="objeto_util_ou_informacao",
        escalation_seed="As estantes somem sob a areia enquanto símbolos diferentes aparecem na saída.",
        visual_seed="biblioteca subterrânea fantástica com areia subindo, chave metálica e livro luminoso num pedestal, sem pessoas em perigo gráfico",
    ),
    SurvivalScenarioSeed(
        scenario_id="observatorio_cupula",
        title_seed="No observatório, você fecha a cúpula ou mantém o sinal?",
        hook_seed="A cúpula do observatório trava aberta quando um sinal impossível aparece no telescópio.",
        scenario_family="observatorio_remoto",
        hazard="anomalia_celeste_ficcional",
        decision_mechanic="protecao_ou_descoberta",
        escalation_seed="O céu muda de cor e o sinal forma um mapa apenas enquanto a cúpula permanece aberta.",
        visual_seed="observatório fictício com cúpula aberta, telescópio apontando para sinal geométrico no céu violeta, sem desastre real",
    ),
    SurvivalScenarioSeed(
        scenario_id="hotel_submerso",
        title_seed="No hotel submerso, você sela o corredor ou libera a cápsula?",
        hook_seed="A janela do hotel submerso racha e o painel permite selar o corredor ou liberar uma cápsula vazia.",
        scenario_family="habitat_submerso",
        hazard="pressao_oceanica_ficcional",
        decision_mechanic="conter_ou_evacuacao_limitada",
        escalation_seed="A água ilumina novos símbolos no vidro e a cápsula só aceita um comando.",
        visual_seed="hotel submerso fantástico com janela trincada não gráfica, painel com dois ícones simples, cápsula externa iluminada",
    ),
    SurvivalScenarioSeed(
        scenario_id="museu_relogio",
        title_seed="No museu parado no tempo, você gira o relógio para frente ou para trás?",
        hook_seed="Todos congelam no museu, menos um relógio com duas setas: futuro ou passado.",
        scenario_family="labirinto_temporal",
        hazard="tempo_congelado_ficcional",
        decision_mechanic="direcao_irreversivel",
        escalation_seed="Cada segundo apaga uma porta do salão e envelhece apenas as sombras.",
        visual_seed="museu fantástico congelado no tempo, relógio dourado com setas opostas, sombras mudando, sem sofrimento",
    ),
    SurvivalScenarioSeed(
        scenario_id="teleferico_caixas",
        title_seed="No teleférico parado, você abre a caixa pesada ou a leve?",
        hook_seed="O teleférico para sobre as nuvens com duas caixas lacradas: uma pesada e uma leve.",
        scenario_family="cabine_aerea",
        hazard="suspensao_sobre_nuvens",
        decision_mechanic="peso_versus_mobilidade",
        escalation_seed="O cabo emite pulsos de luz e cada caixa altera o equilíbrio de forma impossível.",
        visual_seed="teleférico fictício acima de nuvens, duas caixas lacradas de tamanhos diferentes, cabo com pulsos luminosos",
    ),
    SurvivalScenarioSeed(
        scenario_id="shopping_robos",
        title_seed="No shopping vazio, você segue o robô ou as pegadas?",
        hook_seed="As luzes do shopping apagam: um robô aponta à esquerda e pegadas luminosas seguem à direita.",
        scenario_family="complexo_comercial_vazio",
        hazard="apagao_com_rotas_mutantes",
        decision_mechanic="confiar_em_guia_ou_pista",
        escalation_seed="As lojas trocam de lugar e os dois caminhos começam a desaparecer.",
        visual_seed="shopping fantástico vazio no escuro, pequeno robô apontando à esquerda e pegadas luminosas à direita, sem ameaça gráfica",
    ),
    SurvivalScenarioSeed(
        scenario_id="jardim_gravidade",
        title_seed="No jardim sem gravidade, você prende a corda ou segura a semente?",
        hook_seed="A gravidade some no jardim e uma corda e uma semente gigante começam a flutuar para lados opostos.",
        scenario_family="jardim_orbital_fantastico",
        hazard="gravidade_impossivel",
        decision_mechanic="ancora_ou_objetivo",
        escalation_seed="O teto se abre para um céu estrelado e a semente revela uma saída por poucos segundos.",
        visual_seed="jardim fantástico sem gravidade, corda flutuante e semente luminosa gigante indo para lados opostos, payoff estrelado",
    ),
)


_CHOICE_ARTICLE_PATTERN = re.compile(
    r"\b(?:o|a|os|as|um|uma|no|na|nos|nas|ao|aos|à|às)\s+([\wÀ-ÿ-]+)",
    flags=re.IGNORECASE,
)
_CHOICE_TOKEN_PATTERN = re.compile(r"[\wÀ-ÿ-]+", flags=re.UNICODE)
_CHOICE_COMMAND_PATTERN = re.compile(
    r"\b(?:abra|aperte|decida|escolha|fecha|feche|gira|gire|leve|mantenha|pegue|prenda|salve|segure|siga|use|usar|você)\b",
    flags=re.IGNORECASE,
)
_CHOICE_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "um",
    "uma",
}


def extract_survival_choice_labels(*texts: str) -> tuple[str, str] | None:
    """Extract the two compact option labels from survival-choice prose."""

    for raw_text in texts:
        text = " ".join(str(raw_text or "").split())
        for separator in re.finditer(r"\bou\b", text, flags=re.IGNORECASE):
            left = re.split(r"[,?:;.!\u2013\u2014]", text[: separator.start()])[-1]
            right = re.split(r"[,?:;.!\u2013\u2014]", text[separator.end() :], maxsplit=1)[0]
            left_articles = _CHOICE_ARTICLE_PATTERN.findall(left)
            right_articles = _CHOICE_ARTICLE_PATTERN.findall(right)
            if left_articles and right_articles:
                labels = (_choice_label(left_articles[-1]), _choice_label(right_articles[0]))
            elif _is_unpunctuated_noun_phrase_choice(text):
                labels = (_first_meaningful_choice_token(left), _first_meaningful_choice_token(right))
            else:
                labels = (_last_meaningful_choice_token(left), _last_meaningful_choice_token(right))
            if all(labels):
                return labels[0], labels[1]
    return None


def _is_unpunctuated_noun_phrase_choice(value: str) -> bool:
    value_without_terminal_question = value.removesuffix("?")
    return not re.search(r"[,?:;.!\u2013\u2014]", value_without_terminal_question) and not _CHOICE_COMMAND_PATTERN.search(value)


def _first_meaningful_choice_token(value: str) -> str:
    tokens = [token for token in _CHOICE_TOKEN_PATTERN.findall(value) if token.casefold() not in _CHOICE_STOPWORDS]
    return _choice_label(tokens[0]) if tokens else ""


def _last_meaningful_choice_token(value: str) -> str:
    tokens = [token for token in _CHOICE_TOKEN_PATTERN.findall(value) if token.casefold() not in _CHOICE_STOPWORDS]
    return _choice_label(tokens[-1]) if tokens else ""


def _choice_label(value: str) -> str:
    return re.sub(r"[^\wÀ-ÿ-]", "", value, flags=re.UNICODE).upper()[:24]


def survival_policy_notes() -> tuple[str, ...]:
    return (
        f"experiment_id={SURVIVAL_EXPERIMENT_ID}",
        f"cohort_id={SURVIVAL_COHORT_ID}",
        "experimental=true",
        "experiment_cohort=survival_decisions",
        "hypothetical=true",
        "fictional_scenario=true",
        "automatic_publication_allowed=false",
        "human_review_required=true",
        "Tratar sempre como cenário ficcional e hipotético, nunca como evento real ou atual.",
        "Não oferecer conselho médico, instruções sobre armas, atos ilegais, dano gráfico ou orientação perigosa para replicação.",
    )


def select_niche_policy(niche_id: str = DEFAULT_NICHE_ID) -> NichePolicy:
    normalized = str(niche_id or DEFAULT_NICHE_ID).strip()
    if normalized == DEFAULT_NICHE_ID:
        return NichePolicy(
            niche_id=DEFAULT_NICHE_ID,
            label_pt_br="Curiosidades de astronomia e cosmos",
            seed_pool=COSMOS_CURIOSITY_POOL,
            policy_notes=tuple(cosmos_policy_notes()),
            experimental=False,
            hypothetical=False,
        )
    if normalized == SURVIVAL_NICHE_ID:
        return NichePolicy(
            niche_id=SURVIVAL_NICHE_ID,
            label_pt_br=SURVIVAL_LABEL_PT_BR,
            seed_pool=SURVIVAL_SCENARIO_POOL,
            policy_notes=survival_policy_notes(),
            experimental=True,
            hypothetical=True,
        )
    if normalized == "fiction_microdrama":
        from app.microdrama_pilot import MICRODRAMA_CONCEPT_POOL, MICRODRAMA_LABEL_PT_BR, microdrama_policy_notes

        return NichePolicy(
            niche_id="fiction_microdrama",
            label_pt_br=MICRODRAMA_LABEL_PT_BR,
            seed_pool=MICRODRAMA_CONCEPT_POOL,
            policy_notes=microdrama_policy_notes(),
            experimental=True,
            hypothetical=True,
        )
    raise ValueError(f"unsupported niche_id: {normalized}")


def build_survival_cohort_plan(
    *,
    seed: int,
    item_count: int = 6,
    rng: random.Random | None = None,
) -> dict[str, object]:
    if item_count != 6:
        raise ValueError("survival experiment cohorts must contain exactly 6 items")
    candidates = list(SURVIVAL_SCENARIO_POOL)
    (rng or random.Random(seed)).shuffle(candidates)
    selected: list[SurvivalScenarioSeed] = []
    used_families: set[str] = set()
    used_hazards: set[str] = set()
    used_mechanics: set[str] = set()
    for candidate in candidates:
        if candidate.scenario_family in used_families:
            continue
        if candidate.hazard in used_hazards:
            continue
        if candidate.decision_mechanic in used_mechanics:
            continue
        selected.append(candidate)
        used_families.add(candidate.scenario_family)
        used_hazards.add(candidate.hazard)
        used_mechanics.add(candidate.decision_mechanic)
        if len(selected) == item_count:
            break
    if len(selected) != item_count:
        raise RuntimeError("survival seed pool cannot satisfy cohort diversity constraints")
    return {
        "niche_id": SURVIVAL_NICHE_ID,
        "niche_label_pt_br": SURVIVAL_LABEL_PT_BR,
        "experiment_id": SURVIVAL_EXPERIMENT_ID,
        "cohort_id": SURVIVAL_COHORT_ID,
        "experimental": True,
        "hypothetical": True,
        "dry_run": True,
        "creates_jobs": False,
        "publishes_or_schedules": False,
        "seed": seed,
        "items": [asdict(item) for item in selected],
    }
