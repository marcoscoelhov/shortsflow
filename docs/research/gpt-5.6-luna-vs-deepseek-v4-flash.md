# GPT-5.6 Luna vs. DeepSeek-V4-Flash-0731 no ShortsFlow

**Data da pesquisa:** 2026-07-31  
**Escopo:** fontes primárias atuais, complementadas por micro A/B real no mesmo dia; sem alteração de configuração.

> **Status historico:** esta pesquisa registra a hipotese anterior de manter DeepSeek nos gates baratos. Mais
> tarde em 2026-07-31, a decisao operacional adotou Luna `high` para geracao/planejamento e Grok 4.5 `high`
> como juiz independente. Consulte o ADR 0002; as recomendacoes abaixo continuam evidencia para um benchmark
> futuro, nao configuracao vigente.

## Resumo executivo

- **“GPT-5.6 Luna” é um nome oficial da OpenAI**, não apenas um apelido encontrado em documentação de terceiros. A página oficial de modelos identifica o modelo como **GPT-5.6 Luna** e o identificador de API como **`gpt-5.6-luna`**. O nome amigável pode aparecer como “GPT-5.6 Luna”; para API deve-se usar o ID técnico. Não encontrei fonte oficial que chame Luna de “alias de provider”.
- Para o pipeline atual do ShortsFlow, **DeepSeek-V4-Flash-0731 continua sendo a opção de menor custo**, especialmente para gates e reparos repetitivos. A documentação DeepSeek expõe o modelo por `deepseek-v4-flash`; a versão servida atualmente é **DeepSeek-V4-Flash-0731**, sem exigir trocar o nome lógico.
- **Luna tem a vantagem documental mais clara para JSON estrito de schema, tool calling e fluxos multi-etapa**, pois a OpenAI documenta Structured Outputs (`json_schema`, `strict: true`) e uma lista ampla de ferramentas. Isso pode reduzir risco de reparo/parser para roteiro, contrato visual e plano de cenas, mas não justifica automaticamente pagar o prêmio em todos os gates; a qualidade relativa em pt-BR precisa ser medida.
- Preço por 1M tokens: Luna **US$0,20 input / US$1,20 output / US$0,02 cached input**; Flash **US$0,14 input miss / US$0,28 output / US$0,0028 cache hit**. Portanto, Luna custa aproximadamente **1,43× no input não cacheado, 4,29× no output e 7,14× no input cacheado**. A diferença de custo é pequena no input e grande no output.
- Recomendação após o micro A/B: **não migrar tudo**, mas testar migração parcial com **Luna `high` para geração/planejamento** e DeepSeek nos gates baratos. Luna `none/low` falhou a restrição de tamanho no briefing comparável; `medium/high/max` passaram, e `high` entregou o melhor equilíbrio observado entre aderência, narrativa e latência.

## Identidade, endpoint e nomenclatura

| Item | GPT-5.6 Luna | DeepSeek-V4-Flash-0731 |
|---|---|---|
| Nome oficial documentado | GPT-5.6 Luna | DeepSeek-V4-Flash-0731 |
| ID usado na API | `gpt-5.6-luna` | `deepseek-v4-flash` |
| Endpoint/forma | OpenAI Responses API e Chat Completions | OpenAI-compatible Chat Completions em `https://api.deepseek.com`; Responses API também suportada pelo Flash |
| Observação de alias | “Luna” é o nome oficial da variante; `gpt-5.6-luna` é o ID. Não há evidência oficial de que seja um alias de provider. | O ID estável `deepseek-v4-flash` aponta para a versão atual `DeepSeek-V4-Flash-0731`; a própria DeepSeek diz que o método de chamada não muda. |

Fontes primárias: [OpenAI — página do modelo GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [DeepSeek — primeiro uso da API](https://api-docs.deepseek.com/), [DeepSeek — changelog de 2026-07-31](https://api-docs.deepseek.com/updates/).

### Confirmação sobre “alias do provider”

A documentação oficial da OpenAI trata **GPT-5.6 Luna** como produto/modelo e lista explicitamente o snapshot/ID `gpt-5.6-luna`. Assim:

1. **Nome oficial:** sim, “GPT-5.6 Luna”.
2. **Identificador/API:** `gpt-5.6-luna`.
3. **Alias de provider:** não confirmado e não necessário para a API OpenAI; “Luna” não deve ser convertido em outro ID sem documentação do provider que estiver fazendo proxy.
4. Se a string aparecer em uma UI ou em um provider compatível, a integração deve verificar o mapeamento desse provider. A fonte OpenAI não documenta que o nome seja um alias interno de outro modelo.

## Capacidades técnicas relevantes

### GPT-5.6 Luna

A página oficial informa:

- janela de contexto de **1.050.000 tokens**;
- máximo de saída de **128.000 tokens**;
- entrada de texto e imagem, saída de texto;
- streaming e function calling;
- Structured Outputs: **suportado**;
- endpoints Chat Completions e Responses;
- ferramentas no Responses API: web search, file search, image generation, code interpreter, hosted shell, apply patch, skills, computer use, MCP e tool search;
- limite publicado por tier (RPM/TPM): Tier 1 **500 RPM / 500.000 TPM**, Tier 2 **5.000 / 2.000.000**, Tier 3 **5.000 / 4.000.000**, Tier 4 **10.000 / 10.000.000**, Tier 5 **30.000 / 180.000.000**. O tier efetivo da conta precisa ser verificado no projeto OpenAI; não há acesso de conta feito nesta pesquisa.

O guia de raciocínio da OpenAI documenta `reasoning.effort` para GPT-5.6 como:

- `none`
- `low`
- `medium`
- `high`
- `xhigh`
- `max`

O guia também mostra `reasoning.summary="auto"` para solicitar resumo de raciocínio, sem expor cadeia de pensamento. Para o ShortsFlow, não pedir raciocínio no JSON: exigir apenas o objeto final e validar localmente.

Structured Outputs permite schema JSON estrito. No Responses API, a forma documentada é `text.format` com `type: "json_schema"`, nome, schema e `strict: true`; no Chat Completions, a documentação mostra `response_format` com `type: "json_schema"`. Isso é uma vantagem concreta sobre uma política baseada apenas em “retorne JSON”.

Fontes primárias: [modelo Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [guia de raciocínio](https://developers.openai.com/api/docs/guides/reasoning), [guia do modelo mais recente](https://developers.openai.com/api/docs/guides/latest-model), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [preços OpenAI](https://developers.openai.com/api/docs/pricing), [comunicado de preço de 30/07/2026](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/).

### DeepSeek-V4-Flash-0731

A página oficial de preços/modelos informa:

- contexto de **1M tokens**;
- máximo de saída de **384K tokens**;
- modos **thinking** e **non-thinking**;
- JSON Output e tool calls suportados;
- Responses API suportada pelo Flash;
- API OpenAI-compatible em `https://api.deepseek.com`;
- limite de concorrência publicado: **2.500** para Flash;
- o changelog de 31/07/2026 diz que Flash-0731 é público em beta, mantém a arquitetura/tamanho do preview e recebeu novo post-training;
- o changelog diz que a chamada continua usando `model="deepseek-v4-flash"`.

A documentação de primeiro uso mostra `thinking: {"type": "enabled"}` e `reasoning_effort: "high"` no formato OpenAI-compatible. A página de preços não publica, na tabela resumida consultada, uma matriz completa de níveis aceitos equivalente à matriz OpenAI `none/low/medium/high/xhigh/max`; portanto não se deve assumir paridade de knobs. Para o ShortsFlow, o parâmetro de pensamento deve ser tratado como configuração específica da DeepSeek e validado no adapter.

JSON Output e Structured Outputs não são a mesma coisa. A DeepSeek documenta JSON mode/output e tool calls, mas a tabela consultada não afirma suporte ao mesmo contrato de JSON Schema estrito `strict: true` da OpenAI. O adapter atual do ShortsFlow usa `response_format={"type":"json_object"}`, tenta remover blocos/trechos de thinking e faz `json.loads`/extração de JSON localmente. Isso funciona como tolerância, mas é menos forte que schema estrito.

Fontes primárias: [DeepSeek — Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/), [DeepSeek — primeiro uso](https://api-docs.deepseek.com/), [DeepSeek — changelog](https://api-docs.deepseek.com/updates/), [JSON mode](https://api-docs.deepseek.com/guides/json_mode), [tool calls](https://api-docs.deepseek.com/guides/tool_calls), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode), [rate limit/concurrency](https://api-docs.deepseek.com/quick_start/rate_limit).

## Preço e custo relativo

Valores oficiais por 1M tokens (USD):

| Métrica | Luna | Flash-0731 | Luna / Flash |
|---|---:|---:|---:|
| Input, cache miss | $0,20 | $0,14 | 1,43× |
| Input, cache hit | $0,02 | $0,0028 | 7,14× |
| Output | $1,20 | $0,28 | 4,29× |

A OpenAI também informa que prompts acima de 272K tokens têm multiplicador de **2× no input e 1,5× no output** para a solicitação inteira; isso é irrelevante para prompts normais de ShortsFlow, mas deve ser observado se o pipeline começar a incluir contexto muito grande. A DeepSeek informa que pretende adotar preço de pico/off-peak de 2×, com vigência sujeita a anúncio oficial; não tratar esse preço futuro como custo garantido.

**Implicação prática:** em chamadas pequenas, o custo absoluto continua baixo, mas os gates e reparos multiplicam o output. Uma migração de todas as fases pode aumentar bastante o custo mesmo que o input permaneça parecido. Cache hit favorece fortemente DeepSeek.

Fontes: [OpenAI Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [OpenAI anúncio de preços](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/), [DeepSeek preços](https://api-docs.deepseek.com/quick_start/pricing/).

## Comparação orientada ao ShortsFlow

| Etapa | Necessidade | Melhor hipótese inicial | Motivo/risco |
|---|---|---|---|
| `primary` / rascunho de roteiro pt-BR | fluência, hook, retenção, aderência editorial, JSON | Luna `high` em cohort isolado | No micro A/B, `high` teve melhor aderência/narrativa; custo nominal de output é maior |
| `repair` | corrigir falhas pontuais e retornar contrato válido | Luna `high`; reservar `max` para exceção final | Structured Outputs pode reduzir segundo reparo; `max` aumentou bastante tokens e latência |
| planejamento de cenas | array completo, campos consistentes, duração e intenções visuais | Luna `high` em experimento | Luna suporta schema estrito; validar custo e qualidade no pipeline real |
| `gate judge` comum | decisão curta, razões enumeradas, baixa latência/custo | manter Flash non-thinking ou menor esforço suportado | gate não deve gastar raciocínio caro; decisão deve ser acompanhada por gates determinísticos locais |
| gate/julgamento complexo ou exceção premium | coerência entre roteiro, fatos e cenas | Luna `medium` (ou Flash thinking se benchmark mostrar empate) | maior margem para instruções multi-etapa; custo maior e sem SLA de latência pública |
| ferramentas/lookup | tool calling e fluxo agentic | Luna quando realmente houver ferramentas | OpenAI publica conjunto amplo de ferramentas no Responses; Flash publica tool calls e Responses, mas não a mesma lista hospedada |

### Roteiros pt-BR

Nenhuma das fontes primárias consultadas publica garantia específica de qualidade pt-BR, nem um benchmark oficial comparável para esse uso. A decisão deve ser baseada em replay local com prompts reais do ShortsFlow: naturalidade, contagem de palavras, duração estimada, repetição, factualidade, CTA e aderência ao tom. Não usar benchmarks gerais como substituto.

### JSON estrito e contratos

- **Luna:** usar Structured Outputs com o schema do contrato (`text.format`/`json_schema` no Responses ou `response_format` no Chat Completions), `strict: true`, e ainda manter validação Pydantic/JSON local.
- **Flash:** manter `json_object`/JSON Output, prompt de objeto/array e parser defensivo até confirmar, em teste, se o endpoint atual aceita algum schema estrito. O pipeline atual já remove thinking/fences e tenta extrair JSON; essa camada continua necessária.
- Em ambos os casos, schema estrito não substitui gates determinísticos: duração, número de cenas, campos permitidos, idioma, referências factuais e regras editoriais devem continuar sendo validados no ShortsFlow.

### Planejamento de cenas e gates

O ganho potencial de Luna está menos no tamanho de contexto (ambos ~1M) e mais em obedecer contratos multi-campo e encadear ferramentas. O Flash já suporta JSON Output e tool calls e é o modelo atual do pipeline, então a mudança de modelo não deve ser aprovada sem comparar:

1. taxa de JSON parseável na primeira tentativa;
2. taxa de schema válido na primeira tentativa;
3. número de reparos por job;
4. aprovação dos gates locais e do juiz;
5. divergência entre decisão do juiz e resultado humano;
6. tokens de input/output e custo por job;
7. p50/p95 de latência por etapa;
8. falhas, timeouts, rate limits e repetibilidade.

### Latência e limites

As páginas de modelo fornecem limites de RPM/TPM/concurrency, mas **não fornecem uma garantia de latência p50/p95 para o endpoint**. A OpenAI descreve Luna como “Fast” e a DeepSeek publica concorrência 2.500 para Flash, mas isso não é comparação de latência. Medir no ambiente real, com o mesmo prompt, região, tamanho de resposta, streaming desligado (como hoje) e número de tentativas.

O limite atual local do ShortsFlow é `llm_json_max_tokens=4096` para objetos, com pelo menos 12.000 para alguns arrays, e timeout por provider. Esses limites locais são menores que os máximos dos modelos e devem ser preservados durante o benchmark para evitar comparar configurações diferentes.

## Micro A/B real de 2026-07-31

Foi executado um teste pequeno, sem alterar o pipeline, com o mesmo contrato de Short fictício em pt-BR: decisão binária no primeiro segundo, quatro beats, payoff, JSON e narração de 110–130 palavras.

### Efforts do Luna no mesmo briefing

| Effort | JSON | Palavras | Latência | Reasoning tokens | Resultado |
|---|---:|---:|---:|---:|---|
| `none` | válido | 144 | 10,50s | 0 | violou tamanho |
| `low` | válido | 148 | 10,62s | 292 | violou tamanho |
| `medium` | válido | 126 | 15,16s | 1.159 | passou; payoff mais genérico |
| `high` | válido | 126 | 14,44s | 944 | melhor equilíbrio observado |
| `max` | válido | 122 | 26,74s | 2.732 | passou, mas com custo/latência maiores |

### Mini-cohort de quatro cenários

| Configuração | JSON válido | Tamanho aderente | Latência média total |
|---|---:|---:|---:|
| Luna `high` | 4/4 (100%) | 3/4 (75%; uma saída teve 131 palavras) | 22,32s |
| DeepSeek `high` | 2/4 (50%) | 2/4 (50%) | 31,52s |
| DeepSeek `low` | 2/3 (66,7%) | 2/3 (66,7%) | 30,29s |

Em duas chamadas DeepSeek `high`, o modelo consumiu o teto local de raciocínio sem produzir o JSON final. Reduzir para `low` não eliminou o problema. Em um briefing diretamente comparável e bem-sucedido, Luna `high` custou aproximadamente US$0,00170 contra US$0,00089 do DeepSeek `high`, mas foi mais rápida e produziu menos tokens totais. As quatro chamadas Luna `high` custaram cerca de US$0,0101.

Este cohort é pequeno e não substitui um replay do pipeline completo. Ele é suficiente para rejeitar `none/low` como default de roteiro e justificar um piloto isolado de Luna `high`.

## Recomendação de decisão

1. **Não migrar toda a produção agora.** O micro A/B fez chamadas pagas de baixo custo, mas não mudou provider/configuração.
2. Criar um cohort isolado de seis jobs reais com:
   - Flash atual;
   - Luna `reasoning.effort=high` para geração/planejamento;
   - Luna `max` somente como repair final excepcional.
3. Forçar o mesmo schema e os mesmos limites de saída; registrar custo estimado por preços oficiais, latência e número de retries.
4. Candidato a migração parcial, se o teste confirmar ganho: **Luna `high` para geração/planejamento/repair; DeepSeek para gate judge comum**, preservando independência entre gerador e juiz.
5. Esforço candidato: **`high` para roteiro, contrato visual e cenas**; `medium` para tarefas estruturadas menos criativas; `max` apenas após falha/rejeição repetida. Não usar `none/low` como default de roteiro com base no A/B atual.
6. Só trocar o adapter depois de confirmar compatibilidade do SDK/endpoints e Structured Outputs com o modelo/proxy efetivamente usado. O nome oficial da OpenAI é `gpt-5.6-luna`; qualquer outro nome deve ser documentado como mapeamento específico do provider.

## Observações sobre o repositório pesquisado

No momento desta pesquisa, o ShortsFlow documentava DeepSeek como provider principal e juiz de gates. Essa
observacao foi superseded mais tarde em 2026-07-31 pelo routing Luna/Grok registrado no ADR 0002. O adapter
Luna atual ainda usa JSON object e parsing/validacao local; Structured Outputs com schema estrito permanece
gap de implementacao, nao capacidade ja ativada.

## Fontes oficiais consultadas

- OpenAI, modelo: https://developers.openai.com/api/docs/models/gpt-5.6-luna
- OpenAI, raciocínio: https://developers.openai.com/api/docs/guides/reasoning
- OpenAI, guia do modelo: https://developers.openai.com/api/docs/guides/latest-model
- OpenAI, Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI, preços: https://developers.openai.com/api/docs/pricing
- OpenAI, comunicado de preço de 30/07/2026: https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/
- OpenAI, anúncio geral do GPT-5.6: https://openai.com/index/gpt-5-6/
- DeepSeek, primeiro uso/API: https://api-docs.deepseek.com/
- DeepSeek, Models & Pricing: https://api-docs.deepseek.com/quick_start/pricing/
- DeepSeek, changelog (inclui atualização V4-Flash de 31/07/2026): https://api-docs.deepseek.com/updates/
- DeepSeek, JSON mode: https://api-docs.deepseek.com/guides/json_mode
- DeepSeek, tool calls: https://api-docs.deepseek.com/guides/tool_calls
- DeepSeek, thinking mode: https://api-docs.deepseek.com/guides/thinking_mode
- DeepSeek, rate limit/concurrency: https://api-docs.deepseek.com/quick_start/rate_limit
