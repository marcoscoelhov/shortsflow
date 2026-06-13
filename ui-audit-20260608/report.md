# Auditoria visual da UI do YTS Render

Data: 2026-06-08
Base testada: `http://127.0.0.1:8080`
Escopo: `/`, `/jobs`, `/publication-hub`, `/library`, `/settings`, `/calendar`, detalhe de job `/jobs/5ce85ca7-e145-4a4f-abf2-4a5d1aa19244`, dialogs de filtros, criação de vídeo, configurações rápidas, sidebar colapsada, desktop 1280x900 e mobile 390x844.

Evidências:
- Desktop montage: `MEDIA:/root/yts-render/ui-audit-20260608/desktop-montage.jpg`
- Mobile montage: `MEDIA:/root/yts-render/ui-audit-20260608/mobile-montage.jpg`
- Dados automáticos: `/root/yts-render/ui-audit-20260608/audit-data.json`

## Score técnico Impeccable

| Dimensão | Score | Achado principal |
|---|---:|---|
| Acessibilidade | 2/4 | Boa base semântica e labels em geral, mas checkboxes/controles pequenos, headings vazios no detalhe e contrastes/status precisam revisão manual. |
| Performance | 3/4 | Sem erros de console; HTML leve; detalhe de job é o mais pesado. Problema maior é performance percebida por páginas longas e mídia/render no detalhe. |
| Theming | 3/4 | Sistema consistente e aderente ao DESIGN.md, mas há slugs/status em inglês e microcopy operacional misturada. |
| Responsivo | 2/4 | Mobile funciona sem scroll horizontal geral, mas páginas viram corredores verticais longos; calendário e biblioteca ficam muito custosos de escanear. |
| Anti-patterns | 3/4 | Não parece landing genérica nem “AI SaaS”. O risco é excesso de cards/painéis e modais grandes demais. |
| **Total** | **13/20** | **Aceitável, com trabalho significativo de produto/operacional.** |

## Verificações objetivas

- Todas as páginas testadas retornaram HTTP 200.
- Console JS: 0 erros nas páginas testadas.
- Tempos Playwright desktop: 549 a 1004 ms por navegação local.
- `body.scrollH` desktop: growth 2221 px, library 4325 px, calendar 1687 px, job-detail 3113 px.
- `body.scrollH` mobile: overview 2825 px, growth 3915 px, library 5831 px, calendar 6056 px, job-detail 5920 px.
- Sem overflow horizontal global em mobile (`scrollW=390`, `clientW=390`) nas rotas testadas.

## Achados priorizados

### P1: Ações primárias somem em dialogs altos

Locais: dialog `Novo Projeto`, configurações rápidas da topbar.

Impacto: o operador abre um fluxo de ação, mas o CTA principal fica fora do primeiro viewport. No dialog de criação, o botão “Criar vídeo” aparece no DOM, mas não fica visível no screenshot 1280x900. Nas configurações rápidas, o painel também corta antes da área final de ação.

Recomendação:
- Fazer modal com `max-height: calc(100vh - 2rem)` e corpo interno rolável.
- Fixar footer com CTA primário e secundário.
- No `Novo Projeto`, mostrar “Criar vídeo” sempre visível, mesmo antes de rolar.

### P1: Mobile está funcional, mas vira uma esteira vertical cansativa

Locais: `/library`, `/calendar`, detalhe do job, growth.

Impacto: a interface não quebra horizontalmente, mas o operador precisa rolar milhares de pixels para tarefas recorrentes. Em mobile, library chega a 5831 px, calendar a 6056 px, job-detail a 5920 px.

Recomendação:
- Mobile deve priorizar ação por contexto, não replicar desktop empilhado.
- Biblioteca: tabs/filtros por estado e paginação/virtualização visual.
- Calendário: trocar grade mensal por agenda semanal/lista por padrão em mobile.
- Detalhe: criar nav local sticky: `Resumo`, `Revisar`, `Vídeo`, `Mídia`, `Técnico`.

### P1: Calendário mensal é denso demais para Shorts operacionais

Locais: `/calendar` desktop e mobile.

Impacto: a grade mensal dá visão ampla, mas os cards dentro dos dias ficam truncados, estreitos e difíceis de comparar. O operador quer saber “o que está pronto, o que está agendado, onde há buraco”, não ler títulos em células de 126 px.

Recomendação:
- Desktop: manter mês, mas adicionar faixa lateral “Prontos para agendar” e “Próximos 7 dias”.
- Mobile: agenda/lista como padrão, grade mensal como visão secundária.
- Tornar cada dia um resumo: contagem + estado, expandindo ao clicar.

### P1: Detalhe do job tem muita decisão simultânea

Local: `/jobs/{id}`.

Impacto: a página tem cabeçalho, banner de revisão, progresso, vídeo final, prova premium, mídia, dados técnicos, decisão de revisão e agendamento. Tudo está tecnicamente disponível, mas a decisão principal compete com diagnóstico e comparação premium.

Recomendação:
- Topo deve responder em 5 segundos: “Aprovar, corrigir ou rejeitar?”.
- Side panel sticky é bom, mas deve ficar mais decisivo: checklist, CTA e motivo de bloqueio primeiro.
- “Prova premium” deve ser subordinada à revisão final, não virar uma segunda área grande antes da decisão.
- Collapses técnicos devem ter títulos visíveis e não gerar headings vazios.

### P1: Biblioteca está longa e com baixo poder de triagem

Local: `/library`.

Impacto: a lista é extensa, repetitiva e faz o operador percorrer muitos roteiros “consumed/agendado” sem priorização clara.

Recomendação:
- Separar estados: `Disponíveis`, `Para revisar`, `Agendados`, `Consumidos`.
- Consumidos devem ser colapsados/arquivados por padrão.
- Adicionar busca/filtro local por estado, origem e job vinculado.
- Reduzir cada item a uma row mais densa, com detalhes sob disclosure.

### P2: Status e labels ainda misturam idioma interno com linguagem de operador

Locais: biblioteca, job detail, body text e badges.

Exemplos vistos: `consumed`, `batch`, `gate aprovado`, `job caacbe41`, timestamps ISO crus em biblioteca.

Impacto: quebra a regra do PRODUCT.md “Português para operadores” e aumenta ruído cognitivo.

Recomendação:
- `consumed` -> `Consumido`.
- `batch` -> `Importação em lote`.
- `gate aprovado` -> `Critérios aprovados` ou `Qualidade aprovada`.
- Timestamps ISO -> data curta pt-BR com hora.
- Job IDs ficam como meta secundária copiável, não leitura primária.

### P2: Fila principal está boa, mas ainda parece tabela pesada dentro de card

Local: `/` e `/jobs`.

Pontos positivos: hierarquia clara, filtros rápidos úteis, origem/via aparecem, progresso visível, densidade adequada para operação.

Gaps:
- O painel da fila ocupa muita área com moldura grande.
- A coluna “Prévia” usa ícone/material text visualmente forte para pouco valor.
- “Precisam de ação” e “Na fila” são bons, mas poderiam abrir filtros diretos.

Recomendação:
- Transformar métricas do topo em filtros clicáveis.
- Reduzir peso visual do container da tabela.
- Destacar próximo comando por row: `Revisar`, `Ver falha`, `Agendar`, `Publicar`.

### P2: Configurações precisam de mais proteção operacional

Locais: `/settings` e modal rápido.

Impacto: configurações importantes aparecem em áreas compactas com checkboxes pequenos. Em uma UI de automação/publicação, alterações de YouTube, TikTok, notificações e retroposts merecem copy de consequência.

Recomendação:
- Agrupar “perigoso/muda publicação” separado de “preferência operacional”.
- Mostrar “impacto desta mudança” dentro do grupo aberto.
- Aumentar área clicável de checkboxes para 44px.
- Usar labels legíveis: `Automação`, `Publicação`, `Narração` com acento.

### P2: Growth tem boas ideias, mas falta hierarquia de ação

Local: `/publication-hub`.

Pontos positivos: métricas de confiança, pendências e coleta são relevantes.

Gaps:
- “Recomendações rápidas” parece lista de cards claros dentro de app escuro. Funciona, mas quebra a linguagem visual mais do que o resto.
- “Assistente de crescimento” mostra bloqueio por base mínima, mas não diz exatamente quantos snapshots faltam para destravar.
- Lista de pendências ocupa muito espaço com botões repetidos.

Recomendação:
- Transformar recomendações em checklist operacional: ação, motivo, impacto, CTA.
- Mostrar threshold explícito para desbloquear IA.
- Trocar botões repetidos por seleção em lote e CTA único.

### P2: Acessibilidade e semântica precisam de uma passada dedicada

Achados:
- Inputs de checkbox com área visual de 10 a 18 px em biblioteca/settings/detalhe.
- Detalhe registrou headings H4 vazios no DOM analisado.
- Vários ícones materiais aparecem como texto no `bodyTextStart` (`search`, `left_panel_close`, `settings`, etc.), o que pode poluir leitores de tela se não forem `aria-hidden`.
- Alguns botões com texto visível foram capturados como “unlabeled” por heurística por causa de estrutura/visibilidade, vale revisar com axe.

Recomendação:
- Garantir `aria-hidden="true"` em ícones puramente decorativos.
- Área clicável de checkbox/radio >= 44px com label inteiro clicável.
- Revisar heading hierarchy no detalhe.
- Rodar axe-core ou Playwright accessibility snapshot antes de release.

### P3: Consistência visual geral

- A identidade “Production Desk” está funcionando: escuro, operacional, sem landing page e sem gradiente AI roxo/azul.
- O vermelho/ember é forte e ajuda nos CTAs, mas em mobile a navegação inferior com botão central vermelho chama mais atenção que a tarefa atual.
- O sidebar colapsado economiza espaço e mantém estado ativo, mas os ícones sem labels exigem memória. Bom para usuário recorrente, ruim como default.

## Recomendações por página

### `/` e `/jobs`

- Bom: melhor tela do produto, objetivo claro, rows úteis, origem/via aparecem.
- Melhorar: métricas clicáveis, ação primária por row, menos moldura de card, filtros com estado aplicado mais explícito.

### `/publication-hub`

- Bom: conceito certo, crescimento não vira gráfico decorativo.
- Melhorar: reduzir botões repetidos, deixar thresholds explícitos, aproximar visual dos painéis escuros do resto do sistema.

### `/library`

- Bom: banco de roteiros existe e é rastreável.
- Melhorar: triagem por estado, arquivar consumidos, traduzir slugs, compactar rows e reduzir scroll.

### `/settings`

- Bom: accordion por área reduz risco de página infinita.
- Melhorar: checkboxes/touch targets, acentos/pt-BR, explicitar consequências de publicação, footer de salvar sempre visível.

### `/calendar`

- Bom: visão mensal comunica distribuição.
- Melhorar: agenda mobile, resumo por dia, lista lateral de prontos, reduzir truncamento e overflow dentro de células.

### `/jobs/{id}`

- Bom: contém tudo que o operador precisa para aprovar/rejeitar/publicar.
- Melhorar: priorizar decisão, reduzir competição com prova premium e dados técnicos, nav local sticky, headings/ARIA.

## Próxima sequência recomendada

1. `impeccable adapt`: mobile de calendário, biblioteca e detalhe.
2. `impeccable harden`: dialogs com footer sticky, checkboxes, headings, ARIA, labels.
3. `impeccable clarify`: traduzir slugs/copy interna e deixar thresholds/impactos claros.
4. `impeccable layout`: reduzir scroll e densidade repetitiva em library/growth/calendar.
5. `impeccable optimize`: mídia do detalhe, lazy sections e listas longas.
6. `impeccable polish`: pass final visual depois das correções.

## Perguntas de produto a decidir

1. O mobile é canal de operação real ou apenas consulta emergencial? Recomendação: tratar como consulta + pequenas ações seguras, não edição completa.
2. O calendário deve otimizar “visão do mês” ou “próximas publicações”? Recomendação: desktop mantém mês; mobile usa agenda.
3. Consumidos na biblioteca ainda são operacionais? Recomendação: não, arquivar por padrão.
4. Prova premium é parte da revisão ou upsell interno de qualidade? Recomendação: parte secundária da revisão, nunca competir com Aprovar/Rejeitar.
