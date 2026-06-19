# LLM Tournament Task List

## Objetivo

Implementar o **Torneio de LLMs** como comparacao textual controlada, barata e auditavel, sem juiz LLM automatico em massa. A rodada deve gerar artefatos compactos, aplicar vetos objetivos locais e produzir um **Relatorio de Decisao do Torneio** para o **Comite de Decisao Pos-Torneio**.

## Implementado

- [x] Manifesto versionado de candidatos em `benchmarks/llm/candidates.v1.json`.
- [x] Benchmark editorial versionado em `benchmarks/editorial/benchmark.v1.json`.
- [x] Probe de candidatos com contrato JSON minimo.
- [x] Runner legado de etapa `script`.
- [x] Julgamento opcional de `results.json` existente sem regerar roteiros.
- [x] `--judge-mode none` como caminho padrao para evitar julgamento LLM em massa.
- [x] **Rodada Textual Completa do Torneio** com etapas `script`, `repair` e `audit`.
- [x] **Triagem Textual do Torneio** antes da rodada full.
- [x] **Orcamento de Falha do Torneio** com corte por falhas operacionais.
- [x] Fixtures compactas de `repair` com tres tipos de problema por caso.
- [x] Fixtures compactas de `audit` com decisoes esperadas `approve`, `repair` e `block`.
- [x] Pacote ampliado de fixtures de `repair`: factual, rastreabilidade, estrutura, idioma/estilo e claim irrecuperavel.
- [x] Pacote ampliado de fixtures de `audit`: falso bloqueio, aprovacao indevida, reparo correto, reparo insuficiente e claim parcialmente suportada.
- [x] Vetos objetivos locais para roteiro, reparo e auditoria.
- [x] `committee_packet.json` com finalistas e artefatos representativos.
- [x] `decision_report.json` e `decision_report.md` sem chamadas a provider externo.
- [x] Suporte opcional a **Custo Estimado Versionado** via tabela local de precos.
- [x] Template de tabela em `benchmarks/llm/prices.template.json`.
- [x] Tabela versionada `benchmarks/llm/prices.v1.json` com precos oficiais confirmados e candidatos sem preco marcados como nao precificados.
- [x] `--textual-round` no runner principal.
- [x] `--plan-only` para estimar chamadas antes de gastar quota.
- [x] `--price-table` no runner principal e no gerador de relatorio.
- [x] Comando de comparacao resumida entre dois `decision_report.json`.
- [x] Resumo operacional do ultimo relatorio em `/llm-tournament`.
- [x] Politica de promocao operacional em `docs/llm-tournament-operational-promotion.md`.
- [x] Candidato sem acesso conhecido mantido no manifesto com `enabled=false`.
- [x] ADR do desenho Codex pos-torneio em `docs/adr/0009-codex-post-tournament-committee.md`.
- [x] Testes unitarios e de fluxo para probe, runner textual e relatorio de decisao.

## Falta Executar

- [x] Rodar uma **Triagem Textual do Torneio** real limitada por candidatos para validar custo, timeout e compatibilidade fora de mock.
  Do instead: usar `--candidate` para 2 ou 3 modelos finalistas provaveis antes de rodar todos. Executado em `data/llm_tournament/runs/20260619-121650-textual/textual_triage_results.json`.

- [ ] Gerar o primeiro **Relatorio de Decisao do Torneio** real a partir de uma rodada textual completa.
  Do instead: manter adiado ate haver autorizacao explicita para gasto com providers. A tentativa limitada iniciada em 2026-06-19 foi interrompida antes de gerar `decision_report.md`; nao usar esse run parcial para promocao operacional.

- [ ] Rodar teste de regressao depois de cada rodada real relevante.
  Do instead: executar `pytest -q tests/test_llm_tournament.py tests/test_llm_tournament_probe.py tests/test_llm_tournament_runner.py`.

## Fechamento sem novo gasto em 2026-06-19

A fase operacional foi encerrada sem novas chamadas a LLM depois da decisao de pausar gastos. A unica evidencia real preservada e a triagem limitada `20260619-121650-textual`, com estes resultados:

- `script`: `grok-4.20-non-reasoning` sobreviveu; `minimax-m3` teve 1 timeout em 3 tarefas.
- `repair`: `grok-4.20-non-reasoning` sobreviveu; `minimax-m3` teve timeouts, `provider_limit` e cortes por `failure_budget_exceeded`.
- `audit`: nenhum candidato sobreviveu; os dois acumularam vetos objetivos, principalmente `missed_expected_issue`.

Conclusao operacional: nao promover nenhum modelo a partir dessa evidencia parcial. A proxima acao sem custo e rodar somente `--plan-only` e testes locais. Qualquer rodada real completa precisa de autorizacao explicita.

## Comandos

Planejar sem chamar providers:

```bash
python scripts/run_llm_tournament.py \
  --textual-round \
  --plan-only \
  --timeout-sec 35 \
  --parallelism 2
```

Triagem real pequena:

```bash
python scripts/run_llm_tournament.py \
  --textual-round \
  --triage-only \
  --candidate grok-4.20-non-reasoning \
  --candidate minimax-m3 \
  --timeout-sec 35 \
  --parallelism 2 \
  --max-failures-per-candidate 2
```

Rodada real com tabela de precos, somente com autorizacao explicita para gasto:

```bash
python scripts/run_llm_tournament.py \
  --textual-round \
  --price-table benchmarks/llm/prices.v1.json \
  --triage-mode quick \
  --full-mode full \
  --timeout-sec 35 \
  --parallelism 2 \
  --max-failures-per-candidate 2
```

Gerar relatorio a partir de pacote existente:

```bash
python scripts/build_llm_tournament_decision_report.py \
  data/llm_tournament/runs/<run>/committee_packet.json \
  --price-table benchmarks/llm/prices.v1.json
```

Comparar duas rodadas:

```bash
python scripts/compare_llm_tournament_decision_reports.py \
  data/llm_tournament/runs/<baseline>/decision_report.json \
  data/llm_tournament/runs/<candidate>/decision_report.json
```

## Guardrails

- Nao usar Wikipedia como fonte factual do benchmark.
- Nao reintroduzir juiz LLM por caso como caminho padrao.
- Nao escolher vencedor unico apagando fraquezas por etapa.
- Nao converter tokens para dinheiro sem tabela de precos versionada.
- Nao aplicar recomendacao no Hub automaticamente.
- Nao rodar todos os candidatos sem `--plan-only` antes.
