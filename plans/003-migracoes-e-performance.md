# Plano 003: Adotar migracoes e corrigir consultas quentes

> **Executor Terra**: use copia descartavel de banco. Nunca execute o script de
> migracao contra banco real. Atualize `plans/README.md` ao terminar.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/db.py app/models.py app/hub_jobs_context.py app/performance_ops.py app/orchestrator_worker.py scripts/migrate_sqlite_to_postgres.py pyproject.toml`

## Status

- **Prioridade**: P1
- **Esforco**: L
- **Risco**: HIGH
- **Depende de**: 001, 002
- **Categoria**: perf / migration
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Novos perfis exigem schema versionado. Hoje `create_all` e dois `ALTER TABLE`
ad-hoc nao conseguem evoluir entidades com seguranca. Ao mesmo tempo, o Hub
carrega todos os jobs para paginar e Analytics faz 1+N. Corrigir juntos permite
adicionar indices por migracao e medir o ganho.

## Estado atual

- `app/db.py:38-59` usa `metadata.create_all` e altera apenas duas colunas.
- `scripts/migrate_sqlite_to_postgres.py:30-49` omite varias tabelas atuais;
  `:73-75` apaga destino antes de copiar e `:91-95` hardcode URLs.
- `hub_jobs_context.py:121-150` usa `.all()` e slice em memoria.
- `performance_ops.py:207-248` busca latest snapshot dentro do loop.
- `models.py:33-56` nao indexa status/created/lease para o claim de
  `orchestrator_worker.py:128-152`.
- Steps externos podem permanecer dentro de `session_scope` por minutos.

## Escopo

**Pode alterar**: `app/db.py`, `app/models.py`, nova pasta de migracoes,
`app/hub_jobs_context.py`, `app/performance_ops.py`, `app/orchestrator_worker.py`,
`app/orchestrator.py`, pipelines necessarios para transaction boundary,
`scripts/migrate_sqlite_to_postgres.py`, testes e docs operacionais.

**Nao alterar**: semantica editorial, UI visual, nomes de estado/artefato,
credenciais reais ou dados em `data/`.

## Git

- Branch: `advisor/003-migrations-performance`
- Commits: migracao baseline; indices/queries; transaction boundaries; migrador.

## Passos

### 1. Introduzir migracoes versionadas

Use Alembic compativel com SQLAlchemy atual. Crie baseline que reconheca banco
existente sem recriar tabelas e migracao explicita para indices. `init_db()` pode
criar banco vazio em desenvolvimento, mas producao deve checar/aplicar revision.

**Verificar**: banco vazio sobe; copia de banco atual recebe stamp/upgrade;
`alembic current` mostra head; downgrade testado em copia.

### 2. Adicionar indices conforme queries

Crie indices nomeados para claim de Job e scans de agenda/snapshot. Valide com
`EXPLAIN QUERY PLAN` em SQLite antes/depois. Nao adicione indices especulativos.

**Verificar**: query de claim usa indice; testes de concorrencia passam.

### 3. Paginar jobs no SQL

Normalize filtros `origin`/`via` usando as colunas persistidas. Para registros
historicos `unknown`, mantenha fallback/inferencia em um caminho limitado, sem
materializar toda a tabela. Use count separado e limit/offset.

**Verificar**: pagina, total e filtros permanecem identicos; teste com 500 jobs
assegura que a query principal retorna no maximo `per_page` linhas.

### 4. Remover 1+N de Analytics

Use subquery `max(fetched_at)` ou window function por `job_id`, juntando o latest
snapshot aos schedules em uma consulta. Aplique limit no SQL quando possivel.

**Verificar**: fixture com 100 schedules produz numero constante de queries e a
mesma lista/cadencia de candidatos.

### 5. Encurtar transacoes dos steps caros

Introduza protocolo `prepare -> execute_external -> persist`. O prepare le os
dados e gera input hash; execute nao segura Session; persist reabre transacao e
confirma que job/attempt/input hash continuam validos antes de gravar.

Migre primeiro TTS e Remotion, depois imagem/musica. Preserve retry e
StepExecution. Um resultado atrasado nunca pode sobrescrever novo attempt.

**Verificar**: provider mock bloqueado por evento por 2s enquanto outra sessao
atualiza estado sem `database locked`; resultado stale e descartado.

### 6. Reescrever o migrador PostgreSQL

CLI deve exigir origem/destino via argumentos/env, default dry-run, confirmar
explicitamente qualquer truncate e descobrir ordem a partir de metadata/FKs.
Copiar todas as tabelas, comparar contagens e checksums amostrais. Nunca imprimir
URL com senha.

**Verificar**: SQLite fixture -> Postgres descartavel quando disponivel; sem
Postgres, testes unitarios cobrem plano/ordem/conversao e dry-run.

## Pronto quando

- [ ] Upgrade de copia existente preserva contagens.
- [ ] Rollback de migracao aditiva funciona em copia.
- [ ] Query de Hub pagina no banco.
- [ ] Latest Analytics nao e 1+N.
- [ ] TTS/Remotion nao seguram write transaction durante external work.
- [ ] Migrador nao apaga nada sem flag explicita.
- [ ] Suite e typecheck passam.

## Pare se

- Nao houver backup/copia de banco para testar.
- Uma mudanca de transaction boundary quebrar idempotencia do StepExecution.
- Postgres exigir semantica diferente nao coberta; entregue primeiro SQLite e
  registre o bloco em vez de fingir equivalencia.

## Manutencao

Toda nova coluna/indice deve vir por revision. Reviewers devem verificar query
plans e stale-result checks, nao apenas tempo de uma fixture pequena.
