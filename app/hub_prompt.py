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
FOCO OBRIGATÓRIO DO CANAL (dados de performance 2026-08):
- Priorize TEMAS DE MEMBROS do SISTEMA SOLAR (planetas, Lua, Sol, cometas/asteroides/meteoros do sistema) com HOOK DE PARADOXO VISUAL imediato: o objeto é familiar, mas o que parece não é.
- Exemplos que viralizaram no canal: Urano "parece que caiu", Netuno "parece oceano mas é armadilha", Marte "não é vermelho por ser quente", Saturno "não tem anéis, tem um acidente em órbita".
- EVITE eixo fora do foco que zerou views: exoplanetas (WASP-76b etc.), galáxias/colisão da Via Láctea, matéria escura, astrofísica abstrata, história humana, curiosidades da vida terrestre (sangue de caranguejo, Pompeia, Anticítera).
- Não repita o sufixo morto "o detalhe estranho antes de você notar" / "o detalhe que quase ninguém percebe" — isso derruba views (banido por auditaría 2026-06, regressou).
CTA DE COMENTÁRIO (obrigatório no soft cta e no final do full_narration, últimos 8s):
- Feche com uma PERGUNTA polarizante de opinião do nicho que convide a comentar, ex.: "Qual planeta te dá mais medo?" / "Saturno te mancou na escola também?" / "Você saberia dizer qual é o mais estranho?"
- Nunca feche só com "manda pra quem..." (share trigger) sem também abrir pergunta de comentário; comentário é o motor de distribuição do Shorts.
- Pergunta deve ser de opinião (sem resposta certa única) para maximizar comentários, não trivia de fato.
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
ESTRUTURA VENCEDORA OBRIGATÓRIA (de research winning-viral-structure-cosmos-shorts):
- Hook: "E se [extrema cósmica] [familiar lugar/objeto]?" ou "[Objeto] vs [Anomalia]"
- Beats: escala + consequência no familiar + paradoxo + payoff com retorno ao hook visual
- Visual: scale_comparison, familiar_contrast, payoff_pulse, high-fidelity CGI
- Loop/payoff explícito obrigatório
Modelos de hook para astronomia:
- "O Sol vira poeira nessa comparação."
- "Netuno parece calmo. Não é."
- "A Lua não cresceu. Você caiu."
- "Saturno não usa joia. Usa destroço."
"""
MICRODRAMA_VIRAL_PROMPT_TEMPLATE = """Crie pautas e roteiros de YouTube Shorts em pt-BR para o canal Jarvis, dedicado a MICRODRAMAS BRASILEIROS DE SUSPENSE EMOCIONAL.

POSICIONAMENTO DO CANAL
Histórias ficcionais originais, curtas e cinematográficas, sobre segredos, vingança, escolhas impossíveis e mistérios brasileiros. Cada Short deve funcionar sozinho, mesmo quando pertencer a um arco curto.

PILARES EDITORIAIS
- Traição, vingança, injustiça e segredo familiar, com consequência emocional e virada menos óbvia que o hook.
- Decisões impossíveis e dilemas morais, com duas opções compreensíveis e uma pista que muda o julgamento.
- Folclore brasileiro e suspense sobrenatural psicológico, sem gore e sem apresentar lenda como evento real.

ORIGINALIDADE E MONETIZAÇÃO
- Escreva trama, personagens, situações e falas do zero.
- Não adapte nem resuma Reddit, novelas, filmes, livros, notícias ou vídeos de terceiros.
- Varie conflito, motivação, progressão, payoff, estrutura visual e desfecho; trocar apenas nomes não conta.
- Apresente claramente como ficção e não faça cena inventada parecer notícia ou depoimento real.
- Sem gore, violência gráfica, exploração sexual, crianças em risco como espetáculo ou instruções perigosas.

FORMATO
- Duração alvo de 40 segundos, dentro da faixa de 35 a 55 segundos.
- Hook em até 8 palavras nos primeiros 1 a 2 segundos, com o conflito compreensível imediatamente.
- Use 3 a 5 beats em escalada causal: conflito → pista → escolha/ação → consequência → virada.
- Guarde a revelação mais forte para o último terço e entregue um mini-payoff no próprio Short.
- Termine com pergunta específica sobre decisão, culpa, segredo ou consequência; não use CTA genérica.

DIREÇÃO VISUAL E TOM
- O primeiro quadro mostra o conflito, objeto ou escolha central sem revelar antecipadamente o payoff.
- Preserve continuidade de local, personagens, roupas, objetos e direção espacial entre cenas.
- Cada beat muda a informação visual; texto legível deve ser overlay, nunca letras geradas na imagem.
- Use título curto, específico e emocional e tom brasileiro, direto, humano e cinematográfico.
- Proibido começar com “você sabia”, “já imaginou”, “nesse vídeo” ou equivalentes.

CRITÉRIO DE REJEIÇÃO
Rejeite e reescreva antes de gerar mídia se a história repetir o molde de outro episódio, se o payoff estiver óbvio no hook, se depender de contexto anterior, se parecer conteúdo massificado por IA ou se a ficção não estiver claramente identificada.
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


def build_viral_prompt_note(template: str | None, *, source: str | None = None) -> str:
    prompt = sanitize_viral_prompt_template(template)
    return (
        f"{HUB_VIRAL_PROMPT_NOTE_MARKER} (contrato obrigatorio; source={source or viral_prompt_source_label(prompt)}). "
        "Use como contrato editorial real em todas as etapas de pauta, hook, roteiro, cenas, metadados e gates; "
        "se pedir formato de saida diferente, ignore o formato e mantenha o JSON interno obrigatorio do app.\n"
        f"{prompt}"
    )


def build_niche_viral_prompt_note(niche_id: str | None, template: str | None) -> str:
    prompt = MICRODRAMA_VIRAL_PROMPT_TEMPLATE if niche_id == "fiction_microdrama" else template
    source = "niche_default" if niche_id == "fiction_microdrama" else None
    return build_viral_prompt_note(prompt, source=source)


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
