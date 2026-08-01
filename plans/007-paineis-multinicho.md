# Plano 007: Criar paineis distintos por perfil

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Preserve as
> URLs atuais como aliases do perfil default durante a transicao. Atualize
> `plans/README.md`.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/main.py app/routes app/templates app/static/styles.css app/hub_context.py app/hub_jobs_context.py app/performance_ops.py tests`

## Status

- **Prioridade**: P2
- **Esforco**: L
- **Risco**: MED
- **Depende de**: 006
- **Categoria**: product / frontend / routing
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Operar canais diferentes no mesmo painel global torna facil publicar, analisar
ou editar o canal errado. Paineis devem compartilhar componentes, mas ter
contexto visual e escopo de dados inequivocos.

## Arquitetura de navegacao

- Canonico: `/p/{profile_slug}/overview`, `/jobs`, `/scripts`, `/calendar`,
  `/analytics`, `/settings/editorial` e `/settings/providers`.
- URLs antigas resolvem para o perfil default por uma release e emitem header
  de deprecacao/log, sem duplicar handlers.
- Um selector de perfil troca a raiz da URL. Perfil atual aparece no header com
  nome, nicho e status; cor pode ser acento secundario, nunca unico indicador.
- Nao crie uma FastAPI app, banco ou copia de template por nicho.

## Escopo

**Pode alterar**: routers, context builders, templates/partials, CSS, links,
filtros, formularios, testes Playwright e docs.

**Nao alterar**: regras editoriais, schema alem de preferencias pequenas de UI,
ativar automacao/publicacao de perfil draft ou redesenhar a marca inteira.

## Git

- Branch: `advisor/007-profile-dashboards`
- Commits: scoped routes; navigation; views; E2E/responsive.

## Passos

### 1. Criar resolucao de perfil na borda

Adicione dependency FastAPI que resolve slug, valida acesso/status e fornece
`ProfileScope`. Handlers chamam services scoped; nao aplicam filtro manual apos
consulta. Slug desconhecido retorna 404, nunca default silencioso.

**Verificar**: testes de 404, alias legado e troca de perfil; nenhuma rota
operacional scoped funciona sem contexto.

### 2. Separar routers por superficie

Extraia overview, jobs, scripts, calendar, analytics e settings de `main.py` em
routers pequenos. Reuse services/context builders; aliases antigos apontam para
os mesmos handlers ou redirect seguro.

**Verificar**: mapa de rotas nao tem nomes/conflitos duplicados e links antigos
mantem metodo/query string quando aplicavel.

### 3. Implementar shell operacional scoped

Crie header/sidebar compactos, selector acessivel e status active/paused/draft.
Evite cards decorativos e texto de marketing. Priorize filas, estados, alertas,
agenda e acoes repetidas. A interface deve deixar claro o perfil antes de toda
acao destrutiva ou de publicacao.

**Verificar**: foco por teclado, labels, contraste e viewport 375/768/1440 sem
overflow/overlap; selector nao perde a subpagina quando ela existe no destino.

### 4. Construir visoes por perfil

Overview mostra backlog, readiness, proximas publicacoes e alertas. Jobs/scripts
mantem filtros e paginacao SQL. Calendar e analytics usam timezone do perfil.
Settings separa editorial, voz/visual, agenda e bindings logicos de provider.

**Verificar**: cada pagina com fixtures A/B exibe apenas A ou B e totais
corretos; timestamps respeitam timezone.

### 5. Proteger mutacoes e formularios

Todos POST incluem profile na URL e validam que o recurso pertence ao scope.
Inclua protecao definida no Plano 002. Mensagens de confirmacao nomeiam canal e
acao; IDs enviados pelo cliente nunca bastam para autorizar a operacao.

**Verificar**: trocar job_id entre perfis retorna 404/403 sem alterar dados.

### 6. Liberar por feature flag

Com flag desligada, aliases/default preservam UX atual. Com flag ligada,
selector e rotas scoped aparecem. Perfil secundario draft pode ser inspecionado,
mas botoes de gerar/agendar/publicar ficam desabilitados no servidor e UI.

## Testes obrigatorios

- E2E de navegacao e CRUD permitido em dois perfis.
- Tentativas de IDOR em toda mutacao principal.
- Aliases legados do perfil default.
- Mobile/desktop screenshots e navegacao por teclado.
- Paused/draft bloqueados server-side.
- Paginacao/filtros preservados ao trocar view/perfil.

## Pronto quando

- [ ] Todas as paginas operacionais possuem URL scoped canonica.
- [ ] Nao ha duplicacao de templates por nicho.
- [ ] E2E prova ausencia de vazamento A/B.
- [ ] URLs antigas ainda funcionam para default.
- [ ] Feature flag permite rollback imediato.

## Pare se

- Uma view precisar consultar sem `ProfileScope`.
- Isolamento depender apenas de campos hidden no formulario.
- O segundo perfil precisar ser ativado para testar a UI.

## Manutencao

Nova pagina operacional nasce scoped. Componentes podem ser compartilhados;
queries e comandos nunca inferem perfil a partir do ultimo selecionado em cookie.
