# Plano 002: Endurecer autenticacao, leases e publicacao

> **Executor Terra**: execute em worktree isolada. Nao publique video real e nao
> use credenciais. Atualize `plans/README.md` ao terminar.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/main.py app/orchestrator.py app/publication_workflow_ops.py app/youtube_publication_ops.py app/manual_script.py app/automation.py app/pipelines/monetization_pipeline.py tests`
> Qualquer mudanca nas transicoes citadas exige parada e replanejamento.

## Status

- **Prioridade**: P0
- **Esforco**: L
- **Risco**: MED
- **Depende de**: `001-estabilizar-verificacao.md`
- **Categoria**: bug / security
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Ha tres caminhos capazes de quebrar um canal real: upload duplicado, reprocesso
concorrente e roteiro importado tratado como fato verificado sem confirmacao.
O middleware tambem viola o contrato documentado ao aceitar cookie em POST.
Corrija antes de multiplicar canais, workers ou automacao.

## Estado atual

- `publication_workflow_ops.py:45-75` valida apenas status do job e grava
  `publishing`, sem claim atomico que rejeite outro chamador.
- `youtube_publication_ops.py:224-254` ja possui claim atomico do schedule, mas
  chama o workflow que nao verifica ownership/attempt.
- `orchestrator.py:383-388` protege `process_job()` contra lease alheio vivo;
  `:434-496` nao aplica a mesma regra a reprocess/regenerate.
- `main.py:179-188` busca token em header, bearer e cookie para qualquer metodo,
  embora `README.md:168` diga que POST exige header/bearer.
- `manual_script.py:250-269` marca roteiro como `status=verified`.
- `automation.py:116-145` ignora o argumento `fact_check_confirmed` e persiste
  sempre `True`.
- `monetization_pipeline.py:130-133` auto-confirma fato/audit/originalidade por
  ser ready script; `:983-985` pula publish audit.

## Escopo

**Pode alterar**:

- `app/main.py` e helpers de auth novos
- `app/orchestrator.py` ou helper de lease novo
- `app/publication_workflow_ops.py`
- `app/youtube_publication_ops.py`
- `app/manual_script.py`
- `app/automation.py`
- `app/pipelines/monetization_pipeline.py`
- modelos/migracao somente se necessarios para attempt/idempotency
- testes de auth, orchestrator, script e publication

**Nao alterar**: API externa real, nomes de estados/artefatos, UX ampla, prompt
viral, thresholds ou providers.

## Git

- Branch: `advisor/002-critical-operations`
- Um commit por subproblema: `fix: make youtube publication idempotent`,
  `fix: preserve active job leases`, `fix: require ready script fact review`,
  `fix: reject cookie-only hub mutations`.

## Passos

### 1. Caracterizar upload concorrente

Escreva teste com dois chamadores/barreira sobre o mesmo job aprovado. O mock de
upload deve contar chamadas. O teste atual deve mostrar duas chamadas ou a
ausencia de claim; depois da correcao, exatamente uma.

Implemente claim atomico com attempt/owner persistido ou predicate de schedule.
`publishing` vivo e `published` devem ser no-op/409; `publish_failed` e stale
`publishing` seguem somente pela policy de recovery existente.

**Verificar**: testes de manual, schedule worker, retry e recovery passam; mock
de upload recebe uma chamada.

### 2. Reusar uma policy unica de lease

Extraia `active_foreign_lease(job, worker_id, now)` e use em process, reprocess e
regenerate. Lease expirado pode ser recuperado; lease vivo nao pode ser roubado.
Nao adicione `force` publico neste plano.

**Verificar**: live foreign lease bloqueia sem apagar StepExecution/artifact;
expired lease permite; job failed sem lease permite.

### 3. Cumprir o contrato de autenticacao de mutacoes

Para metodos unsafe, aceite somente `x-shortsflow-hub-token` ou bearer. Cookie
continua para GET/HEAD. Como forms SSR hoje dependem do browser, adicione token
CSRF assinado ou header HTMX injetado sem expor o segredo bruto no HTML. Prefira
token CSRF de sessao; nao coloque `hub_auth_token` em query/form.

Defina cookie `Secure` quando request/public URL for HTTPS e preserve HttpOnly,
SameSite e expiracao razoavel.

**Verificar**: cookie-only POST retorna 401/403; POST com CSRF valido passa;
header/bearer API passa; GET autenticado por cookie passa.

### 4. Corrigir o trust model do Banco de Roteiros

`parse_ready_script()` deve preservar texto, mas produzir fact pack
`user_supplied`/`unverified` ate confirmacao explicita. O importador deve receber
e persistir o valor real de `fact_check_confirmed`; default e `False`.

No Hub, exigir checkbox/acao consciente para pular auditor factual. Airtable so
pode marcar confirmado quando o registro possui campo explicito mapeado; score
editorial nao equivale a fact-check.

Nao auto-confirmar originalidade nem publish audit a partir do input mode.
Confirmacoes devem vir de registro humano ou audit real.

**Verificar**: import sem confirmacao nao fica elegivel para auto-publish; com
confirmacao registrada preserva o fluxo; valor enviado deixa de ser ignorado.

### 5. Preservar compatibilidade de artefatos

Adicione novos campos de trust sem remover `facts`, `source_fact_ids` ou nomes de
artifact. Jobs antigos `provider=ready_script/status=verified` devem ser lidos de
forma conservadora e pedir review, salvo evidencia persistida de confirmacao.

**Verificar**: fixture de job antigo abre no Hub e nao quebra; nao e publicado
automaticamente sem evidencia.

## Pronto quando

- [ ] Suite completa e Remotion typecheck passam.
- [ ] Teste concorrente prova um upload.
- [ ] Lease vivo bloqueia reprocess e scene regeneration.
- [ ] Cookie sozinho nao autoriza nenhuma mutacao.
- [ ] Ready script sem confirmacao nao e `verified` nem auto-confirmado.
- [ ] Nenhuma chamada YouTube/TikTok real ocorreu.

## Pare se

- A API do YouTube nao fornecer idempotency key: use claim local, nao improvise
  chamada externa de verificacao no teste.
- A correcao exigir renomear status publico.
- Nao houver como distinguir registros antigos confirmados; migre conservador.

## Manutencao

Reviewers devem conferir atomicidade no banco, nao apenas checks em Python. Todo
novo canal de publicacao deve implementar o mesmo contrato de claim/attempt.
