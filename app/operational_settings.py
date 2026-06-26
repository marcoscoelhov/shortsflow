from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal, session_scope
from app.models import OperationalSetting


@dataclass(frozen=True)
class OperationalSettingSpec:
    key: str
    label: str
    group: str
    input_type: str
    options: tuple[tuple[str, str], ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    step: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class OperationalInfoSpec:
    key: str
    label: str
    group: str
    value: str
    description: str | None = None


PROVIDER_OPTIONS = (
    ("disabled", "Desativado"),
    ("openai", "OpenAI"),
    ("deepseek", "DeepSeek"),
    ("qwen", "Qwen"),
    ("minimax", "MiniMax"),
    ("xai", "XAI (Grok)"),
)

TTS_PROVIDER_OPTIONS = (
    ("gemini_tts", "Gemini TTS"),
    ("elevenlabs", "ElevenLabs"),
    ("edge_tts", "Edge TTS (emergencia)"),
)

VISION_VERIFIER_OPTIONS = (
    ("local_openai", "Local OpenAI-compatible"),
    ("minimax_mmx", "MiniMax mmx"),
    ("auto", "Auto"),
    ("disabled", "Desativado"),
)

OPERATIONAL_SETTING_SPECS = (
    OperationalSettingSpec("llm_primary_provider", "LLM principal", "LLM", "select", PROVIDER_OPTIONS),
    OperationalSettingSpec("llm_fallback_provider", "LLM fallback", "LLM", "select", PROVIDER_OPTIONS),
    OperationalSettingSpec("llm_script_draft_provider", "Rascunho de roteiro", "LLM", "select", PROVIDER_OPTIONS),
    OperationalSettingSpec("llm_repair_provider", "Reparo", "LLM", "select", PROVIDER_OPTIONS),
    OperationalSettingSpec(
        "llm_scene_provider",
        "Planejador de cenas (LLM)",
        "LLM",
        "select",
        PROVIDER_OPTIONS,
        description="Cria o plano textual de cenas e prompts; nao gera imagens.",
    ),
    OperationalSettingSpec(
        "llm_gate_judge_provider",
        "Juiz LLM dos gates",
        "LLM",
        "select",
        PROVIDER_OPTIONS,
        description="Provider para juiz editorial (viral, metadata, visual, growth). Recomendado: DeepSeek v4 Flash; use modelos premium só por exceção.",
    ),
    OperationalSettingSpec(
        "llm_gate_judge_model",
        "Modelo do juiz LLM",
        "LLM",
        "text",
        description="Override opcional do modelo do juiz editorial.",
    ),
    OperationalSettingSpec(
        "llm_premium_review_enabled",
        "Usar LLM Pro em exceções",
        "LLM",
        "checkbox",
        description="Permite DeepSeek V4 Pro apenas em revisão premium/final, temas complexos ou escalonamento explícito.",
    ),
    OperationalSettingSpec("llm_premium_review_provider", "LLM Pro excepcional", "LLM", "select", PROVIDER_OPTIONS),
    OperationalSettingSpec("llm_premium_review_model", "Modelo Pro excepcional", "LLM", "text"),
    OperationalSettingSpec("llm_enable_fallback", "Fallback ativo", "LLM", "checkbox"),
    OperationalSettingSpec(
        "background_music_provider",
        "Fonte de trilha",
        "Musica",
        "select",
        (("local_bank", "Banco local"), ("minimax", "MiniMax"), ("auto", "Auto")),
    ),
    OperationalSettingSpec("background_music_enabled", "Trilha ativa", "Musica", "checkbox"),
    OperationalSettingSpec("music_bank_auto_populate", "Popular banco local", "Musica", "checkbox"),
    OperationalSettingSpec("allow_music_api_fallback", "Fallback para API", "Musica", "checkbox"),
    OperationalSettingSpec(
        "vision_verifier_provider",
        "Verificador visual",
        "Visao local",
        "select",
        VISION_VERIFIER_OPTIONS,
        description="Use local_openai com o servico shortsflow-vision para liberar revisao visual automatica.",
    ),
    OperationalSettingSpec("local_vision_base_url", "URL da visao local", "Visao local", "text"),
    OperationalSettingSpec("local_vision_model", "Modelo da visao local", "Visao local", "text"),
    OperationalSettingSpec(
        "vision_verifier_timeout_sec",
        "Timeout da visao",
        "Visao local",
        "number",
        min_value=10,
        max_value=600,
        step="1",
    ),
    OperationalSettingSpec(
        "tts_primary_provider",
        "TTS primario",
        "Narracao",
        "select",
        TTS_PROVIDER_OPTIONS,
        description="Gemini TTS e o padrao; ElevenLabs e equivalente. Edge TTS e emergencia e bloqueia elegibilidade automatizada.",
    ),
    OperationalSettingSpec("youtube_publish_mode", "Modo YouTube", "Publicacao", "select", (("manual", "Manual"), ("api", "API"))),
    OperationalSettingSpec("youtube_api_enabled", "API YouTube ativa", "Publicacao", "checkbox"),
    OperationalSettingSpec("youtube_notify_subscribers", "Notificar inscritos", "Publicacao", "checkbox"),
    OperationalSettingSpec("tiktok_auto_publish_enabled", "Publicar no TikTok", "Publicacao", "checkbox"),
    OperationalSettingSpec(
        "tiktok_privacy_level",
        "Privacidade TikTok",
        "Publicacao",
        "select",
        (
            ("PUBLIC_TO_EVERYONE", "Publico"),
            ("MUTUAL_FOLLOW_FRIENDS", "Amigos mutuos"),
            ("FOLLOWER_OF_CREATOR", "Seguidores"),
            ("SELF_ONLY", "Privado"),
        ),
        description="A API oficial exige que o valor exista nas opcoes retornadas pela conta conectada.",
    ),
    OperationalSettingSpec("tiktok_retropost_daily_limit", "Retroposts TikTok/dia", "Publicacao", "number", min_value=0, max_value=10, step="1"),
    OperationalSettingSpec("automation_daily_timezone", "Fuso da automacao", "Automacao", "text"),
    OperationalSettingSpec("automation_daily_run_time", "Horario do ciclo", "Automacao", "time"),
    OperationalSettingSpec("automation_publish_time", "Horario de publicacao", "Automacao", "time"),
    OperationalSettingSpec("automation_fill_window_days", "Janela da agenda", "Automacao", "number", min_value=1, max_value=60, step="1"),
    OperationalSettingSpec("automation_max_generation_attempts", "Tentativas de geracao", "Automacao", "number", min_value=1, max_value=10, step="1"),
    OperationalSettingSpec("automation_max_publish_attempts_per_job", "Tentativas de upload", "Automacao", "number", min_value=1, max_value=10, step="1"),
    OperationalSettingSpec("automation_score_threshold", "Score minimo", "Automacao", "number", min_value=0, max_value=1, step="0.01"),
    OperationalSettingSpec(
        "performance_collection_enabled",
        "Coleta de performance",
        "Crescimento",
        "checkbox",
        description="Controla apenas a leitura recorrente de Analytics; nao pausa criacao nem publicacao automatizada.",
    ),
    OperationalSettingSpec(
        "performance_sync_active_window_days",
        "Janela ativa",
        "Crescimento",
        "number",
        min_value=1,
        max_value=365,
        step="1",
    ),
    OperationalSettingSpec(
        "performance_sync_archive_window_days",
        "Janela semanal",
        "Crescimento",
        "number",
        min_value=1,
        max_value=365,
        step="1",
    ),
    OperationalSettingSpec(
        "performance_sync_batch_limit",
        "Lote de coleta",
        "Crescimento",
        "number",
        min_value=1,
        max_value=100,
        step="1",
    ),
    OperationalSettingSpec(
        "competitive_scout_automation_enabled",
        "Scout competitivo automático",
        "Crescimento",
        "checkbox",
        description="Roda scout, síntese e avanço de experimentos dentro do ciclo diário de automação.",
    ),
    OperationalSettingSpec(
        "competitive_scout_auto_approve_profiles",
        "Autoaprovar perfis do scout",
        "Crescimento",
        "checkbox",
        description="Desligado por padrão para manter aprovação humana antes de um perfil orientar Jobs.",
    ),
    OperationalSettingSpec(
        "competitive_scout_auto_start_experiments",
        "Autoiniciar experimentos",
        "Crescimento",
        "checkbox",
        description="Desligado por padrão; ligue apenas quando perfis autoaprovados puderem entrar em experimento sem revisão.",
    ),
    OperationalSettingSpec(
        "competitive_scout_auto_promote_profiles",
        "Autopromover vencedores",
        "Crescimento",
        "checkbox",
        description="Desligado por padrão; promoção de perfil deve ser decisão humana após Analytics próprio.",
    ),
    OperationalSettingSpec(
        "competitive_scout_llm_analysis_enabled",
        "Analise LLM no scout",
        "Crescimento",
        "checkbox",
        description="Quando desligado, o scout usa apenas heuristica local para evitar custo de LLM.",
    ),
    OperationalSettingSpec(
        "competitive_scout_global_enabled",
        "Scout global",
        "Crescimento",
        "checkbox",
        description="Expande buscas textuais para regioes fortes em Shorts; canais aprovados continuam sem filtro regional.",
    ),
    OperationalSettingSpec(
        "competitive_scout_reference_batch_limit",
        "Lote do scout",
        "Crescimento",
        "number",
        min_value=1,
        max_value=100,
        step="1",
    ),
    OperationalSettingSpec(
        "competitive_scout_max_query_region_pairs",
        "Buscas globais max.",
        "Crescimento",
        "number",
        min_value=1,
        max_value=100,
        step="1",
        description="Limite de pares busca/regiao por rodada para controlar quota da YouTube Data API.",
    ),
    OperationalSettingSpec(
        "competitive_scout_max_analyses_per_run",
        "Analises por rodada",
        "Crescimento",
        "number",
        min_value=1,
        max_value=100,
        step="1",
        description="Limite de candidatos enviados para analise depois dos filtros de views, duracao e maturidade.",
    ),
    OperationalSettingSpec(
        "competitive_scout_min_profile_references",
        "Refs por perfil",
        "Crescimento",
        "number",
        min_value=1,
        max_value=100,
        step="1",
    ),
    OperationalSettingSpec(
        "competitive_scout_queries",
        "Buscas do scout",
        "Crescimento",
        "textarea",
        description="Uma busca por linha. Usada quando nao ha canal de referencia aprovado ou para complementar descoberta.",
    ),
    OperationalSettingSpec(
        "competitive_scout_regions",
        "Regioes do scout",
        "Crescimento",
        "textarea",
        description="Codigos ISO de pais por linha, virgula ou espaco. Ex.: IN, US, ID, BR, MX.",
    ),
)

OPERATIONAL_INFO_SPECS = (
    OperationalInfoSpec(
        "image_generation_provider",
        "Gerador de imagens",
        "Imagem",
        "MiniMax",
        "Gera os assets visuais no passo Imagens. Hoje nao ha outro provider real selecionavel.",
    ),
)

OPERATIONAL_SETTING_KEYS = {spec.key for spec in OPERATIONAL_SETTING_SPECS}
_SPECS_BY_KEY = {spec.key: spec for spec in OPERATIONAL_SETTING_SPECS}
_CHECKBOX_KEYS = {spec.key for spec in OPERATIONAL_SETTING_SPECS if spec.input_type == "checkbox"}
_SENSITIVE_KEY_PARTS = ("api_key", "secret", "token", "oauth", "password")


def load_operational_settings(session: Session) -> dict[str, Any]:
    rows = session.scalars(select(OperationalSetting)).all()
    overrides: dict[str, Any] = {}
    for row in rows:
        if row.key not in OPERATIONAL_SETTING_KEYS:
            continue
        payload = row.value or {}
        if "value" in payload:
            overrides[row.key] = payload["value"]
    return overrides


def build_operational_settings_context(settings: Settings) -> dict[str, Any]:
    with SessionLocal() as session:
        saved_keys = set(load_operational_settings(session))
    groups: list[dict[str, Any]] = []
    for group_name in ("LLM", "Imagem", "Musica", "Narracao", "Publicacao", "Automacao", "Crescimento"):
        fields = []
        for spec in OPERATIONAL_SETTING_SPECS:
            if spec.group != group_name:
                continue
            value = getattr(settings, spec.key)
            fields.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "input_type": spec.input_type,
                    "value": value,
                    "checked": bool(value),
                    "options": [{"value": option_value, "label": label} for option_value, label in spec.options],
                    "min": spec.min_value,
                    "max": spec.max_value,
                    "step": spec.step,
                    "saved": spec.key in saved_keys,
                    "description": spec.description,
                }
            )
        for spec in OPERATIONAL_INFO_SPECS:
            if spec.group != group_name:
                continue
            fields.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "input_type": "readonly",
                    "value": "Mock local" if settings.use_mock_providers and spec.key == "image_generation_provider" else spec.value,
                    "checked": False,
                    "options": [],
                    "min": None,
                    "max": None,
                    "step": None,
                    "saved": False,
                    "description": spec.description,
                }
            )
        if not fields:
            continue
        groups.append({"name": group_name, "fields": fields})
    return {"groups": groups, "saved_count": len(saved_keys)}


def apply_operational_settings(settings: Settings) -> None:
    with SessionLocal() as session:
        updates = load_operational_settings(session)
    if not updates:
        return
    validated = validate_operational_update(settings, updates)
    for key, value in validated.items():
        setattr(settings, key, value)


def save_operational_settings(settings: Settings, raw_values: dict[str, Any]) -> dict[str, Any]:
    validated = validate_operational_update(settings, raw_values)
    with session_scope() as session:
        for key, value in validated.items():
            row = session.get(OperationalSetting, key)
            payload = {"value": value}
            if row is None:
                session.add(OperationalSetting(key=key, value=payload))
            else:
                row.value = payload
    for key, value in validated.items():
        setattr(settings, key, value)
    return validated


def clear_operational_settings(settings: Settings) -> None:
    with session_scope() as session:
        for row in session.scalars(select(OperationalSetting)).all():
            session.delete(row)
    env_settings = Settings()
    for key in OPERATIONAL_SETTING_KEYS:
        setattr(settings, key, getattr(env_settings, key))


def parse_operational_form_values(form_values: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for spec in OPERATIONAL_SETTING_SPECS:
        if spec.input_type == "checkbox":
            parsed[spec.key] = str(form_values.get(spec.key, "")).lower() in {"1", "true", "on", "yes"}
            continue
        raw_value = form_values.get(spec.key)
        if raw_value is None:
            continue
        parsed[spec.key] = str(raw_value).strip()
    return parsed


def validate_operational_update(settings: Settings, values: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(values) - OPERATIONAL_SETTING_KEYS)
    if unknown:
        raise ValueError(f"configuracao operacional desconhecida: {', '.join(unknown)}")
    for key in values:
        if any(part in key for part in _SENSITIVE_KEY_PARTS):
            raise ValueError(f"{key} nao pode ser salvo como configuracao operacional")
    normalized = {key: _coerce_value(_SPECS_BY_KEY[key], value) for key, value in values.items()}
    _validate_operational_semantics(normalized)
    candidate_payload = settings.model_dump(mode="python")
    candidate_payload.update(normalized)
    validated_settings = Settings.model_validate(candidate_payload)
    return {key: getattr(validated_settings, key) for key in normalized}


def _coerce_value(spec: OperationalSettingSpec, value: Any) -> Any:
    if spec.input_type == "checkbox":
        return bool(value)
    if spec.input_type == "number":
        if value == "":
            raise ValueError(f"{spec.label} nao pode ficar vazio")
        number = float(value)
        if spec.step == "1":
            return int(number)
        return number
    cleaned = str(value).strip()
    if not cleaned:
        if spec.key == "llm_gate_judge_model":
            return None
        raise ValueError(f"{spec.label} nao pode ficar vazio")
    allowed_options = {option_value for option_value, _label in spec.options}
    if allowed_options and cleaned not in allowed_options:
        raise ValueError(f"{spec.label} invalido: {cleaned}")
    return cleaned


def _validate_operational_semantics(values: dict[str, Any]) -> None:
    timezone = values.get("automation_daily_timezone")
    if timezone:
        try:
            ZoneInfo(str(timezone))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"fuso da automacao invalido: {timezone}") from exc
    for key in ("automation_daily_run_time", "automation_publish_time"):
        if key in values:
            _validate_time_string(key, str(values[key]))
    active_window = values.get("performance_sync_active_window_days")
    archive_window = values.get("performance_sync_archive_window_days")
    if active_window is not None and archive_window is not None and int(active_window) > int(archive_window):
        raise ValueError("janela ativa de performance nao pode ser maior que a janela semanal")


def _validate_time_string(key: str, value: str) -> None:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{key} deve usar HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{key} deve usar horario valido")
