# Plano 009: Construir loop de viralidade e retencao

> **Estado em 2026-07-31:** ainda nao implementado. O comando `survival-cohort-plan` gera seeds dry-run e nao
> satisfaz assignment persistido, retry estavel, propostas, rollback ou painel descritos neste plano. A lane
> `survival_decisions` nao deve ser apresentada como conclusao deste trabalho.

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Otimize por
> evidencia profile-scoped; nao torne fatos mais agressivos nem publique
> mudancas automaticamente. Atualize `plans/README.md`.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/editorial app/quality app/pipelines/script_pipeline.py app/pipelines/image_assets.py app/performance_ops.py app/models.py benchmarks/editorial app/templates tests`

## Status

- **Prioridade**: P2
- **Esforco**: XL
- **Risco**: HIGH
- **Depende de**: 004, 006, 007
- **Categoria**: growth / editorial / experimentation
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

O app ja produz video, mas o gate viral atual e majoritariamente lexical e pode
premiar palavras de impacto sem melhorar curiosidade, clareza ou payoff. O loop
de crescimento existente gera recomendacoes, mas nao transforma evidencia em
experimentos versionados, aprovaveis e reversiveis.

## Principios

- Agressividade significa contraste, especificidade, ritmo e progressao visual;
  nunca exagero factual, medo artificial ou clickbait sem payoff.
- Fatos e direitos sao hard gates antes da nota de retencao.
- Metricas maduras orientam propostas, nao alteram prompt/policy sozinhas.
- Toda comparacao e por perfil, formato, duracao e coorte comparavel.

## Escopo

**Pode alterar**: retention/editorial policies, gates, script/image candidate
generation, modelos de experimento/proposta, analytics, benchmarks, Hub e testes.

**Nao alterar**: publicacao automatica de experimento sem aprovacao, thresholds
de factualidade/direitos, fabricar dados de performance ou gerar variantes de
video completas em escala antes de medir custo.

## Modelo alvo

- `RetentionProfileVersion`: contrato imutavel de hook, loop, pacing, payoff,
  linguagem e visual grammar por perfil.
- `RetentionExperiment`: hipotese, baseline/candidate, janela, coorte, custo,
  metricas primarias/guardrails e status.
- `GrowthProposal`: evidencia, mudanca estruturada, benchmark, risco, aprovacao,
  versao publicada/rollback.

Metricas primarias sugeridas: hold inicial quando disponivel, average percentage
viewed, completion e rewatch. Guardrails: dislikes/feedback, claims rejeitados,
falhas de gate, custo e tempo de producao. Views isoladas nao bastam.

## Git

- Branch: `advisor/009-retention-loop`
- Commits: models; structural gate; candidates; proposals; dashboard/benchmark.

## Passos

### 1. Instrumentar baseline confiavel

Normalize snapshots por perfil/video, idade da publicacao, duracao e source.
Defina maturidade minima e confidence label; nao compare video de horas com
coorte madura. Registre qual prompt/retention/visual version produziu cada job.

**Verificar**: dados imaturos aparecem como insuficientes e nao geram proposta.

### 2. Substituir score lexical por contrato estrutural

Mantenha checks deterministicos para duracao, repeticao, hook timing, perguntas
sem payoff e densidade. Adicione avaliacao semantica apenas para zona cinzenta,
com rubric versionada e output estruturado. Palavras como "chocante" nao
aumentam score por si.

**Verificar**: benchmark inclui buzzword fraco, hook especifico, payoff ausente,
fato nao suportado e roteiro excelente sem vocabulario sensacionalista.

### 3. Gerar candidatos editoriais limitados

Para cada pauta aprovada, gere ate 3 hooks, 2 open loops e 2 payoffs a partir do
mesmo fact pack. Faca hard-filter factual/direitos e rank por estrutura,
novidade em relacao ao historico e adequacao ao perfil. O pipeline final escolhe
uma combinacao e registra candidatos/rejeicoes.

**Verificar**: nenhum candidato rejeitado por fato entra no roteiro; repeticao
de formula em jobs recentes reduz ranking.

### 4. Aumentar impacto visual nos pontos certos

Gere variantes visuais apenas para hook e payoff, com subject/action/camera,
contraste de escala, continuidade e safe zones. Evite texto embutido, gore,
claims visuais falsos e mudanca de identidade. Selecione antes do render final
por gate visual; nao renderize combinatoria completa.

**Verificar**: maximo de custo/candidatos e enforceado; imagens mantem fato,
direitos, framing vertical e continuidade.

### 5. Transformar learning brief em `GrowthProposal`

Analise coortes maduras e proponha delta estruturado de PromptVersion,
RetentionProfileVersion ou VisualPolicy. Inclua amostra, efeito, incerteza,
guardrails, benchmark e rollback. Humano aprova/rejeita; aprovado cria draft,
nunca edita versao publicada.

**Verificar**: uma proposta nao pode promover a si mesma; audit log liga
evidencia, aprovador, nova versao e experimento.

### 6. Executar experimentos controlados

Comece com um fator por vez e alocacao manual/profile-scoped. Defina antes a
metrica primaria, janela e criterio de parada. Nao use teste estatistico
sofisticado com amostra insuficiente; reporte incerteza e efeito bruto.

**Verificar**: assignment e persistido antes da geracao; retry mantem variante;
rollback restaura binding anterior para novos jobs.

### 7. Criar painel de retencao

Mostre baseline vs candidato, coorte, maturidade, custo, falhas de gate,
propostas pendentes e historico de versoes. Evite ranking global entre nichos.
Acao de aprovar nomeia perfil, delta e janela do experimento.

## Testes obrigatorios

- Benchmark estrutural e factual adversarial.
- Maturidade/coortes/timezone e dados ausentes.
- Candidate limits, custo e determinismo com mock.
- Assignment estavel em retry/reprocess.
- Approval, publish de draft e rollback auditavel.
- Nenhuma proposta cross-profile ou promocao automatica.

## Pronto quando

- [ ] O gate nao recompensa buzzwords isoladas.
- [ ] Jobs registram versoes editoriais/visuais usadas.
- [ ] Variantes de hook/payoff respeitam limites de custo e fatos.
- [ ] GrowthProposal requer aprovacao e possui rollback.
- [ ] Dashboard distingue sinal maduro de ruido.
- [ ] Suite, benchmark v2 e smoke visual passam.

## Pare se

- A plataforma nao fornecer metrica comparavel; registre o gap e use avaliacao
  editorial, sem inventar proxy.
- A melhoria depender de reduzir factualidade, direitos ou review humano.
- O volume nao sustentar experimento; acumule baseline em vez de declarar vencedor.

## Manutencao

Revise rubrics e benchmarks por versao. Retire variantes perdedoras, preserve
receipts e snapshots e limite experimentos simultaneos para manter causalidade.
