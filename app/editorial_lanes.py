from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EditorialLane:
    slug: str
    niche_id: str
    label: str
    route: str
    queue_title: str
    description: str
    default_duration_sec: int
    minimum_duration_sec: int
    maximum_duration_sec: int
    tone: str
    tone_label: str
    theme_placeholder: str
    allows_automatic_topic: bool

    def as_template_context(self) -> dict[str, object]:
        return asdict(self)


EDITORIAL_LANES = (
    EditorialLane(
        slug="cosmos",
        niche_id="curiosidades",
        label="Cosmos",
        route="/",
        queue_title="Fila Cosmos",
        description="Astronomia e ciência visual em histórias curtas de 35 a 55 segundos.",
        default_duration_sec=45,
        minimum_duration_sec=35,
        maximum_duration_sec=55,
        tone="intrigante_direto",
        tone_label="Intrigante direto",
        theme_placeholder="Ex.: um paradoxo visual sobre Marte, Lua ou meteoritos.",
        allows_automatic_topic=True,
    ),
    EditorialLane(
        slug="microdramas",
        niche_id="fiction_microdrama",
        label="Microdramas",
        route="/microdramas",
        queue_title="Fila Microdramas",
        description="Ficção original de 100 a 150 segundos, com tensão, pistas e reviravolta.",
        default_duration_sec=120,
        minimum_duration_sec=100,
        maximum_duration_sec=150,
        tone="drama_chocante_reviravolta",
        tone_label="Drama com reviravolta",
        theme_placeholder="Ex.: a carta da mãe que chegou vinte anos tarde.",
        allows_automatic_topic=False,
    ),
    EditorialLane(
        slug="experimentos",
        niche_id="survival_decisions",
        label="Experimentos",
        route="/experimentos",
        queue_title="Fila de experimentos",
        description="Cenários ficcionais controlados, sempre manuais e fora da publicação automática.",
        default_duration_sec=45,
        minimum_duration_sec=35,
        maximum_duration_sec=55,
        tone="narrativo_misterioso",
        tone_label="Narrativo misterioso",
        theme_placeholder="Ex.: duas escolhas impossíveis em um cenário explicitamente fictício.",
        allows_automatic_topic=False,
    ),
)

_LANES_BY_NICHE = {lane.niche_id: lane for lane in EDITORIAL_LANES}


def editorial_lane_for_niche(niche_id: str) -> EditorialLane:
    try:
        return _LANES_BY_NICHE[niche_id]
    except KeyError as exc:
        raise ValueError(f"unsupported editorial lane niche: {niche_id}") from exc


def editorial_lanes_context() -> list[dict[str, object]]:
    return [lane.as_template_context() for lane in EDITORIAL_LANES]
