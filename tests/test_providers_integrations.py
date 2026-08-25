from tests.e2e_support import *  # noqa: F403
import threading

from app.config import Settings
from app.providers.errors import ProviderFailure
from app.providers.llm_clients import DeepSeekCreativeProvider, OpenAICreativeProvider, XAICreativeProvider


@pytest.mark.parametrize(
    ("provider_class", "expected_provider", "method_name"),
    [
        (DeepSeekCreativeProvider, "deepseek_text", "_json_completion"),
        (DeepSeekCreativeProvider, "deepseek_text", "_json_array_completion"),
        (OpenAICreativeProvider, "openai_text", "_json_completion"),
        (OpenAICreativeProvider, "openai_text", "_json_array_completion"),
        (XAICreativeProvider, "xai_text", "_json_completion"),
    ],
)
@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(message=None)]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=123))]),
    ],
)
def test_chat_completion_malformed_response_becomes_provider_failure(
    provider_class, expected_provider: str, method_name: str, response: object
) -> None:
    provider = object.__new__(provider_class)
    provider.model_name = "test-model"
    provider.reasoning_effort = "medium"
    provider.max_output_tokens = 4096
    provider.timeout_sec = 10.0
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: response),
        )
    )

    with pytest.raises(ProviderFailure) as exc_info:
        getattr(provider, method_name)("prompt")

    assert exc_info.value.provider == expected_provider


def test_llm_facade_preserves_public_provider_imports() -> None:
    from app.providers import llm
    from app.providers import llm_clients, llm_routing

    assert llm.DeepSeekCreativeProvider is llm_clients.DeepSeekCreativeProvider
    assert llm.GeminiCreativeProvider is llm_clients.GeminiCreativeProvider
    assert llm.LLMProviderRegistry is llm_routing.LLMProviderRegistry
    assert llm.MinimaxCreativeProvider is MinimaxCreativeProvider
    assert llm.MockCreativeProvider is MockCreativeProvider
    assert llm.OpenAICreativeProvider is llm_clients.OpenAICreativeProvider
    assert llm.ResilientCreativeProvider is llm_routing.ResilientCreativeProvider


def test_llm_defaults_match_quality_first_routing_policy() -> None:
    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    assert defaults["llm_primary_provider"] == "openai"
    assert defaults["llm_script_draft_provider"] == "deepseek"
    assert defaults["llm_repair_provider"] == "openai"
    assert defaults["llm_repair_model"] == "gpt-5.6-luna"
    assert defaults["llm_repair_reasoning_effort"] == "high"
    assert defaults["llm_repair_timeout_sec"] == 360.0
    assert defaults["llm_scene_provider"] == "openai"
    assert defaults["llm_fallback_provider"] == "deepseek"
    assert defaults["llm_enable_fallback"] is True
    assert defaults["deepseek_base_url"] == "https://opencode.ai/zen/go/v1"
    assert defaults["deepseek_model"] == "deepseek-v4-flash"
    assert defaults["openai_model"] == "gpt-5.6-luna"
    assert defaults["openai_reasoning_effort"] == "max"
    assert defaults["llm_script_reasoning_effort"] == "high"
    assert defaults["llm_gate_judge_provider"] == "xai"
    assert defaults["llm_gate_judge_model"] == "grok-4.5"
    assert defaults["llm_premium_review_provider"] == "deepseek"
    assert defaults["llm_premium_review_model"] == "deepseek-v4-pro"
    assert defaults["xai_base_url"] == "https://opencode.ai/zen/go/v1"
    assert defaults["xai_model"] == "grok-4.5"
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
            xai_model="kimi-k2.6",
            xai_reasoning_effort="high",
            xai_timeout_sec=180,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = XAICreativeProvider()

    assert provider.model_name == "kimi-k2.6"
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
    setattr(provider, "gate_judge_provider", None)

    assert provider._script_generation_candidates() == [
        ("draft", provider.script_draft_provider, 180.0)
    ]


def test_script_generation_candidates_prioritize_dedicated_draft_provider() -> None:
    class Provider:
        def __init__(self, provider_name: str, model_name: str, timeout_sec: float, reasoning_effort: str | None = None) -> None:
            self.provider_name = provider_name
            self.model_name = model_name
            self.timeout_sec = timeout_sec
            self.reasoning_effort = reasoning_effort

    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(minimax_script_timeout_sec=150.0, llm_script_draft_timeout_sec=45.0)
    provider.strict_minimax_validation = False
    primary = Provider("openai", "gpt-5.6-luna", 150.0, "max")
    fallback = Provider("deepseek", "deepseek-v4-flash", 180.0)
    emergency = Provider("xai", "grok-4.5", 180.0)
    provider.primary = primary
    provider.fallback = fallback
    provider.script_draft_provider = fallback
    provider.gate_judge_provider = emergency

    assert provider._script_generation_candidates() == [
        ("draft", fallback, 180.0),
        ("primary", primary, 150.0),
        ("emergency", emergency, 180.0),
    ]
    assert primary.reasoning_effort == "max"


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


def test_deepseek_microdrama_generation_forwards_high_reasoning_to_chat_completions(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(
        deepseek_api_key="legacy-deepseek-key",
        deepseek_base_url="https://opencode.ai/zen/go/v1",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout_sec=180,
        openai_api_key="opencode-go-key",
        llm_script_reasoning_effort="high",
        llm_json_max_tokens=4096,
        microdrama_script_max_tokens=4096,
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
                                    "title": "A carta",
                                    "full_narration": "A carta voltou fechada, mas agora tinha a letra dela.",
                                    "qa_metrics": {},
                                }
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.providers.llm.get_settings", lambda: settings)
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    result = DeepSeekCreativeProvider().generate_script(
        {
            "niche_id": "fiction_microdrama",
            "target_duration_sec": 120,
            "canonical_topic": "uma carta impossível",
        }
    )

    assert result["title"] == "A carta"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["reasoning_effort"] == "high"
    assert captured["response_format"] == {"type": "json_object"}


def test_llm_registry_gate_judge_defaults_to_opencode_go_grok45(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: Settings(
            _env_file=None,
            use_mock_providers=False,
            openai_api_key="opencode-go-key",
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", lambda **_kwargs: SimpleNamespace())

    provider = LLMProviderRegistry().gate_judge_provider()

    assert isinstance(provider, XAICreativeProvider)
    assert provider.model_name == "grok-4.5"
    assert provider.reasoning_effort == "high"


def test_opencode_go_grok45_gate_judge_uses_responses_api_and_parses_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "passed": True,
                        "confidence": 0.91,
                        "reasons": [],
                        "scores": {"viral_intensity": 0.9},
                        "notes": "Pronto para revisão.",
                    }
                )
            )

    class FakeCompletions:
        def create(self, **_kwargs):
            raise AssertionError("OpenCode Go grok-4.5 must use /responses")

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="opencode-go-key",
            xai_api_key=None,
            xai_base_url="https://opencode.ai/zen/go/v1",
            xai_model="grok-4.5",
            xai_reasoning_effort="high",
            xai_timeout_sec=180,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    result = XAICreativeProvider().judge_quality_gate(
        "editorial",
        {"script": {"hook": "A carta voltou fechada."}},
    )

    assert result["passed"] is True
    assert result["provider"] == "xai"
    assert result["model"] == "grok-4.5"
    assert captured["reasoning"] == {"effort": "high"}
    assert "text" not in captured
    assert captured["max_output_tokens"] == 4096


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

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='[{"scene_id":"scene-1","order":1}]')

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

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
    assert captured["instructions"] == "Return ONLY the final JSON array. No reasoning, prose, or markdown fences."
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["max_output_tokens"] == 4096
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


def test_resilient_creative_provider_uses_dedicated_deepseek_draft_before_primary() -> None:
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
            return {
                "title": "Roteiro DeepSeek",
                "full_narration": "A prova aparece e muda o sentido da carta.",
                "qa_metrics": {"source_provider": "deepseek"},
            }

    class Primary:
        provider_name = "minimax"

        def generate_script(self, topic_plan):
            raise AssertionError("primary should not run after a valid dedicated draft")

    provider.script_draft_provider = Draft()
    provider.primary = Primary()
    provider.fallback = None

    script = provider.generate_script({"canonical_topic": "polvos"})

    assert script["qa_metrics"]["generation_provider_role"] == "draft"
    assert script["qa_metrics"]["generation_provider"] == "deepseek"
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


def test_resilient_creative_provider_uses_emergency_provider_before_slow_fallback() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(minimax_script_timeout_sec=30, llm_script_draft_timeout_sec=30)
    provider.strict_minimax_validation = False

    class FailingProvider:
        def __init__(self, provider_name: str, model_name: str) -> None:
            self.provider_name = provider_name
            self.model_name = model_name

        def generate_script(self, topic_plan):
            raise ProviderFailure(self.provider_name, f"{self.provider_name} failed")

    class EmergencyProvider:
        provider_name = "xai"
        model_name = "kimi-k2.6"
        timeout_sec = 180.0

        def generate_script(self, topic_plan):
            return {
                "title": "Roteiro de emergência",
                "full_narration": "A carta reaparece e muda tudo no último instante.",
                "qa_metrics": {},
            }

    provider.primary = FailingProvider("openai", "gpt-5.6-luna")
    provider.fallback = FailingProvider("deepseek", "deepseek-v4-flash")
    provider.script_draft_provider = None
    provider.gate_judge_provider = EmergencyProvider()
    provider._run_primary_with_timeout = lambda fn, timeout_sec: fn()

    script = provider.generate_script({"canonical_topic": "a carta"})

    assert script["qa_metrics"]["generation_provider_role"] == "emergency"
    assert script["qa_metrics"]["generation_provider"] == "xai"
    assert script["qa_metrics"]["script_generation_fallback_used"] is True
    assert script["qa_metrics"]["script_generation_fallback_reasons"] == ["openai failed"]


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


def test_opencode_go_luna_uses_responses_api_for_json_object(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps({"ok": True}))

    class ForbiddenChatCompletions:
        def create(self, **_kwargs):
            raise AssertionError("OpenCode Go Luna must use the Responses API")

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()
            self.chat = SimpleNamespace(completions=ForbiddenChatCompletions())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="opencode-go-key",
            openai_base_url="https://opencode.ai/zen/go/v1",
            openai_model="gpt-5.6-luna",
            openai_reasoning_effort="high",
            openai_timeout_sec=360.0,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    result = OpenAICreativeProvider()._json_completion("prompt comum")

    assert result == {"ok": True}
    assert captured == {
        "model": "gpt-5.6-luna",
        "instructions": "Return ONLY the final JSON object. No reasoning, prose, or markdown fences.",
        "input": "prompt comum",
        "text": {"format": {"type": "json_object"}},
        "reasoning": {"effort": "high"},
        "max_output_tokens": 4096,
        "timeout": 360.0,
    }


def test_opencode_go_luna_uses_script_high_reasoning_for_microdrama_draft(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps({"title": "A carta", "full_narration": "A carta voltou."}))

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="opencode-go-key",
            openai_base_url="https://opencode.ai/zen/go/v1",
            openai_model="gpt-5.6-luna",
            openai_reasoning_effort="max",
            llm_script_reasoning_effort="high",
            openai_timeout_sec=360.0,
            llm_json_max_tokens=4096,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    result = OpenAICreativeProvider()._microdrama_json_completion("roteiro", max_tokens=4096)

    assert result["title"] == "A carta"
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["max_output_tokens"] == 4096


def test_opencode_go_luna_uses_responses_api_for_json_array(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps([{"topic": "Lua"}]))

    provider = object.__new__(OpenAICreativeProvider)
    provider.model_name = "gpt-5.6-luna"
    provider.reasoning_effort = "high"
    provider.max_output_tokens = 4096
    provider.timeout_sec = 360.0
    provider.use_responses_api = True
    provider.client = SimpleNamespace(responses=FakeResponses())

    result = provider._json_array_completion("gere uma lista")

    assert result == [{"topic": "Lua"}]
    assert captured["max_output_tokens"] == 4096
    assert captured["reasoning"] == {"effort": "high"}
    assert "text" not in captured


def test_opencode_go_luna_malformed_responses_output_becomes_provider_failure() -> None:
    provider = object.__new__(OpenAICreativeProvider)
    provider.model_name = "gpt-5.6-luna"
    provider.reasoning_effort = "high"
    provider.max_output_tokens = 4096
    provider.timeout_sec = 360.0
    provider.use_responses_api = True
    provider.client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(output_text=None)),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        provider._json_completion("prompt comum")

    assert exc_info.value.provider == "openai_text"


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


def test_minimax_generate_script_batch_uses_individual_calls_not_single_giant_json(monkeypatch) -> None:
    """O lote real deve gerar cada track em chamada individual (como o mock).

    Um único JSON com N roteiros completos estoura max_tokens e produz JSON
    inválido no provider real; tracks individuais reutilizam generate_script.
    """
    from app.providers.llm import MinimaxCreativeProvider

    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "minimax"
    provider.failure_provider_name = "minimax_text"
    provider.settings = SimpleNamespace(target_duration_sec=120)

    generated_angles: list[str] = []
    completion_calls: list[str] = []

    def fake_json_completion(prompt: str, *, max_tokens: int | None = None):
        completion_calls.append(prompt)
        return {
            "title": f"Track gerada {len(completion_calls)}",
            "hook": "A carta mudou tudo.",
            "loop": "Quem escondia a verdade?",
            "body_beats": [
                "A filha leu a carta antes do discurso.",
                "O sócio negou a assinatura.",
                "A gravação mostrava o pai confessando.",
            ],
            "payoff": "A primeira página não acusava o sócio.",
            "ending": "O paletó guardava a confissão do pai.",
            "cta": "Você revelaria o segredo?",
            "full_narration": "A carta mudou tudo. Quem escondia a verdade? A filha leu a carta antes do discurso. O sócio negou a assinatura. A gravação mostrava o pai confessando. A primeira página não acusava o sócio. O paletó guardava a confissão do pai. Você revelaria o segredo?",
            "estimated_duration_sec": 120,
            "key_facts": [],
            "source_fact_ids": [],
            "claim_trace": [],
            "token_count": 60,
            "language": "pt-BR",
            "retention_map": {},
            "story_arc": {"setup": "A carta mudou tudo.", "tension": "Quem escondia a verdade?", "turn": "A primeira página não acusava o sócio.", "consequence": "O paletó guardava a confissão do pai."},
            "visual_opening": {},
            "qa_metrics": {},
            "prompt_version": "test",
        }

    def fake_generate_script(topic_plan):
        generated_angles.append(str(topic_plan.get("angle") or ""))
        payload = fake_json_completion("script")
        payload["qa_metrics"] = {**payload.get("qa_metrics", {}), "source_provider": provider.provider_name}
        return payload

    monkeypatch.setattr(provider, "_json_completion", fake_json_completion)
    monkeypatch.setattr(provider, "generate_script", fake_generate_script)

    batch = provider.generate_script_batch({"angle": "segredo da carta"}, 10)

    tracks = batch["tracks"]
    assert len(tracks) == 10
    assert all(f"variante {i + 1}." in angle for i, angle in enumerate(generated_angles))
    assert "ponto de vista do protagonista destinatário" in generated_angles[0]
    assert "ponto de vista de uma testemunha" in generated_angles[1]
    assert "ponto de vista de quem guardou o segredo" in generated_angles[2]
    assert [int(track["_track_index"]) for track in tracks] == list(range(10))
    assert all(str(track["title"]).endswith(f"(variante {i + 1})") for i, track in enumerate(tracks))
    assert all(track["qa_metrics"]["source_provider"] == "minimax" for track in tracks)


def test_real_text_provider_uses_isolated_microdrama_script_prompt(monkeypatch) -> None:
    from app.providers.llm import MinimaxCreativeProvider

    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "openai"
    provider.failure_provider_name = "openai_text"
    provider.settings = SimpleNamespace(target_duration_sec=120, microdrama_script_max_tokens=8192)
    prompts: list[str] = []
    max_token_budgets: list[int | None] = []

    def fake_json_completion(prompt: str, *, max_tokens: int | None = None):
        prompts.append(prompt)
        max_token_budgets.append(max_tokens)
        return {"title": "A carta", "full_narration": "Roteiro completo", "qa_metrics": {}}

    monkeypatch.setattr(provider, "_json_completion", fake_json_completion)

    provider.generate_script(
        {
            "niche_id": "fiction_microdrama",
            "editorial_mode": "fiction_microdrama",
            "canonical_topic": "A carta da mãe que chegou vinte anos tarde",
            "angle": "A filha descobre quem escondeu as cartas.",
            "retention_map": {"target_duration_sec": 120},
        }
    )

    assert "MICRODRAMA FICCIONAL ORIGINAL" in prompts[0]
    assert "roteiro viral de curiosidades" not in prompts[0]
    assert "288 a 324 palavras" in prompts[0]
    assert "body_beats, juntos, devem somar pelo menos 220 palavras" in prompts[0]
    assert "loop deve aparecer exatamente uma vez em full_narration" in prompts[0]
    assert "NAO RETORNE o JSON" in prompts[0]
    assert "hook_score" in prompts[0]
    assert "clarity_score" in prompts[0]
    assert "information_density_score" in prompts[0]
    assert "ending_strength_score" in prompts[0]
    assert max_token_budgets == [8192]


def test_resilient_generate_script_batch_uses_bounded_parallelism_and_keeps_order() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(microdrama_script_generation_parallelism=2)
    barrier = threading.Barrier(2)
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_generate_script(topic_plan):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        barrier.wait(timeout=1)
        with lock:
            active -= 1
        return {
            "title": topic_plan["angle"],
            "full_narration": f'Narração para {topic_plan["angle"]}',
            "qa_metrics": {},
        }

    provider.generate_script = fake_generate_script

    result = provider.generate_script_batch({"angle": "segredo da carta"}, 4)

    assert max_active == 2
    assert [track["_track_index"] for track in result["tracks"]] == [0, 1, 2, 3]
    titles = [str(track["title"]) for track in result["tracks"]]
    assert all(title.endswith(f"(variante {index})") for index, title in enumerate(titles, start=1))
    assert "ponto de vista do protagonista destinatário" in titles[0]
    assert "ponto de vista de uma testemunha" in titles[1]
    assert "ponto de vista de quem guardou o segredo" in titles[2]


def test_resilient_generate_script_batch_retries_only_failed_tracks_and_keeps_full_batch() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(microdrama_script_generation_parallelism=2)
    calls_by_angle: dict[str, int] = {}

    def fake_generate_script(topic_plan):
        angle = str(topic_plan["angle"])
        calls_by_angle[angle] = calls_by_angle.get(angle, 0) + 1
        if "variante 2." in angle and calls_by_angle[angle] == 1:
            raise ProviderFailure("llm_registry", "transient double-provider failure")
        return {
            "title": angle,
            "full_narration": f"Narração para {angle}",
            "qa_metrics": {},
        }

    provider.generate_script = fake_generate_script

    result = provider.generate_script_batch({"angle": "segredo da carta"}, 4)

    assert [track["_track_index"] for track in result["tracks"]] == [0, 1, 2, 3]
    assert len(calls_by_angle) == 4
    assert next(count for angle, count in calls_by_angle.items() if "variante 2." in angle) == 2
    assert all(count == 1 for angle, count in calls_by_angle.items() if "variante 2." not in angle)


def test_resilient_generate_script_batch_reports_tracks_that_fail_selective_retry() -> None:
    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(microdrama_script_generation_parallelism=2)
    calls_by_angle: dict[str, int] = {}

    def fake_generate_script(topic_plan):
        angle = str(topic_plan["angle"])
        calls_by_angle[angle] = calls_by_angle.get(angle, 0) + 1
        if "variante 2." in angle:
            raise ProviderFailure("llm_registry", "persistent double-provider failure")
        return {"title": angle, "full_narration": f"Narração para {angle}", "qa_metrics": {}}

    provider.generate_script = fake_generate_script

    with pytest.raises(ProviderFailure, match=r"track 2: persistent double-provider failure"):
        provider.generate_script_batch({"angle": "segredo da carta"}, 3)

    assert next(count for angle, count in calls_by_angle.items() if "variante 2." in angle) == 2
    assert all(count == 1 for angle, count in calls_by_angle.items() if "variante 2." not in angle)


def test_resilient_generate_script_batch_falls_back_per_track() -> None:
    class PrimaryProvider:
        provider_name = "openai"
        model_name = "gpt-5.6-luna"

        def generate_script(self, topic_plan):
            if "variante 2." in str(topic_plan.get("angle")):
                raise ProviderFailure("openai", "track 2 failed")
            return {"title": "primary", "full_narration": "Narração primária", "qa_metrics": {}}

    class FallbackProvider:
        provider_name = "deepseek"
        model_name = "deepseek-v4-pro"

        def generate_script(self, topic_plan):
            return {"title": "fallback", "full_narration": "Narração fallback", "qa_metrics": {}}

    provider = object.__new__(ResilientCreativeProvider)
    provider.settings = SimpleNamespace(microdrama_script_generation_parallelism=2)
    setattr(provider, "strict_minimax_validation", False)
    setattr(provider, "primary", PrimaryProvider())
    setattr(provider, "fallback", FallbackProvider())
    setattr(provider, "script_draft_provider", None)
    setattr(
        provider,
        "_script_generation_candidates",
        lambda: [("primary", provider.primary, 150.0), ("fallback", provider.fallback, 150.0)],
    )
    setattr(provider, "_run_primary_with_timeout", lambda fn, timeout_sec: fn())

    result = provider.generate_script_batch({"angle": "microdrama"}, 3)

    assert [track["qa_metrics"]["generation_provider"] for track in result["tracks"]] == [
        "openai",
        "deepseek",
        "openai",
    ]
    assert result["tracks"][1]["qa_metrics"]["script_generation_fallback_used"] is True


def test_sanitize_script_text_removes_dashes_and_non_latin() -> None:
    from app.providers.llm import sanitize_script_text

    payload = {
        "title": "A carta chegou — tarde (变)",
        "hook": "A carta chegou – tarde.",
        "body_beats": ["Beat um.", "中文字符", "Frase normal."],
        "story_arc": {"setup": "A carta chegou — tarde."},
        "retention_map": {"mapped_text": "A carta chegou – tarde."},
        "qa_metrics": {"word_count": "120"},
        "source_fact_ids": ["f1"],
    }
    clean = sanitize_script_text(payload)
    assert "—" not in str(clean)
    assert "–" not in str(clean)
    assert "变" not in str(clean)
    assert "中" not in str(clean)
    assert clean["title"] == "A carta chegou tarde ()"
    assert clean["hook"] == "A carta chegou tarde."
    assert clean["story_arc"]["setup"] == clean["retention_map"]["mapped_text"] == "A carta chegou tarde."
    assert clean["qa_metrics"]["word_count"] == "120"
    assert clean["source_fact_ids"] == ["f1"]


def test_generate_script_sanitizes_provider_payload(monkeypatch) -> None:
    from app.providers.llm import MinimaxCreativeProvider, sanitize_script_text

    provider = object.__new__(MinimaxCreativeProvider)
    provider.settings = SimpleNamespace(
        microdrama_script_max_tokens=4096,
        llm_script_reasoning_effort="high",
        llm_json_max_tokens=4096,
    )
    provider.provider_name = "minimax"
    provider.failure_provider_name = "minimax_text"

    def dirty_microdrama(_prompt: str, *, max_tokens: int):
        return {
            "title": "A carta — chegou (变)",
            "hook": "A carta chegou vinte anos tarde.",
            "body_beats": ["Beat um.", "中"],
            "full_narration": "A carta – chegou vinte anos tarde.",
            "qa_metrics": {},
        }

    monkeypatch.setattr(provider, "_microdrama_json_completion", dirty_microdrama)
    result = provider.generate_script(
        {"niche_id": "fiction_microdrama", "target_duration_sec": 120, "canonical_topic": "tema", "angle": "ângulo"}
    )
    assert "—" not in json.dumps(result, ensure_ascii=False)
    assert "–" not in json.dumps(result, ensure_ascii=False)
    assert "中" not in json.dumps(result, ensure_ascii=False)
    assert result["qa_metrics"]["source_provider"] == "minimax"


def test_repair_script_sanitizes_provider_payload(monkeypatch) -> None:
    from app.providers.llm import MinimaxCreativeProvider

    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "minimax"
    provider.failure_provider_name = "minimax_text"
    provider.settings = SimpleNamespace(llm_json_max_tokens=4096)

    def dirty_repair(prompt: str, *, max_tokens=None):
        return {
            "title": "A carta — chegou",
            "hook": "A carta chegou – tarde.",
            "body_beats": ["Beat.", "中"],
            "full_narration": "A carta chegou tarde.",
            "qa_metrics": {},
        }

    monkeypatch.setattr(provider, "_json_completion", dirty_repair)
    result = provider.repair_script(
        {"title": "t", "hook": "h", "full_narration": "f", "body_beats": ["b"], "qa_metrics": {}},
        ["repeated_clause"],
        {"canonical_topic": "tema", "angle": "ângulo", "niche_id": "fiction_microdrama", "target_duration_sec": 120, "editorial_mode": "fiction_microdrama"},
    )
    assert "—" not in json.dumps(result, ensure_ascii=False)
    assert "–" not in json.dumps(result, ensure_ascii=False)
    assert "中" not in json.dumps(result, ensure_ascii=False)
    assert result["qa_metrics"]["repair_provider"] == "minimax"


def test_luna_max_responses_uses_larger_budget_without_explicit_max_tokens(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps({"title": "A carta", "full_narration": "A carta chegou.", "qa_metrics": {}})
            )

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(
        "app.providers.llm.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="opencode-go-key",
            openai_base_url="https://opencode.ai/zen/go/v1",
            openai_model="gpt-5.6-luna",
            openai_reasoning_effort="max",
            openai_timeout_sec=360.0,
            llm_json_max_tokens=4096,
            llm_topic_batch_max_tokens=12000,
        ),
    )
    monkeypatch.setattr("app.providers.llm.OpenAI", FakeOpenAI)

    provider = OpenAICreativeProvider()
    result = provider._json_completion("Retorne JSON estrito.")

    assert result["title"] == "A carta"
    assert captured["reasoning"] == {"effort": "max"}
    assert captured["max_output_tokens"] == 12000


def test_recompute_script_duration_metrics_derives_from_narration() -> None:
    from app.providers.llm import recompute_script_duration_metrics

    narration = " ".join(["A frase número %d segue aqui." % i for i in range(40)])
    payload = {"full_narration": narration, "estimated_duration_sec": 55.0, "qa_metrics": {"word_count": 999}}
    out = recompute_script_duration_metrics(payload)
    assert out["estimated_duration_sec"] == round(len(narration.split()) / 2.55, 2)
    assert out["qa_metrics"]["word_count"] == len(narration.split())
    assert out["qa_metrics"]["estimated_duration_sec"] == out["estimated_duration_sec"]
    assert out["qa_metrics"]["words_per_second"] > 0


def test_repair_script_recomputes_duration_from_actual_narration(monkeypatch) -> None:
    from app.providers.llm import MinimaxCreativeProvider

    provider = object.__new__(MinimaxCreativeProvider)
    provider.provider_name = "minimax"
    provider.failure_provider_name = "minimax_text"
    provider.settings = SimpleNamespace(llm_json_max_tokens=4096)

    narration = " ".join(["Frase narrativa número %d do roteiro completo." % i for i in range(46)])
    expected_duration = round(len(narration.split()) / 2.55, 2)

    def fake_repair(prompt: str, *, max_tokens=None):
        return {
            "title": "A carta chegou",
            "hook": "A carta chegou.",
            "body_beats": ["Beat um.", "Beat dois."],
            "full_narration": narration,
            "estimated_duration_sec": 55.0,
            "qa_metrics": {"word_count": 999},
        }

    monkeypatch.setattr(provider, "_json_completion", fake_repair)
    result = provider.repair_script(
        {"title": "t", "hook": "h", "full_narration": "f", "body_beats": ["b"], "qa_metrics": {}},
        ["estimated_duration_outside_target_window"],
        {"canonical_topic": "tema", "angle": "ângulo", "niche_id": "fiction_microdrama", "target_duration_sec": 120, "editorial_mode": "fiction_microdrama"},
    )
    assert result["estimated_duration_sec"] == expected_duration
    assert result["qa_metrics"]["word_count"] == len(narration.split())
    assert result["qa_metrics"]["repair_provider"] == "minimax"
