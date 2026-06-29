from __future__ import annotations

import concurrent.futures
import json
import queue
import threading
from typing import Any, Callable

from app.providers import llm as llm_facade
from app.providers.errors import ProviderFailure
from app.providers.llm_clients import (
    DeepSeekCreativeProvider,
    GeminiCreativeProvider,
    OpenAICreativeProvider,
    QwenCreativeProvider,
    XAICreativeProvider,
)


class ResilientCreativeProvider:
    def __init__(self) -> None:
        self.settings = llm_facade.get_settings()
        self.registry = LLMProviderRegistry()
        self.primary = self.registry.primary_provider()
        self.fallback = self.registry.fallback_provider()
        self.script_draft_provider = self.registry.script_draft_provider()
        self.repair_provider = self.registry.repair_provider()
        self.scene_provider = self.registry.scene_provider()
        self.gate_judge_provider = self.registry.gate_judge_provider()
        self.premium_review_provider = self.registry.premium_review_provider()
        self.strict_minimax_validation = self.settings.strict_minimax_validation

    def plan_topic(
        self,
        seed_theme: str,
        attempt: int,
        history: list[dict[str, Any]],
        requested_angle: str | None,
        tone: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if self.primary:
            timeout_sec = float(getattr(self.settings, "llm_topic_timeout_sec", self.settings.minimax_text_timeout_sec))
            try:
                return self._run_primary_with_timeout(
                    lambda: self.primary.plan_topic(seed_theme, attempt, history, requested_angle, tone=tone, notes=notes),
                    timeout_sec=timeout_sec,
                )
            except concurrent.futures.TimeoutError as exc:
                if self.strict_minimax_validation:
                    raise ProviderFailure(self._provider_failure_name(self.primary), f"topic planner timed out after {timeout_sec}s") from exc
                if not self.fallback:
                    raise ProviderFailure("llm_registry", f"topic planner timed out after {timeout_sec}s and no fallback provider is available") from exc
                payload = self.fallback.plan_topic(seed_theme, attempt, history, requested_angle, tone=tone, notes=notes)
                payload["quality_metrics"]["fallback_reason"] = (
                    f"{self._provider_failure_name(self.primary)} topic planner timed out after {timeout_sec}s"
                )
                payload["quality_metrics"]["fallback_used"] = True
                payload["quality_metrics"]["fallback_stage"] = "topic_plan_timeout"
                return payload
            except ProviderFailure as exc:
                if self.strict_minimax_validation:
                    raise
                if not self.fallback:
                    raise
                payload = self.fallback.plan_topic(seed_theme, attempt, history, requested_angle, tone=tone, notes=notes)
                payload["quality_metrics"]["fallback_reason"] = str(exc)
                payload["quality_metrics"]["fallback_used"] = True
                return payload
        if self.strict_minimax_validation:
            raise ProviderFailure("llm_registry", "strict minimax validation requires a primary llm provider")
        if not self.fallback:
            raise ProviderFailure("llm_registry", "no topic llm provider is available")
        return self.fallback.plan_topic(seed_theme, attempt, history, requested_angle, tone=tone, notes=notes)

    def generate_script(self, topic_plan: dict[str, Any]) -> dict[str, Any]:
        candidates = self._script_generation_candidates()
        if not candidates:
            raise ProviderFailure("llm_registry", "no script llm provider is available")
        failures: list[str] = []
        for index, (role, provider, timeout_sec) in enumerate(candidates):
            try:
                payload = self._run_primary_with_timeout(
                    lambda provider=provider: provider.generate_script(topic_plan),
                    timeout_sec=timeout_sec,
                )
                metrics = payload.setdefault("qa_metrics", {})
                metrics["generation_provider_role"] = role
                metrics["generation_provider"] = getattr(provider, "provider_name", role)
                metrics["script_generation_fallback_used"] = index > 0
                if failures:
                    metrics["script_generation_fallback_reasons"] = failures
                return payload
            except concurrent.futures.TimeoutError as exc:
                message = f"{getattr(provider, 'provider_name', role)} script generation timed out after {timeout_sec}s"
                failures.append(message)
                if self.strict_minimax_validation and provider is self.primary:
                    raise ProviderFailure(getattr(provider, "failure_provider_name", role), message) from exc
            except ProviderFailure as exc:
                failures.append(str(exc))
                if self.strict_minimax_validation and provider is self.primary:
                    raise
        raise ProviderFailure("llm_registry", f"script generation failed across llm providers: {'; '.join(failures)}")

    def generate_visual_contract(self, script: dict[str, Any]) -> dict[str, Any]:
        candidates = self._visual_contract_candidates()
        if not candidates:
            raise ProviderFailure("llm_registry", "no visual contract llm provider is available")
        failures: list[str] = []
        for index, (role, provider, timeout_sec) in enumerate(candidates):
            try:
                payload = self._run_primary_with_timeout(
                    lambda provider=provider: provider.generate_visual_contract(script),
                    timeout_sec=timeout_sec,
                )
                payload["source_provider_role"] = role
                payload["visual_contract_fallback_used"] = index > 0
                if failures:
                    payload["visual_contract_fallback_reasons"] = failures
                return payload
            except concurrent.futures.TimeoutError as exc:
                message = f"{getattr(provider, 'provider_name', role)} visual contract timed out after {timeout_sec}s"
                failures.append(message)
                if self.strict_minimax_validation and provider is self.primary:
                    raise ProviderFailure(getattr(provider, "failure_provider_name", role), message) from exc
            except ProviderFailure as exc:
                failures.append(str(exc))
                if self.strict_minimax_validation and provider is self.primary:
                    raise
        raise ProviderFailure("llm_registry", f"visual contract generation failed across providers: {'; '.join(failures)}")

    def audit_publish_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.primary:
            timeout_sec = float(getattr(self.settings, "llm_publish_audit_timeout_sec", self.settings.minimax_text_timeout_sec))
            try:
                return self._run_primary_with_timeout(
                    lambda: self.primary.audit_publish_package(payload),
                    timeout_sec=timeout_sec,
                )
            except concurrent.futures.TimeoutError as exc:
                if self.strict_minimax_validation:
                    raise ProviderFailure(self._provider_failure_name(self.primary), f"publish audit timed out after {timeout_sec}s") from exc
                if not self.fallback:
                    raise ProviderFailure("llm_registry", f"publish audit timed out after {timeout_sec}s and no fallback provider is available") from exc
                audit = self.fallback.audit_publish_package(payload)
                audit["fallback_reason"] = f"{self._provider_failure_name(self.primary)} publish audit timed out after {timeout_sec}s"
                audit["fallback_used"] = True
                audit["fallback_stage"] = "publish_audit_timeout"
                return audit
            except ProviderFailure as exc:
                if self.strict_minimax_validation:
                    raise
                if not self.fallback:
                    raise
                audit = self.fallback.audit_publish_package(payload)
                audit["fallback_reason"] = str(exc)
                audit["fallback_used"] = True
                return audit
        if self.strict_minimax_validation:
            raise ProviderFailure("llm_registry", "strict minimax validation requires a primary llm provider")
        if not self.fallback:
            raise ProviderFailure("llm_registry", "no publish audit llm provider is available")
        return self.fallback.audit_publish_package(payload)

    def judge_quality_gate(self, gate_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = self._quality_judge_candidates(gate_kind, payload)
        if not candidates:
            return {"passed": False, "reasons": ["llm_judge_unavailable"], "confidence": 0.0, "provider": "none", "gate_kind": gate_kind}
        failures: list[str] = []
        timeout_sec = float(getattr(self.settings, "llm_gate_judge_timeout_sec", 45.0))
        for role, provider in candidates:
            try:
                result = self._run_primary_with_timeout(
                    lambda provider=provider: provider.judge_quality_gate(gate_kind, payload),
                    timeout_sec=timeout_sec,
                )
                result["judge_provider_role"] = role
                return result
            except concurrent.futures.TimeoutError:
                failures.append(f"{role} timed out after {timeout_sec}s")
            except ProviderFailure as exc:
                failures.append(str(exc))
        return {
            "passed": False,
            "reasons": ["llm_judge_failed", *failures[:2]],
            "confidence": 0.0,
            "provider": "llm_registry",
            "gate_kind": gate_kind,
        }

    def _quality_judge_candidates(self, gate_kind: str | None = None, payload: dict[str, Any] | None = None) -> list[tuple[str, Any]]:
        candidates: list[tuple[str, Any]] = []
        seen: set[int] = set()
        ordered: list[tuple[str, Any]] = []
        if self._should_use_premium_review(gate_kind or "", payload or {}):
            ordered.append(("premium_review", getattr(self, "premium_review_provider", None)))
        ordered.extend(
            [
                ("gate_judge", self.gate_judge_provider),
                ("fallback", self.fallback),
                ("repair", self.repair_provider),
            ]
        )
        for role, provider in ordered:
            if provider is None or id(provider) in seen or not hasattr(provider, "judge_quality_gate"):
                continue
            seen.add(id(provider))
            candidates.append((role, provider))
        return candidates

    def _should_use_premium_review(self, gate_kind: str, payload: dict[str, Any]) -> bool:
        if not bool(getattr(self.settings, "llm_premium_review_enabled", True)):
            return False
        if getattr(self, "premium_review_provider", None) is None:
            return False
        explicit = str(payload.get("review_tier") or payload.get("llm_review_tier") or "").strip().lower()
        if explicit in {"premium", "pro", "final", "complex"} or bool(payload.get("escalate_to_premium_llm")):
            return True
        compact = json.dumps(payload, ensure_ascii=False).lower()
        if any(marker in compact for marker in ("premium_review", "premium_publish", "premium_version_selected", "final_review", "promising_final_review")):
            return True
        if gate_kind == "growth_score" and any(marker in compact for marker in ("promising", "premium", "publish_score_below_threshold")):
            return True
        if any(marker in compact for marker in ("complex_theme", "factual_strict", "high_risk_claim", "medical_claim", "engineering_claim")):
            return True
        return False

    def plan_scenes(self, script: dict[str, Any], target_scene_count: int) -> list[dict[str, Any]]:
        if self.primary:
            timeout_sec = float(getattr(self.settings, "llm_scene_plan_timeout_sec", self.settings.minimax_scene_plan_timeout_sec))
            try:
                return self._run_primary_with_timeout(
                    lambda: self.primary.plan_scenes(script, target_scene_count),
                    timeout_sec=timeout_sec,
                )
            except concurrent.futures.TimeoutError:
                if self.strict_minimax_validation:
                    raise ProviderFailure(self._provider_failure_name(self.primary), f"scene planner timed out after {timeout_sec}s")
                provider = getattr(self, "scene_provider", None) or self.fallback
                if not provider:
                    raise ProviderFailure("llm_registry", f"scene planner timed out after {timeout_sec}s and no fallback provider is available")
                scenes = provider.plan_scenes(script, target_scene_count)
                for scene in scenes:
                    scene["provider_fallback_reason"] = (
                        f"{self._provider_failure_name(self.primary)} scene planner timed out after {timeout_sec}s"
                    )
                return scenes
            except ProviderFailure as exc:
                if self.strict_minimax_validation:
                    raise
                provider = getattr(self, "scene_provider", None) or self.fallback
                if not provider:
                    raise
                scenes = provider.plan_scenes(script, target_scene_count)
                for scene in scenes:
                    scene["provider_fallback_reason"] = str(exc)
                return scenes
        if self.strict_minimax_validation:
            raise ProviderFailure("llm_registry", "strict minimax validation requires a primary llm provider")
        provider = getattr(self, "scene_provider", None) or self.fallback
        if not provider:
            raise ProviderFailure("llm_registry", "no scene llm provider is available")
        return provider.plan_scenes(script, target_scene_count)

    def repair_script(self, script: dict[str, Any], gate_reasons: list[str], topic_plan: dict[str, Any]) -> dict[str, Any]:
        provider = getattr(self, "repair_provider", None) or self.primary
        if provider:
            try:
                return self._run_primary_with_timeout(
                    lambda: provider.repair_script(script, gate_reasons, topic_plan),
                    timeout_sec=self._provider_timeout_sec(provider, self.settings.minimax_script_timeout_sec),
                )
            except concurrent.futures.TimeoutError as exc:
                if self.strict_minimax_validation:
                    timeout_sec = self._provider_timeout_sec(provider, self.settings.minimax_script_timeout_sec)
                    raise ProviderFailure(getattr(provider, "failure_provider_name", "llm_provider"), f"script repair timed out after {timeout_sec}s") from exc
                if self.settings.llm_enable_fallback and self.fallback:
                    payload = self._run_primary_with_timeout(
                        lambda: self.fallback.repair_script(script, [*gate_reasons, str(exc)], topic_plan),
                        timeout_sec=self._provider_timeout_sec(
                            self.fallback,
                            float(getattr(self.settings, "llm_script_draft_timeout_sec", self.settings.minimax_script_timeout_sec)),
                        ),
                    )
                    payload.setdefault("qa_metrics", {})["fallback_used"] = True
                    timeout_sec = self._provider_timeout_sec(provider, self.settings.minimax_script_timeout_sec)
                    payload["qa_metrics"]["fallback_reason"] = (
                        f"{getattr(provider, 'provider_name', 'llm')} script repair timed out after {timeout_sec}s"
                    )
                    payload["qa_metrics"]["fallback_stage"] = "script_repair_timeout"
                    return payload
                raise
            except ProviderFailure as exc:
                if self.strict_minimax_validation:
                    raise
                if self.settings.llm_enable_fallback and self.fallback:
                    payload = self._run_primary_with_timeout(
                        lambda: self.fallback.repair_script(script, [*gate_reasons, str(exc)], topic_plan),
                        timeout_sec=self._provider_timeout_sec(
                            self.fallback,
                            float(getattr(self.settings, "llm_script_draft_timeout_sec", self.settings.minimax_script_timeout_sec)),
                        ),
                    )
                    payload.setdefault("qa_metrics", {})["fallback_used"] = True
                    payload["qa_metrics"]["fallback_reason"] = str(exc)
                    return payload
                raise
        if self.strict_minimax_validation:
            raise ProviderFailure("llm_registry", "strict minimax validation requires a primary llm provider")
        if not self.fallback:
            raise ProviderFailure("llm_registry", "no script repair llm provider is available")
        return self.fallback.repair_script(script, gate_reasons, topic_plan)

    def repair_script_with_fallback(self, script: dict[str, Any], gate_reasons: list[str], topic_plan: dict[str, Any]) -> dict[str, Any] | None:
        if self.strict_minimax_validation:
            return None
        if not self.settings.llm_enable_fallback or not self.fallback:
            return None
        payload = self._run_primary_with_timeout(
            lambda: self.fallback.repair_script(script, gate_reasons, topic_plan),
            timeout_sec=self._provider_timeout_sec(
                self.fallback,
                float(getattr(self.settings, "llm_script_draft_timeout_sec", self.settings.minimax_script_timeout_sec)),
            ),
        )
        payload.setdefault("qa_metrics", {})["fallback_used"] = True
        payload["qa_metrics"]["fallback_stage"] = "script_quality_gate"
        return payload

    def _provider_timeout_sec(self, provider: llm_facade.LLMProvider, default_timeout_sec: float) -> float:
        return float(getattr(provider, "timeout_sec", default_timeout_sec) or default_timeout_sec)

    def _provider_failure_name(self, provider: llm_facade.LLMProvider | None) -> str:
        return str(getattr(provider, "failure_provider_name", None) or getattr(provider, "provider_name", None) or "llm_provider")

    def _script_generation_candidates(self) -> list[tuple[str, llm_facade.LLMProvider, float]]:
        primary_timeout = float(getattr(self.settings, "minimax_script_timeout_sec", 150.0))
        draft_timeout = float(getattr(self.settings, "llm_script_draft_timeout_sec", primary_timeout))
        if self.strict_minimax_validation:
            return [("primary", self.primary, primary_timeout)] if self.primary else []
        candidates: list[tuple[str, llm_facade.LLMProvider, float]] = []
        seen: set[int] = set()
        for role, provider, timeout_sec in [
            ("primary", self.primary, primary_timeout),
            ("fallback", self.fallback, self._provider_timeout_sec(self.fallback, draft_timeout) if self.fallback else draft_timeout),
            ("draft", getattr(self, "script_draft_provider", None), draft_timeout),
        ]:
            if not provider or id(provider) in seen:
                continue
            seen.add(id(provider))
            candidates.append((role, provider, timeout_sec))
        return candidates

    def _visual_contract_candidates(self) -> list[tuple[str, llm_facade.LLMProvider, float]]:
        primary_timeout = float(getattr(self.settings, "llm_scene_plan_timeout_sec", self.settings.minimax_scene_plan_timeout_sec))
        fallback_timeout = primary_timeout
        if self.strict_minimax_validation:
            return [("primary", self.primary, primary_timeout)] if self.primary else []
        candidates: list[tuple[str, llm_facade.LLMProvider, float]] = []
        seen: set[int] = set()
        for role, provider, timeout_sec in [
            ("primary", self.primary, primary_timeout),
            ("scene", getattr(self, "scene_provider", None), fallback_timeout),
            ("fallback", self.fallback, self._provider_timeout_sec(self.fallback, fallback_timeout) if self.fallback else fallback_timeout),
        ]:
            if not provider or id(provider) in seen or not hasattr(provider, "generate_visual_contract"):
                continue
            seen.add(id(provider))
            candidates.append((role, provider, timeout_sec))
        return candidates

    def _run_primary_with_timeout(self, fn: Callable[[], Any], timeout_sec: float) -> Any:
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                result_queue.put(("ok", fn()), block=False)
            except BaseException as exc:  # noqa: BLE001
                result_queue.put(("error", exc), block=False)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)
        if thread.is_alive():
            raise concurrent.futures.TimeoutError()
        status, payload = result_queue.get_nowait()
        if status == "error":
            raise payload
        return payload


class LLMProviderRegistry:
    def __init__(self) -> None:
        self.settings = llm_facade.get_settings()

    def primary_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        return self._build_provider(self.settings.llm_primary_provider, required=True)

    def fallback_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        provider = self._build_provider(self.settings.llm_fallback_provider, required=False)
        if provider:
            return provider
        return None

    def script_draft_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        return self._build_provider(getattr(self.settings, "llm_script_draft_provider", ""), required=False)

    def repair_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        return self._build_provider(self.settings.llm_repair_provider, required=False)

    def scene_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        return self._build_provider(self.settings.llm_scene_provider, required=False)

    def gate_judge_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        provider = self._build_provider(self.settings.llm_gate_judge_provider, required=False)
        if provider is None:
            return None
        judge_model = (self.settings.llm_gate_judge_model or "").strip()
        if judge_model and hasattr(provider, "model_name"):
            provider.model_name = judge_model
        return provider

    def premium_review_provider(self) -> llm_facade.LLMProvider | None:
        if self.settings.use_mock_providers:
            return llm_facade.MockCreativeProvider()
        if not bool(getattr(self.settings, "llm_premium_review_enabled", True)):
            return None
        provider = self._build_provider(getattr(self.settings, "llm_premium_review_provider", ""), required=False)
        if provider is None:
            return None
        review_model = (getattr(self.settings, "llm_premium_review_model", None) or "").strip()
        if review_model and hasattr(provider, "model_name"):
            provider.model_name = review_model
        return provider

    def _build_provider(self, name: str, required: bool) -> llm_facade.LLMProvider | None:
        normalized = (name or "").strip().lower()
        if normalized in {"", "none", "disabled"}:
            if required:
                raise ProviderFailure("llm_registry", "primary llm provider is disabled")
            return None
        if normalized in {"mock", "local"}:
            if not self.settings.use_mock_providers:
                if required:
                    raise ProviderFailure("llm_registry", "mock provider is disabled for real runs")
                return None
            return llm_facade.MockCreativeProvider()
        try:
            if normalized in {"openai", "gpt-5", "gpt5", "gpt-5.4", "gpt5.4"}:
                return OpenAICreativeProvider()
            if normalized in {"minimax", "minimax_2_7", "minimax-m2.7", "minimax_m3", "minimax-m3"}:
                return llm_facade.MinimaxCreativeProvider()
            if normalized in {"xai", "grok", "grok-4.20", "grok-4.20-non-reasoning", "openai_compatible"}:
                return XAICreativeProvider()
            if normalized in {"deepseek", "deepseek_v4", "deepseek_v4_flash", "deepseek-v4-flash", "deepseek_v4_pro", "deepseek-v4-pro"}:
                return DeepSeekCreativeProvider()
            if normalized in {"qwen", "qwen_plus", "qwen-plus", "qwen3.7-plus", "qwen3_7_plus", "qwen3.6-max", "qwen3.6-max-preview"}:
                return QwenCreativeProvider()
            if normalized in {"gemini", "gemini_flash", "gemini-flash", "gemini_3_5_flash", "gemini-3.5-flash"}:
                return GeminiCreativeProvider()
        except ProviderFailure:
            if required:
                raise
            return None
        if required:
            raise ProviderFailure("llm_registry", f"unknown llm provider: {name}")
        return None
