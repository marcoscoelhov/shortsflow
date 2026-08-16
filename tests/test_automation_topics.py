from __future__ import annotations

import json
import random
from types import SimpleNamespace

import pytest

import app.automation_topics as automation_topics
from app.automation_topics import (
    COSMOS_CURIOSITY_POOL,
    WINNER_SEED_MIN_SCORE,
    CosmosCuriositySeed,
    cosmos_topic_candidates_note,
    select_cosmos_topics,
    select_cosmos_topic,
)
from app.pipelines.topic_pipeline import TopicPipeline
from app.pipelines.common import RecoverableStepError
from app.providers.errors import ProviderFailure


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


def test_cosmos_draft_inputs_are_three_distinct_winner_seeds() -> None:
    selected = select_cosmos_topics([], count=3)

    assert len(selected) == 3
    assert len({candidate.topic for candidate in selected}) == 3
    assert all(candidate.score >= WINNER_SEED_MIN_SCORE for candidate in selected)


def test_cosmos_draft_rotation_backfills_after_recent_catalog_exhaustion() -> None:
    recent = [seed.topic for seed in COSMOS_CURIOSITY_POOL if seed.base_score >= WINNER_SEED_MIN_SCORE]

    selected = select_cosmos_topics(recent, count=3)

    assert len(selected) == 3
    assert len({candidate.topic for candidate in selected}) == 3
    assert all(candidate.score >= WINNER_SEED_MIN_SCORE for candidate in selected)


class _Storage:
    def __init__(self, root) -> None:
        self.root = root

    def persist_json(self, job_id, relative_path, payload):
        path = self.root / job_id / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


class _Session:
    def __init__(self, request) -> None:
        self.request = request
        self.added = []

    def scalar(self, _statement):
        return self.request

    def execute(self, _statement):
        return None

    def add(self, value):
        self.added.append(value)


class _Creative:
    def __init__(self, drafts, *, selection=None, batch_error=None, judge_error=None) -> None:
        self.drafts = list(drafts)
        self.selection = selection or _selection(7)
        self.batch_error = batch_error
        self.judge_error = judge_error
        self.batch_calls = []
        self.plan_calls = []
        self.judge_calls = []

    def plan_topic_batch(self, candidates, draft_count, attempt, history, tone=None, notes=None):
        self.batch_calls.append(
            {
                "candidates": candidates,
                "draft_count": draft_count,
                "attempt": attempt,
                "history": history,
                "tone": tone,
                "notes": notes,
            }
        )
        if self.batch_error:
            raise self.batch_error
        return {"drafts": self.drafts}

    def select_topic_draft(self, drafts):
        self.judge_calls.append(drafts)
        if self.judge_error:
            raise self.judge_error
        return self.selection

    def plan_topic(self, seed_theme, attempt, history, requested_angle, tone=None, notes=None):
        self.plan_calls.append({"seed_theme": seed_theme, "requested_angle": requested_angle, "notes": notes})
        draft = self.drafts[0]
        if isinstance(draft, Exception):
            raise draft
        return draft


def _draft(topic: str, score=0.5, *, fallback=False) -> dict:
    metrics = {
        "viral_potential_score": score,
        "viral_potential_reason": f"Razão viral curta para {topic}",
        "source_provider": "deepseek" if fallback else "openai",
    }
    if fallback:
        metrics.update({"fallback_used": True, "fallback_reason": "openai_text failed"})
    return {
        "canonical_topic": topic,
        "angle": f"Ângulo visual sobre {topic}",
        "hook_promise": f"{topic} revela uma surpresa visível.",
        "title_candidates": [
            topic,
            f"{topic}: o detalhe que quase ninguém percebe",
            f"Por que {topic} parece impossível",
        ],
        "entities": [topic],
        "search_terms": [f"{topic} astronomy"],
        "quality_metrics": metrics,
    }


TOPICS = [
    "A Lua gigante no horizonte",
    "A Voyager sussurra para a Terra",
    "Os anéis de Saturno brilham",
    "O pulsar funciona como um farol",
    "Encélado lança gêiseres no espaço",
    "Titã tem rios sem água",
    "WASP-76b pode ter chuva de ferro",
    "A missão DART moveu um asteroide",
    "Europa esconde um oceano sob o gelo",
    "Uma galáxia vira um anel de luz",
]


def _drafts(*, fallback=False) -> list[dict]:
    return [_draft(topic, 0.99 - index * 0.03, fallback=fallback) for index, topic in enumerate(TOPICS)]


def _selection(selected_index: int) -> dict:
    order = [selected_index, *[index for index in range(10) if index != selected_index]]
    return {
        "selected_index": selected_index,
        "selected_reason": "Este rascunho combina surpresa, clareza e força visual.",
        "ranking": [
            {
                "index": index,
                "viral_potential_score": round(0.99 - position * 0.03, 2),
                "reason": f"Avaliação independente do rascunho {index}.",
            }
            for position, index in enumerate(order)
        ],
        "confidence": 0.91,
        "provider": "xai",
        "model": "grok-4.6",
        "judge_provider_role": "gate_judge",
    }


def _pipeline_harness(tmp_path, drafts, *, origin="automatic_topic", selection=None, judge_error=None):
    candidates = select_cosmos_topics([], count=8)
    request = SimpleNamespace(
        seed_theme=candidates[0].topic,
        requested_angle=candidates[0].requested_angle,
        tone="intrigante_direto",
        notes="\n".join(["automatic_topic_policy=cosmos_astronomia_universo_first", cosmos_topic_candidates_note(candidates)]),
        niche_id="curiosidades",
    )
    creative = _Creative(drafts, selection=selection, judge_error=judge_error)
    events = []
    owner = SimpleNamespace(
        settings=SimpleNamespace(schema_version="1.0.0", llm_topic_repair_attempts=2),
        storage=_Storage(tmp_path),
        providers=SimpleNamespace(creative=creative),
        _append_event=lambda *args: events.append(args),
        _persist_repair_telemetry=lambda *_args: "quality/topic_plan_repair.json",
        _serialize_for_json=lambda payload: payload,
    )
    pipeline = TopicPipeline(owner)
    pipeline.recent_topic_history = lambda *_args, **_kwargs: []
    session = _Session(request)
    job = SimpleNamespace(job_id="job-topic-drafts", job_origin=origin, topic_summary=None)
    return pipeline, session, job, creative, events


def test_automatic_topic_generates_one_batch_and_independent_judge_selects_nonmax_self_score(tmp_path) -> None:
    drafts = _drafts()
    pipeline, session, job, creative, events = _pipeline_harness(tmp_path, drafts, selection=_selection(7))

    artifacts = pipeline.step_topic_plan(session, job, attempt=1)

    assert len(creative.batch_calls) == 1
    assert creative.batch_calls[0]["draft_count"] == 10
    assert len(creative.batch_calls[0]["candidates"]) == 8
    assert creative.plan_calls == []
    assert len(creative.judge_calls) == 1
    assert session.added[0].canonical_topic == TOPICS[7]
    assert "topic_drafts.json" in artifacts
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["draft_count"] == 10
    assert len(audit["drafts"]) == 10
    assert audit["selected_index"] == 7
    assert audit["selected_judge_score"] == 0.99
    assert audit["judge_provider"] == "xai"
    assert audit["judge_model"] == "grok-4.6"
    assert audit["judge_provider_role"] == "gate_judge"
    assert audit["ranking"][0]["index"] == 7
    assert session.added[0].quality_metrics["topic_draft_selected_index"] == 7
    assert session.added[0].quality_metrics["topic_draft_selected_judge_score"] == 0.99
    assert events[-1][3]["topic_draft_selected_index"] == 7


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda result: result["ranking"].__setitem__(1, dict(result["ranking"][0])), "ranking_indices_invalid"),
        (lambda result: result.__setitem__("selected_index", 3), "selected_index_ranking_mismatch"),
        (lambda result: result["ranking"][0].__setitem__("viral_potential_score", "0.99"), "ranking_score_invalid"),
        (lambda result: result["ranking"].reverse(), "ranking_not_descending"),
        (lambda result: result["ranking"][0].__setitem__("reason", ""), "ranking_reason_missing"),
    ],
)
def test_topic_draft_judge_contract_fails_closed(tmp_path, mutate, reason) -> None:
    selection = _selection(7)
    mutate(selection)
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts(), selection=selection)

    with pytest.raises(RecoverableStepError, match="topic draft judge selection malformed"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert len(creative.judge_calls) == 1
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["failure_reason"] == reason
    assert audit["selected_index"] is None


@pytest.mark.parametrize("count", [9, 11])
def test_automatic_topic_requires_exactly_ten_drafts_before_judge(tmp_path, count) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts()[:count] if count < 10 else [*_drafts(), _draft("Netuno tem nuvens azuis", 0.4)])

    with pytest.raises(RecoverableStepError, match="exactly 10"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["draft_count"] == count


def test_duplicate_in_batch_blocks_before_judge_and_persists_audit(tmp_path) -> None:
    drafts = _drafts()
    drafts[6] = _draft(TOPICS[0], 0.4)
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, drafts)

    with pytest.raises(RecoverableStepError, match="invalid or repeating"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["drafts"][6]["rejection_reason"] == "topic_draft_not_distinct"


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda draft: draft.pop("angle"), "topic_draft_schema_invalid"),
        (lambda draft: draft.__setitem__("title_candidates", draft["title_candidates"][:2]), "topic_draft_schema_invalid"),
        (lambda draft: draft.__setitem__("quality_metrics", {"viral_potential_score": 0.5}), "topic_draft_schema_invalid"),
    ],
)
def test_raw_draft_schema_missing_fields_blocks_before_normalization(tmp_path, mutate, reason) -> None:
    drafts = _drafts()
    mutate(drafts[3])
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, drafts)

    with pytest.raises(RecoverableStepError, match="invalid or repeating"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["drafts"][3]["rejection_reason"] == reason


def test_identity_duplicate_with_paraphrased_angle_and_hook_blocks_before_judge(tmp_path) -> None:
    drafts = _drafts()
    drafts[6] = {
        **drafts[6],
        "canonical_topic": drafts[0]["canonical_topic"],
        "entities": drafts[0]["entities"],
        "angle": "Uma perspectiva completamente diferente de abordar o tema",
        "hook_promise": "Uma promessa narrativa totalmente distinta da primeira versão",
    }
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, drafts)

    with pytest.raises(RecoverableStepError, match="invalid or repeating"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["drafts"][6]["rejection_reason"] == "topic_draft_not_distinct"


def test_identity_match_against_history_canonical_topic_blocks_before_judge(tmp_path) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts())
    pipeline.recent_topic_history = lambda *_args, **_kwargs: [
        {"canonical_topic": TOPICS[2], "title": "um título totalmente diferente", "hook": "um gancho totalmente diferente"}
    ]

    with pytest.raises(RecoverableStepError, match="invalid or repeating"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["drafts"][2]["rejection_reason"] == "topic_too_similar_to_history"


def test_all_eligible_seeds_are_supplied_as_batch_candidates_without_cap(monkeypatch, tmp_path) -> None:
    seeds = tuple(
        CosmosCuriositySeed(
            topic=f"Tema espacial {index}",
            requested_angle=f"Ângulo {index}",
            hook_seed=f"Hook {index}",
            visual_seed=f"Visual {index}",
            tags=("astronomia",),
            base_score=0.99,
        )
        for index in range(13)
    )
    monkeypatch.setattr(automation_topics, "COSMOS_CURIOSITY_POOL", seeds)
    monkeypatch.setattr("app.pipelines.topic_pipeline.COSMOS_CURIOSITY_POOL", seeds)
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts())
    session.request.notes = "automatic_topic_policy=cosmos_astronomia_universo_first"

    pipeline.step_topic_plan(session, job, attempt=1)

    assert len(creative.batch_calls) == 1
    assert len(creative.batch_calls[0]["candidates"]) == 13
    assert creative.batch_calls[0]["draft_count"] == 10


def test_topic_matching_approved_history_blocks_before_judge_and_persists_audit(tmp_path) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts())
    pipeline.recent_topic_history = lambda *_args, **_kwargs: [
        {"canonical_topic": TOPICS[2], "title": TOPICS[2], "hook": f"{TOPICS[2]} revela uma surpresa visível."}
    ]

    with pytest.raises(RecoverableStepError, match="invalid or repeating"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert creative.judge_calls == []
    audit = json.loads((tmp_path / job.job_id / "topic_drafts.json").read_text(encoding="utf-8"))
    assert audit["drafts"][2]["rejection_reason"] == "topic_too_similar_to_history"


def test_judge_failure_blocks_without_generator_fallback(tmp_path) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(
        tmp_path,
        _drafts(),
        judge_error=ProviderFailure("xai_text", "Grok unavailable"),
    )

    with pytest.raises(RecoverableStepError, match="independent topic draft judge failed"):
        pipeline.step_topic_plan(session, job, attempt=1)

    assert session.added == []
    assert len(creative.batch_calls) == 1
    assert len(creative.judge_calls) == 1
    assert creative.plan_calls == []


def test_automatic_topic_derives_candidates_for_legacy_ingress_without_candidate_note(tmp_path) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(tmp_path, _drafts())
    session.request.notes = "automatic_topic_policy=cosmos_astronomia_universo_first"

    pipeline.step_topic_plan(session, job, attempt=1)

    assert len(creative.batch_calls) == 1
    assert 1 <= len(creative.batch_calls[0]["candidates"]) <= 12


def test_manual_theme_keeps_existing_single_topic_plan_path(tmp_path) -> None:
    pipeline, session, job, creative, _events = _pipeline_harness(
        tmp_path,
        [_draft("A Lua gigante no horizonte", 0.71)],
        origin="manual_theme",
    )

    artifacts = pipeline.step_topic_plan(session, job, attempt=1)

    assert len(creative.plan_calls) == 1
    assert creative.batch_calls == []
    assert creative.judge_calls == []
    assert "topic_drafts.json" not in artifacts
