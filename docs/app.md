# Documentacao do App

YTS Render e um app FastAPI para gerar Shorts verticais em pt-BR, revisar o resultado em um hub web e publicar no YouTube em fluxo manual ou via API.

Em linguagem simples, ele funciona como uma linha de producao local: recebe uma ideia, titulo ou roteiro, cria o pacote completo de um Short, aplica gates de qualidade e deixa uma pessoa decidir quando aprovar, agendar e publicar. A explicacao para pessoas nao tecnicas fica em [docs/explicacao-para-leigos.md](explicacao-para-leigos.md).

## Visao geral

Blocos principais:

- `app/main.py`: rotas FastAPI, SSR com Jinja2, formularios do hub, calendario e OAuth do YouTube.
- `app/hub_context.py`: builders de contexto do hub, listas de jobs, dashboard de publicacao, calendario e status operacional.
- `app/orchestrator.py`: worker, maquina de estados do job, retries, lease, eventos e delegacao de steps.
- `app/publication_ops.py`: review, publicacao, agenda por canal, sync YouTube/TikTok e sweep de retencao de artefatos.
- `app/pipelines/`: etapas especializadas do pipeline.
- `app/providers/`: providers de texto, imagem, TTS, musica e fallback.
- `legacy/`: quarentena temporaria de codigo removido do runtime ativo e mantido apenas para auditoria antes da exclusao.
- `app/routes/`: routers isolados, hoje com `/healthz`.
- `app/youtube_api.py`: integracao OAuth e upload real via YouTube Data API.
- `app/models.py`: persistencia SQLAlchemy de jobs, agenda, review, erros, retries, telemetria e artefatos logicos.

## Fronteiras de manutencao IA-friendly

O app foi modularizado para que uma mudanca comum exija contexto de poucos arquivos e preserve contratos publicos. O ponto de entrada continua sendo `JobOrchestrator`, mas ele deve ser tratado como casca de lifecycle: criar job, reivindicar trabalho, renovar lease, executar retry, registrar eventos, montar progresso e acionar publicacao agendada.

Mapa de ownership para novas mudancas:

| Area | Comece por | Evite comecar por |
| --- | --- | --- |
| Pauta, tendencia, learning brief e registry | `app/pipelines/topic_pipeline.py` | `app/orchestrator.py` |
| Roteiro, fact pack, auditoria textual e repair | `app/pipelines/script_pipeline.py`, `script_fact_pack.py`, `script_audit.py`, `script_repair.py` | `app/orchestrator.py` |
| Cenas | `app/pipelines/scene_pipeline.py` | `app/orchestrator.py` |
| Imagens, TTS, legendas e musica | `app/pipelines/asset_pipeline.py`, `image_assets.py`, `tts_assets.py`, `subtitle_assets.py`, `music_assets.py` | `app/orchestrator.py` |
| Automacao diaria, backlog e autoaprovacao | `app/automation.py` | `app/main.py` |
| Render | `app/pipelines/render_pipeline.py` | `app/orchestrator.py` |
| Monetizacao e pacote de publish | `app/pipelines/monetization_pipeline.py` | `app/main.py` |
| Revisao, agenda, publish, performance, retencao e canais | `app/publication_ops.py` | `app/main.py` |
| Listas, calendario, status operacional e contexto SSR | `app/hub_context.py` | queries inline em templates |
| Providers | `app/providers/llm.py`, `image.py`, `music.py`, `tts.py`, `registry.py` | recriar fachada de reexports em `app.providers` |

`app/providers/__init__.py` e apenas marcador de package. Novas implementacoes devem entrar no modulo dono dentro de `app/providers/`, e consumidores devem importar diretamente desse modulo.

`app/main.py` ainda concentra rotas SSR principais. Para manter o contexto pequeno, novas regras de consulta, agregacao ou apresentacao de estado devem ir para `HubContext` ou para `PublicationOperations`; a rota deve apenas validar formulario, chamar o dono e redirecionar.

Testes novos devem preferir a suite de dominio correspondente: `test_pipeline_script.py`, `test_pipeline_assets.py`, `test_hub_publication.py`, `test_orchestrator_flow.py`, `test_providers_integrations.py` ou `test_deep_modules_unit.py`.

Persistencia local padrao:

- banco: `data/yts_render.db`
- artefatos: `data/artifacts/<job_id>/`
- token OAuth do YouTube: `data/youtube_oauth_token.json`
- state temporario do OAuth: `data/youtube_oauth_state.json`

## Ciclo de vida do job

1. O usuario cria um job pela home ou por `POST /jobs`.
2. `main.py` valida o payload com `TopicRequestCreate` e chama `orchestrator.create_job`.
3. O job entra como `queued`.
4. O worker reivindica jobs pendentes e executa o pipeline.
5. Ao fim, o status do job vira `monetization_review`, `blocked_for_monetization` ou `ready_for_upload`.
6. O revisor abre `/jobs/{job_id}`, assiste ao video, revisa checklist e aprova ou rejeita.
7. Ao aprovar, o job vira `approved_for_publish`.
8. A partir disso, o operador pode salvar metadados de upload, agendar pela pagina do job ou pelo calendario, publicar imediatamente ou reabrir para republicacao.
9. Em modo YouTube `api` no Hub com OAuth conectado, o worker processa slots vencidos e sobe o video no YouTube automaticamente.
10. Em modo `manual`, o hub continua servindo para aprovacao, agenda local e registro de publish manual.

## Modos de entrada

`POST /jobs` recebe tres modos operacionais pelo campo `input_mode`:

- `theme`: assunto bruto. Quando `seed_theme` vem vazio, o hub tenta resolver um tema automatico por tendencias e registra fallback quando nao encontra candidato vivo. O roteiro e gerado por IA a partir da **Pauta Viral Estruturada** persistida em `structured_viral_contract.json`.
- `title`: titulo completo fornecido pelo operador. O app preserva a promessa central, aplica a **Pauta Viral Estruturada** e ainda passa pelo fluxo normal de pauta, roteiro e gates.
- `script`: **Roteiro Pronto** em texto rotulado. O app preserva o texto como fonte editorial e nao chama LLM para gerar outro roteiro.

A **Pauta Viral Estruturada** e o contrato usado para tema/titulo:

```text
Titulo: ...
Hook: ...
Loop: ...
Beats:
- ...
Payoff: ...
Fechamento: ...
Hashtags: ...
```

O provider de roteiro ainda retorna o JSON interno do app, mas esse JSON precisa satisfazer semanticamente os campos do contrato: `title`, `hook`, `loop`, `body_beats`, `payoff`, `ending`, `full_narration`, `retention_map` e os metadados de publicacao. O `full_narration` deve ser a concatenacao fiel de `hook + loop + body_beats + payoff + ending`; se vier com vazamento estrutural ou faltando bloco, o repair normaliza a narracao.

O `Roteiro Pronto` exige estes rotulos:

```text
Titulo: ...
Hook: ...
Loop: ...
Beats:
- ...
Payoff: ...
Fechamento: ...
Hashtags: #opcional
```

Regras importantes desse modo:

- `ready_script_fact_check_confirmed=true` e obrigatorio no hub/API.
- `Titulo` vira metadado, nao narracao.
- a narracao e montada com `Hook`, `Loop`, `Beats`, `Payoff` e `Fechamento`.
- `Loop` e tratado como tensao narrativa, nao como fato declarado.
- `Payoff` e a virada/explicacao do ultimo terco e tambem participa do fechamento do loop.
- fatos declarados entram a partir de `Beats` e `Payoff` sob responsabilidade da confirmacao humana.
- desvios grandes de formato ou duracao bloqueiam antes de midia; o app nao reescreve automaticamente hook, beats, payoff ou fechamento.

## Origem e via de criacao

Cada `Job` persiste dois sinais separados:

- `job_origin`: origem editorial do conteudo, como Banco, Roteiro manual, Auto, Tema manual ou Titulo manual.
- `creation_via`: caminho operacional que criou o job, como Hub, Ciclo diario, CLI, API ou Recriacao.

O Hub exibe esses sinais em portugues na fila, na pagina do job e nos filtros avancados. Jobs historicos sem os campos novos sao inferidos a partir de `TopicRequest.notes` e `AutomationAttempt.source` quando houver evidencia segura; caso contrario, aparecem como origem ou via incerta.

## Estados

### Job

- `queued`: criado e aguardando worker.
- `running`: worker executando o pipeline.
- `monetization_review`: falta revisao humana antes da aprovacao.
- `blocked_for_monetization`: houve bloqueio hard de compliance, factualidade, direitos ou qualidade.
- `ready_for_upload`: passou no gate final e esta pronto para aprovacao humana.
- `approved_for_publish`: aprovado e liberado para agenda/publicacao.
- `published`: publicado e registrado.
- `rejected`: rejeitado na revisao.
- `failed`: falha geral no pipeline.

Falhas especificas por etapa tambem sao estados finais validos:

- `script_quality_failed`
- `scene_plan_quality_failed`
- `asset_quality_failed`
- `subtitle_quality_failed`
- `render_quality_failed`

### Agenda de publicacao

- `scheduled`: slot salvo.
- `publishing`: upload em andamento.
- `publish_failed`: tentativa de upload falhou.
- `published`: upload concluido.
- `cancelled`: agenda limpa ou reaberta para republicacao.

## Pipeline

Etapas atuais de `JobOrchestrator._steps()`:

| Etapa | Retry | Responsabilidade |
| --- | ---: | --- |
| `input_gate` | 0 | Valida entrada basica do job. |
| `topic_plan` | 2 | Gera pauta, angulo, entidades, promessa e candidatos de titulo. |
| `script` | 2 | Gera roteiro e passa pelo `ScriptQualityGate`, com repair quando cabivel. |
| `scene_plan` | 1 | Divide o roteiro em cenas, marca a primeira como **Imagem de Hook Visual** e valida estrutura visual. |
| `asset_generation` | 2 | Gera ou seleciona imagens e aplica score semantico. |
| `tts` | 2 | Gera narracao e metadados basicos de audio. |
| `subtitle_alignment` | 1 | Normaliza legenda e arquivos de render. |
| `background_music` | 1 | Seleciona ou gera trilha, faz mix e valida audio final. |
| `render` | 1 | Gera `render/final.mp4` vertical via Remotion por padrao, com `render/remotion.log`, `render/edit_plan.json` e `premium_finishing_report.json`. |
| `monetization_readiness_gate` | 0 | Consolida direitos, disclosure, factualidade, repeticao e publish readiness. |
| `publish_to_review_hub` | 0 | Persiste o pacote de publicacao e leva o job ao hub. |

A primeira cena carrega a **Imagem de Hook Visual**: o prompt visual deve tornar o hook legivel em menos de um segundo, com contraste, movimento, resultado ou consequencia concreta, sem revelar payoff que ainda nao apareceu no roteiro. Prompts de imagem tambem carregam restricoes fortes contra texto renderizado, marcas, pseudo-letras, telas, copos/embalagens com texto e layouts de painel/split-screen, porque texto acidental em imagem prejudica publicacao e legibilidade.

Cada etapa grava `StepExecution`, eventos em `events.jsonl` e artefatos JSON ou midia no diretorio do job.

Os nomes de etapa, artefatos e chaves principais de `quality_summary` sao contratos publicos do app. Refatoracoes internas podem trocar classes ou helpers, mas nao devem renomear esses contratos sem migracao e teste dedicado.

O auditor `scripts/audit_system_quality.py` trata `topic_plan.quality_metrics` como evidencia explicita. Ele aceita aliases emitidos por provedores diferentes para loop, payoff, replay, promessa verificavel e beats de retencao (incluindo valores booleanos, numericos >= 7 e strings descritivas). O auditor nao infere qualidade editorial apenas por campos textuais completos; se as metricas editoriais nao vierem no artefato, o score de `topic_plan` deve permanecer baixo. `fallback_used=true` continua aparecendo como gap operacional leve.

No estagio `script`, warnings do `ScriptQualityGate` sao expostos como gaps de melhoria mesmo quando `script_quality_gate_pass=true`. Isso acontece especialmente em roteiro pronto preservado: o pipeline pode permitir seguir para revisao humana, mas o auditor ainda precisa explicar por que o score tecnico ficou abaixo do alvo.

## Publicacao e YouTube

Comportamento atual:

- `manual`: o formulario de publish exige `youtube_video_id` ou `youtube_url` e apenas registra a publicacao no hub.
- `api`: o hub pode subir o video direto pela YouTube Data API.
- agenda automatica: so e consumida pelo worker quando o modo efetivo e `api`.
- automacao diaria: um CLI pode gerar ate tres tentativas, autoaprovar apenas `ready_for_upload` com score suficiente e agendar nativamente no YouTube para o primeiro dia vago.

Fluxo OAuth:

- `GET /youtube/connect` cria a URL de autorizacao e persiste `youtube_oauth_state.json`.
- `GET /youtube/oauth/callback` troca `code` por token e salva `youtube_oauth_token.json`.
- `POST /youtube/disconnect` remove token e state locais.
- O status de publicacao e o status de Analytics sao separados: publicar usa `youtube.force-ssl`/`youtube.upload`; leitura da Data API usa `youtube.readonly`; Analytics usa `yt-analytics.readonly`. A YouTube Reporting API ainda nao tem adapter neste app, portanto o status operacional de Reporting permanece `reporting_connected=false` mesmo quando o OAuth de Analytics esta correto.

O Centro de Crescimento do Canal usa `YouTubeAnalyticsSnapshot` para salvar leituras de `reports.query` por Job publicado. A coleta automatica roda fora do request da pagina, via CLI/timer dedicado, e atualiza Jobs publicados com `youtube_video_id` conforme a janela ativa de performance. Cada snapshot guarda metricas base, linhas diarias e, quando a consulta por video permitir, breakdown por pais dentro do JSON do artefato. Origem de trafego, dispositivo, impressoes e CTR ficam marcados como pendencia da YouTube Reporting API ate existir implementacao real de criacao/download de relatorios assincronos.

O Score de Crescimento e deliberadamente simples: `averageViewPercentage` vira o score principal, `views >= 100` marca confianca, e `subscribersGained`, `shares` e `views` servem como desempate. Likes e comentarios aparecem como contexto, mas nao guiam o ranking principal.

A politica de coleta recorrente e:

- Jobs publicados dentro de `performance_sync_active_window_days` sao candidatos diarios quando o snapshot esta ausente ou velho.
- Jobs entre a janela ativa e `performance_sync_archive_window_days` sao candidatos semanais.
- Jobs sem `youtube_video_id` ficam como pendencia operacional, nao como performance ruim.
- A pausa de criacao/publicacao automatizada nao pausa a coleta de performance; use `performance_collection_enabled` para esse controle.

As recomendacoes rapidas do Centro de Crescimento sao deterministicas e auditaveis. O relatorio historico consolidado fica disponivel no Hub e no CLI por `python -m app.cli growth-report`; ele destaca vencedores, piores retencoes, conversao para inscritos e gaps como baixa conversacao, baixo compartilhamento, retencao alta com pouca distribuicao e snapshots zerados. Relatorios de alcance/impressao/CTR dependem da YouTube Reporting API, que e um fluxo separado de relatorios assincronos, nao da chamada sincronica `reports.query`, e ainda nao esta implementada no runtime.

## Scout competitivo de Shorts

O scout competitivo mapeia Shorts publicos de referencia para aprender estruturas de retencao sem copiar texto literal. A fase atual cobre descoberta por canais aprovados, canais informados manualmente ou buscas textuais, enriquecimento via YouTube Data API, filtro de maturidade/duracao/views e persistencia auditavel em banco mais JSON.

Comando operacional:

```bash
python -m app.cli competitive-scout --channel-id UC... --query "curiosidades ciencia shorts" --max-results 25
```

Se nenhum `--channel-id` nem `--query` for informado, o scout usa `ReferenceChannel` com `status=approved` no nicho escolhido. A busca usa `search.list` com `type=video` e `videoDuration=short`, depois valida a duracao real pelo `contentDetails.duration` de `videos.list`; portanto "Short" e tratado como candidato curto e nao como garantia da plataforma.

Quando `competitive_scout_global_enabled=true`, as buscas textuais sao expandidas por regioes fortes em Shorts definidas em `competitive_scout_regions` (padrao: `IN`, `US`, `ID`, `BR`, `MX`, `JP`, `PH`, `VN`, `TH`, `KR`). Para controlar custo e quota, a rodada respeita `competitive_scout_max_query_region_pairs` antes de chamar `search.list` e `competitive_scout_max_analyses_per_run` depois dos filtros de views, duracao e maturidade. Se `competitive_scout_llm_analysis_enabled=false`, a analise dos candidatos usa apenas heuristica local, sem chamada de LLM pago. Os artefatos registram `regions_considered`, `search_requests_considered`, `shorts_matched_filters` e `discovery_contexts` por Short selecionado.

A analise usa o provider LLM primario quando disponivel e cai para heuristica deterministica quando nao houver provider ou quando a resposta falhar. No MVP, referencias externas entram com `transcript_source=none`; transcricao ou download de video externo so devem entrar em uma fase posterior com fonte autorizada ou consentida. Os artefatos ficam em `data/artifacts/scout/<run_id>/` e as tabelas principais sao `reference_channels`, `reference_shorts`, `scout_runs`, `learned_retention_profiles`, `retention_experiments` e `retention_experiment_jobs`.

Depois de uma rodada concluida, o operador pode sintetizar **Perfis de Retencao Aprendidos** por linha editorial. O sistema copia agressivamente o esqueleto estatistico do lote, como sequencia de abertura, movimentos de tensao e contrato de payoff, mas registra explicitamente elementos proibidos de copia literal. Perfis nascem como `pending_approval`; so perfis `approved` ou `promoted` podem iniciar **Experimento de Retencao Aprendida**.

Comandos operacionais:

```bash
python -m app.cli competitive-scout-profiles <run_id>
python -m app.cli retention-profile-approve <profile_id>
python -m app.cli retention-experiment-start <profile_id>
python -m app.cli retention-experiment-evaluate <experiment_id>
python -m app.cli retention-experiment-promote <experiment_id>
```

Enquanto houver experimento `running`, os proximos Jobs do mesmo nicho recebem o esqueleto aprovado nas notas editoriais e sao vinculados em `retention_experiment_jobs`. A avaliacao do experimento usa Analytics proprio do canal, com padrao forte em `retention_experiment_success_retention_percent` (padrao 80%) e volume minimo `retention_experiment_min_views` (padrao 100). Jobs que falham antes de ficarem publicaveis entram como `unpublishable`; snapshots de Analytics ainda sem volume confiavel entram como `measured_low_confidence` e mantem o experimento em `needs_more_data`. Quando o alvo do experimento ja foi preenchido e nao ha Jobs pendentes de publicacao, Analytics ou volume confiavel, isso tambem pode encerrar o experimento como `failed`. O resultado pode ser `success_strong`, `success_partial`, `failed` ou `needs_more_data`.

A promocao final e uma acao humana separada e so aceita experimento com `success_strong`. Quando promovido, o perfil vira `promoted`, arquiva qualquer perfil promovido anterior da mesma linha editorial e passa a orientar Jobs futuros do nicho mesmo sem experimento aberto. Isso ajusta o metaprompt efetivo usado na criacao por meio de notas versionadas do Job, mas nao edita automaticamente a Configuracao Global de Prompt Viral.

O ciclo diario de automacao roda o scout competitivo automaticamente quando `competitive_scout_automation_enabled=true` (padrao). Esse ciclo avalia experimentos em andamento, executa uma nova rodada de scout com canais aprovados e as buscas de `competitive_scout_queries`, e sintetiza perfis para revisao. Por padrao, `competitive_scout_auto_approve_profiles`, `competitive_scout_auto_start_experiments` e `competitive_scout_auto_promote_profiles` ficam desligados para preservar decisao humana; quando ligados explicitamente, o ciclo autoaprova perfis, inicia experimentos ou promove vencedores conforme cada flag. Com o scout global ligado, essas buscas sao repetidas nas regioes configuradas ate o limite de pares busca/regiao. Falha ou ausencia de fonte do scout entra em `AutomationRun.run_metadata.competitive_scout`, mas nao derruba criacao/publicacao do ciclo diario.

No Hub, `POST /competitive-scout/auto-cycle` nao executa mais a rodada dentro do request HTTP. A rota cria uma linha em `competitive_scout_auto_runs`, agenda a execucao em background e redireciona com `scout_auto_run=<id>`. O status persistido fica em `GET /competitive-scout/auto-runs/{auto_run_id}` e tambem aparece no Centro de Crescimento; o fragmento ja atualiza a cada 30s.

Para rodar apenas o scout automatico, sem criar Job nem agenda:

```bash
python -m app.cli competitive-scout-auto-cycle
```

## Publicacao cruzada no TikTok

Quando `YTS_TIKTOK_AUTO_PUBLISH_ENABLED=true`, jobs que ja entraram na agenda ou publicacao do YouTube ganham um registro em `ChannelPublication` para o canal `tiktok`. Jobs com agenda futura seguem o mesmo horario planejado; jobs ja publicados entram em retropostagem controlada, limitada por `YTS_TIKTOK_RETROPOST_DAILY_LIMIT` (padrao 1 por dia).

O envio usa a Content Posting API oficial do TikTok com `YTS_TIKTOK_ACCESS_TOKEN` e escopo `video.publish`. Esse token e configurado manualmente no ambiente; o Hub nao gerencia OAuth, refresh token nem ciclo de renovacao do TikTok. A API exige consulta de creator info, privacidade compativel com a conta e pode restringir clientes nao auditados a publicacoes privadas; essas recusas ficam registradas como `publish_failed` no canal TikTok.

O contexto de integracao exposto no hub usa:

- `publish_mode`
- `api_enabled`
- `connected`
- `publish_connected`
- `analytics_connected`
- `analytics_missing_items`
- `channel_id`
- `missing_items`
- `connected_at`
- `token_expires_at`

## Rotas principais

| Metodo | Rota | Uso |
| --- | --- | --- |
| `GET` | `/` | Home do hub com formulario, jobs e resumo operacional. |
| `POST` | `/hub/prompt` | Salva ou reseta o template viral do hub. |
| `GET` | `/jobs` | Pagina completa da fila; quando `HX-Request=true`, retorna apenas o fragmento HTML da tabela paginada. |
| `GET` | `/publication-hub` | Centro de Crescimento do Canal com estatisticas, Analytics e orientacao editorial. |
| `GET` | `/publication-hub/fragment` | Fragmento HTMX do Centro de Crescimento do Canal. |
| `GET` | `/library` | Pagina de Biblioteca de Roteiros para importar e acompanhar o Banco de Roteiros Prontos. |
| `GET` | `/settings` | Pagina de configuracoes operacionais do hub. |
| `GET` | `/youtube/connect` | Inicia OAuth do YouTube. |
| `GET` | `/youtube/oauth/callback` | Conclui OAuth do YouTube. |
| `POST` | `/youtube/disconnect` | Remove token OAuth local. |
| `GET` | `/calendar` | Calendario mensal de programados, publicados e jobs aprovados livres para agendar. |
| `POST` | `/calendar/schedule` | Agenda um job aprovado a partir do dia escolhido no calendario. |
| `POST` | `/automation/toggle` | Liga ou pausa a automacao diaria. |
| `POST` | `/automation/run` | Executa um ciclo de automacao sob demanda. |
| `POST` | `/automation/ready-scripts/import` | Importa lote de roteiros prontos confirmados. |
| `POST` | `/jobs` | Cria novo job. |
| `GET` | `/api/jobs/{job_id}` | JSON compacto com status e render. |
| `GET` | `/jobs/{job_id}` | Detalhe do job com revisao, agenda e metadados. |
| `POST` | `/jobs/{job_id}/review` | Aprova, rejeita ou cria retry integral. |
| `POST` | `/jobs/{job_id}/publish-metadata` | Salva titulo, descricao e hashtags de upload. |
| `POST` | `/jobs/{job_id}/publish` | Publica agora ou registra publicacao manual. |
| `POST` | `/jobs/{job_id}/schedule` | Salva ou limpa agenda local. |
| `POST` | `/jobs/{job_id}/reopen-publication` | Reabre um publish para republicacao. |
| `POST` | `/jobs/{job_id}/performance` | Registra metricas manuais do YouTube Studio. |
| `POST` | `/jobs/{job_id}/youtube-analytics/sync` | Sincroniza snapshot de Analytics do YouTube para um job publicado com `youtube_video_id`. |
| `POST` | `/youtube-analytics/sync-due` | Sincroniza o lote de Jobs publicados que ja estao elegiveis para nova coleta. |
| `POST` | `/competitive-scout/auto-cycle` | Enfileira uma rodada manual assíncrona do scout competitivo. |
| `GET` | `/competitive-scout/auto-runs/{auto_run_id}` | Consulta status persistido da rodada manual do scout competitivo. |
| `GET` | `/healthz` | Healthcheck do app. |

Arquivos sob `data/artifacts/` sao servidos por `/artifacts/...` quando ainda existem.

## Configuracao

`app/config.py` e a fonte de verdade para `Settings`.

Defaults importantes:

- `app_url=http://127.0.0.1:8080`
- `niche_id=curiosidades`
- `language=pt-BR`
- `target_duration_sec=50`
- `llm_primary_provider=deepseek`
- `llm_fallback_provider=deepseek`
- `youtube_publish_mode=manual`
- `youtube_api_enabled=false`
- `automation_enabled=false`
- `automation_daily_timezone=America/Sao_Paulo`
- `automation_daily_run_time=02:00`
- `automation_publish_time=11:00`
- `performance_collection_enabled=true`
- `performance_sync_active_window_days=45`
- `performance_sync_archive_window_days=180`
- `performance_sync_batch_limit=10`
- `artifact_retention_enabled=true`

Camadas de configuracao:

- `.env`: boot, infraestrutura e segredos. Inclui `YTS_APP_URL`, `YTS_HUB_AUTH_TOKEN`, `YTS_DATABASE_URL`, chaves de provedores, OAuth do YouTube, token manual do TikTok e exposicao Tailnet.
- Hub de Revisao: ajustes operacionais nao secretos. Inclui LLM ativo, fallback de LLM, planejador de cenas, fonte de musica, autopopulacao do banco local, TTS primario, modo de publicacao, API do YouTube, publicacao cruzada no TikTok, horario do ciclo diario, horario padrao de publicacao, janela da agenda, score minimo e coleta de performance. O gerador de imagens aparece como informacao operacional; hoje, em execucao real, ele e MiniMax.
- defaults do codigo: valores seguros usados quando nem `.env` nem Hub definem uma sobreposicao.

Quando `YTS_HUB_AUTH_TOKEN` esta configurado, requisicoes `GET` e `HEAD` aceitam o cookie `yts_hub_token` para navegacao. Requisicoes `POST` exigem `x-yts-hub-token` ou `Authorization: Bearer <token>`; cookie nao autentica mutacoes por desenho.

As sobreposicoes do Hub ficam na tabela `operational_settings`. Elas sao aplicadas no startup do FastAPI e nos comandos `yts-render automation-run` e `yts-render analytics-sync-run`. Segredos nunca devem ser adicionados a essa tabela; novos campos editaveis precisam entrar pela allowlist em `app/operational_settings.py`.

Terminologia do painel:

- **Planejador de cenas (LLM)**: escolhe o LLM que cria `scene_plan.json`, com cenas, intencao visual e prompts. Ele nao gera imagens.
- **Gerador de imagens**: provider que gera ou seleciona os assets visuais no passo `asset_generation`. Hoje, em execucao real, e MiniMax; por isso aparece como leitura operacional, nao como seletor editavel.
- **TTS primario**: escolhe o provider principal da narracao. Gemini TTS e o padrao; ElevenLabs e publicavel quando configurado; Edge TTS e emergencia e bloqueia elegibilidade automatizada.

Musica de fundo:

Fact pack e politica factual:

- temas `factual_strict` ou claims sensiveis exigem fontes verificadas ou revisao
- temas de curiosidade cotidiana de baixo risco podem usar `common_knowledge` quando `viral_truth_policy.automatic_publish_allowed=true`
- observacoes comuns de produtos domesticos, como celular, tela, controle remoto, escova, ventilador, elevador, fone e micro-ondas, podem entrar nessa politica quando nao falam de plataforma, marca, preco, estatistica, percentual ou taxa
- `micro-ondas` e normalizado como `micro ondas` antes do match factual, portanto regras novas devem considerar pontuacao removida
- mesmo em politica de baixo risco, numeros precisos, datas, claims medicos, financeiros, juridicos, engenharia especifica e fontes inventadas continuam bloqueaveis

Musica de fundo:

- o padrao e banco local, alteravel no Hub de Revisao
- `local_bank` le `YTS_MUSIC_BANK_DIR/manifest.json` e usa apenas faixas aprovadas para YouTube, com licenca ou origem rastreavel
- a autopopulacao do banco local pode ser ligada ou desligada no Hub
- trilhas MiniMax antigas podem ser importadas com `scripts/import_minimax_music_artifacts.py` e recebem prioridade sobre as sinteticas locais
- o fallback para API fica desligado por padrao para impedir custo silencioso quando o banco local falha
- `minimax` força MiniMax Music como fonte primaria
- `auto` tenta o banco local e depois MiniMax, quando houver chave
- o manifest pode ser uma lista ou um objeto com `tracks`; cada item deve ter `path`, `license` ou `license_note`, `source_url` ou `license_file`, `approved_for_youtube=true`, e nao deve estar marcado como Content ID registrado
- veja `docs/music-bank.md` para o formato recomendado do banco local

Credenciais MiniMax por midia:

- texto usa `YTS_MINIMAX_TEXT_API_KEY` ou `YTS_MINIMAX_API_KEY`
- imagem tenta primeiro a chave resolvida de texto
- imagem usa `YTS_MINIMAX_IMAGE_API_KEY` so depois de limite ou quota na chave de texto, e marca essa chave como esgotada para o job atual
- se nao houver chave de texto, imagem usa diretamente `YTS_MINIMAX_IMAGE_API_KEY`
- musica usa `YTS_MINIMAX_MUSIC_API_KEY` ou a chave resolvida de texto apenas quando MiniMax Music esta configurado como provider ou fallback
- narracao usa Gemini TTS quando `YTS_TTS_PRIMARY_PROVIDER=gemini_tts` ou a sobreposicao do Hub escolhe `gemini_tts`, e `YTS_GEMINI_TTS_API_KEY` ou `YTS_GEMINI_API_KEY` esta configurada; por padrao, escolhe uma voz Gemini pelo perfil de narrador do roteiro e registra a decisao em `narration_asset.json`; se Gemini falhar, tenta ElevenLabs
- narracao usa ElevenLabs quando `YTS_TTS_PRIMARY_PROVIDER=elevenlabs` ou a sobreposicao do Hub escolhe `elevenlabs`, e `YTS_ELEVENLABS_API_KEY` esta configurada; se ElevenLabs falhar, cai para Edge TTS e registra o fallback nos metadados
- `edge_tts` pode ser selecionado como emergencia, mas e tratado como provider tecnico e bloqueia elegibilidade automatizada

Limite de provedor para troca de chave de imagem significa quota, saldo, credito ou rate limit. Timeout, erro de conexao, resposta invalida e `5xx` continuam sendo falhas transientes da chamada atual.

## Persistencia e artefatos

Modelos principais:

- `Job`
- `TopicRequest`
- `TopicPlan`
- `Script`
- `ScenePlan`
- `SceneAsset`
- `NarrationAsset`
- `SubtitleTrack`
- `BackgroundMusicAsset`
- `RenderOutput`
- `PublicationSchedule`
- `ChannelPublication`
- `ReviewRecord`
- `PerformanceMetric`
- `YouTubeAnalyticsSnapshot`
- `FallbackEvent`
- `ErrorLog`
- `StepExecution`
- `TopicRegistry`

Artefatos comuns por job:

```text
request.json
topic_plan.json
script.json
scene_plan.json
events.jsonl
publish_package.json
publish_metadata_overrides.json
publication_schedule.json
youtube_publish_attempts.json
publish_result.json
asset_visual_gate.json
visual_review_report.json
render/final.mp4
render/poster.jpg
render/remotion.log
render/edit_plan.json
premium_finishing_report.json
```

Como Remotion e o backend padrao por ADR-0012, o ambiente operacional precisa ter `npm install` executado dentro de `remotion/`. Quando `YTS_RENDER_PRIMARY_BACKEND=ffmpeg` for usado para manutencao legado, os artefatos voltam a incluir `render/ffmpeg.log` e `render_motion_plan.json`.

O boot do Hub roda um preflight do Remotion antes de iniciar o worker e registra aviso claro se `remotion/node_modules/.bin/remotion`, `remotion/src/index.ts` ou `remotion/package-lock.json` estiverem ausentes. `/healthz` tambem expõe `render.primary_backend`, `render.remotion_ready` e `render.remotion_missing_items`.

`artifact_url()` converte `file://...` dentro de `data/artifacts/` para `/artifacts/...`. Quando o arquivo ja foi removido, a UI nao renderiza link quebrado.

## Retencao automatica

O worker roda sweep periodico de retencao e classifica jobs em tres grupos:

- `hard_failure`: `24h`
- `recoverable`: `168h`
- `publishable`: `504h`

Regra atual:

- falhas criticas de pipeline entram no grupo curto
- `monetization_review`, `blocked_for_monetization`, `rejected` e `publish_failed` entram no grupo medio
- `ready_for_upload`, `approved_for_publish` e agendas `scheduled` entram no grupo longo
- `queued`, `running`, `publishing`, `published` e `cancelled` ficam fora do cleanup automatico

Quando o TTL vence:

1. o diretorio de artefatos do job e removido
2. o app grava `retention_cleanup.json`
3. o job preserva `quality_summary.retention`
4. o hub continua mostrando metadados e historico leve, mas esconde midia pesada

## Interface

Templates ativos:

- `app/templates/base.html`
- `app/templates/jobs.html`
- `app/templates/jobs_table.html`
- `app/templates/publication_dashboard.html`
- `app/templates/calendar.html`
- `app/templates/job_detail.html`

A job page atual e deliberadamente centrada em decisao:

1. assistir o video
2. aprovar
3. agendar ou publicar

Conteudo tecnico, erros e artefatos ficam colapsados em paines secundarios.

Quando existir `visual_review_report.json`, o detalhe do job mostra a **Revisao visual auxiliar** dentro de "Qualidade e monetizacao". Esse relatorio e evidencia para a pessoa revisora; ele nao muda sozinho agenda ou aprovacao.

A etapa `monetization_readiness_gate` roda revisao visual auxiliar por padrao quando o primeiro relatorio aponta `visual_review_required`. Se a IA visual consegue confirmar os assets, o relatorio de monetizacao e reconstruido com `visual_review_confirmed` antes de gravar o status final. Se o verificador visual estiver indisponivel, falhar ou devolver apenas heuristica de prompt, o job continua pedindo revisao visual humana.

Na automacao, a mesma revisao visual auxiliar tambem pode ser usada para backlog. Ela pode confirmar `visual_review_confirmed` e reconstruir o relatorio de monetizacao. Se a unica pendencia era visual, o job pode avancar para autoaprovacao. Se ainda restar `fact_review_required`, publish audit ou outra revisao manual, o job permanece em `monetization_review` e o ciclo diario tenta o proximo candidato do mesmo slot, em vez de desperdicancar a janela de publicacao.

`/jobs` e uma rota de navegacao direta e precisa entregar o shell completo do **Console Operacional**. O mesmo endpoint tambem serve `jobs_table.html` para atualizacoes HTMX da fila quando a requisicao carrega `HX-Request=true`; sem esse header, retornar apenas o fragmento e regressao visual.

O calendario e uma superficie operacional secundaria. Ele mostra slots programados e publicados, mas tambem abre um modal de agenda pelo botao `+` de cada dia do mes atual. Esse modal lista apenas jobs em `approved_for_publish` que ainda nao estejam publicados nem tenham agenda ativa.

## Automacao diaria

A automacao diaria roda por CLI e systemd timer, nao por scheduler interno do FastAPI:

```bash
python -m app.cli automation-run
python -m app.cli analytics-sync-run
scripts/install_automation_timer.sh
scripts/install_analytics_sync_timer.sh
```

O ciclo verifica pausa global, preflight do YouTube API, lock por data local de Sao Paulo e janela de agenda a partir de amanha. A agenda automatica trabalha com dois slots diarios: o horario configurado (`automation_publish_time`) e reservado para **Banco de Roteiros Prontos**, e o segundo slot e fixo as 18:00 de Brasilia para **Tema Automatico**. O ciclo considera somente o primeiro dia incompleto e tenta preencher os dois horarios antes de avancar para datas posteriores. No slot das 18h, **Tema Automatico** e a fonte preferida; se ele falhar e ainda houver tentativa disponivel, o ciclo usa o **Banco de Roteiros Prontos** como fallback. Antes de gerar conteudo novo, o ciclo tenta backlog publicavel compativel com a fonte preferida ou de fallback.

Jobs criados pelo **Ciclo Diario de Automacao** ja nascem com lease exclusivo do processo CLI. Assim, o worker do Hub nao pode reivindicar e processar o mesmo Job em paralelo. Se o processo morrer, o lease expira e o worker pode recuperar o Job normalmente. Um ciclo que agenda apenas parte do dia registra `schedule_complete=false` e `unfilled_slots`; uma nova execucao no mesmo dia pode retomar essa agenda sem exigir `--force`.

O backlog e avaliado por candidato, nao apenas por slot. Quando um candidato parcial passa na revisao visual automatica mas continua com revisao factual/manual pendente, a tentativa fica registrada como `not_eligible` e o loop continua para outro candidato compativel. Isso preserva o ganho de remover divida visual sem bloquear um job realmente publicavel que esteja logo atras na fila.

Falhas e reparos parciais relevantes entram em `AutomationRun.metadata.automation_notifications` e aparecem pelo icone de notificacoes da topbar. A fila de jobs permanece limpa; o operador deve abrir a notificacao para ver o candidato, a pendencia restante e o link do job.

Um job so entra em publicacao automatizada se terminar em `ready_for_upload`, passar no score composto minimo de `0.82`, nao tiver repeticao alta e cumprir os thresholds de factualidade, retencao, metadados e assets. Ao passar, o sistema aprova o job e usa agendamento nativo do YouTube com `publishAt` no horario do slot em `America/Sao_Paulo`; isso registra agenda `scheduled`, nao `published`.

O lease do worker tem piso de uma hora e heartbeat menos agressivo. Passos reais de imagem, TTS e Remotion/ffmpeg podem segurar SQLite por minutos; esse piso evita que outro worker recupere o mesmo job por heartbeat pulado enquanto a etapa ainda esta legitimamente em execucao.

## Coleta de performance

A coleta de performance e separada da automacao de criacao/publicacao. O comando abaixo busca apenas snapshots de Analytics para Jobs publicados elegiveis:

```bash
python -m app.cli analytics-sync-run
scripts/install_analytics_sync_timer.sh
```

O timer roda as 03h em `America/Sao_Paulo`, depois do ciclo diario principal. A rotina respeita `performance_collection_enabled`, exige OAuth com escopo de Analytics e limita o lote por `performance_sync_batch_limit`.

Para auditar a base consolidada sem abrir o Hub:

```bash
python -m app.cli growth-report --minimum-views 100
```

## Testes

A suite principal foi dividida por dominio. Os testes ativos vivem em:

- `tests/test_hub_publication.py`: hub, calendario, agenda, publish, OAuth e automacao.
- `tests/test_orchestrator_flow.py`: lifecycle, worker, estados, retries e fluxo completo.
- `tests/test_pipeline_assets.py`: cenas, assets, TTS, legendas, musica e render.
- `tests/test_pipeline_script.py`: roteiro, fact pack, auditoria textual, repair e monetizacao textual.
- `tests/test_providers_integrations.py`: providers e registries.
- `tests/e2e_support.py` e `tests/conftest.py`: fixtures e helpers compartilhados.

Comando padrao:

```bash
.venv/bin/python -m pytest -q
```

## Onde alterar

Para mudar UX do hub:

- `app/main.py`
- `app/hub_context.py`
- `app/templates/*.html`
- `app/static/styles.css`

Para mudar publicacao e YouTube:

- `app/publication_ops.py`
- `app/youtube_api.py`
- `app/schemas.py`

Para mudar automacao diaria:

- `app/automation.py`
- `app/cli.py`
- `app/models.py`
- `app/templates/publication_dashboard.html`

Para mudar regras de retencao:

- `app/config.py`
- `app/publication_ops.py`
- `app/storage.py`
