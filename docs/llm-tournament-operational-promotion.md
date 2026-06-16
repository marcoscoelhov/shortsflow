# Politica de Promocao Operacional do Torneio de LLMs

## Objetivo

Usar o **Relatorio de Decisao do Torneio** para orientar roteamento de LLMs sem aplicar mudancas automaticamente no Hub.

## Pode mudar manualmente depois de um relatorio

- Provider textual primario para roteiro, reparo ou auditoria, quando o vencedor da etapa tiver `pass_rate >= 0.8`, zero falhas operacionais relevantes e artefatos revisados.
- Fallback textual, quando o candidato tiver bom custo operacional e nao tiver sido eliminado na triagem.
- `timeout-sec` operacional do torneio, se a evidencia mostrar falha por timeout e nao por contrato editorial.
- Lista curta de finalistas para uma rodada seguinte, desde que os eliminados fiquem registrados no relatorio.

## Exige nova rodada antes de promover

- Troca de modelo para todas as etapas quando o **melhor modelo unico** nao cobriu `script`, `repair` e `audit`.
- Promoção de candidato com `pass_rate < 0.8`, falhas de contrato JSON, fonte inventada ou baixa rastreabilidade.
- Mudanca baseada em custo monetario quando `cost_basis` nao incluir tabela de precos versionada.
- Inclusao de modelo que estava `enabled=false`, sem probe real posterior bem-sucedido.

## Exige revisao humana alem da rodada

- Qualquer mudanca que afete publicacao automatizada, elegibilidade automatizada ou auditoria factual.
- Relatorio com riscos em `risks` que mencionem candidatos nao comparaveis, eliminacao por triagem ou falta de vencedor por etapa.
- Caso em que artefatos dos finalistas parecam editorialmente fortes, mas usem linguagem insegura, claim parcialmente suportada ou promessa maior que a evidencia.

## Sequencia recomendada

1. Rodar `--plan-only`.
2. Rodar triagem pequena com 2 ou 3 candidatos.
3. Rodar rodada textual completa com tabela de precos versionada quando houver fonte oficial.
4. Abrir `/llm-tournament` e revisar caminhos do `decision_report.md` e `committee_packet.json`.
5. Aplicar manualmente apenas as mudancas permitidas acima.
6. Rodar regressao focada:

```bash
pytest -q tests/test_llm_tournament.py tests/test_llm_tournament_probe.py tests/test_llm_tournament_runner.py
```

## Notas para a proxima rodada full

Melhorias que nao mudam o criterio do torneio:

- Manter tarefas intercaladas por caso, fixture e candidato para evitar que um provider lento monopolize a fila.
- Usar paralelismo alto como padrao operacional (`--parallelism 24`) e registrar o valor usado no relatorio da rodada.
- Continuar separando ranking por etapa (`script`, `repair`, `audit`), porque o melhor gerador nao necessariamente e o melhor juiz.
- Medir tempo por etapa e por candidato no relatorio para diferenciar gargalo local, timeout de API e corte por budget.

Melhorias que mudam politica e exigem nova rodada comparavel:

- Avaliar `timeout-sec` e `failure_budget` mais agressivos por provider lento, principalmente quando a falha recorrente for timeout ou `provider_limit`.
- Considerar thresholds por tipo de fixture em `audit`; `missed_expected_issue` deve pesar mais que falso positivo simples.
- Promover juiz de `audit` separadamente do provider de `script` e `repair`; nao usar vencedor geral unico se as etapas divergirem.
- Fazer rerun apos ajuste de quota/cap de provider antes de comparar modelos eliminados por `failure_budget_exceeded`.

Pendencias externas antes de outra rodada full:

- Gemini esta autenticando, mas retornou `RESOURCE_EXHAUSTED` por cap mensal do projeto associado a chave.
- DeepSeek respondeu em parte da rodada, mas teve timeouts; validar limite operacional antes de concluir que e problema de credito.
- MiniMax usa a mesma familia de API ja configurada, mas precisa ser avaliado por etapa porque M2 e M3 tiveram comportamento diferente em `audit`.
