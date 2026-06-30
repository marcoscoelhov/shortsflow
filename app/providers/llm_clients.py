from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.providers import llm as llm_facade
from app.providers.errors import ProviderFailure
from app.providers.llm import MinimaxCreativeProvider


class DeepSeekCreativeProvider(MinimaxCreativeProvider):
    provider_name = "deepseek"
    failure_provider_name = "deepseek_text"

    def __init__(self) -> None:
        settings = llm_facade.get_settings()
        if not settings.deepseek_api_key:
            raise ProviderFailure(self.failure_provider_name, "missing deepseek api key")
        self.timeout_sec = settings.deepseek_timeout_sec
        self.model_name = settings.deepseek_model
        self.client = llm_facade.OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=self.timeout_sec,
        )

    def _json_completion(self, prompt: str) -> Any:
        settings = llm_facade.get_settings()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Return ONLY the final JSON object. Do not include reasoning or chain-of-thought. No markdown fences. The response must be a JSON object."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=int(getattr(settings, "llm_json_max_tokens", 4096) or 4096),
                timeout=self.timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderFailure(self.failure_provider_name, str(exc)) from exc
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ProviderFailure(self.failure_provider_name, "empty text response")
        raw = self._strip_think(raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            extracted = self._extract_json(raw)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except Exception:
                    pass
            raise ProviderFailure(self.failure_provider_name, f"invalid json: {raw[:300]}") from exc


    def _json_array_completion(self, prompt: str) -> Any:
        settings = llm_facade.get_settings()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Return ONLY the final JSON array. Do not include reasoning or chain-of-thought. No markdown fences. Top-level must be an array."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=max(12000, int(getattr(settings, "llm_json_max_tokens", 4096) or 4096)),
                timeout=self.timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderFailure(self.failure_provider_name, str(exc)) from exc
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ProviderFailure(self.failure_provider_name, "empty text response")
        raw = self._strip_think(raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            extracted = self._extract_json(raw)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except Exception:
                    pass
            raise ProviderFailure(self.failure_provider_name, f"invalid json array: {raw[:300]}") from exc


class GeminiCreativeProvider(MinimaxCreativeProvider):
    provider_name = "gemini"
    failure_provider_name = "gemini_text"

    def __init__(self) -> None:
        settings = llm_facade.get_settings()
        api_key = settings.resolved_gemini_text_api_key
        if not api_key:
            raise ProviderFailure(self.failure_provider_name, "missing gemini text api key")
        self.timeout_sec = settings.gemini_text_timeout_sec
        self.model_name = settings.gemini_text_model
        self.client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(float(self.timeout_sec) * 1000)),
        )

    def _json_completion(self, prompt: str) -> Any:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderFailure(self.failure_provider_name, str(exc)) from exc
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            raise ProviderFailure(self.failure_provider_name, "empty text response")
        raw = self._strip_think(raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            extracted = self._extract_json(raw)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except Exception:
                    pass
            raise ProviderFailure(self.failure_provider_name, f"invalid json: {raw[:300]}") from exc

    def _json_array_completion(self, prompt: str) -> Any:
        return self._json_completion(prompt)


class OpenAICreativeProvider(MinimaxCreativeProvider):
    provider_name = "openai"
    failure_provider_name = "openai_text"

    def __init__(self) -> None:
        settings = llm_facade.get_settings()
        if not settings.openai_api_key:
            raise ProviderFailure(self.failure_provider_name, "missing openai api key")
        self.timeout_sec = settings.openai_timeout_sec
        self.model_name = settings.openai_model
        self.client = llm_facade.OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=self.timeout_sec,
        )

    def _json_completion(self, prompt: str) -> Any:
        try:
            response = self.client.responses.create(
                model=self.model_name,
                instructions="Return valid JSON only. No markdown fences.",
                input=prompt,
                text={"format": {"type": "json_object"}},
                timeout=self.timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderFailure(self.failure_provider_name, str(exc)) from exc
        raw = (getattr(response, "output_text", None) or "").strip()
        if not raw:
            raise ProviderFailure(self.failure_provider_name, "empty text response")
        raw = self._strip_think(raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            extracted = self._extract_json(raw)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except Exception:
                    pass
            raise ProviderFailure(self.failure_provider_name, f"invalid json: {raw[:300]}") from exc

    def _json_array_completion(self, prompt: str) -> Any:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Return ONLY the final JSON array. Do not include reasoning or chain-of-thought. No markdown fences. Top-level must be an array."},
                    {"role": "user", "content": prompt},
                ],
                timeout=self.timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderFailure(self.failure_provider_name, str(exc)) from exc
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ProviderFailure(self.failure_provider_name, "empty text response")
        raw = self._strip_think(raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            extracted = self._extract_json(raw)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except Exception:
                    pass
            raise ProviderFailure(self.failure_provider_name, f"invalid json array: {raw[:300]}") from exc


class XAICreativeProvider(MinimaxCreativeProvider):
    provider_name = "xai"
    failure_provider_name = "xai_text"

    def __init__(self) -> None:
        settings = llm_facade.get_settings()
        if not settings.xai_api_key:
            raise ProviderFailure(self.failure_provider_name, "missing xai api key")
        self.timeout_sec = settings.xai_timeout_sec
        self.model_name = settings.xai_model
        self.client = llm_facade.OpenAI(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            timeout=self.timeout_sec,
        )


class QwenCreativeProvider(MinimaxCreativeProvider):
    provider_name = "qwen"
    failure_provider_name = "qwen_text"

    def __init__(self) -> None:
        settings = llm_facade.get_settings()
        if not settings.qwen_api_key:
            raise ProviderFailure(self.failure_provider_name, "missing qwen api key")
        self.timeout_sec = settings.qwen_timeout_sec
        self.model_name = settings.qwen_model
        self.client = llm_facade.OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=self.timeout_sec,
        )
