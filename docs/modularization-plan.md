# Modularizacao Forte IA-friendly

## Objetivo

Reduzir `JobOrchestrator` a uma casca de coordenacao: lifecycle de job, worker, retry, lease, eventos, persistencia comum e delegacao de steps.

As regras de dominio devem morar em pipelines dedicados, mantendo os mesmos artifacts, `quality_summary` e estados publicos.

## Criterio IA-friendly

Uma area e considerada IA-friendly quando uma mudanca comum exige contexto de no maximo dois ou tres arquivos principais, com ownership claro e poucos acoplamentos privados entre modulos.

O objetivo nao e apenas separar arquivos. O modulo deve permitir manutencao local por area, reduzir necessidade de carregar `JobOrchestrator`, `providers.py` ou suites monoliticas inteiras e preservar contratos publicos com testes focados.

## Status

Concluido como baseline estavel. A modularizacao forte esta pronta para manutencao via IA porque os dominios principais ja tem owners explicitos, a suite foi dividida por dominio e os contratos externos do app foram preservados.

Ainda existem cortes incrementais possiveis, mas eles nao bloqueiam a manutencao segura: reduzir imports de compatibilidade do orquestrador e mover rotas SSR para routers mais finos quando isso reduzir a interface aprendida pelos chamadores.

## Corte Implementado

- `app/pipelines/script_pipeline.py`: entrada da etapa `script`.
- `app/pipelines/script_fact_pack.py`: dono de fact pack, queries, OpenAlex e alinhamento factual.
- `app/pipelines/script_audit.py`: dono da auditoria textual pre-assets.
- `app/pipelines/script_repair.py`: dono de pos-processamento, claim trace, consistencia factual e repair do roteiro.
- `app/pipelines/script_metrics.py`: normalizacao de metricas de roteiro.
- `app/pipelines/topic_pipeline.py`: dono de `topic_plan`, historico recente, learning brief, normalizacao e registry de topicos.
- `app/pipelines/scene_pipeline.py`: entrada da etapa `scene_plan` e fallback de cenas.
- `app/pipelines/asset_pipeline.py`: entrada das etapas de assets, TTS, legendas e musica.
- `app/pipelines/image_assets.py`: dono de geracao primaria, normalizacao de URI, score semantico, thresholds e prompts visuais.
- `app/pipelines/tts_assets.py`: dono do ajuste de duracao de TTS, escala de SRT e medicao de audio.
- `app/pipelines/subtitle_assets.py`: dono da segmentacao, reparo de fronteiras, drift e renderizacao de legendas.
- `app/pipelines/music_assets.py`: dono de debug, mix com repair, mix direto, musica de fundo e sound design.
- `app/pipelines/render_pipeline.py`: entrada unica da etapa `render` via Remotion.
- `app/pipelines/monetization_pipeline.py`: entrada da etapa `monetization_readiness_gate`, rights, disclosure, fact claims, repeticao, metadata, publish package, hashtags, readiness e auditoria de publish.
- `app/pipelines/common.py`: exceptions de step e helper `model_payload`.
- `app/providers/`: providers separados por dominio, com imports diretos pelos modulos donos.
- `app/automation.py`: dono do ciclo diario, backlog publicavel, score de autoaprovacao, revisao visual auxiliar automatizada e agendamento automatico por origem de slot.
- `app/publication_ops.py`: dono de review, publicacao, agenda por canal, retencao de artifacts, sync YouTube e fila TikTok.
- `app/hub_context.py`: interface publica do contexto SSR do hub.
- `app/hub_jobs_context.py`, `app/hub_calendar_context.py`, `app/hub_publication_context.py`: implementacao interna especializada, sem cadeias `owner`/`Any`.
- `app/routes/health.py`: router isolado para `/healthz`.
- `tests/`: suites divididas por dominio, com `tests/e2e_support.py` e `tests/conftest.py` para fixtures/helpers compartilhados.

O `JobOrchestrator` continua expondo os mesmos metodos publicos e os mesmos step names. A compatibilidade foi preservada para UI, CLI, automacao, artifacts, estados e scripts operacionais.

Os wrappers privados de dominio do `JobOrchestrator` nao sao API estavel. Testes e manutencao devem chamar o modulo dono diretamente, por exemplo `script_pipeline`, `asset_pipeline`, `scene_pipeline`, `render_pipeline` ou `monetization_pipeline`.

`app/providers/__init__.py` nao reexporta classes antigas. Novas manutencoes devem importar dos modulos donos: `app.providers.llm`, `app.providers.image`, `app.providers.music`, `app.providers.tts` e `app.providers.registry`.

`app.main` ainda concentra rotas SSR principais, mas consome apenas a interface publica de `HubContext`. Mudancas em listas, calendario e publicacao devem comecar no contexto especializado dono, sem expor essa topologia aos chamadores.

O antigo `tests/test_e2e.py` vazio e sua ancora de compatibilidade foram excluidos. Novos testes devem entrar na suite de dominio correspondente: `test_hub_publication.py`, `test_orchestrator_flow.py`, `test_pipeline_assets.py`, `test_pipeline_script.py` ou `test_providers_integrations.py`.

## Tasklist Mestre

- [x] Fase 1: dividir `app.providers` em package por dominio.
- [x] Fase 2: remover ownership de dominio dos wrappers privados do `JobOrchestrator`.
- [x] Fase 3: tornar `subtitle_assets.py` dono de legendas.
- [x] Fase 4: tornar `tts_assets.py` dono de ajuste de duracao e SRT.
- [x] Fase 5: tornar `image_assets.py` dono de assets visuais.
- [x] Fase 6: tornar `music_assets.py` dono de musica de fundo e sound design.
- [x] Fase 7: extrair `topic_plan` do `JobOrchestrator`.
- [x] Fase 8: extrair publicacao, agenda por canal e retencao de artifacts do `JobOrchestrator`.
- [x] Fase 9: dividir `script_pipeline.py` em fact pack, auditoria textual e repair.
- [x] Fase 10: dividir `main.py` em routers e context builders.
- [x] Fase 11: dividir `tests/test_e2e.py` em suites por modulo e arquivar a ancora vazia em `legacy/tests/`.
- [x] Fase 12: mover codigo legado removivel para `legacy/` sem criar imports ativos para essa pasta.
- [x] Fase 13: excluir a quarentena `legacy/` depois de ciclos estaveis e usar o historico Git para recuperacao.

## Evidencia de Validacao

Validacao local permitida para mudancas de codigo:

```bash
SHORTSFLOW_USE_MOCK_PROVIDERS=true .venv/bin/python -m pytest -q <testes-deterministicos>
```

Testes locais devem ser rapidos, deterministicos e sem render pesado. A contagem
de testes nao e um contrato: testes redundantes podem ser podados sem substituir
o criterio de comportamento protegido.

A suite canonica completa roda no workflow
`.github/workflows/deploy-remote-runtime.yml`, no SHA que sera promovido. Chamadas
a providers reais, render de midia e E2E pesado rodam somente no VPS; a estacao
local nunca e fallback de runtime.

Deploy de producao continua exigindo aprovacao humana explicita. Segredos, OAuth,
SQLite e artifacts permanecem no VPS e nao sao copiados para o repositorio.

## Proximos Cortes Seguros

1. Reduzir imports e helpers legados de `app/orchestrator.py` depois de confirmar que nenhum modulo novo depende deles.
2. Avaliar se rotas de publicacao e jobs devem sair de `app/main.py` para routers completos, agora que `HubContext` ja isolou os builders.
3. Manter testes nos seams publicos de `PublicationOperations`, `HubContext` e dominios de script; nao testar `__self__`, MRO, atributos privados ou ausencia de wrappers.
4. Validar upload nativo real no YouTube somente quando houver autorizacao explicita para criar ou agendar conteudo externo no canal.

## Contratos Que Nao Devem Quebrar

- Artifacts: `fact_pack.json`, `script.json`, `scene_plan.json`, `render_output.json`, `monetization_report.json`, `asset_visual_gate.json`, `visual_review_report.json`, `render/edit_plan.json`, `premium_finishing_report.json`.
- Artifacts de publicacao: `publish_package.json`, `publication_schedule.json`, `youtube_publish_attempts.json`, `publish_result.json`.
- Estados terminais ou operacionais: `monetization_review`, `blocked_for_monetization`, `ready_for_upload`, `approved_for_publish`, `published`, `rejected`.
- Chaves de `quality_summary`: `script`, `scene_plan`, `assets`, `render`, `monetization`.
- Eventos em `events.jsonl`.
- Step names em `JobOrchestrator._steps()`, porque aparecem em progresso, telemetria e artifacts.
- Estrutura publica de roteiro: `title`, `hook`, `loop`, `body_beats`, `payoff`, `ending`, `full_narration`, `retention_map`, `claim_trace` e `qa_metrics`.

## Regra Para Novas Mudancas

Antes de editar, identifique o owner do dominio em `docs/app.md`. Se a mudanca exigir abrir `app/orchestrator.py`, `app/main.py` e varios pipelines ao mesmo tempo, provavelmente a fronteira esta vazando e deve ser corrigida com um helper pequeno no modulo dono.

Codigo removido nao deve voltar como facade de compatibilidade sem um consumidor real. Para auditoria ou recuperacao, use o historico Git.
