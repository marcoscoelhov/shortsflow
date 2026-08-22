from tests.e2e_support import *  # noqa: F403
from app.config import Settings
from app.providers.errors import ProviderFailure
from app.providers.llm_clients import OpenAICreativeProvider, QwenCreativeProvider, XAICreativeProvider


def test_llm_facade_preserves_public_provider_imports() -> None:
    from app.providers import llm
    from app.providers import llm_clients, llm_routing

    assert llm.DeepSeekCreativeProvider is llm_clients.DeepSeekCreativeProvider
    assert llm.GeminiCreativeProvider is llm_clients.GeminiCreativeProvider
    assert llm.LLMProviderRegistry is llm_routing.LLMProviderRegistry
    assert llm.MinimaxCreativeProvider is MinimaxCreativeProvider
    assert llm.MockCreativeProvider is MockCreativeProvider
    assert llm.OpenAICreativeProvider is llm_clients.OpenAICreativeProvider
    assert llm.QwenCreativeProvider is llm_clients.QwenCreativeProvider
    assert llm.ResilientCreativeProvider is llm_routing.ResilientCreativeProvider


def test_llm_defaults_match_quality_first_routing_policy() -> None:
    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    assert defaults["llm_primary_provider"] == "openai"
    assert defaults["llm_script_draft_provider"] == "openai"
    assert defaults["llm_repair_provider"] == "openai"
    assert defaults["llm_repair_model"] == "gpt-5.6-luna"
    assert defaults["llm_repair_reasoning_effort"] == "max"
    assert defaults["llm_repair_timeout_sec"] == 360.0
    assert defaults["llm_scene_provider"] == "openai"
    assert defaults["llm_fallback_provider"] == "deepseek"
    assert defaults["llm_enable_fallback"] is True
    assert defaults["deepseek_base_url"] == "https://opencode.ai/zen/go/v1"
    assert defaults["deepseek_model"] == "deepseek-v4-flash"
    assert defaults["openai_model"] == "gpt-5.6-luna"
    assert defaults["openai_reasoning_effort"] == "high"
    assert defaults["llm_gate_judge_provider"] == "xai"
    assert defaults["llm_gate_judge_model"] == "kimi-k3"
    assert defaults["llm_premium_review_provider"] == "deepseek"
    assert defaults["llm_premium_review_model"] == "deepseek-v4-pro"
    assert defaults["xai_base_url"] == "https://opencode.ai/zen/go/v1"
    assert defaults["xai_model"] == "kimi-k3"
    assert defaults["xai_reasoning_effort"] == "high"


def test_llm_registry_uses_mock_when_mock_providers_enabled() -> None:
    registry = LLMProviderRegistry()
    assert registry.primary_provider().provider_name == "mock"
    assert registry.fallback_provider().provider_name == "mock"
    assert registry.repair_provider().provider_name == "mock"
    assert registry.scene_provider().provider_name == "mock"

def test_llm_registry_does_not_mock_fallback_in_real_runs(monkeypatch) -> None:
    settings = SimpleNamespace(
        use_mock_providers=False,
        llm_fallback_provider="deepseek",
        deepseek_api_key=None,
        real_run_allow_mock_fallback=False,
    )
    monkeypatch.setattr("app.providers.llm.get_settings", lambda: settings)

    registry = LLMProviderRegistry()

    assert registry.fallback_provider() is None


def test_llm_registry_does_not_build_configured_fallback_when_disabled(monkeypatch) -> None:
    registry = object.__new__(LLMProviderRegistry)
    registry.settings = SimpleNamespace(
        use_mock_providers=False,
        llm_enable_fallback=False,
        llm_fallback_provider="deepseek",
    )

    def fail_if_built(*_args, **_kwargs):
        raise AssertionError("disabled fallback must not be constructed")

    monkeypatch.setattr(registry, "_build_provider", fail_if_built)

    assert registry.fallback_provider() is None


def test_llm_registry_builds_deepseek_fallback_with_opencode_go_settings_when_enabled(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: None))

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_enable_fallback=True,
            llm_fallback_provider="deepseek",
            deepseek_api_key="legacy-deepseek-key",
            deepseek_base_url="https://opencode.ai/zen/go/v1",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_sec=180,
            openai_api_key="opencode-go-key",
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().fallback_provider()

    assert isinstance(provider, DeepSeekCreativeProvider)
    assert provider.model_name == "deepseek-v4-flash"
    assert captured["api_key"] == "opencode-go-key"
    assert captured["base_url"] == "https://opencode.ai/zen/go/v1"


def test_xai_judge_reuses_opencode_go_key_when_base_url_is_go(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: None))

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            openai_api_key="opencode-go-key",
            xai_api_key="native-xai-key",
            xai_base_url="https://opencode.ai/zen/go/v1",
            xai_model="kimi-k3",
            xai_reasoning_effort="high",
            xai_timeout_sec=180,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = XAICreativeProvider()

    assert provider.model_name == "kimi-k3"
    assert captured["api_key"] == "opencode-go-key"
    assert captured["base_url"] == "https://opencode.ai/zen/go/v1"


def test_script_generation_candidates_skip_duplicate_provider_model() -> None:
    class Provider:
        provider_name = "deepseek"
        model_name = "deepseek-v4-flash"
        timeout_sec = 180.0

    provider = object.__new__(ResilientCreativeProvider)
    setattr(provider, "settings", SimpleNamespace(minimax_script_timeout_sec=150.0, llm_script_draft_timeout_sec=45.0))
    setattr(provider, "strict_minimax_validation", False)
    primary = Provider()
    setattr(provider, "primary", primary)
    setattr(provider, "fallback", None)
    setattr(provider, "script_draft_provider", Provider())

    assert provider._script_generation_candidates() == [("primary", primary, 150.0)]


def test_generate_script_rejects_empty_provider_payload() -> None:
    class EmptyProvider:
        provider_name = "deepseek"
        model_name = "deepseek-v4-flash"

        def generate_script(self, topic_plan):
            return {}

    provider = object.__new__(ResilientCreativeProvider)
    setattr(provider, "strict_minimax_validation", False)
    setattr(provider, "primary", EmptyProvider())
    setattr(provider, "fallback", None)
    setattr(provider, "script_draft_provider", None)
    setattr(provider, "_script_generation_candidates", lambda: [("primary", provider.primary, 1.0)])
    setattr(provider, "_run_primary_with_timeout", lambda fn, timeout_sec: fn())

    with pytest.raises(ProviderFailure) as exc:
        provider.generate_script({"canonical_topic": "cosmos"})

    assert "empty script response" in str(exc.value)
    assert "deepseek" in str(exc.value)


def test_deepseek_provider_uses_v4_flash_openai_compatible_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    settings = SimpleNamespace(
        deepseek_api_key="deepseek-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout_sec=90,
        llm_json_max_tokens=4096,
    )

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "title": "A comida que pinta flamingos",
                                    "hook": "A pena rosa começa no prato.",
                                    "body_beats": ["Pigmentos da dieta podem influenciar a cor."],
                                    "ending": "No replay, a primeira frase já mostrava a tinta.",
                                    "cta": None,
                                    "full_narration": "A pena rosa começa no prato. Pigmentos da dieta podem influenciar a cor. No replay, a primeira frase já mostrava a tinta.",
                                    "estimated_duration_sec": 30,
                                    "key_facts": ["Pigmentos da dieta podem influenciar a cor."],
                                    "source_fact_ids": [],
                                    "token_count": 24,
                                    "language": "pt-BR",
                                    "retention_map": {},
                                    "visual_opening": {},
                                    "qa_metrics": {},
                                    "prompt_version": EDITORIAL_PROMPT_VERSION,
                                }
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.providers.llm.get_settings", lambda: settings)
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = DeepSeekCreativeProvider()
    result = provider.repair_script({"title": "x"}, ["weak_loop_closure"], {"canonical_topic": "flamingos"})

    assert captured["client_kwargs"]["api_key"] == "deepseek-key"
    assert captured["client_kwargs"]["base_url"] == "https://api.deepseek.com"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["max_tokens"] == 4096
    assert "cada valor textual de retention_map deve ser cópia literal" in str(captured["messages"])
    assert "repetition_score usa escala 0.0 a 1.0" in str(captured["messages"])
    assert result["qa_metrics"]["repair_provider"] == "deepseek"


def test_deepseek_opencode_go_uses_primary_key_instead_of_legacy_deepseek_key(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(
        deepseek_api_key="legacy-deepseek-key",
        deepseek_base_url="https://opencode.ai/zen/go/v1",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout_sec=90,
        openai_api_key="opencode-go-key",
        openai_base_url="https://primary-provider.example/v1",
    )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.providers.llm.get_settings", lambda: settings)
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = DeepSeekCreativeProvider()

    assert provider.model_name == "deepseek-v4-flash"
    assert captured["api_key"] == "opencode-go-key"
    assert captured["base_url"] == "https://opencode.ai/zen/go/v1"


def test_llm_registry_builds_qwen_optional_provider(monkeypatch) -> None:
    settings = SimpleNamespace(
        use_mock_providers=False,
        llm_scene_provider="qwen",
        qwen_api_key="qwen-key",
        qwen_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        qwen_model="qwen3.7-plus",
        qwen_timeout_sec=90,
    )

    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

    monkeypatch.setattr("app.providers.llm.get_settings", lambda: settings)
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().scene_provider()

    assert provider.provider_name == "qwen"
    assert provider.model_name == "qwen3.7-plus"
    assert captured["client_kwargs"]["base_url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def test_qwen_provider_cannot_audit_or_judge_publication() -> None:
    provider = object.__new__(QwenCreativeProvider)

    with pytest.raises(ProviderFailure, match="not a publication authority"):
        provider.audit_publish_package({"forged_score": 1.0})
    with pytest.raises(ProviderFailure, match="not a quality-gate authority"):
        provider.judge_quality_gate("publish_readiness", {"forged_score": 1.0})

def test_openai_provider_uses_responses_api_with_json_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "title": "Cafe mascara a fadiga",
                                    "hook": "Cafe nao cria energia do nada.",
                                    "body_beats": ["A cafeina atrasa a percepcao do cansaco."],
                                    "ending": "Na segunda olhada, o primeiro aviso vira pista.",
                                    "cta": None,
                                    "full_narration": "Cafe nao cria energia do nada. A cafeina atrasa a percepcao do cansaco. Na segunda olhada, o primeiro aviso vira pista.",
                                    "estimated_duration_sec": 35,
                                    "key_facts": ["A cafeina atrasa a percepcao do cansaco."],
                                    "source_fact_ids": ["F1"],
                                    "claim_trace": [{"text": "A cafeina atrasa a percepcao do cansaco.", "source_fact_ids": ["F1"], "grounding": "fact_pack"}],
                                    "token_count": 20,
                                    "language": "pt-BR",
                                    "retention_map": {},
                                    "visual_opening": {},
                                    "qa_metrics": {},
                                    "prompt_version": EDITORIAL_PROMPT_VERSION,
                                }
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="openai-key",
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-5.4",
            openai_reasoning_effort="max",
            openai_timeout_sec=120,
            llm_json_max_tokens=2048,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = OpenAICreativeProvider()
    result = provider.generate_script({"canonical_topic": "cafeina e sono", "title_candidates": ["Cafe mascara a fadiga"]})

    assert captured["client_kwargs"]["api_key"] == "openai-key"
    assert captured["model"] == "gpt-5.4"
    assert captured["reasoning_effort"] == "max"
    assert captured["max_tokens"] == 2048
    assert captured["response_format"] == {"type": "json_object"}
    assert "cada valor textual de retention_map deve ser cópia literal" in str(captured["messages"])
    assert "repetition_score usa escala 0.0 a 1.0" in str(captured["messages"])
    assert "meta editorial: retenção máxima, replay, compartilhamento orgânico e espanto genuíno" in str(captured["messages"])
    assert "body_beats equivale aos Beats em escalada" in str(captured["messages"])
    assert result["qa_metrics"]["source_provider"] == "openai"


def test_openai_scene_planning_uses_responses_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='[{"scene_id":"scene-1","order":1}]'))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="opencode-go-key",
            openai_base_url="https://opencode.ai/zen/go/v1",
            openai_model="gpt-5.6-luna",
            openai_reasoning_effort="high",
            openai_timeout_sec=120,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    scenes = OpenAICreativeProvider().plan_scenes({"full_narration": "Uma cena de teste."}, 1)

    assert captured["client_kwargs"]["base_url"] == "https://opencode.ai/zen/go/v1"
    assert captured["model"] == "gpt-5.6-luna"
    assert captured["messages"][0]["content"] == "Return ONLY the final JSON array. No reasoning, prose, or markdown fences."
    assert scenes == [{"scene_id": "scene-1", "order": 1}]

def test_openai_provider_topic_prompt_uses_hub_viral_ruler(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "canonical_topic": "flamingos rosa",
                                    "angle": "pigmento que muda a cor",
                                    "hook_promise": "o prato muda a pena",
                                    "title_candidates": ["Flamingos rosa: a comida muda a cor deles"],
                                    "entities": ["flamingos", "pigmentos"],
                                    "search_terms": ["flamingo carotenoids plumage"],
                                    "quality_metrics": {},
                                }
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="openai-key",
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-5.4",
            openai_timeout_sec=120,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = OpenAICreativeProvider()
    result = provider.plan_topic("Por que os flamingos ficam rosa?", 1, [], None)

    assert captured["client_kwargs"]["api_key"] == "openai-key"
    assert captured["response_format"] == {"type": "json_object"}
    assert "Crie pautas de curiosidades globais para YouTube Shorts em pt-BR." in str(captured["messages"])
    assert "Loop: pergunta mental de tensão que só fecha no payoff" in str(captured["messages"])
    assert "exceto search_terms quando pesquisa factual em ingles ajudar" in str(captured["messages"])
    assert "search_terms em ingles para pesquisa factual" in str(captured["messages"])
    assert result["quality_metrics"]["source_provider"] == "openai"

def test_llm_registry_supports_openai_primary_provider(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=lambda **_kwargs: None)

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_primary_provider="openai",
            llm_fallback_provider="deepseek",
            llm_script_draft_provider="deepseek",
            llm_repair_provider="deepseek",
            llm_scene_provider="deepseek",
            real_run_allow_mock_fallback=False,
            openai_api_key="openai-key",
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-5.4",
            openai_timeout_sec=120,
            deepseek_api_key="deepseek-key",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_sec=90,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    registry = LLMProviderRegistry()

    assert registry.primary_provider().provider_name == "openai"


def test_repair_provider_uses_luna_max_on_opencode_go(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=lambda **_kwargs: None)

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_repair_provider="openai",
            llm_repair_model="gpt-5.6-luna",
            llm_repair_reasoning_effort="max",
            llm_repair_timeout_sec=360,
            real_run_allow_mock_fallback=False,
            openai_api_key="opencode-go-key",
            openai_base_url="https://opencode.ai/zen/go/v1",
            openai_model="gpt-5.6-luna",
            openai_reasoning_effort="high",
            openai_timeout_sec=180,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().repair_provider()

    assert isinstance(provider, OpenAICreativeProvider)
    assert provider.provider_name == "openai"
    assert provider.model_name == "gpt-5.6-luna"
    assert provider.reasoning_effort == "max"
    assert provider.timeout_sec == 360


def test_gate_judge_provider_uses_strong_openai_model(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=lambda **_kwargs: None)

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_gate_judge_provider="openai",
            llm_gate_judge_model="gpt-5.4",
            openai_api_key="openai-key",
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-5.4-nano",
            openai_timeout_sec=120,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().gate_judge_provider()

    assert provider is not None
    assert provider.provider_name == "openai"
    assert provider.model_name == "gpt-5.4"


def test_xai_grok46_gate_judge_uses_high_reasoning(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "passed": True,
                                    "confidence": 0.91,
                                    "reasons": [],
                                    "scores": {"hook": 0.9},
                                    "provider": "xai",
                                }
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_gate_judge_provider="xai",
            llm_gate_judge_model="grok-4.6",
            xai_api_key="xai-key",
            xai_base_url="https://api.x.ai/v1",
            xai_model="grok-4.20-non-reasoning",
            xai_reasoning_effort="high",
            xai_timeout_sec=120,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().gate_judge_provider()
    assert isinstance(provider, XAICreativeProvider)

    result = provider.judge_quality_gate("editorial", {"script": {"hook": "Escolha agora"}})

    assert result["passed"] is True
    assert captured["model"] == "grok-4.6"
    assert captured["reasoning_effort"] == "high"


def test_quality_judge_candidates_prioritize_gate_judge_provider() -> None:
    class Judge:
        provider_name = "openai"

        def judge_quality_gate(self, gate_kind: str, payload: dict) -> dict:
            return {"passed": True, "confidence": 0.9, "reasons": [], "provider": "openai", "gate_kind": gate_kind}

    class Repair:
        provider_name = "deepseek"

        def judge_quality_gate(self, gate_kind: str, payload: dict) -> dict:
            return {"passed": False, "confidence": 0.0, "reasons": ["repair"], "provider": "deepseek", "gate_kind": gate_kind}

    resilient = object.__new__(ResilientCreativeProvider)
    resilient.settings = SimpleNamespace(llm_gate_judge_timeout_sec=30.0)
    resilient.gate_judge_provider = Judge()
    resilient.fallback = None
    resilient.repair_provider = Repair()

    roles = [role for role, _provider in resilient._quality_judge_candidates()]

    assert roles == ["gate_judge", "repair"]


def test_quality_judge_candidates_fail_closed_when_fallback_disabled() -> None:
    class Judge:
        provider_name = "xai"

        def judge_quality_gate(self, gate_kind: str, payload: dict) -> dict:
            raise ProviderFailure("xai_text", "credits unavailable")

    class Repair:
        provider_name = "openai"

        def judge_quality_gate(self, gate_kind: str, payload: dict) -> dict:
            return {"passed": True, "confidence": 0.99, "provider": "openai"}

    resilient = object.__new__(ResilientCreativeProvider)
    object.__setattr__(
        resilient,
        "settings",
        SimpleNamespace(
            llm_gate_judge_timeout_sec=120.0,
            llm_premium_review_enabled=False,
            llm_enable_fallback=False,
        ),
    )
    object.__setattr__(resilient, "gate_judge_provider", Judge())
    object.__setattr__(resilient, "premium_review_provider", None)
    object.__setattr__(resilient, "fallback", None)
    object.__setattr__(resilient, "repair_provider", Repair())

    roles = [role for role, _provider in resilient._quality_judge_candidates("editorial", {})]

    assert roles == ["gate_judge"]


def test_quality_judge_does_not_retry_same_provider_and_model_as_premium() -> None:
    premium = SimpleNamespace(provider_name="xai", model_name="grok-4.6", judge_quality_gate=lambda *_args: {})
    gate = SimpleNamespace(provider_name="xai", model_name="grok-4.6", judge_quality_gate=lambda *_args: {})
    resilient = object.__new__(ResilientCreativeProvider)
    resilient.settings = SimpleNamespace(llm_enable_fallback=False, llm_premium_review_enabled=True)
    resilient.premium_review_provider = premium
    resilient.gate_judge_provider = gate
    resilient.fallback = None
    resilient.repair_provider = None

    candidates = resilient._quality_judge_candidates("growth_score", {"review_tier": "premium"})

    assert [(role, provider.model_name) for role, provider in candidates] == [("premium_review", "grok-4.6")]


def test_premium_review_provider_uses_deepseek_pro_model_for_exceptions(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: None))

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            use_mock_providers=False,
            llm_premium_review_enabled=True,
            llm_premium_review_provider="deepseek",
            llm_premium_review_model="deepseek-v4-pro",
            deepseek_api_key="deepseek-key",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_sec=90,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = LLMProviderRegistry().premium_review_provider()

    assert provider is not None
    assert provider.provider_name == "deepseek"
    assert provider.model_name == "deepseek-v4-pro"


def test_premium_review_candidate_only_for_explicit_exception() -> None:
    class Judge:
        provider_name = "deepseek"

        def judge_quality_gate(self, gate_kind: str, payload: dict) -> dict:
            return {"passed": True, "confidence": 0.9, "reasons": [], "provider": "deepseek", "gate_kind": gate_kind}

    class Premium(Judge):
        provider_name = "deepseek-pro"

    resilient = object.__new__(ResilientCreativeProvider)
    resilient.settings = SimpleNamespace(llm_gate_judge_timeout_sec=30.0, llm_premium_review_enabled=True)
    resilient.gate_judge_provider = Judge()
    resilient.premium_review_provider = Premium()
    resilient.fallback = None
    resilient.repair_provider = None

    normal_roles = [role for role, _provider in resilient._quality_judge_candidates("editorial", {"local_reasons": ["weak_ending"]})]
    premium_roles = [role for role, _provider in resilient._quality_judge_candidates("growth_score", {"review_tier": "premium"})]

    assert normal_roles == ["gate_judge"]
    assert premium_roles == ["premium_review", "gate_judge"]


def test_resilient_creative_provider_uses_minimax_before_deepseek_fallback() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(
        minimax_script_timeout_sec=30,
        llm_script_draft_timeout_sec=0.5,
        llm_enable_fallback=True,
    )
    provider.strict_minimax_validation = False

    class Draft:
        provider_name = "deepseek"

        def generate_script(self, topic_plan):
            raise AssertionError("draft provider should not run before primary script generation")

    class Primary:
        provider_name = "minimax"

        def generate_script(self, topic_plan):
            return {
                "title": "Roteiro MiniMax",
                "hook": "O começo já entrega tensão.",
                "body_beats": ["A prova aparece sem enrolação."],
                "ending": "Na segunda olhada, o começo vira pista.",
                "cta": None,
                "full_narration": "O começo já entrega tensão. A prova aparece sem enrolação. Na segunda olhada, o começo vira pista.",
                "estimated_duration_sec": 28,
                "key_facts": [],
                "source_fact_ids": [],
                "token_count": 20,
                "language": "pt-BR",
                "qa_metrics": {"source_provider": "minimax"},
            }

    provider.script_draft_provider = Draft()
    provider.primary = Primary()
    provider.fallback = None

    script = provider.generate_script({"canonical_topic": "polvos"})

    assert script["qa_metrics"]["generation_provider_role"] == "primary"
    assert script["qa_metrics"]["generation_provider"] == "minimax"
    assert script["qa_metrics"]["script_generation_fallback_used"] is False

def test_resilient_creative_provider_falls_back_to_deepseek_after_minimax_failure() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(
        minimax_script_timeout_sec=30,
        llm_script_draft_timeout_sec=0.5,
        llm_enable_fallback=True,
    )
    provider.strict_minimax_validation = False

    class Primary:
        provider_name = "minimax"

        def generate_script(self, topic_plan):
            raise ProviderFailure("minimax_text", "minimax failed")

    class Fallback:
        provider_name = "deepseek"

        def generate_script(self, topic_plan):
            return {
                "title": "Roteiro fallback",
                "hook": "O começo já entrega tensão.",
                "body_beats": ["A prova aparece sem enrolação."],
                "ending": "Na segunda olhada, o começo vira pista.",
                "cta": None,
                "full_narration": "O começo já entrega tensão. A prova aparece sem enrolação. Na segunda olhada, o começo vira pista.",
                "estimated_duration_sec": 28,
                "key_facts": [],
                "source_fact_ids": [],
                "token_count": 20,
                "language": "pt-BR",
                "qa_metrics": {"source_provider": "deepseek"},
            }

    provider.script_draft_provider = None
    provider.primary = Primary()
    provider.fallback = Fallback()

    script = provider.generate_script({"canonical_topic": "polvos"})

    assert script["qa_metrics"]["generation_provider_role"] == "fallback"
    assert script["qa_metrics"]["generation_provider"] == "deepseek"
    assert script["qa_metrics"]["script_generation_fallback_used"] is True
    assert script["qa_metrics"]["script_generation_fallback_reasons"] == ["minimax failed"]

def test_resilient_creative_provider_topic_uses_role_timeout() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(llm_topic_timeout_sec=0.01, minimax_text_timeout_sec=30)
    provider.strict_minimax_validation = False

    class SlowPrimary:
        failure_provider_name = "deepseek_text"

        def plan_topic(self, *args, **kwargs):
            time.sleep(0.05)
            return {"quality_metrics": {}}

    class Fallback:
        def plan_topic(self, *args, **kwargs):
            return {
                "canonical_topic": "fallback",
                "angle": "rapido",
                "hook_promise": "gancho",
                "title_candidates": ["fallback"],
                "quality_metrics": {},
            }

    provider.primary = SlowPrimary()
    provider.fallback = Fallback()

    plan = provider.plan_topic("tema", 1, [], None)

    assert plan["canonical_topic"] == "fallback"
    assert plan["quality_metrics"]["fallback_used"] is True
    assert "deepseek_text topic planner timed out after 0.01s" in plan["quality_metrics"]["fallback_reason"]


def test_luna_topic_failure_preserves_deepseek_fallback_metadata() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(llm_topic_timeout_sec=30, minimax_text_timeout_sec=30)
    provider.strict_minimax_validation = False

    class Luna:
        provider_name = "openai"

        def plan_topic(self, *args, **kwargs):
            raise ProviderFailure("openai_text", "Luna unavailable")

    class DeepSeek:
        provider_name = "deepseek"

        def plan_topic(self, *args, **kwargs):
            return {
                "canonical_topic": "A Lua no horizonte",
                "angle": "A ilusão visual da Lua",
                "hook_promise": "A Lua parece crescer sem mudar de tamanho.",
                "title_candidates": ["A Lua gigante no horizonte"],
                "entities": ["Lua"],
                "search_terms": ["Moon illusion horizon"],
                "quality_metrics": {
                    "source_provider": "deepseek",
                    "viral_potential_score": 0.8,
                    "viral_potential_reason": "Contraste visual reconhecível.",
                },
            }

    provider.primary = Luna()
    provider.fallback = DeepSeek()

    plan = provider.plan_topic("Lua", 1, [], None)

    assert plan["quality_metrics"]["source_provider"] == "deepseek"
    assert plan["quality_metrics"]["fallback_used"] is True
    assert plan["quality_metrics"]["fallback_stage"] == "topic_plan_failure"
    assert "Luna unavailable" in plan["quality_metrics"]["fallback_reason"]


def test_shared_provider_topic_batch_uses_one_json_call_and_exactly_ten_contract(monkeypatch) -> None:
    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "openai"
    provider.failure_provider_name = "openai_text"
    calls: list[tuple[str, int | None]] = []
    drafts = [
        {
            "canonical_topic": f"Tema astronômico {index}",
            "angle": f"Ângulo {index}",
            "hook_promise": f"Objeto espacial {index} revela algo visível.",
            "title_candidates": [f"Título {index}"],
            "entities": [f"Objeto {index}"],
            "search_terms": [f"astronomy object {index}"],
            "quality_metrics": {
                "viral_potential_score": 0.8,
                "viral_potential_reason": "Contraste visual claro.",
            },
        }
        for index in range(10)
    ]

    def fake_completion(prompt: str, *, max_tokens: int | None = None):
        calls.append((prompt, max_tokens))
        return {"drafts": drafts}

    monkeypatch.setattr(provider, "_json_completion", fake_completion)

    result = provider.plan_topic_batch(
        [{"topic": "Lua"}, {"topic": "Saturno"}],
        10,
        1,
        [],
        tone="intrigante_direto",
        notes="sem repetição",
    )

    assert len(calls) == 1
    assert calls[0][1] == 12000
    assert 'JSON estrito {"drafts": [...]}' in calls[0][0]
    assert "exatamente 10" in calls[0][0]
    assert len(result["drafts"]) == 10
    assert all(draft["quality_metrics"]["source_provider"] == "openai" for draft in result["drafts"])


def test_luna_batch_failure_invokes_deepseek_batch_once_and_annotates_every_draft() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(llm_topic_timeout_sec=30, minimax_text_timeout_sec=30)
    provider.strict_minimax_validation = False
    calls = {"luna": 0, "deepseek": 0}

    class Luna:
        provider_name = "openai"
        failure_provider_name = "openai_text"

        def plan_topic_batch(self, *args, **kwargs):
            calls["luna"] += 1
            raise ProviderFailure("openai_text", "Luna batch unavailable")

    class DeepSeek:
        provider_name = "deepseek"

        def plan_topic_batch(self, *args, **kwargs):
            calls["deepseek"] += 1
            return {"drafts": [{"quality_metrics": {}} for _ in range(10)]}

    provider.primary = Luna()
    provider.fallback = DeepSeek()

    result = provider.plan_topic_batch([{"topic": "Lua"}], 10, 1, [])

    assert calls == {"luna": 1, "deepseek": 1}
    assert all(draft["quality_metrics"]["source_provider"] == "deepseek" for draft in result["drafts"])
    assert all(draft["quality_metrics"]["fallback_used"] is True for draft in result["drafts"])
    assert all(draft["quality_metrics"]["fallback_stage"] == "topic_batch_failure" for draft in result["drafts"])
    assert all("Luna batch unavailable" in draft["quality_metrics"]["fallback_reason"] for draft in result["drafts"])


def test_topic_draft_selection_calls_only_gate_judge_once_with_configured_timeout(monkeypatch) -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(llm_gate_judge_timeout_sec=17.0)
    calls: list[tuple[str, dict]] = []

    class GateJudge:
        provider_name = "xai"
        model_name = "grok-4.6"

        def judge_quality_gate(self, gate_kind, payload):
            calls.append((gate_kind, payload))
            return {"selected_index": 0, "ranking": [], "confidence": 0.5, "selected_reason": "Razão."}

    class ForbiddenJudge:
        provider_name = "deepseek"

        def judge_quality_gate(self, *_args):
            raise AssertionError("generator/fallback must not judge topic drafts")

    provider.gate_judge_provider = GateJudge()
    provider.primary = ForbiddenJudge()
    provider.fallback = ForbiddenJudge()
    provider.repair_provider = ForbiddenJudge()
    observed_timeout: list[float] = []

    def run(callable_, *, timeout_sec):
        observed_timeout.append(timeout_sec)
        return callable_()

    monkeypatch.setattr(provider, "_run_primary_with_timeout", run)

    result = provider.select_topic_draft([{"canonical_topic": "Lua"}])

    assert calls == [("topic_draft_selection", {"drafts": [{"canonical_topic": "Lua"}]})]
    assert observed_timeout == [17.0]
    assert result["judge_provider_role"] == "gate_judge"
    assert result["provider"] == "xai"
    assert result["model"] == "grok-4.6"


def test_luna_batch_route_passes_topic_batch_max_tokens(monkeypatch) -> None:
    provider = object.__new__(OpenAICreativeProvider)
    provider.provider_name = "openai"
    provider.failure_provider_name = "openai_text"
    provider.model_name = "gpt-5.6-luna"
    provider.reasoning_effort = "high"
    provider.max_output_tokens = 4096
    provider.timeout_sec = 60.0
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"drafts": []})))]
            )

    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    provider.plan_topic_batch([{"topic": "Lua"}], 10, 1, [])

    assert captured["max_tokens"] == 12000


def test_deepseek_batch_route_passes_topic_batch_max_tokens(monkeypatch) -> None:
    provider = object.__new__(DeepSeekCreativeProvider)
    provider.provider_name = "deepseek"
    provider.failure_provider_name = "deepseek_text"
    provider.model_name = "deepseek-v4-flash"
    provider.timeout_sec = 60.0
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"drafts": []})))]
            )

    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    provider.plan_topic_batch([{"topic": "Lua"}], 10, 1, [])

    assert captured["max_tokens"] == 12000


def test_ordinary_completions_still_use_llm_json_max_tokens(monkeypatch) -> None:
    provider = object.__new__(OpenAICreativeProvider)
    provider.provider_name = "openai"
    provider.failure_provider_name = "openai_text"
    provider.model_name = "gpt-5.6-luna"
    provider.reasoning_effort = "high"
    provider.max_output_tokens = 4096
    provider.timeout_sec = 60.0
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"ok": True})))]
            )

    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    provider._json_completion("prompt comum")

    assert captured["max_tokens"] == 4096


def test_shared_judge_has_topic_draft_selection_prompt(monkeypatch) -> None:
    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "xai"
    provider.model_name = "grok-4.6"
    captured: list[str] = []

    def fake_completion(prompt: str):
        captured.append(prompt)
        return {"selected_index": 0, "selected_reason": "Razão.", "ranking": [], "confidence": 0.5}

    monkeypatch.setattr(provider, "_json_completion", fake_completion)

    result = provider.judge_quality_gate("topic_draft_selection", {"drafts": []})

    assert len(captured) == 1
    assert "selected_index" in captured[0]
    assert "ranking exatamente 10" in captured[0]
    assert result["provider"] == "xai"
    assert result["model"] == "grok-4.6"

def test_resilient_creative_provider_disables_repair_fallback_in_strict_minimax_mode() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(minimax_script_timeout_sec=0.01, llm_enable_fallback=True, strict_minimax_validation=True)
    provider.strict_minimax_validation = True
    provider.primary = None
    provider.fallback = MockCreativeProvider()

    assert provider.repair_script_with_fallback({"title": "x"}, ["fact_pack_source_ids_missing"], {"canonical_topic": "polvos"}) is None

def test_job_lease_delta_has_floor_for_real_provider_steps(monkeypatch) -> None:
    test_orchestrator = JobOrchestrator()
    monkeypatch.setattr(test_orchestrator.settings, "job_lease_seconds", 60)

    assert test_orchestrator._lease_delta().total_seconds() == 3600
