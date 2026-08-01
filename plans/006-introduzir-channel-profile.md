# Plano 006: Introduzir ChannelProfile e isolamento multinicho

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Faca migracao
> aditiva e backfill em copia do banco. Atualize `plans/README.md`.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/models.py app/schemas.py app/config.py app/db.py app/automation.py app/pipelines/topic_pipeline.py app/manual_script.py app/performance_ops.py app/publication_workflow_ops.py tests`

## Status

- **Prioridade**: P1
- **Esforco**: XL
- **Risco**: HIGH
- **Depende de**: 003, 004, 005
- **Categoria**: multi-tenant domain / data
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Multinicho nao e trocar um prompt global. Cada canal precisa de identidade,
fontes, voz, limites, agenda, prompts e metricas isolados. Sem uma raiz de
escopo, paineis distintos criariam vazamento de dados e configuracao.

## Estado atual

- `SUPPORTED_NICHES` aceita apenas `curiosidades` e a configuracao possui nicho
  global.
- Jobs, scripts, schedules e metricas nao pertencem a um perfil persistido.
- `recent_topic_history(session, niche_id)` recebe nicho mas ignora o parametro.
- Segredos/provider keys estao no ambiente e devem continuar fora do banco.
- A estrategia atual prioriza um canal cosmos ate provar breakout; o segundo
  perfil deve nascer desabilitado.

## Modelo alvo

`ChannelProfile` e a raiz de agregacao operacional:

- `id`, `slug` imutavel, `display_name`, `status` (`draft`, `active`, `paused`)
- `niche_key`, idioma, timezone, audiencia e proposta editorial
- referencias para prompt/retention/voice/visual policy versionados
- agenda, plataforma e feature flags logicos
- timestamps e version para optimistic locking

Politicas de nicho sao dados validados e versionados, nao codigo carregado
dinamicamente. Tokens continuam em env/secret manager; o perfil guarda apenas
um binding logico como `youtube_account_key`.

## Escopo

**Pode alterar**: modelos/migracoes, schemas, repositories/queries, automation,
topic/script ingestion, publication/metrics, config, seed e testes.

**Nao alterar**: criar paineis/URLs novos (Plano 007), habilitar publicacao de
segundo canal, mover segredos para banco ou duplicar a aplicacao FastAPI.

## Git

- Branch: `advisor/006-channel-profile`
- Commits: model/backfill; scope API; propagation; second-profile fixtures.

## Passos

### 1. Adicionar perfil default por migracao

Crie `ChannelProfile` e uma migracao que insira `default-cosmos` a partir da
config atual. Adicione `profile_id` inicialmente nullable, faca backfill em
jobs, scripts/imports, schedules, publications, snapshots, prompt bindings e
entidades de automacao; depois torne non-null onde o dominio exigir.

**Verificar**: contagens pre/pos sao iguais; todo registro operacional possui
perfil; IDs/URLs/artefatos antigos continuam validos.

### 2. Criar `ProfileScope` explicito

Introduza value object/contexto imutavel com `profile_id` e slug. Services e
repositories operacionais devem exigi-lo; nao use variavel global ou filtro
opcional. Queries administrativas cross-profile devem ter API separada e nome
explicito.

**Verificar**: teste falha ao chamar repository scoped sem perfil; consulta de
um perfil nunca retorna fixture do outro.

### 3. Propagar escopo pelo lifecycle

Job herda perfil da origem: geracao automatica, banco de roteiros, import manual
ou API. StepExecution e artefatos herdam via Job; schedule/publication/metricas
validam o mesmo perfil. Retry/reprocess nao pode trocar perfil.

**Verificar**: job completo em dois perfis com mocks produz artefatos e metricas
isolados; tentativa de associacao cruzada e rejeitada.

### 4. Tornar politicas declarativas e versionadas

Crie schemas Pydantic para `NichePolicy`: taxonomia, fontes permitidas,
sensibilidade factual, termos proibidos, faixa de duracao, linguagem visual e
cadencia. Referencie versoes imutaveis; nao permita JSON arbitrario sem schema.

**Verificar**: config invalida nao publica; job conserva snapshot da policy.

### 5. Corrigir historia e deduplicacao de temas

Faca `recent_topic_history` filtrar por perfil/nicho real. Defina deduplicacao
local ao perfil e, opcionalmente, alerta global para canais relacionados. Nao
bloqueie um nicho por similaridade irrelevante em outro.

**Verificar**: fixtures com mesmo titulo em dois perfis exercitam ambas regras.

### 6. Preparar segundo perfil sem ativa-lo

Inclua seed de exemplo desabilitado para teste, nao para producao. Automation,
scheduler e publisher so operam `active`; `draft/paused` podem ser visualizados
mas nao criar/publicar jobs.

**Verificar**: perfil draft nao e claimed nem publicado mesmo com agenda valida.

## Testes obrigatorios

- Upgrade/backfill/downgrade em copia.
- Isolamento de todas as queries quentes e operacoes de escrita.
- Concorrencia de update de profile/policy.
- Import de roteiro escolhe perfil explicitamente.
- Paused/draft bloqueiam automation e publication.
- Nenhum token aparece no banco, log ou snapshot.

## Pronto quando

- [ ] Todo dado operacional novo tem `profile_id` obrigatorio.
- [ ] Perfil default reproduz comportamento atual.
- [ ] Dois perfis de teste nao vazam jobs, temas, agenda ou metricas.
- [ ] O segundo perfil permanece desabilitado em producao.
- [ ] Suite e migration checks passam.

## Pare se

- Nao for possivel mapear registro legado ao default sem perda.
- Alguma query scoped precisar de fallback silencioso para "todos".
- Um secret precisar ser persistido para concluir o plano; mantenha binding
  logico e registre a integracao faltante.

## Manutencao

Toda entidade nova deve declarar se e global ou profile-scoped. Reviewers devem
procurar `.all()` e repositories sem `ProfileScope`, pois isolamento por UI nao
substitui isolamento no dominio e no banco.
