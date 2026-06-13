# Relatorio do objetivo

Data: 2026-06-01

## Objetivo

Fazer as recomendacoes do grill, validar o sistema ponta a ponta, testar principalmente o fluxo de autoaprovacao e publicacao puxando do Banco de Roteiros Prontos, auditar por que os jobs de 2026-05-31 nao foram autopublicados e corrigir bugs.

## Correcoes aplicadas

1. Worker do hub mais resistente a lock de SQLite.
   - `app/orchestrator.py` agora executa tarefas do worker por unidade isolada.
   - Um `sqlite3.OperationalError: database is locked` em manutencao, claim ou sync deixa aquela tarefa ser pulada, mas nao derruba o loop inteiro.
   - Isso protege sincronizacao de publicacoes, claim de jobs e publish local/YouTube contra uma falha lateral.

2. Banco de Roteiros Prontos voltou a ser fonte primaria do ciclo diario.
   - `app/automation.py` seleciona item `available` do banco antes de tema automatico.
   - Similaridade narrativa alta em roteiro do banco virou `high_narrative_similarity_warning`, nao fallback para tema automatico.
   - Tema automatico fica como fallback apenas quando nao ha roteiro `available`.

3. Roteiro do banco consumido nao volta para `available` ou `needs_review` por falha posterior do job.
   - Depois que um item do banco cria Job de Video, ele permanece consumido ou agendado.
   - Falha tecnica passa a exigir recuperacao dirigida do job, sem reciclar silenciosamente o roteiro.

4. Gates editoriais nao bloqueiam roteiro do banco validado humanamente.
   - `app/pipelines/monetization_pipeline.py` embute confirmacoes humanas para banco: `fact_review_confirmed`, `publish_audit_confirmed`, `originality_confirmed` e `metadata_confirmed`.
   - Bloqueios de factualidade, retencao narrativa, metadados, publish audit textual e similaridade viram warnings/diagnostico quando o job veio do banco e o fact check foi confirmado.
   - Bloqueios tecnicos continuam bloqueando: visual, direitos, disclosure de IA, duracao, audio, render, moderacao/input, assets, YouTube e falhas reais de agenda/publicacao.

5. Score de autoaprovacao para banco virou diagnostico.
   - `app/automation.py` ainda calcula e persiste `autoapproval_score.json`.
   - Para `ready_script_bank`, score baixo por criterios editoriais nao impede agendamento.
   - Score tecnico visual baixo continua bloqueando.

6. Visibilidade no hub.
   - `app/templates/jobs.html` mostra blockers da automacao quando o ciclo diario falha.
   - `app/templates/ready_script_bank.html` mostra similaridade como sinal, nao como "pulo".

## Auditoria dos jobs de 2026-05-31

Run auditado: `automation_runs.local_date = 2026-05-31`, `run_id = 195c4e0b-2757-4733-b60f-09a8fa8a8147`.

Resultado do ciclo:

- Status: `failed`
- Erro: `max_generation_attempts_exhausted`
- Alvo de publicacao: `2026-06-01 14:00:00 UTC`
- Tentativas usadas: 3
- Todas as tentativas foram `automatic_topic`, nenhuma foi `ready_script_bank`.

Tentativas:

1. `f4f6c62f-c117-476f-8fa4-2518e6ee62a7`
   - Origem: `automatic_topic`
   - Status: `monetization_review`
   - Motivo: `visual_review_required`
   - Observacao: texto/factualidade passaram; ficou bloqueado por revisao visual, que e gate tecnico/visual valido.

2. `ae1af65e-8e80-442b-ae1d-1baa027c295a`
   - Origem: `automatic_topic`
   - Status: `monetization_review`
   - Motivo: `publish_audit_required`, `visual_review_required`
   - Observacao: estava em simple mode com publish audit pulado; para tema automatico isso ainda exige revisao.

3. `e66f0b88-edd5-4031-8fdb-610b112c4b15`
   - Origem: `automatic_topic`
   - Status: `script_quality_failed`
   - Motivo: `script quality gate failed: repeated_clause`

Causa principal:

O cron de 2026-05-31 nao publicou porque nao gerou nenhum job elegivel a publicacao automatica. Ele tambem nao puxou do banco nesse dia porque, no estado real do banco, nao havia item `available`: a contagem atual auditada mostra `needs_review=12`, `scheduled=8`, `available=0`.

Causa de dominio corrigida:

Antes da correcao, jobs vindos do banco que falhavam depois de consumidos voltavam para `needs_review`, e gates editoriais podiam manter jobs do banco fora de `ready_for_upload`. Isso fazia o banco parecer esgotado e empurrava o ciclo para `automatic_topic`. A regra nova preserva consumo do banco e remove bloqueio editorial automatizado para roteiro de banco validado.

Auditoria de publicacao agendada para 2026-05-31:

- Job `24d27541-6299-457a-a09a-1755aabfc1c3`, origem `ready_script_bank`, foi agendado em `2026-05-28` para `2026-05-31 14:00:00 UTC`.
- `publication_schedules.status` ficou `published`, com `youtube_video_id=PhrYzNpg8BM`.
- O banco local marcou `published_at=2026-05-31 21:02:29`.
- Nao havia entries do servico entre `2026-05-31 13:50` e `14:30` no journal auditado. A primeira atividade do hub no journal de 31/05 apareceu perto de `20:59`, e a sincronizacao/localizacao do status ocorreu por volta de `21:02`.

Conclusao operacional:

Houve dois problemas diferentes:

1. O ciclo diario de 31/05 nao criou job novo publicavel porque caiu para tema automatico e as tres tentativas falharam nos gates.
2. Um job que ja estava agendado para 31/05 foi marcado como publicado localmente tarde, por sync local atrasado do worker/hub. A publicacao no YouTube ficou associada ao `youtube_video_id`, mas o estado local so refletiu isso as `21:02`.

## Validacao executada

Comandos que passaram:

```bash
python -m py_compile app/orchestrator.py app/automation.py app/pipelines/monetization_pipeline.py
.venv/bin/pytest -q tests/test_pipeline_script.py::test_ready_script_selection_clears_stale_similarity_skip tests/test_pipeline_script.py::test_ready_script_selection_treats_high_similarity_as_warning tests/test_hub_publication.py::test_automation_ready_script_bank_score_is_diagnostic_and_schedules tests/test_hub_publication.py::test_ready_script_bank_monetization_embeds_human_editorial_confirmations
.venv/bin/pytest -q tests/test_hub_publication.py tests/test_pipeline_script.py
.venv/bin/pytest -q tests/test_orchestrator_flow.py
git diff --check
```

Resultados:

- Testes focados: 4 passed.
- Hub + pipeline script: 172 passed.
- Orchestrator flow: 56 passed.
- `git diff --check`: sem erro.
- `py_compile`: sem erro.

Observacao sobre suite combinada:

Rodar `tests/test_hub_publication.py tests/test_pipeline_script.py tests/test_orchestrator_flow.py` no mesmo processo teve 224 passes e 4 failures. Dois eram isolamento dos testes novos, corrigidos. Dois eram timeout por fila compartilhada do worker em suite combinada; os mesmos testes passaram isolados e `tests/test_orchestrator_flow.py` passou completo separado.

## Estado esperado apos a correcao

- Se houver roteiro `available` no Banco de Roteiros Prontos, o ciclo diario deve usar banco como origem primaria.
- Similaridade alta do roteiro do banco deve aparecer como warning, nao impedir selecao.
- Score editorial baixo de roteiro do banco deve aparecer como diagnostico, nao impedir agendamento.
- Falha tecnica posterior ao consumo do roteiro deve manter o item consumido e deixar o job para recuperacao.
- Tema automatico so deve ser usado quando o banco estiver esgotado.
