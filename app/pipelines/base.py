from __future__ import annotations

from typing import Any

from app.quality.llm_judge import LlmQualityJudge

_DISABLED_LLM_JUDGE = LlmQualityJudge(
    enabled=False,
    timeout_sec=30.0,
    gray_zone_low=0.72,
    gray_zone_high=0.82,
    judge_callable=None,
)


class BasePipeline:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    @property
    def settings(self) -> Any:
        return self.owner.settings

    @property
    def storage(self) -> Any:
        return self.owner.storage

    @property
    def providers(self) -> Any:
        return self.owner.providers

    @property
    def script_gate(self) -> Any:
        return self.owner.script_gate

    @property
    def viral_intensity_gate(self) -> Any:
        return self.owner.viral_intensity_gate

    @property
    def visual_impact_gate(self) -> Any:
        return self.owner.visual_impact_gate

    @property
    def metadata_ctr_gate(self) -> Any:
        return self.owner.metadata_ctr_gate

    @property
    def growth_score_gate(self) -> Any:
        return self.owner.growth_score_gate

    @property
    def llm_judge(self) -> LlmQualityJudge:
        return getattr(self.owner, "llm_judge", _DISABLED_LLM_JUDGE)

    @property
    def scene_gate(self) -> Any:
        return self.owner.scene_gate

    @property
    def visual_contract_gate(self) -> Any:
        return self.owner.visual_contract_gate

    @property
    def asset_gate(self) -> Any:
        return self.owner.asset_gate

    @property
    def asset_visual_gate(self) -> Any:
        return self.owner.asset_visual_gate

    @property
    def subtitle_gate(self) -> Any:
        return self.owner.subtitle_gate

    @property
    def render_gate(self) -> Any:
        return self.owner.render_gate

    def _append_event(self, job_id: str, event_name: str, status: str, payload: dict[str, Any]) -> None:
        self.owner._append_event(job_id, event_name, status, payload)

    def _persist_repair_telemetry(self, job_id: str, stage: str, payload: dict[str, Any]) -> str:
        return self.owner._persist_repair_telemetry(job_id, stage, payload)

    def _remove_stale_quality_report(self, job_id: str, relative_path: str) -> None:
        self.owner._remove_stale_quality_report(job_id, relative_path)

    def _serialize_for_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.owner._serialize_for_json(payload)

    def _persist_llm_judge_artifact(
        self,
        job_id: str,
        gate_kind: str,
        *,
        local_reasons: list[str],
        judge_result: Any,
        overridden: bool,
    ) -> None:
        self.storage.persist_json(
            job_id,
            f"llm_judge_{gate_kind}.json",
            self._serialize_for_json(
                {
                    "gate_kind": gate_kind,
                    "local_reasons": local_reasons,
                    "passed": judge_result.passed,
                    "confidence": judge_result.confidence,
                    "reasons": judge_result.reasons,
                    "scores": judge_result.scores,
                    "provider": judge_result.provider,
                    "skipped": judge_result.skipped,
                    "notes": judge_result.notes,
                    "overridden": overridden,
                }
            ),
        )

    def _recent_topic_history(self, *args: Any, **kwargs: Any) -> Any:
        return self.owner.topic_pipeline.recent_topic_history(*args, **kwargs)

    def _channel_learning_brief(self, *args: Any, **kwargs: Any) -> Any:
        return self.owner.topic_pipeline.channel_learning_brief(*args, **kwargs)
