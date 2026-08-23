from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select

from app.db import init_db, session_scope
from app.models import Job, RetentionExperiment, RetentionExperimentAssignment, TopicRequest
from app.utils import stable_hash


MICRODRAMA_NICHE_ID = "fiction_microdrama"
MICRODRAMA_LABEL_PT_BR = "Dramas chocantes com reviravolta"
MICRODRAMA_PILOT_ID_PREFIX = "jarvis_shocking_twist_drama_pilot_v2"
MICRODRAMA_PILOT_DURATION_SEC = 120
MICRODRAMA_SCRIPT_TRACK_COUNT = 10
MICRODRAMA_FICTIONAL_UNIVERSE = "universos_variados"
MICRODRAMA_POSITIONING = "dramas_chocantes_com_reviravolta"

_ARM_FOCUS = {
    "A": "betrayal_family_secret_shocking_twist",
    "B": "injustice_impossible_choice_consequence_twist",
    "C": "dark_mystery_supernatural_twist_no_gore",
}


@dataclass(frozen=True)
class MicrodramaConcept:
    arm: str
    concept_id: str
    seed_theme: str
    requested_angle: str
    story_format: str = "standalone"
    niche_id: str = MICRODRAMA_NICHE_ID


_ARM_A = (
    MicrodramaConcept(
        "A",
        "a_carta_da_mae",
        "A carta da mãe que chegou vinte anos tarde",
        "Uma filha reconhece a letra da mãe desaparecida e descobre que a pessoa que guardou as cartas também a criou.",
        "arc_2_parts",
    ),
    MicrodramaConcept(
        "A",
        "a_alianca_no_bolo",
        "A aliança escondida dentro do bolo de aniversário",
        "Uma confeiteira encontra a prova de uma traição familiar, mas o nome gravado aponta para a pessoa errada.",
    ),
    MicrodramaConcept(
        "A",
        "a_foto_recortada",
        "A pessoa recortada de todas as fotos da família",
        "Uma jovem restaura um álbum e percebe que o desconhecido apagado das fotos ainda mora na mesma rua.",
        "arc_3_parts",
    ),
    MicrodramaConcept(
        "A",
        "a_heranca_do_radio",
        "O rádio herdado que toca uma confissão",
        "Dois irmãos disputam uma herança simples até uma fita revelar por que o pai favoreceu quem parecia tê-lo traído.",
    ),
    MicrodramaConcept(
        "A",
        "a_madrinha_na_estacao",
        "A madrinha que esperava na estação toda sexta-feira",
        "Uma afilhada segue a rotina secreta da madrinha e encontra uma segunda família protegida por uma promessa antiga.",
        "arc_2_parts",
    ),
    MicrodramaConcept(
        "A",
        "a_chave_da_casa_vazia",
        "A chave da casa vazia no buquê da noiva",
        "Durante o casamento, a noiva recebe uma chave anônima e precisa decidir se expõe a vingança preparada por sua irmã.",
    ),
)

_ARM_B = (
    MicrodramaConcept(
        "B",
        "b_audio_antes_da_cirurgia",
        "O áudio que só pode ser ouvido antes da cirurgia",
        "Uma mulher precisa escolher entre ouvir uma confissão que pode mudar sua família ou preservar a calma da irmã.",
    ),
    MicrodramaConcept(
        "B",
        "b_passagem_unica",
        "Uma passagem de ônibus e duas pessoas para partir",
        "Após uma enchente fictícia não gráfica, um rapaz decide entre acompanhar a avó ou ceder o lugar à criança da vizinha.",
    ),
    MicrodramaConcept(
        "B",
        "b_prova_na_formatura",
        "A prova da inocência escondida no discurso de formatura",
        "Uma estudante pode limpar o nome do pai, mas a revelação destruiria o futuro da amiga que a protegeu.",
        "arc_2_parts",
    ),
    MicrodramaConcept(
        "B",
        "b_remedio_da_vizinha",
        "A sacola trocada na farmácia do bairro",
        "Uma entregadora encontra dinheiro e um remédio urgente em sacolas trocadas e tem minutos para escolher qual destino priorizar.",
    ),
    MicrodramaConcept(
        "B",
        "b_verdade_no_velorio",
        "A verdade que ninguém queria ouvir no velório",
        "Sem mostrar o corpo, uma neta decide se cumpre o último pedido do avô ou revela uma mentira que sustentou a família.",
        "arc_3_parts",
    ),
    MicrodramaConcept(
        "B",
        "b_caderno_da_professora",
        "O caderno que poderia salvar um aluno e condenar outro",
        "Uma professora encontra versões incompatíveis do mesmo incidente e precisa agir antes que uma acusação injusta se espalhe.",
    ),
)

_ARM_C = (
    MicrodramaConcept(
        "C",
        "c_retrato_que_piscava",
        "O retrato de família que piscava depois de cada mentira",
        "Uma mulher culpa a moldura antiga até perceber que apenas a pessoa apagada da fotografia permanece imóvel.",
        "arc_2_parts",
    ),
    MicrodramaConcept(
        "C",
        "c_quarto_atras_do_espelho",
        "O espelho que mostrava um quarto inexistente",
        "Uma inquilina vê alguém repetir seus movimentos do outro lado até descobrir que o reflexo tenta impedir sua próxima escolha.",
    ),
    MicrodramaConcept(
        "C",
        "c_mensagem_do_numero_desativado",
        "A mensagem enviada pelo próprio número desativado",
        "Um homem recebe um áudio com sua voz pedindo que não abra a porta e percebe que a gravação foi feita dentro da casa.",
        "arc_3_parts",
    ),
    MicrodramaConcept(
        "C",
        "c_chave_do_hotel",
        "A chave de hotel que abria uma porta da infância",
        "Uma hóspede encontra atrás da porta um quarto idêntico ao que jurava ter esquecido, mas com uma fotografia tirada naquela manhã.",
    ),
    MicrodramaConcept(
        "C",
        "c_convidado_que_sumia_das_fotos",
        "O convidado que desaparecia de todas as fotos",
        "Depois da festa, uma fotógrafa percebe que o desconhecido some das imagens sempre que a anfitriã aparece sorrindo.",
        "arc_2_parts",
    ),
    MicrodramaConcept(
        "C",
        "c_elevador_do_setimo_andar",
        "O elevador que abria num sétimo andar inexistente",
        "Uma porteira encontra no andar impossível objetos perdidos por moradores que escondem arrependimentos, sem violência gráfica.",
    ),
)

MICRODRAMA_CONCEPT_POOL = _ARM_A + _ARM_B + _ARM_C


def microdrama_policy_notes() -> tuple[str, ...]:
    return (
        "fictional_scenario=true",
        "fiction_format=microdrama",
        "automatic_publication_allowed=false",
        "human_review_required=true",
        "originality_review_required=true",
        "twist_required=true",
        "twist_must_reinterpret_story=true",
        "shock_without_graphic_violence=true",
        (
            "Política: usar apenas tramas originais, rotular explicitamente como ficção, não copiar textos do Reddit "
            "ou de novelas, sem gore e sem enganar o público como se fossem eventos reais. O choque deve vir de "
            "uma revelação, traição, identidade, escolha ou consequência; a reviravolta precisa ser preparada por "
            "pistas e reinterpretar o começo, não apenas acrescentar informação aleatória no final."
        ),
    )


def build_microdrama_pilot_plan(*, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    arms = {"A": list(_ARM_A), "B": list(_ARM_B), "C": list(_ARM_C)}
    for concepts in arms.values():
        rng.shuffle(concepts)
    items: list[dict[str, Any]] = []
    for round_index in range(6):
        for arm in ("A", "B", "C"):
            item = asdict(arms[arm][round_index])
            item.update(
                {
                    "position": len(items) + 1,
                    "target_duration_sec": MICRODRAMA_PILOT_DURATION_SEC,
                    "language": "pt-BR",
                    "arm_focus": _ARM_FOCUS[arm],
                    "positioning": MICRODRAMA_POSITIONING,
                    "fictional_universe": MICRODRAMA_FICTIONAL_UNIVERSE,
                    "twist_required": True,
                    "human_review_required": True,
                    "automatic_publication_allowed": False,
                }
            )
            items.append(item)
    return {
        "experiment_id": f"{MICRODRAMA_PILOT_ID_PREFIX}_s{seed}",
        "seed": seed,
        "niche_id": MICRODRAMA_NICHE_ID,
        "language": "pt-BR",
        "target_duration_sec": MICRODRAMA_PILOT_DURATION_SEC,
        "publishes_or_schedules": False,
        "human_review_required": True,
        "automatic_publication_allowed": False,
        "items": items,
    }


def start_microdrama_pilot(orchestrator: Any, *, seed: int) -> dict[str, Any]:
    init_db()
    plan = build_microdrama_pilot_plan(seed=seed)
    experiment_id = str(plan["experiment_id"])
    with session_scope() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        if experiment is None:
            experiment = RetentionExperiment(
                experiment_id=experiment_id,
                profile_id="default",
                content_hash=stable_hash(plan),
                status="planned",
                line_id="jarvis_shocking_twist_drama_pilot_v2",
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
    for item in plan["items"][:3]:
        assignment_id = f"{experiment_id}:{item['position']:02d}"
        with session_scope() as session:
            assignment = session.get(RetentionExperimentAssignment, assignment_id)
            if assignment is None:
                raise RuntimeError(f"microdrama pilot assignment missing: {assignment_id}")
            existing_job_id = assignment.job_id
        if existing_job_id:
            with session_scope() as session:
                job = session.get(Job, existing_job_id)
                request = session.scalar(select(TopicRequest).where(TopicRequest.job_id == existing_job_id))
                if job is not None:
                    job.target_duration_sec = MICRODRAMA_PILOT_DURATION_SEC
                if request is not None:
                    request.target_duration_sec = MICRODRAMA_PILOT_DURATION_SEC
            continue
        job_id = orchestrator.create_job(
            {
                "seed_theme": item["seed_theme"],
                "niche_id": MICRODRAMA_NICHE_ID,
                "language": "pt-BR",
                "target_duration_sec": MICRODRAMA_PILOT_DURATION_SEC,
                "tone": "drama_chocante_reviravolta",
                "cta_style": "soft",
                "notes": _microdrama_job_notes(experiment_id, assignment_id, item),
                "requested_angle": item["requested_angle"],
                "job_origin": "manual_theme",
                "creation_via": "cli",
            }
        )
        with session_scope() as session:
            assignment = session.get(RetentionExperimentAssignment, assignment_id)
            if assignment is None:
                raise RuntimeError(f"microdrama pilot assignment disappeared: {assignment_id}")
            assignment.job_id = job_id
            assignment.status = "job_created"
        created_job_count += 1

    with session_scope() as session:
        experiment = session.get(RetentionExperiment, experiment_id)
        if experiment is None:
            raise RuntimeError(f"microdrama pilot experiment disappeared: {experiment_id}")
        experiment.status = "canaries_created"

    result = get_microdrama_pilot(experiment_id)
    result["created_job_count"] = created_job_count
    result["canaries"] = result["assignments"][:3]
    result["publishes_or_schedules"] = False
    return result


def get_microdrama_pilot(experiment_id: str) -> dict[str, Any]:
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
        plan = (experiment.result_summary or {}).get("plan") or {}
        return {
            "experiment_id": experiment.experiment_id,
            "status": experiment.status,
            "seed": int((experiment.result_summary or {}).get("seed", 0)),
            "language": str(plan.get("language", "pt-BR")),
            "target_duration_sec": int(plan.get("target_duration_sec", MICRODRAMA_PILOT_DURATION_SEC)),
            "publishes_or_schedules": False,
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


def _microdrama_job_notes(experiment_id: str, assignment_id: str, item: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"experiment_id={experiment_id}",
            f"experiment_assignment_id={assignment_id}",
            f"experiment_arm={item['arm']}",
            f"experiment_concept_id={item['concept_id']}",
            f"story_format={item['story_format']}",
            *microdrama_policy_notes(),
        )
    )
