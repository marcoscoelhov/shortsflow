---
target: app/templates/jobs.html
total_score: 22
p0_count: 0
p1_count: 3
timestamp: 2026-05-27T23-45-29Z
slug: app-templates-jobs-html
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Progresso, status e auto-refresh existem, mas publicacao/agendamento nao aparecem como area confiavel no topo. |
| 2 | Match System / Real World | 2 | Linguagem ainda mistura operador e implementacao: fallback, job_id e Novo Projeto. |
| 3 | User Control and Freedom | 2 | Filtros, busca e modais fechaveis existem, mas as acoes reais exigem abrir detalhes. |
| 4 | Consistency and Standards | 2 | Navegacao promete Visao geral, Automacao e Publicacao, mas ha duplicidade de destino e secao de publicacao oculta. |
| 5 | Error Prevention | 2 | Filtros e selects ajudam, mas 19 status tecnicos aumentam erro de escolha. |
| 6 | Recognition Rather Than Recall | 2 | Proxima acao aparece na linha, mas revisar, agendar e recuperar falhas exigem mapa mental. |
| 7 | Flexibility and Efficiency | 2 | Busca e filtros ajudam, mas nao ha acoes inline, lote ou caminho rapido por estado. |
| 8 | Aesthetic and Minimalist Design | 2 | O visual e sobrio, mas as linhas carregam metadados demais para triagem rapida. |
| 9 | Error Recovery | 2 | Falhas sao visiveis, mas a recuperacao ainda depende de abrir o job e interpretar detalhes. |
| 10 | Help and Documentation | 1 | Ha ajuda pontual em modais, pouca orientacao no fluxo principal de revisao/publicacao. |
| **Total** | | **22/40** | **Acceptable, with significant workflow improvements needed** |

## Anti-Patterns Verdict

**LLM assessment**: A interface nao parece gerada por IA no sentido decorativo. Ela evita landing page, evita hero generico e tem densidade real de ferramenta. O ponto fraco e mais profundo: parece uma fila tecnica polida, nao uma mesa de decisao madura. A tela mostra estado, progresso e metadados, mas nao faz a proxima acao dominar.

**Deterministic scan**: `node .agents/skills/impeccable/scripts/detect.mjs --json app/templates app/static/styles.css` retornou `[]`, exit code 0. Nenhum achado bruto, nenhum achado pos-ignore. A ignore list de `single-font` em `base.html` nao precisou ser aplicada.

**Visual overlays**: Overlay nao ficou disponivel. A mutacao no browser funcionou, mas o live server respondeu `404 Not Found` para `http://localhost:8400/detect.js`; nao havia detector browser empacotado em `.agents/skills/impeccable/scripts`. Fallback usado: CLI detector limpo, snapshots de acessibilidade, screenshots desktop/mobile e console/errors do browser.

## Overall Impression

A base visual esta no caminho certo para um console operacional: escura, contida, sem marketing e com linguagem majoritariamente pt-BR. A maior oportunidade e transformar a tela inicial de uma lista de jobs em uma fila de decisoes: revisar agora, agendar agora, investigar falha, acompanhar render.

## What's Working

1. O registro visual combina com o produto: escuro, denso, operacional, sem estetica SaaS decorativa.
2. Cada linha ja carrega sinais relevantes: status, progresso, origem, via de criacao e proxima acao.
3. A responsividade existe: em 390x844 a navegacao muda para bottom nav, a busca vira botao e os cards expoem labels como Status, Progresso e Criado em.

## Priority Issues

**[P1] Publicacao e prometida pela navegacao, mas fica invisivel**

Why it matters: A sidebar tem Publicacao e o template renderiza `#publication-hub`, mas a evidencia visual mostra foco apenas na fila e agenda. Isso quebra confianca justamente na parte de publicacao, que e uma decisao de alto risco.

Fix: Mostrar uma faixa compacta de publicacao na tela principal com aguardando aprovacao, aprovados sem agenda, programados, falhas e CTA Abrir agenda. Se Publicacao e Agendamento forem a mesma esteira operacional, consolidar o item de nav e remover a promessa duplicada.

Suggested command: `$impeccable layout app/templates/jobs.html`

**[P1] A tela diz precisam de acao, mas nao organiza a acao**

Why it matters: O resumo mostra 21 jobs que precisam de acao, mas a lista nao separa revisar, agendar e investigar falha. O operador precisa abrir job por job para descobrir o trabalho real.

Fix: Adicionar uma faixa Proximas decisoes antes da fila, agrupada em Revisar, Agendar e Falhas. Nas linhas, transformar `next_action` textual em CTA contextual: Revisar, Agendar, Ver erro ou Confirmar publicacao.

Suggested command: `$impeccable shape app/templates/jobs.html`

**[P1] Filtros expõem taxonomia tecnica demais**

Why it matters: O modal de filtros lista 19 status. Para operador, isso e uma lista de estados internos, nao uma decisao operacional. A chance de escolher o filtro errado aumenta.

Fix: Separar filtros por linguagem de operacao: Em producao, Precisa decisao, Agenda/publicacao, Falhas. Colocar status tecnico em uma secao Avancado.

Suggested command: `$impeccable distill app/templates/jobs.html`

**[P2] Mobile e legivel, mas lento para triagem**

Why it matters: Em viewport 390x844, cada job vira um bloco alto com status, progresso, criado em e metadados. O usuario mobile consegue ler um item, mas perde comparacao entre prioridades.

Fix: No mobile, mostrar primeiro titulo, status, progresso e CTA. Colapsar origem, via, fallback e timestamp completo em detalhes secundarios.

Suggested command: `$impeccable adapt app/templates/jobs.html`

**[P2] Copy operacional ainda vaza implementacao**

Why it matters: Termos como fallback, job_id e Novo Projeto nao batem com o contrato de produto em pt-BR. A UI deve falar com operador, nao com log de pipeline.

Fix: Trocar fallback por usou alternativa ou alternativa acionada, expor ID do job apenas quando necessario, trocar Novo Projeto por Criar video, e revisar labels ligados a worker/publicacao automatica.

Suggested command: `$impeccable clarify app/templates/jobs.html`

## Persona Red Flags

**Alex, power user**: A fila mostra 4 de 96 jobs por pagina e nao oferece acao inline nem acao em lote. Alex quer filtrar Precisa revisar e aprovar/agendar rapido, mas precisa abrir detalhes. O modal de filtro com 19 status tambem e lento para operacao repetida.

**Sam, acessibilidade/teclado**: A estrutura tem labels e aria-live, o que ajuda. O ponto fraco e o select de status com 19 opcoes, pesado para leitor de tela, e a promessa de Publicacao na navegacao sem uma area claramente visivel. Metadados pequenos como timestamp e fallback tambem podem pesar para baixa visao.

**Casey, mobile distraido**: A bottom nav ajuda, mas a triagem e cansativa. Cada job ocupa muita altura, os filtros rapidos viram trilho horizontal e a acao real fica escondida no detalhe. Casey consegue abrir um job, mas nao compara prioridades rapidamente.

## Minor Observations

- Visao geral e Automacao apontam para `/`, mas so Automacao parece ativa.
- O titulo Jobs prioritarios existe no template, mas fica escondido visualmente.
- Timestamp com microsegundos parece log, nao UI de operador.
- A previa usa thumb generica; uma imagem real do artefato aumentaria confianca na revisao.
- A pagina carrega 4 de 96 jobs por vez; isso reduz densidade para um operador que esta triando fila grande.

## Questions to Consider

1. Esta tela e uma fila de render ou uma fila de decisoes?
2. Se o operador tiver so 30 segundos, a tela deve empurrar primeiro revisar, agendar ou investigar falha?
3. Publicacao e Agendamento sao duas areas diferentes ou uma unica esteira operacional?
4. Origem, via e fallback precisam aparecer em toda linha ou so quando mudam o risco da decisao?
