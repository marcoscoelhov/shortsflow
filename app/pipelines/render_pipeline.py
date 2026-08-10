from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Job
from app.pipelines.base import BasePipeline


class RenderPipeline(BasePipeline):
    def step_render(self, session: Session, job: Job, attempt: int) -> list[str]:
        report = self.owner.premium_finishing.generate_primary_render(session, job.job_id)
        render_telemetry_file = self._persist_repair_telemetry(
            job.job_id,
            "render",
            {
                "job_id": job.job_id,
                "attempt": attempt,
                "backend": "remotion",
                "final_passed": True,
                "attempts": [{"strategy": "remotion_primary", "passed": True}],
            },
        )
        quality_summary = dict(job.quality_summary or {})
        render_metrics = dict(report.get("metrics") or {})
        quality_summary["render"] = {
            **render_metrics,
            "render_gate_pass": True,
            "duration_ms": render_metrics.get("duration_ms"),
            "resolution": "1080x1920",
            "audio_loudness_target_lufs": -16.0,
            "audio_true_peak_limit_db": -1.5,
            "background_music_mixed": bool(report.get("background_music_mixed")),
            "render_repair_used": False,
            "backend": "remotion",
        }
        job.quality_summary = quality_summary
        return [
            "render/final.mp4",
            "render/poster.jpg",
            "render/edit_plan.json",
            "render/remotion.log",
            "render_output.json",
            "premium_finishing_report.json",
            render_telemetry_file,
        ]
