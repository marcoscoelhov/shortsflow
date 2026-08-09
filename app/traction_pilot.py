from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from sqlalchemy import select

from app.db import init_db, session_scope
from app.models import Job, RetentionExperiment, RetentionExperimentAssignment, TopicRequest
from app.utils import stable_hash


PILOT_ID_PREFIX = "niche_traction_minimax_fit_20260731"
PILOT_DURATION_SEC = 40
PILOT_ACCEPTABLE_DURATION_SEC = {"min": 30, "max": 50}
PILOT_VISION_POLICY = "qwen_local_exact_no_fallback"
JWST_SOURCE_URL = "https://science.nasa.gov/universe/exoplanets/discovery-alert-webb-reveals-a-steamy-exoplanet-atmosphere/"


@dataclass(frozen=True)
class PilotConcept:
    arm: str
    concept_id: str
    seed_theme: str
    requested_angle: str
    factual_rule: str
    source_url: str
    niche_id: str = "curiosidades"


_ARM_A = (
    PilotConcept("A", "voyager_golden_record", "A mensagem que a Voyager leva para fora do Sistema Solar", "Mostrar o disco e a sonda como objetos factuais centrais; MiniMax apenas para escala e atmosfera.", "As Voyager carregam o Golden Record com sons e imagens selecionados para representar a Terra.", "https://science.nasa.gov/mission/voyager/golden-record-contents/"),
    PilotConcept("A", "dart_dimorphos", "A colisão espacial que mudou a órbita de um asteroide", "Ancorar a prova em visual oficial/programático de Dimorphos; não inventar aproximação entre planetas.", "A missão DART alterou o período orbital de Dimorphos ao colidir deliberadamente com ele.", "https://science.nasa.gov/planetary-defense-dart/"),
    PilotConcept("A", "parker_solar_probe", "O mergulho recorde da Parker perto do Sol", "Usar diagrama ou imagem oficial da missão para a passagem; IA somente na escala emocional.", "A Parker Solar Probe foi projetada para estudar a coroa solar de mais perto do que qualquer espaçonave anterior.", "https://science.nasa.gov/mission/parker-solar-probe/"),
    PilotConcept("A", "jwst_exoplanet_spectrum", "Como um arco-íris revela a atmosfera de um exoplaneta", "A prova deve ser um espectro oficial ou gráfico programático, não um planeta inventado como evidência.", "Espectroscopia permite inferir moléculas em atmosferas de exoplanetas a partir da luz medida.", JWST_SOURCE_URL),
    PilotConcept("A", "apollo_lunar_footprint", "Por que uma pegada lunar pode durar tanto", "Ancorar Lua, regolito e pegada em material oficial; evitar mecanismos visuais complexos.", "Sem vento ou chuva como na Terra, marcas na superfície lunar podem persistir por longos períodos.", "https://science.nasa.gov/moon/moon-facts/"),
    PilotConcept("A", "europa_clipper_flyby", "A sonda que vai investigar se Europa pode sustentar vida", "Mostrar a missão e Europa com visual oficial; atmosfera estilizada não pode virar prova.", "Europa Clipper investigará se a lua Europa possui condições adequadas para sustentar vida.", "https://science.nasa.gov/mission/europa-clipper/"),
)

_ARM_B = (
    PilotConcept("B", "elevador_luz_porta", "No elevador apagado: LUZ ou PORTA?", "Duas escolhas no primeiro quadro; a escolha óbvia falha por pista anterior; CTA: qual você escolheria e por quê?", "Cenário inteiramente ficcional.", "", "survival_decisions"),
    PilotConcept("B", "farol_radio_luz", "No farol isolado: RÁDIO ou LUZ?", "Mostrar as duas escolhas imediatamente e inverter a consequência no payoff.", "Cenário inteiramente ficcional.", "", "survival_decisions"),
    PilotConcept("B", "biblioteca_chave_livro", "Na biblioteca de areia: CHAVE ou LIVRO?", "A pista visual inicial deve explicar por que a escolha óbvia falha.", "Cenário inteiramente ficcional.", "", "survival_decisions"),
    PilotConcept("B", "trem_azul_vermelho", "No trem sem freio: AZUL ou VERMELHO?", "Duas portas legíveis em menos de um segundo, sem texto falso gerado na imagem.", "Cenário inteiramente ficcional.", "", "survival_decisions"),
    PilotConcept("B", "hotel_corredor_capsula", "No hotel submerso: CORREDOR ou CÁPSULA?", "Escolha binária instantânea, continuidade espacial e consequência reversa.", "Cenário inteiramente ficcional.", "", "survival_decisions"),
    PilotConcept("B", "shopping_robo_pegadas", "No shopping vazio: ROBÔ ou PEGADAS?", "A pista mostrada no hook deve retornar no payoff sem alegar história real.", "Cenário inteiramente ficcional.", "", "survival_decisions"),
)

_ARM_C = (
    PilotConcept("C", "lunar_base_airlock_generator", "Você tem 30 segundos numa base lunar: comporta ou gerador?", "Declarar hipótese; usar a ausência de atmosfera respirável como regra verdadeira e uma decisão humana simples.", "A Lua possui apenas uma exosfera extremamente tênue, não uma atmosfera respirável.", "https://science.nasa.gov/moon/moon-facts/"),
    PilotConcept("C", "spacecraft_radiation_shelter", "Tempestade solar: abrigo ou comunicação?", "Declarar hipótese; a regra factual é o risco de partículas energéticas para pessoas e eletrônica.", "Eventos solares podem produzir radiação de partículas perigosa para astronautas e sistemas espaciais.", "https://www.nasa.gov/communicating-with-missions/space-weather/"),
    PilotConcept("C", "europa_ice_lab", "Sob o gelo de Europa: amostra ou energia?", "Cenário hipotético com regra verdadeira sobre o oceano sob a crosta; evitar mostrar mecanismo complexo como fato.", "Há fortes evidências de um oceano de água salgada sob a crosta gelada de Europa.", "https://science.nasa.gov/jupiter/moons/europa/"),
    PilotConcept("C", "iss_orbital_debris", "Alerta de detrito: sela o módulo ou salva o experimento?", "Declarar hipótese e mostrar apenas uma estação genérica; a regra verdadeira é a alta velocidade orbital dos detritos.", "Detritos orbitais viajam em velocidades capazes de danificar espaçonaves.", "https://www.nasa.gov/reference/space-debris-and-human-spacecraft/"),
    PilotConcept("C", "lunar_night_power", "Noite lunar: aquece o abrigo ou mantém o rádio?", "Declarar hipótese; basear o dilema na longa duração do ciclo dia-noite lunar.", "Um ciclo completo de dia e noite na Lua dura cerca de 29,5 dias terrestres.", "https://science.nasa.gov/moon/moon-facts/"),
    PilotConcept("C", "mars_dust_power", "A poeira cobre os painéis: energia ou comunicação?", "Declarar hipótese e focar painéis/poeira, sem usar a cor de Marte como payoff.", "Poeira acumulada pode reduzir a energia produzida por painéis solares em missões marcianas.", "https://science.nasa.gov/mission/insight/"),
)


def build_traction_pilot_plan(*, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    arms = {"A": list(_ARM_A), "B": list(_ARM_B), "C": list(_ARM_C)}
    for concepts in arms.values():
        rng.shuffle(concepts)
    items: list[dict[str, Any]] = []
    for round_index in range(6):
        for arm in ("A", "B", "C"):
            concept = arms[arm][round_index]
            item = asdict(concept)
            item.update(
                {
                    "position": len(items) + 1,
                    "target_duration_sec": PILOT_DURATION_SEC,
                    "language": "pt-BR",
                    "vision_policy": PILOT_VISION_POLICY,
                    "human_review_required": True,
                }
            )
            items.append(item)
    return {
        "experiment_id": f"{PILOT_ID_PREFIX}_s{seed}",
        "seed": seed,
        "language": "pt-BR",
        "target_duration_sec": PILOT_DURATION_SEC,
        "acceptable_duration_sec": dict(PILOT_ACCEPTABLE_DURATION_SEC),
        "publishes_or_schedules": False,
        "vision_policy": PILOT_VISION_POLICY,
        "items": items,
    }


def build_programmatic_pilot_asset(
    concept_id: str,
    scene: dict[str, Any],
    output_path: Any,
) -> dict[str, Any] | None:
    role = str(scene.get("retention_role") or "").strip().lower()
    try:
        order = int(scene.get("order") or 0)
    except (TypeError, ValueError):
        order = 0
    if concept_id != "jwst_exoplanet_spectrum" or (role != "proof_or_tension" and order != 3):
        return None
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1080, 1920), (4, 8, 24))
    draw = ImageDraw.Draw(image)
    draw.ellipse((300, 170, 780, 650), fill=(18, 30, 58), outline=(130, 186, 255), width=12)
    draw.ellipse((490, 330, 590, 430), fill=(1, 4, 12))
    colors = [(82, 116, 255), (75, 220, 240), (92, 232, 144), (250, 222, 78), (255, 128, 65), (238, 67, 94)]
    band_top, band_bottom = 760, 1030
    band_width = 780 // len(colors)
    for index, color in enumerate(colors):
        left = 150 + index * band_width
        draw.rectangle((left, band_top, left + band_width + 1, band_bottom), fill=color)
    points = []
    for index in range(37):
        x = 150 + index * (780 / 36)
        dip = 170 if index in {8, 9, 21, 22, 30} else 0
        y = 1270 - ((index * 37) % 190) + dip
        points.append((x, y))
    draw.line(points, fill=(241, 248, 255), width=18, joint="curve")
    for x, y in points:
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(241, 248, 255))
    draw.arc((150, 1460, 930, 1840), 190, 350, fill=(82, 189, 255), width=18)
    image.save(output_path)
    return {
        "provider": "programmatic",
        "width": 1080,
        "height": 1920,
        "prompt_snapshot": (
            "programmatic exoplanet transit spectroscopy visual with a planet silhouette, "
            "continuous color spectrum and absorption curve, no labels or invented measurements"
        ),
        "uri": output_path.resolve().as_uri(),
        "source_url": JWST_SOURCE_URL,
        "attribution": "NASA science source; explanatory graphic generated by ShortsFlow",
        "license_note": "Programmatic explanatory visual grounded in the cited NASA source.",
    }


def start_traction_pilot(orchestrator: Any, *, seed: int, canary_count: int = 3) -> dict[str, Any]:
    if canary_count != 3:
        raise ValueError("the first traction pilot checkpoint must contain exactly three canaries")
    init_db()
    plan = build_traction_pilot_plan(seed=seed)
    experiment_id = str(plan["experiment_id"])
    with session_scope() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        if experiment is None:
            experiment = RetentionExperiment(
                experiment_id=experiment_id,
                profile_id="default",
                content_hash=stable_hash(plan),
                status="planned",
                line_id="niche_traction_minimax_fit",
                target_job_count=18,
                result_summary={"plan": plan, "seed": seed},
            )
            session.add(experiment)
        else:
            experiment.content_hash = stable_hash(plan)
            experiment.target_job_count = 18
            experiment.result_summary = {"plan": plan, "seed": seed}
        for item in plan["items"]:
            assignment_id = f"{experiment_id}:{item['position']:02d}"
            assignment = session.get(RetentionExperimentAssignment, assignment_id)
            if assignment is None:
                session.add(
                    RetentionExperimentAssignment(
                        assignment_id=assignment_id,
                        experiment_id=experiment_id,
                        position=int(item["position"]),
                        arm=str(item["arm"]),
                        concept_id=str(item["concept_id"]),
                        status="planned",
                        assignment_metadata=item,
                    )
                )
            else:
                assignment.assignment_metadata = item

    created_job_count = 0
    for item in plan["items"][:canary_count]:
        assignment_id = f"{experiment_id}:{item['position']:02d}"
        with session_scope() as session:
            assignment = session.get(RetentionExperimentAssignment, assignment_id)
            if assignment is None:
                raise RuntimeError(f"pilot assignment missing: {assignment_id}")
            existing_job_id = assignment.job_id
        if existing_job_id:
            with session_scope() as session:
                job = session.get(Job, existing_job_id)
                request = session.scalar(
                    select(TopicRequest).where(TopicRequest.job_id == existing_job_id)
                )
                if job is not None:
                    job.target_duration_sec = PILOT_DURATION_SEC
                if request is not None:
                    request.target_duration_sec = PILOT_DURATION_SEC
            continue
        notes = _pilot_job_notes(experiment_id, assignment_id, item)
        job_id = orchestrator.create_job(
            {
                "seed_theme": item["seed_theme"],
                "niche_id": item["niche_id"],
                "language": "pt-BR",
                "target_duration_sec": PILOT_DURATION_SEC,
                "tone": "intrigante_direto",
                "cta_style": "soft",
                "notes": notes,
                "requested_angle": item["requested_angle"],
                "job_origin": "manual_theme",
                "creation_via": "cli",
            }
        )
        with session_scope() as session:
            assignment = session.get(RetentionExperimentAssignment, assignment_id)
            if assignment is None:
                raise RuntimeError(f"pilot assignment disappeared: {assignment_id}")
            assignment.job_id = job_id
            assignment.status = "job_created"
        created_job_count += 1

    with session_scope() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        if experiment is None:
            raise RuntimeError(f"pilot experiment disappeared: {experiment_id}")
        experiment.status = "canaries_created"

    result = get_traction_pilot(experiment_id)
    result["created_job_count"] = created_job_count
    result["canaries"] = result["assignments"][:canary_count]
    return result


def get_traction_pilot(experiment_id: str) -> dict[str, Any]:
    init_db()
    with session_scope() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        if experiment is None:
            raise KeyError(experiment_id)
        assignments = session.scalars(
            select(RetentionExperimentAssignment)
            .where(RetentionExperimentAssignment.experiment_id == experiment_id)
            .order_by(RetentionExperimentAssignment.position)
        ).all()
        return {
            "experiment_id": experiment.experiment_id,
            "status": experiment.status,
            "seed": int((experiment.result_summary or {}).get("seed", 0)),
            "language": str(((experiment.result_summary or {}).get("plan") or {}).get("language", "pt-BR")),
            "target_duration_sec": int(
                ((experiment.result_summary or {}).get("plan") or {}).get("target_duration_sec", PILOT_DURATION_SEC)
            ),
            "assignments": [
                {
                    **dict(assignment.assignment_metadata or {}),
                    "assignment_id": assignment.assignment_id,
                    "job_id": assignment.job_id,
                    "status": assignment.status,
                }
                for assignment in assignments
            ],
        }


def _pilot_job_notes(experiment_id: str, assignment_id: str, item: dict[str, Any]) -> str:
    parts = [
        f"experiment_id={experiment_id}",
        f"experiment_assignment_id={assignment_id}",
        f"experiment_arm={item['arm']}",
        f"experiment_concept_id={item['concept_id']}",
        f"vision_policy={PILOT_VISION_POLICY}",
        "human_review_required=true",
        "automatic_publication_allowed=false",
        "Duração alvo: 40 segundos; faixa aceitável: 30 a 50 segundos. Manter voz, ritmo, seis cenas e intensidade de CTA constantes.",
        str(item["requested_angle"]),
        f"Regra factual: {item['factual_rule']}",
    ]
    if item.get("source_url"):
        parts.append(f"Fonte primária obrigatória: {item['source_url']}")
    if item["arm"] == "B":
        parts.extend(["Cenário fictício.", "CTA exata: qual você escolheria e por quê?"])
    elif item["arm"] == "C":
        parts.append("Declarar explicitamente que o cenário é hipotético; a regra científica permanece factual.")
    return "\n".join(parts)
