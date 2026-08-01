# Plano 001: Estabilizar a verificacao canonica

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Execute cada
> passo e confirme o resultado esperado. Atualize `plans/README.md` ao terminar.
>
> **Drift check**: `git diff --stat 08fbea1 -- pyproject.toml tests/conftest.py tests/e2e_support.py tests/test_test_harness_isolation.py README.md`
> Se fixtures ou lifecycle do worker mudaram, pare e reporte antes de editar.

## Status

- **Prioridade**: P0
- **Esforco**: M
- **Risco**: MED
- **Depende de**: nenhum
- **Categoria**: tests / dx
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

A suite usa um `JobOrchestrator` global e inicia seu worker para toda a sessao.
Testes que chamam `process_job()` diretamente podem competir com esse worker e
com outros processos sobre `data-test/`. Um executor precisa de baseline rapido,
deterministico e isolado antes de tocar lifecycle ou pipeline.

## Estado atual

- `tests/conftest.py:11-20` limpa um unico `data-test/`, inicializa o banco e
  inicia o worker global para toda a sessao.
- `tests/e2e_support.py:36-69` define ambiente e importa singleton de app,
  engine e orchestrator no import do modulo.
- `tests/e2e_support.py:132-139` ainda possui `setup_module/teardown_module` que
  tambem limpa dados e inicia/para o mesmo worker.
- `README.md:319-333` define `.venv/bin/python -m pytest -q` como gate canonico.
- O repositorio nao define lint/typecheck Python; o extra dev tem apenas pytest.

Comandos existentes:

| Proposito | Comando | Esperado |
|---|---|---|
| Suite | `.venv/bin/python -m pytest -q` | todos passam |
| Remotion | `cd remotion && npm run typecheck` | exit 0 |
| Status | `git status --short` | so arquivos do plano |

## Escopo

**Pode alterar**:

- `tests/conftest.py`
- `tests/e2e_support.py`
- `tests/test_test_harness_isolation.py`
- testes que dependam explicitamente do worker global
- `pyproject.toml`
- `README.md`

**Nao alterar**: codigo de runtime em `app/`, comportamento de pipeline,
thresholds editoriais, providers ou artefatos.

## Git

- Branch: `advisor/001-verification-baseline`
- Commits sugeridos: `test: isolate worker lifecycle in pytest`; depois
  `chore: document deterministic verification gates`.
- Nao fazer push.

## Passos

### 1. Reproduzir e registrar o baseline sozinho

Garanta que nao existe outro pytest usando `data-test/`. Rode a suite duas vezes
em sequencia. Registre duracao, quantidade e qualquer warning no commit/PR draft.

**Verificar**: `.venv/bin/python -m pytest -q` duas vezes -> mesmo resultado.

### 2. Remover lifecycle duplicado

Escolha um unico owner de setup. Prefira fixtures pytest; remova
`setup_module/teardown_module` de `e2e_support.py`. O worker nao deve iniciar por
default para testes unitarios ou para testes que chamam `process_job()` direto.

Crie fixture explicita `running_worker` para testes que verificam polling/claim.
Ela deve iniciar, aguardar prontidao e parar/join no teardown.

**Verificar**: teste novo confirma que um teste sem fixture nao tem worker vivo;
teste com fixture confirma inicio e parada.

### 3. Isolar dados por sessao/processo

Use diretorio temporario exclusivo por sessao/processo antes de importar os
singletons de `app.db`/`app.main`. Se o import precoce impedir isso, pare e
extraia uma factory de test app apenas em um plano separado; nao recarregue
modulos de forma fragil.

**Verificar**: dois comandos pytest focados executados em paralelo usam bancos e
artifacts diferentes e passam.

### 4. Separar fast lane e suite pesada

Adicione markers para testes que executam pipeline/FFmpeg (`pipeline` ou `slow`).
Mantenha `pytest -q` como gate completo. Documente uma fast lane para iteracao,
por exemplo `pytest -q -m 'not slow'`, sem esconder falhas do gate final.

**Verificar**: fast lane passa e e materialmente mais rapida; suite completa passa.

### 5. Padronizar qualidade Python minima

Adicione Ruff e pip-audit ao extra dev, com configuracao conservadora que nao
force reformatacao massiva. Nao gere lockfile neste passo; isso pertence ao 003.

**Verificar**: `.venv/bin/python -m ruff check app tests scripts` e
`.venv/bin/python -m pip_audit` existem e retornam resultado interpretavel.

## Testes obrigatorios

- Worker desligado por default.
- Fixture liga/desliga worker sem thread residual.
- Dois processos pytest nao compartilham banco/artifacts.
- Falha dentro da fixture ainda executa teardown.
- Suite completa duas vezes sem flake.

## Pronto quando

- [ ] `.venv/bin/python -m pytest -q` passa duas vezes seguidas.
- [ ] `cd remotion && npm run typecheck` passa.
- [ ] Fast lane esta documentada sem substituir o gate completo.
- [ ] Nao ha thread `shortsflow-worker` viva apos pytest.
- [ ] Nenhum arquivo em `app/` foi alterado.

## Pare se

- O isolamento exigir mudar engine/runtime global em `app/db.py`.
- Uma falha reproduzivel for bug real do app, nao da fixture; abra um achado para
  o Plano 002 e nao masque a falha no teste.
- Ruff exigir churn amplo fora dos arquivos tocados.

## Manutencao

Todo teste futuro que dependa de worker deve declarar a fixture. Providers reais
continuam proibidos. O reviewer deve procurar processos/threads residuais e
qualquer `sleep` usado como sincronizacao no lugar de evento/estado observavel.
