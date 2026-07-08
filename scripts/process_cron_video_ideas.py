from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import init_db, session_scope
from app.editorial.repetition import build_channel_repetition_report
from app.job_origin import CREATION_VIA_CLI, JOB_ORIGIN_MANUAL_TITLE
from app.models import CronVideoIdea, Job, Script
from app.orchestrator import JobOrchestrator
from app.utils import new_id

FIELD_MAP = {
    "Título viral provisório": "title",
    "Hook de 1 linha em pt-BR": "hook",
    "Loop/pergunta que segura até o fim": "loop_question",
    "Promessa visual": "visual_promise",
    "Ângulo emocional": "emotional_angle",
    "Risco de chatice": "boredom_risk",
    "Score viral inicial": "viral_score",
}

RISK_RANK = {"baixo": 0, "médio": 1, "medio": 1, "alto": 2}


def parse_ideas(text: str) -> dict[str, dict[str, str]]:
    ideas: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"### ID:\s*(SF-\d{8}-\d+)", line)
        if match:
            current = {"cron_item_id": match.group(1)}
            ideas[current["cron_item_id"]] = current
            continue
        if not current or not line.startswith("- **"):
            continue
        field_match = re.match(r"- \*\*(.+?)\:\*\*\s*(.+)", line)
        if field_match and field_match.group(1) in FIELD_MAP:
            current[FIELD_MAP[field_match.group(1)]] = field_match.group(2).strip()
    return ideas


def viral_score(value: str) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else 0.0


def select_best_ids(
    ideas: dict[str, dict[str, str]],
    *,
    top: int,
    min_score: float,
    max_risk: str,
) -> list[str]:
    max_rank = RISK_RANK[max_risk]
    candidates = [
        idea
        for idea in ideas.values()
        if viral_score(idea.get("viral_score", "")) >= min_score
        and RISK_RANK.get(str(idea.get("boredom_risk") or "").strip().lower(), 0) <= max_rank
    ]
    candidates.sort(key=lambda item: (viral_score(item.get("viral_score", "")), item["cron_item_id"]), reverse=True)
    return [item["cron_item_id"] for item in candidates[:top]]


def _scriptish(idea: dict[str, str]) -> dict[str, Any]:
    return {
        "title": idea.get("title", ""),
        "hook": idea.get("hook", ""),
        "body_beats": [idea.get("visual_promise", "")],
        "ending": idea.get("loop_question", ""),
        "estimated_duration_sec": 45,
    }


def repetition_report(session, idea: dict[str, str]) -> dict[str, Any]:
    rows = session.execute(
        select(Job.job_id, Job.topic_summary, Script.title, Script.hook, Script.ending, Script.estimated_duration_sec, Script.body_beats)
        .join(Script, Script.job_id == Job.job_id)
        .order_by(Job.created_at.desc())
        .limit(80)
    ).all()
    recent = [
        {
            "job_id": job_id,
            "topic_summary": topic_summary,
            "title": title,
            "hook": hook,
            "ending": ending,
            "estimated_duration_sec": estimated_duration_sec,
            "body_beats": body_beats,
        }
        for job_id, topic_summary, title, hook, ending, estimated_duration_sec, body_beats in rows
    ]
    existing_ideas = session.scalars(select(CronVideoIdea).where(CronVideoIdea.cron_item_id != idea["cron_item_id"])).all()
    recent.extend(
        {
            "job_id": row.cron_item_id,
            "topic_summary": row.title,
            "title": row.title,
            "hook": row.hook,
            "ending": row.loop_question,
            "estimated_duration_sec": 45,
            "body_beats": [row.visual_promise] if row.visual_promise else [],
        }
        for row in existing_ideas
    )
    return build_channel_repetition_report(
        current={"canonical_topic": idea.get("title", ""), "angle": idea.get("emotional_angle", ""), "script": _scriptish(idea)},
        recent_rows=recent,
    )


def notes_for(idea: dict[str, str]) -> str:
    return "\n".join(
        [
            f"cron_item_id={idea['cron_item_id']}",
            "input_mode=title",
            f"hook={idea.get('hook', '')}",
            f"loop={idea.get('loop_question', '')}",
            f"visual={idea.get('visual_promise', '')}",
            f"score={idea.get('viral_score', '')}",
        ]
    )


def upsert_and_create_jobs(path: Path, ids: list[str], *, process: bool) -> list[dict[str, Any]]:
    init_db()
    ideas = parse_ideas(path.read_text(encoding="utf-8"))
    missing = [item_id for item_id in ids if item_id not in ideas]
    if missing:
        raise SystemExit(f"IDs não encontrados no arquivo: {', '.join(missing)}")
    orchestrator = JobOrchestrator()
    out: list[dict[str, Any]] = []
    for item_id in ids:
        idea = ideas[item_id]
        with session_scope() as session:
            row = session.scalar(select(CronVideoIdea).where(CronVideoIdea.cron_item_id == item_id))
            report = repetition_report(session, idea)
            if row is None:
                row = CronVideoIdea(
                    idea_id=new_id(),
                    cron_job_id=path.stem.split("_", 1)[0],
                    cron_item_id=item_id,
                    title=idea.get("title", ""),
                )
                session.add(row)
            row.hook = idea.get("hook")
            row.loop_question = idea.get("loop_question")
            row.visual_promise = idea.get("visual_promise")
            row.emotional_angle = idea.get("emotional_angle")
            row.viral_score = idea.get("viral_score")
            row.repetition_report = report
            created_job_id = row.created_job_id
        if created_job_id:
            status = "already_created"
            if process:
                with session_scope() as session:
                    job = session.get(Job, created_job_id)
                    current_status = str(job.status or "") if job else "missing"
                if current_status not in {
                    "approved",
                    "approved_for_publish",
                    "ready_for_upload",
                    "monetization_review",
                    "blocked_for_monetization",
                    "published",
                    "failed",
                }:
                    status = orchestrator.process_job(created_job_id)
                else:
                    status = current_status
            out.append({"cron_item_id": item_id, "status": status, "job_id": created_job_id})
            continue
        if report.get("repetition_risk") == "high":
            out.append({"cron_item_id": item_id, "status": "blocked_duplicate", "report": report})
            continue
        job_id = orchestrator.create_job(
            {
                "seed_theme": idea["title"],
                "target_duration_sec": 45,
                "notes": notes_for(idea),
                "requested_angle": idea.get("emotional_angle"),
                "job_origin": JOB_ORIGIN_MANUAL_TITLE,
                "creation_via": CREATION_VIA_CLI,
            }
        )
        with session_scope() as session:
            row = session.scalar(select(CronVideoIdea).where(CronVideoIdea.cron_item_id == item_id))
            if row:
                row.created_job_id = job_id
        status = "queued"
        if process:
            status = orchestrator.process_job(job_id)
        out.append({"cron_item_id": item_id, "status": status, "job_id": job_id, "repetition_risk": report.get("repetition_risk")})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist cron video ideas, anti-repeat check, and optionally process jobs.")
    parser.add_argument("--file", default="/root/.hermes/cron/output/fb2cae8427d6_20260702_120316.txt")
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--top", type=int, default=2, help="Quantidade automática quando --ids não for informado")
    parser.add_argument("--min-score", type=float, default=8.0, help="Nota mínima para seleção automática")
    parser.add_argument("--max-risk", choices=sorted(RISK_RANK), default="médio", help="Risco máximo de chatice aceito")
    parser.add_argument("--process", action="store_true")
    args = parser.parse_args()
    ids = args.ids
    if ids is None:
        ideas = parse_ideas(Path(args.file).read_text(encoding="utf-8"))
        ids = select_best_ids(ideas, top=args.top, min_score=args.min_score, max_risk=args.max_risk)
        if not ids:
            print(json.dumps({"status": "no_matching_ideas", "file": str(args.file)}, ensure_ascii=False, indent=2))
            return 0
    print(json.dumps(upsert_and_create_jobs(Path(args.file), ids, process=args.process), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
