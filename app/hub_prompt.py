from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_VIRAL_PROMPT_TEMPLATE = """Crie uma pauta de curiosidades para YouTube Shorts em pt-BR.
Objetivo: maximizar retencao, compartilhamento, comentarios e replay mental sem clickbait falso.
Use estrutura de copywriting agressiva para retenção:
1. Hook de choque nos primeiros 1-2 segundos: contraste, ameaça cognitiva, paradoxo ou fato que pareça impossivel mas seja verdadeiro.
2. Loop aberto imediato: plante uma pergunta mental que so sera fechada no final.
3. Promessa clara e especifica: diga/implique por que a pessoa precisa continuar assistindo agora.
4. Escalada em 3 a 5 beats: cada frase deve revelar algo mais forte, mais estranho ou mais visual que a anterior.
5. Payoff atrasado: guarde a explicacao mais surpreendente para o ultimo terco.
6. Fechamento com recontextualizacao forte ou loop: termine fazendo o espectador repensar o primeiro hook, com frase memoravel.
Retenção:
- cada frase deve criar motivo para assistir a proxima
- evite frase neutra, didatica ou enciclopedica quando puder virar tensão, contraste ou consequência
- use curiosidade concreta, causalidade e imagens mentais fortes
- priorize consequencia visual especifica, tensão concreta ou virada verificavel sobre lista de fatos soltos
SEO:
- palavra-chave principal cedo no titulo quando natural
- titulo com curiosidade especifica, 45 a 75 caracteres quando possivel
- evite titulo generico, caixa alta exagerada e promessa que o roteiro nao prove
Tom:
- rapido, intrigante, confiante e mais agressivo em retenção
- linguagem brasileira natural, com tensão e ritmo de Shorts
- sem enrolacao, sem aula morna, sem introducao generica
Proibido:
- nao comece com "voce sabia", "você sabia", "ja imaginou", "já imaginou", "nesse video" ou aberturas genericas equivalentes
- o hook deve abrir direto com contraste, consequencia, conflito ou fato especifico
- nao entregue a explicacao completa no primeiro beat; abra um loop e feche depois
- nao use clickbait falso: todo choque precisa ser provado no roteiro"""
HUB_SETTINGS_FILENAME = "hub_settings.json"
MAX_VIRAL_PROMPT_TEMPLATE_CHARS = 12000


def hub_settings_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / HUB_SETTINGS_FILENAME


def sanitize_viral_prompt_template(template: str | None) -> str:
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
