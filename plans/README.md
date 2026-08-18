# Planos de Implementacao ShortsFlow

Gerado / reconciliado pela skill `improve` em 2026-08-18, contra **origin/staging `8d9de7a`**.

O lote vigente de **qualidade de roteiro/video** e **017–019** (auditoria 2026-08-18, commit `e1a7cdb`). Execute-os em worktree/branch isolada (`advisor/NNN-<slug>`), com providers mock, sem push e sem YouTube real.

Os planos **010–016** continuam como backlog de ops (lease, YouTube, analytics). Nao misturar com 017–019 no mesmo worktree.

Os planos **000–009** (13/07, commit `08fbea1`) ficam como **backlog historico**. Nao executar 002/003: os pedacos ainda validos foram reescritos em 010–014. Nao executar 006–009: `docs/CONTROL.md` marca multinicho / refactor grande como Not Now.

Relatorio mestre antigo: [000-shortsflow-auditoria-completa.md](000-shortsflow-auditoria-completa.md).

## Ordem vigente — qualidade roteiro/video (2026-08-18)

| Plano | Titulo | Prioridade | Esforco | Depende de | Status |
|---|---|---:|---:|---|---|
<<<<<<< HEAD
| 017 | Restaurar Loop e Payoff na narracao falada | P0 | S | — | DONE |
| 018 | Alinhar ritmo 135–155 WPM e rebase de cortes | P0 | M | — | DONE |
=======
| 017 | Restaurar Loop e Payoff na narracao falada | P0 | S | — | DONE |
| 018 | Alinhar ritmo 135–155 WPM e rebase de cortes | P0 | M | — | DONE |
>>>>>>> origin/advisor/018-ritmo-e-timing
| 019 | Juiz LLM fail-closed | P0 | S | — | DONE |

017, 018 e 019 sao independentes (arquivos diferentes). Podem rodar em worktrees paralelas. Nao tocar `test_pipeline_script.py` nos tres ao mesmo tempo — 018 so edita esse arquivo se um fixture de WPM exigir.

## Backlog ops (010–016)

| Plano | Titulo | Prioridade | Esforco | Depende de | Status |
|---|---|---:|---:|---|---|
| 010 | Preservar lease vivo no reprocesso | P0 | M | — | TODO |
| 011 | Claim atomico antes do upload YouTube | P0 | L | — | TODO |
| 012 | Roteiro pronto nao e fact pack verified | P0 | M | — | TODO |
| 013 | Paginar jobs do Hub no SQL | P1 | M | — | TODO |
| 014 | Tirar o 1+N do sync de Analytics | P1 | M | — | TODO |
| 015 | Isolar timeout de LLM | P1 | L | — | TODO |
| 016 | Reconciliar contratos do operador (docs) | P1 | S | — | TODO |

Status validos: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED: <motivo>`, `REJECTED: <motivo>`.

## Backlog historico (2026-07-13)

| Plano | Titulo | Status |
|---|---|---|
| 001 | Estabilizar a verificacao canonica | HISTORICAL — so reabrir se pytest colidir em `data-test/` |
| 002 | Endurecer autenticacao, leases e publicacao | SUPERSEDED by 010, 011, 012, 016 |
| 003 | Migracoes e consultas quentes | SUPERSEDED in part by 013, 014; Alembic/indexes/tx boundary still deferred |
| 004 | Versionar prompt mestre | HISTORICAL / Not Now |
| 005 | Modularizar pipeline | HISTORICAL — ADR 0004 already landed incrementally |
| 006 | ChannelProfile | HISTORICAL / CONTROL Not Now |
| 007 | Paineis multinicho | HISTORICAL / CONTROL Not Now |
| 008 | Seams de extensao | HISTORICAL / CONTROL Not Now |
| 009 | Loop de retencao / experimentos | HISTORICAL / CONTROL Not Now |

## Dependencias

- 017–019 nao se bloqueiam.
- Nenhum dos 010–016 bloqueia o outro.
- Se a suite inteira interferir em `data-test/`, pare e trate 001 antes de um plano L.
- Nao misture 011 com publicacao real.

## Regras globais para o executor

1. Branch `advisor/NNN-<slug>` em worktree separada, a partir de `origin/staging` (`8d9de7a` ou sucessor). Nao use o `main` local `e1a7cdb` como se fosse staging.
2. Nao renomear estados publicos, chaves de `quality_summary` ou artefatos sem o plano pedir.
3. Conventional Commits pequenos. Sem push, sem PR, sem deploy.
4. `SHORTSFLOW_USE_MOCK_PROVIDERS=true`. Sem provider pago, sem upload.
5. Drift check do plano primeiro. Excerpt diferente = STOP.
6. `git status --short` no fim: so arquivos do escopo + esta linha de status.

## Achados considerados e rejeitados (2026-08-18)

- CSRF / remover cookie em POST: rejeitado. O Hub autentica formularios pelo cookie de `/auth`. O contrato morto era o README. Plano 016 so documenta.
- Cookie `Secure`: adiado. Hub escuta em loopback atras de HTTPS Tailscale; nao e o vazamento do cookie-vs-doc.
- Fatiar `automation.py` / `monetization_pipeline.py` / `llm.py`: Not Now (CONTROL + ADR 0004).
- ChannelProfile / segundo painel: Not Now ate o experimento de um canal.
- Alembic + indices do worker + tirar provider de dentro da transacao: fica no 003 historico; nao entrou nos 7 escolhidos.
- Lint/mypy/lock Python: baixa alavancagem contra lease/upload.
- Remover FFmpeg: ja rejeitado em 13/07.
- Comentario "Marcos policy" em `script_pipeline.py`: o invariante ja esta nas linhas seguintes; sem plano.
