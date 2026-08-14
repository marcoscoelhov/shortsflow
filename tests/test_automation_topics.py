from __future__ import annotations

import random

import pytest

import app.automation_topics as automation_topics
from app.automation_topics import (
    COSMOS_CURIOSITY_POOL,
    WINNER_SEED_MIN_SCORE,
    CosmosCuriositySeed,
    select_cosmos_topic,
)


def test_cosmos_pool_has_named_deep_space_winner_seeds() -> None:
    assert WINNER_SEED_MIN_SCORE == 0.97
    winner_topics = "\n".join(
        seed.topic.lower() for seed in COSMOS_CURIOSITY_POOL if seed.base_score >= WINNER_SEED_MIN_SCORE
    )

    for named_subject in ("encélado", "europa", "titã", "wasp-76b", "voyager", "dart", "pulsar"):
        assert named_subject in winner_topics


def test_cosmos_selection_never_uses_a_seed_below_the_winner_threshold(monkeypatch) -> None:
    below_threshold = CosmosCuriositySeed(
        topic="Objeto abaixo do corte",
        requested_angle="Não elegível.",
        hook_seed="Este objeto não pode ser escolhido.",
        visual_seed="Objeto abstrato.",
        tags=("ineligible",),
        base_score=WINNER_SEED_MIN_SCORE - 0.01,
    )
    monkeypatch.setattr(automation_topics, "COSMOS_CURIOSITY_POOL", (below_threshold,))

    with pytest.raises(RuntimeError, match="winner seed threshold"):
        select_cosmos_topic([], rng=random.Random(7))


def test_cosmos_selection_keeps_recent_topic_anti_repetition() -> None:
    selected = select_cosmos_topic(
        ["Por que Vênus é mais quente que Mercúrio?"],
        rng=random.Random(7),
    )

    assert selected.topic != "Por que Vênus é mais quente que Mercúrio?"
    assert selected.score >= WINNER_SEED_MIN_SCORE
