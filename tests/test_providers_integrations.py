from tests.e2e_support import *  # noqa: F403


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
    assert result["qa_metrics"]["repair_provider"] == "deepseek"

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

def test_openai_provider_uses_responses_api_with_json_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
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

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

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
    result = provider.generate_script({"canonical_topic": "cafeina e sono", "title_candidates": ["Cafe mascara a fadiga"]})

    assert captured["client_kwargs"]["api_key"] == "openai-key"
    assert captured["model"] == "gpt-5.4"
    assert captured["text"] == {"format": {"type": "json_object"}}
    assert "meta editorial: retenção máxima, replay, compartilhamento orgânico e espanto genuíno" in str(captured["input"])
    assert "body_beats equivale aos Beats em escalada" in str(captured["input"])
    assert result["qa_metrics"]["source_provider"] == "openai"

def test_openai_provider_topic_prompt_uses_hub_viral_ruler(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
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

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

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
    assert captured["text"] == {"format": {"type": "json_object"}}
    assert "Crie pautas de curiosidades globais para YouTube Shorts em pt-BR." in str(captured["input"])
    assert "Loop: pergunta mental de tensão que só fecha no payoff" in str(captured["input"])
    assert "exceto search_terms quando pesquisa factual em ingles ajudar" in str(captured["input"])
    assert "search_terms em ingles para pesquisa factual" in str(captured["input"])
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
