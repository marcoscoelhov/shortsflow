from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.db import session_scope
from app.growth_metrics import build_growth_score
from app.models import Job, LearnedRetentionProfile, ReferenceChannel, ReferenceShort, RetentionExperiment, RetentionExperimentJob, ScoutRun, YouTubeAnalyticsSnapshot
from app.providers.errors import ProviderFailure
from app.providers.llm import LLMProviderRegistry
from app.utils import ensure_dir, new_id, read_json, stable_hash, utcnow, word_tokens, write_json
from app.youtube_api import YouTubePublisher


SCOUT_ANALYSIS_PROMPT_VERSION = "shorts-scout-v1"
HEURISTIC_SCOUT_PROMPT_VERSION = "shorts-scout-heuristic-v1"
EXPERIMENT_UNPUBLISHABLE_JOB_STATUSES = {
    "failed",
    "script_quality_failed",
    "scene_plan_quality_failed",
    "asset_quality_failed",
    "subtitle_quality_failed",
    "render_quality_failed",
    "blocked_for_monetization",
    "rejected",
}
EXPERIMENT_AWAITING_PUBLICATION_JOB_STATUSES = {
    "monetization_review",
    "ready_for_upload",
    "approved_for_publish",
}


LINE_KEYWORDS: dict[str, set[str]] = {
    "curiosidade_cotidiana": {
        "agua",
        "água",
        "banho",
        "bolacha",
        "cafe",
        "café",
        "calor",
        "casa",
        "celular",
        "chuva",
        "cozinha",
        "copo",
        "espelho",
        "gelo",
        "pao",
        "pão",
        "roupa",
        "sol",
        "curious",
        "curiosities",
        "daily",
        "everyday",
        "facts",
        "fakta",
        "unik",
    },
    "percepcao_corpo_leve": {
        "bocejo",
        "cerebro",
        "cérebro",
        "corpo",
        "memoria",
        "memória",
        "olho",
        "pele",
        "sensacao",
        "sensação",
        "sono",
        "body",
        "brain",
        "cuerpo",
        "eye",
        "memory",
        "otak",
        "piel",
        "skin",
        "sleep",
        "tubuh",
    },
    "ciencia_visual_simples": {
        "atmosfera",
        "fisica",
        "física",
        "luz",
        "oceano",
        "planeta",
        "raio",
        "vulcao",
        "vulcão",
        "ciencia",
        "light",
        "planet",
        "physics",
        "science",
        "sains",
        "space",
        "universe",
        "volcano",
    },
    "tecnologia_popular": {
        "algoritmo",
        "bateria",
        "internet",
        "ia",
        "inteligencia",
        "inteligência",
        "smartphone",
        "tecnologia",
        "whatsapp",
        "ai",
        "battery",
        "smartphone",
        "technology",
        "teknologi",
    },
    "natureza_payoff_visual": {
        "abelha",
        "animal",
        "animais",
        "formiga",
        "fungo",
        "natureza",
        "planta",
        "polvo",
        "tubarao",
        "tubarão",
        "alam",
        "animal",
        "animals",
        "animales",
        "hewan",
        "nature",
        "naturaleza",
        "plant",
        "shark",
    },
}

SHOCK_TERMS = {
    "absurdo",
    "estranho",
    "impossivel",
    "impossível",
    "nunca",
    "segredo",
    "surpreendente",
}
TENSION_TERMS = {"mas", "antes", "depois", "quando", "enquanto", "só", "so", "parece", "vira"}


@dataclass(frozen=True)
class ReferenceShortCandidate:
    youtube_video_id: str
    youtube_channel_id: str
    channel_title: str
    title: str
    description: str
    published_at: datetime | None
    duration_sec: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    line_id: str
    performance_score: float
    confidence: str
    performance_proxy: dict[str, Any]
    raw_metadata: dict[str, Any]
    discovery_contexts: list[dict[str, Any]]

    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"


class ScoutAnalyzer(Protocol):
    def analyze_reference_short(self, candidate: ReferenceShortCandidate) -> dict[str, Any]:
        ...


def normalize_text(text: str) -> str:
    replacements = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return str(text or "").lower().translate(replacements)


def classify_editorial_line(title: str, description: str = "") -> str:
    tokens = set(word_tokens(normalize_text(f"{title} {description}")))
    best_line = "desconhecida"
    best_score = 0
    for line_id, keywords in LINE_KEYWORDS.items():
        score = len(tokens & {normalize_text(keyword) for keyword in keywords})
        if score > best_score:
            best_line = line_id
            best_score = score
    return best_line


def parse_youtube_duration(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?", text)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86_400 + hours * 3_600 + minutes * 60 + seconds


def parse_youtube_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def reference_maturity_hours(published_at: datetime | None, *, now: datetime | None = None) -> float | None:
    if published_at is None:
        return None
    now_utc = now or utcnow()
    published_utc = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    return max(0.0, (now_utc - published_utc).total_seconds() / 3600)


def build_performance_proxy(
    *,
    view_count: int | None,
    like_count: int | None,
    comment_count: int | None,
    published_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    views = max(int(view_count or 0), 0)
    likes = max(int(like_count or 0), 0)
    comments = max(int(comment_count or 0), 0)
    maturity_hours = reference_maturity_hours(published_at, now=now)
    age_days = (maturity_hours / 24) if maturity_hours is not None else None
    like_rate = round((likes / views) * 100, 3) if views else None
    comment_rate = round((comments / views) * 100, 3) if views else None
    velocity = round(views / max(age_days or 1.0, 1.0), 2)
    score = round((views / 10_000) + (likes / 1_000) + (comments / 200) + min(velocity / 10_000, 4), 3)
    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "like_rate": like_rate,
        "comment_rate": comment_rate,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "views_per_day": velocity,
        "score": score,
    }


class HeuristicScoutAnalyzer:
    def analyze_reference_short(self, candidate: ReferenceShortCandidate) -> dict[str, Any]:
        text = f"{candidate.title}. {candidate.description}"
        normalized = normalize_text(text)
        tokens = set(word_tokens(normalized))
        has_question = "?" in candidate.title or {"por", "que"}.issubset(tokens) or "como" in tokens
        shock_hits = sorted(tokens & {normalize_text(term) for term in SHOCK_TERMS})
        tension_hits = sorted(tokens & {normalize_text(term) for term in TENSION_TERMS})
        observed_structure = []
        if shock_hits:
            observed_structure.append("abre_com_contraste_ou_choque")
        if has_question:
            observed_structure.append("abre_loop_por_pergunta_mental")
        if tension_hits:
            observed_structure.append("usa_tensao_progressiva")
        observed_structure.append("promete_payoff_visual_ou_cotidiano")
        retention_moves = [
            "capturar atencao com promessa especifica",
            "segurar explicacao completa",
            "entregar virada reaplicavel no ultimo movimento",
        ]
        return {
            "prompt_version": HEURISTIC_SCOUT_PROMPT_VERSION,
            "analysis_provider": "heuristic",
            "source_confidence": candidate.confidence,
            "line": candidate.line_id,
            "observed_structure": observed_structure,
            "retention_moves": retention_moves,
            "unusual_pattern": "indefinido_sem_transcricao_autorizada",
            "transferability": "usar como sinal fraco de titulo, descricao e metadata; nao copiar narrativa especifica",
            "risks": ["sem_retencao_externa_real", "sem_transcricao_autorizada"],
            "forbidden_copy_elements": ["palavras do titulo", "descricao", "exemplos especificos do video"],
            "why_it_might_work": "metadata publica sugere interesse; estrutura textual disponivel indica curiosidade transferivel",
        }


class LLMScoutAnalyzer:
    def __init__(self, fallback: ScoutAnalyzer | None = None) -> None:
        self.fallback = fallback or HeuristicScoutAnalyzer()
        try:
            self.provider = LLMProviderRegistry().primary_provider()
        except ProviderFailure:
            self.provider = None

    def analyze_reference_short(self, candidate: ReferenceShortCandidate) -> dict[str, Any]:
        if self.provider is None or not hasattr(self.provider, "_json_completion"):
            return self.fallback.analyze_reference_short(candidate)
        prompt = self._prompt(candidate)
        try:
            payload = self.provider._json_completion(prompt)  # type: ignore[attr-defined]
        except Exception:
            return self.fallback.analyze_reference_short(candidate)
        if not isinstance(payload, dict):
            return self.fallback.analyze_reference_short(candidate)
        payload.setdefault("prompt_version", SCOUT_ANALYSIS_PROMPT_VERSION)
        payload.setdefault("analysis_provider", getattr(self.provider, "provider_name", "llm"))
        payload.setdefault("analysis_model", getattr(self.provider, "model_name", None))
        payload.setdefault("line", candidate.line_id)
        payload.setdefault("source_confidence", candidate.confidence)
        return payload

    def _prompt(self, candidate: ReferenceShortCandidate) -> str:
        source = {
            "title": candidate.title,
            "description_excerpt": candidate.description[:1400],
            "line_id": candidate.line_id,
            "duration_sec": candidate.duration_sec,
            "performance_proxy": candidate.performance_proxy,
            "transcript_source": "none",
        }
        return (
            "Analise este Short de referencia para aprender estrutura viral sem copiar texto.\n"
            "Responda JSON com: observed_structure, retention_moves, unusual_pattern, transferability, "
            "risks, forbidden_copy_elements, why_it_might_work.\n"
            "Nao invente transcricao. Se so houver titulo/descricao, marque baixa confianca.\n"
            f"Entrada JSON:\n{json.dumps(source, ensure_ascii=False)}"
        )


class CompetitiveScout:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        youtube: Any | None = None,
        analyzer: ScoutAnalyzer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.youtube = youtube or YouTubePublisher(self.settings)
        self.analyzer = analyzer or (LLMScoutAnalyzer() if self.settings.competitive_scout_llm_analysis_enabled else HeuristicScoutAnalyzer())

    def approved_reference_channel_ids(self, *, niche_id: str = "curiosidades") -> list[str]:
        with session_scope() as session:
            return list(
                session.scalars(
                    select(ReferenceChannel.youtube_channel_id)
                    .where(ReferenceChannel.status == "approved")
                    .where(ReferenceChannel.niche_id == niche_id)
                    .order_by(ReferenceChannel.updated_at.desc())
                ).all()
            )

    def run_automation_cycle(
        self,
        *,
        niche_id: str | None = None,
        queries: list[str] | None = None,
        channel_ids: list[str] | None = None,
        max_results_per_source: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not bool(self.settings.competitive_scout_automation_enabled):
            return {"status": "skipped", "reason": "competitive_scout_automation_disabled"}
        selected_niche = niche_id or self.settings.niche_id
        result: dict[str, Any] = {
            "status": "completed",
            "niche_id": selected_niche,
            "evaluated_experiments": [],
            "promoted_profiles": [],
            "scout_run": None,
            "profiles": None,
            "approved_profiles": [],
            "started_experiments": [],
            "skipped": [],
        }
        result["evaluated_experiments"] = self.evaluate_due_experiments(niche_id=selected_niche)
        if bool(self.settings.competitive_scout_auto_promote_profiles):
            for evaluation in result["evaluated_experiments"]:
                if evaluation.get("decision") != "success_strong":
                    continue
                try:
                    result["promoted_profiles"].append(self.promote_experiment_winner(str(evaluation["experiment_id"])))
                except ValueError as exc:
                    result["skipped"].append({"stage": "promote", "experiment_id": evaluation.get("experiment_id"), "reason": str(exc)})

        target_channels = channel_ids if channel_ids is not None else self.approved_reference_channel_ids(niche_id=selected_niche)
        target_queries = queries if queries is not None else self._automation_queries()
        if not target_channels and not target_queries:
            result["status"] = "skipped"
            result["reason"] = "no_competitive_scout_sources"
            return result
        try:
            scout_run = self.run(
                niche_id=selected_niche,
                channel_ids=target_channels,
                queries=target_queries,
                max_results_per_source=max_results_per_source,
                now=now,
            )
        except Exception as exc:  # noqa: BLE001
            result["status"] = "failed"
            result["reason"] = str(exc)
            return result
        result["scout_run"] = scout_run
        if int(scout_run.get("shorts_selected") or 0) <= 0:
            result["skipped"].append({"stage": "synthesize_profiles", "reason": "no_selected_reference_shorts"})
            return result

        profile_result = self.synthesize_profiles_from_run(str(scout_run["run_id"]))
        result["profiles"] = profile_result
        created_profiles = [item for item in profile_result.get("created") or [] if isinstance(item, dict)]
        for item in created_profiles:
            profile_id = str(item.get("profile_id") or "")
            if not profile_id:
                continue
            if bool(self.settings.competitive_scout_auto_approve_profiles) and item.get("status") == "pending_approval":
                try:
                    approved = self.approve_profile(profile_id)
                    result["approved_profiles"].append(approved)
                    item = {**item, "status": approved.get("status")}
                except ValueError as exc:
                    result["skipped"].append({"stage": "approve_profile", "profile_id": profile_id, "reason": str(exc)})
                    continue
            if bool(self.settings.competitive_scout_auto_start_experiments) and item.get("status") in {"approved", "promoted"}:
                if self._line_has_running_experiment(profile_id):
                    result["skipped"].append({"stage": "start_experiment", "profile_id": profile_id, "reason": "line_already_has_running_experiment"})
                    continue
                try:
                    result["started_experiments"].append(self.start_experiment(profile_id))
                except ValueError as exc:
                    result["skipped"].append({"stage": "start_experiment", "profile_id": profile_id, "reason": str(exc)})
        return result

    def evaluate_due_experiments(self, *, niche_id: str | None = None) -> list[dict[str, Any]]:
        selected_niche = niche_id or self.settings.niche_id
        with session_scope() as session:
            experiment_ids = list(
                session.scalars(
                    select(RetentionExperiment.experiment_id)
                    .join(LearnedRetentionProfile, LearnedRetentionProfile.profile_id == RetentionExperiment.profile_id)
                    .where(RetentionExperiment.status == "running")
                    .where(LearnedRetentionProfile.niche_id == selected_niche)
                    .order_by(RetentionExperiment.started_at.asc(), RetentionExperiment.created_at.asc())
                ).all()
            )
        results: list[dict[str, Any]] = []
        for experiment_id in experiment_ids:
            try:
                results.append(self.evaluate_experiment(experiment_id))
            except ValueError as exc:
                results.append({"experiment_id": experiment_id, "status": "skipped", "reason": str(exc)})
        return results

    def synthesize_profiles_from_run(
        self,
        run_id: str,
        *,
        min_references: int | None = None,
        aggressive: bool = True,
    ) -> dict[str, Any]:
        threshold = int(min_references or self.settings.competitive_scout_min_profile_references)
        with session_scope() as session:
            run = session.get(ScoutRun, run_id)
            if run is None or not run.artifact_path:
                raise ValueError("Rodada de scout não encontrada ou sem artefato")
            payload = self._read_artifact(run.artifact_path)
            selected_video_ids = [
                str(item.get("youtube_video_id") or "").strip()
                for item in payload.get("selected") or []
                if isinstance(item, dict) and str(item.get("youtube_video_id") or "").strip()
            ]
            shorts = list(
                session.scalars(
                    select(ReferenceShort)
                    .where(ReferenceShort.youtube_video_id.in_(selected_video_ids))
                    .where(ReferenceShort.status == "selected")
                ).all()
            )
            shorts_by_line: dict[str, list[ReferenceShort]] = defaultdict(list)
            for short in shorts:
                if short.line_id:
                    shorts_by_line[short.line_id].append(short)

            created: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for line_id, line_shorts in sorted(shorts_by_line.items()):
                if len(line_shorts) < threshold:
                    skipped.append({"line_id": line_id, "references": len(line_shorts), "minimum": threshold})
                    continue
                existing = session.scalar(
                    select(LearnedRetentionProfile)
                    .where(LearnedRetentionProfile.source_run_id == run_id)
                    .where(LearnedRetentionProfile.line_id == line_id)
                    .where(LearnedRetentionProfile.status.in_(["pending_approval", "approved", "promoted"]))
                )
                if existing is not None:
                    created.append(
                        {
                            "profile_id": existing.profile_id,
                            "line_id": line_id,
                            "status": existing.status,
                            "references": len(existing.supporting_reference_short_ids or []),
                            "existing": True,
                        }
                    )
                    continue
                skeleton = self._dominant_skeleton(line_id=line_id, shorts=line_shorts, aggressive=aggressive)
                profile_id = new_id()
                artifact_path = self._persist_scout_artifact(
                    run_id,
                    f"retention_profile_{line_id}_{profile_id}.json",
                    {
                        "schema_version": self.settings.schema_version,
                        "profile_id": profile_id,
                        "source_run_id": run_id,
                        "line_id": line_id,
                        "created_at": utcnow().isoformat(),
                        "dominant_skeleton": skeleton,
                        "references": [self._short_reference_json(short) for short in line_shorts],
                    },
                )
                profile = LearnedRetentionProfile(
                    profile_id=profile_id,
                    schema_version=self.settings.schema_version,
                    content_hash="pending",
                    version=f"{line_id}-{utcnow().strftime('%Y%m%d%H%M%S')}",
                    status="pending_approval",
                    niche_id=run.niche_id,
                    line_id=line_id,
                    title=f"Esqueleto vencedor: {line_id}",
                    confidence="alta" if len(line_shorts) >= threshold * 2 else "media",
                    source_run_id=run_id,
                    analysis_artifact_path=artifact_path,
                    supporting_reference_short_ids=[short.reference_short_id for short in line_shorts],
                    dominant_skeleton=skeleton,
                    metrics={
                        "reference_count": len(line_shorts),
                        "minimum_references": threshold,
                        "aggressive": aggressive,
                        "average_reference_score": round(sum(float(short.performance_score or 0) for short in line_shorts) / max(len(line_shorts), 1), 3),
                    },
                )
                profile.content_hash = stable_hash(
                    {
                        "version": profile.version,
                        "status": profile.status,
                        "line_id": profile.line_id,
                        "supporting_reference_short_ids": profile.supporting_reference_short_ids,
                        "dominant_skeleton": profile.dominant_skeleton,
                        "metrics": profile.metrics,
                    }
                )
                session.add(profile)
                run.profiles_created = int(run.profiles_created or 0) + 1
                run.summary = {**dict(run.summary or {}), "profiles_created": int(run.profiles_created or 0)}
                run.content_hash = stable_hash({"run_id": run.run_id, "status": run.status, "summary": run.summary})
                created.append(
                    {
                        "profile_id": profile_id,
                        "line_id": line_id,
                        "status": profile.status,
                        "references": len(line_shorts),
                        "artifact_path": artifact_path,
                        "existing": False,
                    }
                )
        return {"run_id": run_id, "created": created, "skipped": skipped, "minimum_references": threshold}

    def approve_profile(self, profile_id: str, *, action: str = "approve") -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"approve", "reject", "archive"}:
            raise ValueError("ação de perfil inválida")
        now = utcnow()
        with session_scope() as session:
            profile = session.get(LearnedRetentionProfile, profile_id)
            if profile is None:
                raise ValueError("Perfil de retenção não encontrado")
            if normalized_action == "approve":
                profile.status = "approved"
                profile.approved_at = profile.approved_at or now
            elif normalized_action == "reject":
                profile.status = "rejected"
                profile.archived_at = profile.archived_at or now
            else:
                profile.status = "archived"
                profile.archived_at = profile.archived_at or now
            profile.content_hash = stable_hash(
                {
                    "profile_id": profile.profile_id,
                    "version": profile.version,
                    "status": profile.status,
                    "approved_at": profile.approved_at.isoformat() if profile.approved_at else None,
                    "archived_at": profile.archived_at.isoformat() if profile.archived_at else None,
                    "dominant_skeleton": profile.dominant_skeleton,
                }
            )
            return {"profile_id": profile.profile_id, "status": profile.status, "line_id": profile.line_id}

    def start_experiment(self, profile_id: str, *, target_job_count: int | None = None) -> dict[str, Any]:
        target = int(target_job_count or self.settings.retention_experiment_target_job_count)
        with session_scope() as session:
            profile = session.get(LearnedRetentionProfile, profile_id)
            if profile is None:
                raise ValueError("Perfil de retenção não encontrado")
            if profile.status not in {"approved", "promoted"}:
                raise ValueError("Perfil precisa estar aprovado antes de iniciar experimento")
            existing = session.scalar(
                select(RetentionExperiment)
                .where(RetentionExperiment.profile_id == profile_id)
                .where(RetentionExperiment.status.in_(["planned", "running"]))
                .order_by(RetentionExperiment.created_at.desc())
            )
            if existing is not None:
                return {
                    "experiment_id": existing.experiment_id,
                    "profile_id": profile_id,
                    "status": existing.status,
                    "target_job_count": existing.target_job_count,
                    "existing": True,
                }
            experiment = RetentionExperiment(
                experiment_id=new_id(),
                profile_id=profile_id,
                schema_version=self.settings.schema_version,
                content_hash="pending",
                status="running",
                line_id=profile.line_id,
                started_at=utcnow(),
                target_job_count=max(1, target),
                result_summary={},
            )
            experiment.content_hash = stable_hash(
                {
                    "experiment_id": experiment.experiment_id,
                    "profile_id": experiment.profile_id,
                    "status": experiment.status,
                    "target_job_count": experiment.target_job_count,
                    "line_id": experiment.line_id,
                }
            )
            session.add(experiment)
            return {
                "experiment_id": experiment.experiment_id,
                "profile_id": profile_id,
                "status": experiment.status,
                "target_job_count": experiment.target_job_count,
                "existing": False,
            }

    def active_experiment_guidance(self, *, niche_id: str = "curiosidades") -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.execute(
                select(RetentionExperiment, LearnedRetentionProfile)
                .join(LearnedRetentionProfile, LearnedRetentionProfile.profile_id == RetentionExperiment.profile_id)
                .where(RetentionExperiment.status == "running")
                .where(LearnedRetentionProfile.status.in_(["approved", "promoted"]))
                .where(LearnedRetentionProfile.niche_id == niche_id)
                .order_by(RetentionExperiment.started_at.desc(), RetentionExperiment.created_at.desc())
            ).first()
            if row is None:
                return None
            experiment, profile = row
            assigned_count = session.scalar(
                select(func.count()).select_from(RetentionExperimentJob).where(RetentionExperimentJob.experiment_id == experiment.experiment_id)
            ) or 0
            if assigned_count >= int(experiment.target_job_count or 0):
                return None
            guidance = self._profile_guidance_text(profile, experiment_id=experiment.experiment_id)
            return {
                "experiment_id": experiment.experiment_id,
                "profile_id": profile.profile_id,
                "line_id": profile.line_id,
                "assigned_count": assigned_count,
                "target_job_count": experiment.target_job_count,
                "guidance_text": guidance,
            }

    def attach_job_to_active_experiment(self, job_id: str, *, niche_id: str = "curiosidades") -> dict[str, Any] | None:
        guidance = self.active_experiment_guidance(niche_id=niche_id)
        if guidance is None:
            return None
        return self.attach_job_to_experiment(str(guidance["experiment_id"]), job_id)

    def attach_job_to_experiment(self, experiment_id: str, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            experiment = session.get(RetentionExperiment, experiment_id)
            if experiment is None:
                raise ValueError("Experimento de retenção não encontrado")
            existing = session.scalar(
                select(RetentionExperimentJob)
                .where(RetentionExperimentJob.experiment_id == experiment_id)
                .where(RetentionExperimentJob.job_id == job_id)
            )
            if existing is not None:
                return {"experiment_id": experiment_id, "job_id": job_id, "status": existing.status, "existing": True}
            row = RetentionExperimentJob(
                experiment_job_id=new_id(),
                experiment_id=experiment_id,
                job_id=job_id,
                schema_version=self.settings.schema_version,
                content_hash="pending",
                status="assigned",
                role="experiment",
                metrics={},
            )
            row.content_hash = stable_hash({"experiment_id": row.experiment_id, "job_id": row.job_id, "status": row.status})
            session.add(row)
            return {"experiment_id": experiment_id, "job_id": job_id, "status": row.status, "existing": False}

    def evaluate_experiment(self, experiment_id: str) -> dict[str, Any]:
        min_views = int(self.settings.retention_experiment_min_views)
        success_threshold = float(self.settings.retention_experiment_success_retention_percent)
        with session_scope() as session:
            experiment = session.get(RetentionExperiment, experiment_id)
            if experiment is None:
                raise ValueError("Experimento de retenção não encontrado")
            assignments = list(
                session.scalars(select(RetentionExperimentJob).where(RetentionExperimentJob.experiment_id == experiment_id)).all()
            )
            job_ids = [assignment.job_id for assignment in assignments]
            snapshots = list(
                session.scalars(
                    select(YouTubeAnalyticsSnapshot)
                    .where(YouTubeAnalyticsSnapshot.job_id.in_(job_ids))
                    .order_by(YouTubeAnalyticsSnapshot.fetched_at.desc())
                ).all()
            ) if job_ids else []
            latest_by_job: dict[str, YouTubeAnalyticsSnapshot] = {}
            for snapshot in snapshots:
                if snapshot.job_id not in latest_by_job:
                    latest_by_job[snapshot.job_id] = snapshot
            jobs_by_id = {
                job.job_id: job
                for job in session.scalars(select(Job).where(Job.job_id.in_(job_ids))).all()
            } if job_ids else {}
            evaluated_jobs: list[dict[str, Any]] = []
            for assignment in assignments:
                snapshot = latest_by_job.get(assignment.job_id)
                job = jobs_by_id.get(assignment.job_id)
                score = build_growth_score(dict(snapshot.summary_metrics or {}) if snapshot else {}, fetched_at=snapshot.fetched_at if snapshot else None, minimum_views=min_views)
                job_status = job.status if job else None
                metrics = {
                    "views": score["views"],
                    "retention_percent": score["retention_percent"],
                    "confidence": score["confidence"],
                    "score": score["score"],
                    "youtube_video_id": snapshot.youtube_video_id if snapshot else None,
                    "job_status": job_status,
                }
                assignment.metrics = metrics
                if snapshot and score["confidence"] == "confiavel" and score["retention_percent"] is not None:
                    assignment.status = "measured"
                elif snapshot:
                    assignment.status = "measured_low_confidence"
                elif job_status in EXPERIMENT_UNPUBLISHABLE_JOB_STATUSES:
                    assignment.status = "unpublishable"
                elif job_status == "published":
                    assignment.status = "awaiting_analytics"
                elif job_status in EXPERIMENT_AWAITING_PUBLICATION_JOB_STATUSES:
                    assignment.status = "awaiting_publication"
                else:
                    assignment.status = "assigned"
                assignment.content_hash = stable_hash({"experiment_id": experiment_id, "job_id": assignment.job_id, "status": assignment.status, "metrics": metrics})
                evaluated_jobs.append({"job_id": assignment.job_id, **metrics})
            reliable = [item for item in evaluated_jobs if item["confidence"] == "confiavel" and item["retention_percent"] is not None]
            winners = [item for item in reliable if float(item["retention_percent"] or 0) >= success_threshold]
            partials = [item for item in reliable if float(item["retention_percent"] or 0) >= max(75.0, success_threshold - 5)]
            pending_assignments = [
                assignment
                for assignment in assignments
                if assignment.status in {"assigned", "awaiting_publication", "awaiting_analytics", "measured_low_confidence"}
            ]
            if winners:
                decision = "success_strong"
                experiment.status = "completed"
                experiment.finished_at = utcnow()
            elif len(assignments) >= int(experiment.target_job_count or 0) and partials:
                decision = "success_partial"
                experiment.status = "completed"
                experiment.finished_at = utcnow()
            elif len(assignments) >= int(experiment.target_job_count or 0) and not pending_assignments:
                decision = "failed"
                experiment.status = "completed"
                experiment.finished_at = utcnow()
            else:
                decision = "needs_more_data"
                experiment.status = "running"
                experiment.finished_at = None
            summary = {
                "decision": decision,
                "target_job_count": experiment.target_job_count,
                "assigned_jobs": len(assignments),
                "measured_jobs": len(reliable),
                "low_confidence_measured_jobs": len([assignment for assignment in assignments if assignment.status == "measured_low_confidence"]),
                "unpublishable_jobs": len([assignment for assignment in assignments if assignment.status == "unpublishable"]),
                "pending_jobs": len(pending_assignments),
                "success_threshold_retention_percent": success_threshold,
                "minimum_views": min_views,
                "winner_job_ids": [item["job_id"] for item in winners],
                "jobs": evaluated_jobs,
            }
            experiment.decision = decision
            experiment.result_summary = summary
            experiment.content_hash = stable_hash({"experiment_id": experiment_id, "status": experiment.status, "decision": decision, "summary": summary})
            return {"experiment_id": experiment_id, "status": experiment.status, **summary}

    def promote_experiment_winner(self, experiment_id: str) -> dict[str, Any]:
        now = utcnow()
        with session_scope() as session:
            experiment = session.get(RetentionExperiment, experiment_id)
            if experiment is None:
                raise ValueError("Experimento de retenção não encontrado")
            if experiment.decision != "success_strong":
                raise ValueError("Promoção exige experimento com success_strong")
            profile = session.get(LearnedRetentionProfile, experiment.profile_id)
            if profile is None:
                raise ValueError("Perfil de retenção não encontrado")
            if profile.status not in {"approved", "promoted"}:
                raise ValueError("Perfil precisa estar aprovado antes da promoção")
            archived_profile_ids: list[str] = []
            previous_promoted = list(
                session.scalars(
                    select(LearnedRetentionProfile)
                    .where(LearnedRetentionProfile.niche_id == profile.niche_id)
                    .where(LearnedRetentionProfile.line_id == profile.line_id)
                    .where(LearnedRetentionProfile.status == "promoted")
                    .where(LearnedRetentionProfile.profile_id != profile.profile_id)
                ).all()
            )
            for previous in previous_promoted:
                previous.status = "archived"
                previous.archived_at = previous.archived_at or now
                previous.metrics = {
                    **dict(previous.metrics or {}),
                    "archived_by_profile_id": profile.profile_id,
                    "archived_reason": "new_retention_profile_promoted_for_line",
                }
                previous.content_hash = stable_hash(
                    {
                        "profile_id": previous.profile_id,
                        "status": previous.status,
                        "archived_at": previous.archived_at.isoformat() if previous.archived_at else None,
                        "metrics": previous.metrics,
                    }
                )
                archived_profile_ids.append(previous.profile_id)
            profile.status = "promoted"
            profile.promoted_at = profile.promoted_at or now
            profile.metrics = {
                **dict(profile.metrics or {}),
                "promoted_from_experiment_id": experiment_id,
                "promotion_decision": experiment.decision,
                "promotion_winner_job_ids": list((experiment.result_summary or {}).get("winner_job_ids") or []),
                "promoted_at": profile.promoted_at.isoformat() if profile.promoted_at else now.isoformat(),
            }
            profile.content_hash = stable_hash(
                {
                    "profile_id": profile.profile_id,
                    "status": profile.status,
                    "promoted_at": profile.promoted_at.isoformat() if profile.promoted_at else None,
                    "dominant_skeleton": profile.dominant_skeleton,
                    "metrics": profile.metrics,
                }
            )
            experiment.result_summary = {
                **dict(experiment.result_summary or {}),
                "promoted_profile_id": profile.profile_id,
                "archived_profile_ids": archived_profile_ids,
                "promoted_at": profile.promoted_at.isoformat() if profile.promoted_at else now.isoformat(),
            }
            experiment.content_hash = stable_hash(
                {
                    "experiment_id": experiment.experiment_id,
                    "status": experiment.status,
                    "decision": experiment.decision,
                    "summary": experiment.result_summary,
                }
            )
            return {
                "experiment_id": experiment_id,
                "profile_id": profile.profile_id,
                "status": profile.status,
                "line_id": profile.line_id,
                "archived_profile_ids": archived_profile_ids,
            }

    def active_retention_guidance(self, *, niche_id: str = "curiosidades") -> dict[str, Any] | None:
        experiment_guidance = self.active_experiment_guidance(niche_id=niche_id)
        if experiment_guidance is not None:
            return {"source_kind": "experiment", **experiment_guidance}
        with session_scope() as session:
            profile = session.scalar(
                select(LearnedRetentionProfile)
                .where(LearnedRetentionProfile.status == "promoted")
                .where(LearnedRetentionProfile.niche_id == niche_id)
                .order_by(LearnedRetentionProfile.promoted_at.desc(), LearnedRetentionProfile.updated_at.desc())
            )
            if profile is None:
                return None
            return {
                "source_kind": "promoted_profile",
                "profile_id": profile.profile_id,
                "line_id": profile.line_id,
                "guidance_text": self._profile_guidance_text(profile, experiment_id=None, promoted=True),
            }

    def _read_artifact(self, artifact_path: str) -> dict[str, Any]:
        path = Path(artifact_path)
        if not path.is_absolute():
            path = self.settings.artifacts_dir / path
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise ValueError("Artefato de scout inválido")
        return payload

    def _automation_queries(self) -> list[str]:
        raw = str(getattr(self.settings, "competitive_scout_queries", "") or "")
        return [
            item.strip()
            for item in re.split(r"[\n;]+", raw)
            if item.strip()
        ]

    def _line_has_running_experiment(self, profile_id: str) -> bool:
        with session_scope() as session:
            profile = session.get(LearnedRetentionProfile, profile_id)
            if profile is None:
                return False
            existing = session.scalar(
                select(RetentionExperiment.experiment_id)
                .join(LearnedRetentionProfile, LearnedRetentionProfile.profile_id == RetentionExperiment.profile_id)
                .where(RetentionExperiment.status == "running")
                .where(LearnedRetentionProfile.niche_id == profile.niche_id)
                .where(LearnedRetentionProfile.line_id == profile.line_id)
                .where(LearnedRetentionProfile.profile_id != profile.profile_id)
            )
            return existing is not None

    def _dominant_skeleton(self, *, line_id: str, shorts: list[ReferenceShort], aggressive: bool) -> dict[str, Any]:
        structure_counter: Counter[str] = Counter()
        move_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()
        forbidden_counter: Counter[str] = Counter()
        why_examples: list[str] = []
        for short in shorts:
            analysis = dict(short.analysis_summary or {})
            for item in self._analysis_items(analysis.get("observed_structure")):
                if str(item or "").strip():
                    structure_counter[str(item).strip()] += 1
            for item in self._analysis_items(analysis.get("retention_moves")):
                if str(item or "").strip():
                    move_counter[str(item).strip()] += 1
            for item in self._analysis_items(analysis.get("risks")):
                if str(item or "").strip():
                    risk_counter[str(item).strip()] += 1
            for item in self._analysis_items(analysis.get("forbidden_copy_elements")):
                if str(item or "").strip():
                    forbidden_counter[str(item).strip()] += 1
            why = str(analysis.get("why_it_might_work") or "").strip()
            if why and why not in why_examples:
                why_examples.append(why)
        structure = [item for item, _count in structure_counter.most_common()] or ["abre_loop_por_pergunta_mental", "usa_tensao_progressiva", "promete_payoff_visual_ou_cotidiano"]
        moves = [item for item, _count in move_counter.most_common()] or [
            "capturar atencao com promessa especifica",
            "segurar explicacao completa",
            "entregar virada reaplicavel no ultimo movimento",
        ]
        references = sorted(
            shorts,
            key=lambda short: (float(short.performance_score or 0), int(short.view_count or 0)),
            reverse=True,
        )
        return {
            "line_id": line_id,
            "reference_count": len(shorts),
            "mode": "aggressive_skeleton_copy" if aggressive else "conservative_transfer",
            "copy_policy": "copiar ordem, pressão narrativa e função dos beats; nunca copiar palavras, exemplos específicos ou roteiro literal",
            "structure_sequence": structure[:8],
            "retention_moves": moves[:8],
            "generator_directive": (
                "Use este esqueleto como contrato de retenção do experimento: preserve a sequência dos movimentos vencedores, "
                "troque tema, fatos, imagens mentais e frases, e mantenha o payoff no ponto equivalente do esqueleto."
            ),
            "opening_contract": structure[0],
            "payoff_contract": moves[-1],
            "forbidden_copy_elements": [item for item, _count in forbidden_counter.most_common(8)] or ["palavras do título", "descrição", "exemplos específicos do vídeo"],
            "risks": [item for item, _count in risk_counter.most_common(8)] or ["sem_retencao_externa_real"],
            "why_it_might_work": why_examples[:3],
            "top_reference_video_ids": [short.youtube_video_id for short in references[:6]],
        }

    def _analysis_items(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = re.split(r"[\n;]+", value)
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            raw_items = [value]
        items: list[str] = []
        for raw in raw_items:
            text = str(raw or "").strip()
            if not text:
                continue
            items.append(text[:240])
        return items

    def _short_reference_json(self, short: ReferenceShort) -> dict[str, Any]:
        return {
            "reference_short_id": short.reference_short_id,
            "youtube_video_id": short.youtube_video_id,
            "title": short.title,
            "line_id": short.line_id,
            "duration_sec": short.duration_sec,
            "view_count": short.view_count,
            "performance_score": short.performance_score,
            "confidence": short.confidence,
            "analysis_artifact_path": short.analysis_artifact_path,
        }

    def _profile_guidance_text(self, profile: LearnedRetentionProfile, *, experiment_id: str | None, promoted: bool = False) -> str:
        skeleton = dict(profile.dominant_skeleton or {})
        moves = self._transferable_guidance_moves(skeleton)
        forbidden = self._transferable_forbidden_copy_items(skeleton)
        header = "Perfil de Retencao Promovido ativo." if promoted else "Experimento de Retencao Aprendida ativo."
        source_line = f"profile_id={profile.profile_id}" if promoted else f"experiment_id={experiment_id}\nprofile_id={profile.profile_id}"
        return (
            f"{header}\n"
            f"{source_line}\n"
            f"line_id={profile.line_id or 'indefinida'}\n"
            "Objetivo: transferir apenas a funcao narrativa do esqueleto vencedor, sem copiar palavras, fatos, exemplos, lingua ou identidade visual de Shorts de referencia.\n"
            f"Movimentos transferiveis: {' | '.join(moves)}\n"
            f"Proibido copiar: {' | '.join(forbidden)}\n"
            "Diretriz: gere roteiro original em pt-BR, com evidencia propria, hook cotidiano especifico, escalada curta e payoff no ultimo terco."
        )

    def _transferable_guidance_moves(self, skeleton: dict[str, Any]) -> list[str]:
        text = " ".join(str(item or "") for item in list(skeleton.get("structure_sequence") or []) + list(skeleton.get("retention_moves") or [])).lower()
        moves: list[str] = []

        def add(condition: bool, item: str) -> None:
            if condition and item not in moves:
                moves.append(item)

        add(any(token in text for token in ["curiosity gap", "pergunta", "what if", "lacuna"]), "abrir com lacuna de curiosidade concreta")
        add(any(token in text for token in ["contraste", "subvert", "oposta", "paradox", "choque"]), "mostrar um contraste cotidiano antes de explicar")
        add(any(token in text for token in ["pattern interrupt", "virada", "twist", "darker", "micro"]), "usar microviradas entre os beats")
        add(any(token in text for token in ["fast-paced", "ritmo", "rapid", "rápid"]), "manter frases curtas e progressao rapida")
        add(any(token in text for token in ["text-on-screen", "visual", "overlays", "imagem"]), "ancorar cada beat em imagem mental ou visual claro")
        add(any(token in text for token in ["payoff", "ultimo", "último", "final"]), "segurar o payoff para o ultimo terco")
        add(any(token in text for token in ["superlative", "highest", "strongest", "insane", "99%"]), "usar promessa especifica e verificavel, sem exagero factual")
        defaults = [
            "abrir com lacuna de curiosidade concreta",
            "mostrar um contraste cotidiano antes de explicar",
            "usar microviradas entre os beats",
            "segurar o payoff para o ultimo terco",
        ]
        for item in defaults:
            if len(moves) >= 6:
                break
            if item not in moves:
                moves.append(item)
        return moves[:6]

    def _transferable_forbidden_copy_items(self, skeleton: dict[str, Any]) -> list[str]:
        text = " ".join(str(item or "") for item in skeleton.get("forbidden_copy_elements") or []).lower()
        items = [
            "titulo literal",
            "sequencia exata de fatos",
            "frases, cadencia ou idioma do video externo",
            "branding, nomes de canal, hashtags ou emojis do criador",
            "visual assets, musica ou ordem de cortes do original",
        ]
        if "disclaimer" in text:
            items.append("disclaimers ou descricoes copiadas")
        return items[:6]

    def run(
        self,
        *,
        niche_id: str = "curiosidades",
        channel_ids: list[str] | None = None,
        queries: list[str] | None = None,
        max_results_per_source: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        run_id = new_id()
        started_at = utcnow()
        with session_scope() as session:
            session.add(
                ScoutRun(
                    run_id=run_id,
                    schema_version=self.settings.schema_version,
                    content_hash=stable_hash({"run_id": run_id, "started_at": started_at.isoformat()}),
                    created_at=started_at,
                    started_at=started_at,
                    niche_id=niche_id,
                )
            )
        try:
            result = self._run(run_id, niche_id=niche_id, channel_ids=channel_ids, queries=queries, max_results_per_source=max_results_per_source, now=now)
        except Exception as exc:
            with session_scope() as session:
                run = session.get(ScoutRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.finished_at = utcnow()
                    run.error = str(exc)
                    run.summary = {"error": str(exc)}
                    run.content_hash = stable_hash({"run_id": run_id, "status": "failed", "error": str(exc)})
            raise
        return result

    def _run(
        self,
        run_id: str,
        *,
        niche_id: str,
        channel_ids: list[str] | None,
        queries: list[str] | None,
        max_results_per_source: int | None,
        now: datetime | None,
    ) -> dict[str, Any]:
        effective_now = now or utcnow()
        limit = max_results_per_source or int(self.settings.competitive_scout_reference_batch_limit)
        target_channels = [item.strip() for item in (channel_ids or self.approved_reference_channel_ids(niche_id=niche_id)) if item.strip()]
        target_queries = [item.strip() for item in (queries or []) if item.strip()]
        query_search_plans = self._query_search_plans(target_queries)
        search_items: list[dict[str, Any]] = []
        for channel_id in target_channels:
            items = self.youtube.search_public_videos(channel_id=channel_id, max_results=limit, order="date", video_duration="short")
            search_items.extend(
                self._annotate_search_item(
                    item,
                    {
                        "source": "channel",
                        "channel_id": channel_id,
                        "region_code": None,
                    },
                )
                for item in items
            )
        for plan in query_search_plans:
            items = self.youtube.search_public_videos(
                query=plan["query"],
                max_results=limit,
                order="relevance",
                region_code=plan["region_code"],
                video_duration="short",
            )
            search_items.extend(self._annotate_search_item(item, plan) for item in items)
        discovery_contexts_by_video_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in search_items:
            video_id = self._video_id_from_search(item)
            if not video_id:
                continue
            context = dict(item.get("_scout_discovery_context") or {})
            if context and context not in discovery_contexts_by_video_id[video_id]:
                discovery_contexts_by_video_id[video_id].append(context)
        video_ids = list(dict.fromkeys(self._video_id_from_search(item) for item in search_items if self._video_id_from_search(item)))
        videos = self.youtube.fetch_public_videos(video_ids)
        candidates = [
            candidate
            for video in videos
            if (
                candidate := self._candidate_from_video(
                    video,
                    now=effective_now,
                    discovery_contexts=discovery_contexts_by_video_id.get(str(video.get("id") or "").strip(), []),
                )
            )
            is not None
        ]
        matched = [candidate for candidate in candidates if self._is_selected_reference(candidate, now=effective_now)]
        selected = sorted(matched, key=lambda candidate: candidate.performance_score, reverse=True)[: int(self.settings.competitive_scout_max_analyses_per_run)]
        analyses = [
            {
                "candidate": candidate,
                "analysis": self.analyzer.analyze_reference_short(candidate),
            }
            for candidate in selected
        ]
        artifact_payload = {
            "schema_version": self.settings.schema_version,
            "run_id": run_id,
            "created_at": utcnow().isoformat(),
            "niche_id": niche_id,
            "channels_considered": len(target_channels),
            "queries_considered": len(target_queries),
            "regions_considered": sorted({str(plan["region_code"]) for plan in query_search_plans if plan.get("region_code")}),
            "search_requests_considered": len(target_channels) + len(query_search_plans),
            "search_items": len(search_items),
            "videos_enriched": len(videos),
            "shorts_matched_filters": len(matched),
            "shorts_selected": len(selected),
            "selected": [
                {
                    "youtube_video_id": item["candidate"].youtube_video_id,
                    "title": item["candidate"].title,
                    "line_id": item["candidate"].line_id,
                    "performance_proxy": item["candidate"].performance_proxy,
                    "discovery_contexts": item["candidate"].discovery_contexts,
                    "analysis": item["analysis"],
                }
                for item in analyses
            ],
        }
        artifact_path = self._persist_scout_artifact(run_id, "scout_run.json", artifact_payload)
        self._persist_results(
            run_id,
            niche_id=niche_id,
            candidates=candidates,
            analyses=analyses,
            artifact_path=artifact_path,
            channels_considered=len(target_channels) + len(target_queries),
        )
        return {
            "run_id": run_id,
            "status": "completed",
            "channels_considered": len(target_channels),
            "queries_considered": len(target_queries),
            "regions_considered": sorted({str(plan["region_code"]) for plan in query_search_plans if plan.get("region_code")}),
            "search_requests_considered": len(target_channels) + len(query_search_plans),
            "shorts_considered": len(candidates),
            "shorts_matched_filters": len(matched),
            "shorts_selected": len(selected),
            "artifact_path": artifact_path,
        }

    def _candidate_from_video(self, video: dict[str, Any], *, now: datetime, discovery_contexts: list[dict[str, Any]] | None = None) -> ReferenceShortCandidate | None:
        video_id = str(video.get("id") or "").strip()
        snippet = dict(video.get("snippet") or {})
        content_details = dict(video.get("contentDetails") or {})
        statistics = dict(video.get("statistics") or {})
        channel_id = str(snippet.get("channelId") or "").strip()
        title = str(snippet.get("title") or "").strip()
        if not video_id or not channel_id or not title:
            return None
        description = str(snippet.get("description") or "")
        duration_sec = parse_youtube_duration(content_details.get("duration"))
        published_at = parse_youtube_datetime(snippet.get("publishedAt"))
        view_count = optional_int(statistics.get("viewCount"))
        like_count = optional_int(statistics.get("likeCount"))
        comment_count = optional_int(statistics.get("commentCount"))
        proxy = build_performance_proxy(
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            published_at=published_at,
            now=now,
        )
        line_id = classify_editorial_line(title, description)
        confidence = "media" if line_id != "desconhecida" and int(view_count or 0) >= int(self.settings.competitive_scout_min_reference_views) else "baixa"
        return ReferenceShortCandidate(
            youtube_video_id=video_id,
            youtube_channel_id=channel_id,
            channel_title=str(snippet.get("channelTitle") or ""),
            title=title,
            description=description,
            published_at=published_at,
            duration_sec=duration_sec,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            line_id=line_id,
            performance_score=float(proxy["score"]),
            confidence=confidence,
            performance_proxy=proxy,
            raw_metadata={**video, "_scout_discovery_contexts": list(discovery_contexts or [])},
            discovery_contexts=list(discovery_contexts or []),
        )

    def _is_selected_reference(self, candidate: ReferenceShortCandidate, *, now: datetime) -> bool:
        if candidate.duration_sec is None or candidate.duration_sec > int(self.settings.competitive_scout_max_video_duration_sec):
            return False
        maturity = reference_maturity_hours(candidate.published_at, now=now)
        if maturity is not None and maturity < int(self.settings.competitive_scout_min_maturity_hours):
            return False
        if int(candidate.view_count or 0) < int(self.settings.competitive_scout_min_reference_views):
            return False
        if candidate.line_id == "desconhecida":
            return False
        return True

    def _persist_results(
        self,
        run_id: str,
        *,
        niche_id: str,
        candidates: list[ReferenceShortCandidate],
        analyses: list[dict[str, Any]],
        artifact_path: str,
        channels_considered: int,
    ) -> None:
        analysis_by_video_id = {item["candidate"].youtube_video_id: item["analysis"] for item in analyses}
        selected_ids = set(analysis_by_video_id)
        with session_scope() as session:
            channel_records: dict[str, ReferenceChannel] = {}
            for candidate in candidates:
                channel = session.scalar(select(ReferenceChannel).where(ReferenceChannel.youtube_channel_id == candidate.youtube_channel_id))
                if channel is None:
                    channel = ReferenceChannel(
                        reference_channel_id=new_id(),
                        youtube_channel_id=candidate.youtube_channel_id,
                        schema_version=self.settings.schema_version,
                        content_hash="pending",
                        status="candidate",
                        source="competitive_scout",
                        niche_id=niche_id,
                        line_id=candidate.line_id if candidate.line_id != "desconhecida" else None,
                        title=candidate.channel_title or candidate.youtube_channel_id,
                        channel_url=f"https://www.youtube.com/channel/{candidate.youtube_channel_id}",
                        confidence=candidate.confidence,
                        last_seen_at=utcnow(),
                        metrics={},
                        raw_metadata={},
                    )
                    session.add(channel)
                    session.flush()
                channel.title = candidate.channel_title or channel.title
                channel.last_seen_at = utcnow()
                channel.line_id = channel.line_id or (candidate.line_id if candidate.line_id != "desconhecida" else None)
                channel.confidence = "media" if channel.confidence == "baixa" and candidate.confidence == "media" else channel.confidence
                channel.metrics = {
                    **dict(channel.metrics or {}),
                    "last_reference_score": candidate.performance_score,
                    "last_reference_video_id": candidate.youtube_video_id,
                }
                channel.content_hash = stable_hash(
                    {
                        "youtube_channel_id": channel.youtube_channel_id,
                        "status": channel.status,
                        "title": channel.title,
                        "line_id": channel.line_id,
                        "metrics": channel.metrics,
                    }
                )
                channel_records[candidate.youtube_channel_id] = channel

            for candidate in candidates:
                short = session.scalar(select(ReferenceShort).where(ReferenceShort.youtube_video_id == candidate.youtube_video_id))
                channel = channel_records.get(candidate.youtube_channel_id)
                analysis = analysis_by_video_id.get(candidate.youtube_video_id)
                analysis_path = None
                if analysis:
                    analysis_path = self._persist_scout_artifact(run_id, f"short_{candidate.youtube_video_id}.json", {"candidate": self._candidate_json(candidate), "analysis": analysis})
                if short is None:
                    short = ReferenceShort(
                        reference_short_id=new_id(),
                        youtube_video_id=candidate.youtube_video_id,
                        reference_channel_id=channel.reference_channel_id if channel else None,
                        youtube_channel_id=candidate.youtube_channel_id,
                        schema_version=self.settings.schema_version,
                        content_hash="pending",
                        status="selected" if candidate.youtube_video_id in selected_ids else "candidate",
                        source_type="external",
                        niche_id=niche_id,
                        line_id=candidate.line_id if candidate.line_id != "desconhecida" else None,
                        title=candidate.title,
                        description=candidate.description[:5000],
                        youtube_url=candidate.youtube_url,
                        published_at=candidate.published_at,
                        duration_sec=candidate.duration_sec,
                        view_count=candidate.view_count,
                        like_count=candidate.like_count,
                        comment_count=candidate.comment_count,
                        performance_score=candidate.performance_score,
                        confidence=candidate.confidence,
                        transcript_source="none",
                        analysis_artifact_path=analysis_path,
                        performance_proxy=candidate.performance_proxy,
                        analysis_summary=analysis,
                        raw_metadata=candidate.raw_metadata,
                    )
                    session.add(short)
                else:
                    short.reference_channel_id = channel.reference_channel_id if channel else short.reference_channel_id
                    short.title = candidate.title
                    short.description = candidate.description[:5000]
                    short.youtube_url = candidate.youtube_url
                    short.published_at = candidate.published_at
                    short.duration_sec = candidate.duration_sec
                    short.view_count = candidate.view_count
                    short.like_count = candidate.like_count
                    short.comment_count = candidate.comment_count
                    short.performance_score = candidate.performance_score
                    short.confidence = candidate.confidence
                    short.performance_proxy = candidate.performance_proxy
                    short.raw_metadata = candidate.raw_metadata
                    short.line_id = candidate.line_id if candidate.line_id != "desconhecida" else short.line_id
                    if analysis:
                        short.status = "selected"
                        short.analysis_artifact_path = analysis_path
                        short.analysis_summary = analysis
                short.content_hash = stable_hash(
                    {
                        "youtube_video_id": short.youtube_video_id,
                        "title": short.title,
                        "duration_sec": short.duration_sec,
                        "view_count": short.view_count,
                        "line_id": short.line_id,
                        "performance_proxy": short.performance_proxy,
                        "analysis_summary": short.analysis_summary,
                    }
                )

            run = session.get(ScoutRun, run_id)
            if run is not None:
                run.status = "completed"
                run.finished_at = utcnow()
                run.channels_considered = channels_considered
                run.shorts_considered = len(candidates)
                run.shorts_selected = len(selected_ids)
                run.artifact_path = artifact_path
                run.summary = {
                    "shorts_considered": len(candidates),
                    "shorts_selected": len(selected_ids),
                    "lines": sorted({candidate.line_id for candidate in candidates}),
                }
                run.content_hash = stable_hash({"run_id": run_id, "status": run.status, "summary": run.summary})

    def _persist_scout_artifact(self, run_id: str, filename: str, payload: dict[str, Any]) -> str:
        relative = Path("scout") / run_id / filename
        path = self.settings.artifacts_dir / relative
        ensure_dir(path.parent)
        write_json(path, payload)
        return relative.as_posix()

    def _candidate_json(self, candidate: ReferenceShortCandidate) -> dict[str, Any]:
        return {
            "youtube_video_id": candidate.youtube_video_id,
            "youtube_channel_id": candidate.youtube_channel_id,
            "channel_title": candidate.channel_title,
            "title": candidate.title,
            "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
            "duration_sec": candidate.duration_sec,
            "view_count": candidate.view_count,
            "like_count": candidate.like_count,
            "comment_count": candidate.comment_count,
            "line_id": candidate.line_id,
            "performance_score": candidate.performance_score,
            "confidence": candidate.confidence,
            "performance_proxy": candidate.performance_proxy,
            "discovery_contexts": candidate.discovery_contexts,
        }

    def _video_id_from_search(self, item: dict[str, Any]) -> str:
        raw_id = item.get("id")
        if isinstance(raw_id, dict):
            return str(raw_id.get("videoId") or "").strip()
        return str(raw_id or "").strip()

    def _query_search_plans(self, queries: list[str]) -> list[dict[str, Any]]:
        if not queries:
            return []
        regions = self._global_regions() if bool(self.settings.competitive_scout_global_enabled) else ["BR"]
        plans: list[dict[str, Any]] = []
        for query in queries:
            for region_code in regions:
                plans.append(
                    {
                        "source": "query",
                        "query": query,
                        "region_code": region_code,
                    }
                )
        return plans[: int(self.settings.competitive_scout_max_query_region_pairs)]

    def _global_regions(self) -> list[str]:
        raw = str(getattr(self.settings, "competitive_scout_regions", "") or "")
        regions = []
        for item in re.split(r"[\s,;]+", raw):
            region = item.strip().upper()
            if re.fullmatch(r"[A-Z]{2}", region) and region not in regions:
                regions.append(region)
        return regions or ["BR"]

    def _annotate_search_item(self, item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {**dict(item or {}), "_scout_discovery_context": {key: value for key, value in context.items() if value is not None}}
