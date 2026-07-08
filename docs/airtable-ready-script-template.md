# Template Airtable → ShortsFlow ready_script_bank

Use este padrão para a automação do ChatGPT preencher a tabela `Roteiros` do Airtable.

## Campos obrigatórios

| Campo Airtable | Tipo sugerido | Regra |
|---|---:|---|
| `Título` | Single line text | CAPS, forte, medo/escala/quebra de crença, sem promessa falsa |
| `Hook` | Single line text | choque em até ~8 palavras; não começar com “você sabia” |
| `Loop` | Single line text | pergunta/tensão que obriga continuar |
| `Beat 1` | Long text | crença comum quebrada |
| `Beat 2` | Long text | fato estranho verificável |
| `Beat 3` | Long text | consequência visual/emocional |
| `Beat 4` | Long text | virada que prepara payoff |
| `Payoff` | Long text | resolução forte do loop |
| `Fechamento` | Long text | frase memorável/compartilhável |
| `Hashtags` | Single line text | `#espaco #astronomia #[tema] #universo #shorts` |
| `Status` | Single select | `Novo` para o ShortsFlow puxar; depois ele marca `Imported` |

`Beat 5` e `Beat 6` podem existir, mas prefira 4 beats para encaixe limpo no banco.

## Prompt para ChatGPT gerar linhas compatíveis

```md
Você escreve roteiros para YouTube Shorts PT-BR de curiosidades espaciais no padrão viral agressivo do ShortsFlow.
Gere {N} roteiros em formato de tabela, com as colunas EXATAS abaixo:

Título | Hook | Loop | Beat 1 | Beat 2 | Beat 3 | Beat 4 | Payoff | Fechamento | Hashtags | Status

Regras obrigatórias:
- Status sempre deve ser: Novo
- Título em CAPS, forte, curto, com medo/escala/quebra de crença. Ex: “NETUNO PARECE CALMO. É VIOLENTO.”
- Hook em até 8 palavras, direto, sem introdução.
- Loop deve abrir uma pergunta/tensão clara.
- Beat 1 quebra uma crença comum.
- Beat 2 traz fato estranho verificável.
- Beat 3 mostra consequência visual ou emocional.
- Beat 4 traz a virada que prepara o payoff.
- Payoff resolve o loop sem ficar didático.
- Fechamento precisa ser memorável, quase comentário fixado.
- Hashtags no formato: #espaco #astronomia #[tema] #universo #shorts
- Não usar “você sabia”, “já imaginou”, “nesse vídeo”.
- Não inventar número, descoberta, recorde ou data.
- Usar fatos conservadores de NASA/ESA/JPL/observatórios/universidades.
- Não usar Wikipedia como fonte.
- Não repetir fórmulas de título.

Gere somente a tabela final. Não inclua explicações antes ou depois.
```

## Observação operacional

O cron diário do ShortsFlow busca somente registros com `Status = Novo`. Os 10 roteiros já existentes foram marcados como `Imported` para não duplicar o banco local.
