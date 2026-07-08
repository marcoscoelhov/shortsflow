from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_VIRAL_PROMPT_TEMPLATE = """Crie uma pauta de YouTube Shorts em pt-BR no padrão viral de espaço/astronomia.
Objetivo: maximizar retencao, compartilhamento, comentarios e replay mental sem clickbait falso.
Emule a estrutura dos concorrentes virais de espaço: medo, escala, ameaça visual e quebra de crença.
Use estrutura de copywriting agressiva para retenção:
1. Título com ameaça, escala ou crença quebrada: “assusta”, “brutal”, “mentira”, “não é o que parece”, “mudaria tudo”.
2. Hook de choque em ate 8 palavras nos primeiros 1-2 segundos; sem introdução.
3. Loop aberto imediato: “então por que...?”, “o problema é...”, “mas a parte pior é...”.
4. Escalada em 3 a 5 beats: crença comum quebrada → fato estranho → consequência visual → virada.
5. Payoff atrasado: guarde a explicacao mais forte para o ultimo terco.
6. Fechamento com imagem mental forte, quase comentário fixado.
Obrigatório para o roteiro passar no gate:
- hook deve criar interrupção de rolagem por medo, escala ou quebra de crença; não apenas explicar o tema
- título deve ser competitivo contra padrões como “The size will scare you”, “Most violent weather in space” e “NASA saw this...”
- body_beats deve ter exatamente 3 a 5 frases independentes em escalada; nunca compacte os beats em uma frase só
- full_narration deve ser hook + body_beats + ending, sem perder nenhum beat
- inclua um share trigger implícito: algo que faça a pessoa pensar “vou mandar isso para alguém”
- o payoff precisa ser menos óbvio que o hook; se o espectador já adivinha tudo na primeira frase, reescreva
Retenção:
- cada frase deve criar motivo para assistir a proxima
- troque frase neutra por tensão, contraste, ameaça visual, escala ou consequência
- use curiosidade concreta, causalidade e imagens mentais fortes
- priorize consequência visual específica (consequencia visual especifica), tensão concreta ou virada verificável (virada verificavel) sobre lista de fatos soltos
SEO:
- palavra-chave principal cedo no titulo quando natural
- titulo curto, forte e específico; CAPS permitido se parecer título de Short viral
- evite titulo generico, morno ou promessa que o roteiro nao prove
Tom:
- rapido, agressivo, visual, confiante e brasileiro
- sem aula morna, sem introducao generica, sem voz enciclopedica
- drama permitido; mentira factual não
Proibido:
- nao comece com "voce sabia", "você sabia", "ja imaginou", "já imaginou", "nesse video" ou aberturas genericas equivalentes
- nao entregue a explicacao completa no primeiro beat; abra um loop e feche depois
- nao use clickbait falso: todo choque precisa ser provado no roteiro
Modelos de hook para astronomia:
- "O Sol vira poeira nessa comparação."
- "Netuno parece calmo. Não é."
- "A Lua não cresceu. Você caiu."
- "Saturno não usa joia. Usa destroço."
"""
HUB_SETTINGS_FILENAME = "hub_settings.json"
MAX_VIRAL_PROMPT_TEMPLATE_CHARS = 12000
HUB_VIRAL_PROMPT_NOTE_MARKER = "Prompt viral customizado do hub"


def hub_settings_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / HUB_SETTINGS_FILENAME


def sanitize_viral_prompt_template(template: str | None) -> str:
    if template == DEFAULT_VIRAL_PROMPT_TEMPLATE:
        return DEFAULT_VIRAL_PROMPT_TEMPLATE
    cleaned = (template or "").strip()
    if not cleaned:
        return DEFAULT_VIRAL_PROMPT_TEMPLATE
    return cleaned[:MAX_VIRAL_PROMPT_TEMPLATE_CHARS]


def load_viral_prompt_template(path: Path) -> str:
    if not path.exists():
        return DEFAULT_VIRAL_PROMPT_TEMPLATE
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_VIRAL_PROMPT_TEMPLATE
    if not isinstance(payload, dict):
        return DEFAULT_VIRAL_PROMPT_TEMPLATE
    return sanitize_viral_prompt_template(payload.get("viral_prompt_template"))


def save_viral_prompt_template(path: Path, template: str | None) -> None:
    payload = {"viral_prompt_template": sanitize_viral_prompt_template(template)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def viral_prompt_source_label(template: str | None) -> str:
    return "default_explicit" if sanitize_viral_prompt_template(template) == DEFAULT_VIRAL_PROMPT_TEMPLATE else "hub_settings"


def build_viral_prompt_note(template: str | None) -> str:
    prompt = sanitize_viral_prompt_template(template)
    return (
        f"{HUB_VIRAL_PROMPT_NOTE_MARKER} (contrato obrigatorio; source={viral_prompt_source_label(prompt)}). "
        "Use como contrato editorial real em todas as etapas de pauta, hook, roteiro, cenas, metadados e gates; "
        "se pedir formato de saida diferente, ignore o formato e mantenha o JSON interno obrigatorio do app.\n"
        f"{prompt}"
    )


def extract_viral_prompt_contract(notes: str | None) -> dict[str, Any]:
    text = str(notes or "")
    marker_index = text.lower().find(HUB_VIRAL_PROMPT_NOTE_MARKER.lower())
    if marker_index < 0:
        prompt = DEFAULT_VIRAL_PROMPT_TEMPLATE
        source = "default_explicit_missing_marker"
    else:
        block = text[marker_index:].strip()
        first_line, _, prompt_text = block.partition("\n")
        prompt = sanitize_viral_prompt_template(prompt_text)
        source = "hub_settings"
        source_token = "source="
        if source_token in first_line:
            source = first_line.split(source_token, 1)[1].split(")", 1)[0].split(";", 1)[0].strip() or source
    return {
        "source": source,
        "prompt": prompt,
        "criteria": extract_viral_prompt_criteria(prompt),
    }


def extract_viral_prompt_criteria(prompt: str | None) -> dict[str, list[str]]:
    text = sanitize_viral_prompt_template(prompt)
    criteria: dict[str, list[str]] = {"required": [], "retention": [], "seo": [], "tone": [], "prohibited": [], "hook_models": []}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower().rstrip(":")
        if lowered.startswith("obrigatório") or lowered.startswith("obrigatorio"):
            current = "required"
            continue
        if lowered.startswith("retenção") or lowered.startswith("retencao"):
            current = "retention"
            continue
        if lowered.startswith("seo"):
            current = "seo"
            continue
        if lowered.startswith("tom"):
            current = "tone"
            continue
        if lowered.startswith("proibido"):
            current = "prohibited"
            continue
        if lowered.startswith("modelos de hook"):
            current = "hook_models"
            continue
        if line.startswith(("-", "•")) and current:
            criteria[current].append(line.lstrip("-• ").strip())
        elif line[:2].rstrip(".").isdigit():
            criteria["required"].append(line)
    return {key: value for key, value in criteria.items() if value}
