# ShortsFlow

App FastAPI para gerar Shorts verticais em pt-BR, revisar o resultado em um hub web e publicar no YouTube em fluxo manual ou via API.

Explicado para leigos: o ShortsFlow e uma fabrica local de Shorts. Voce entrega uma ideia, titulo ou roteiro; o app transforma isso em roteiro estruturado, imagens, narracao, legenda, musica, video vertical, checklist de publicacao e agenda. A pessoa revisora entra no fim para assistir, aprovar e publicar com seguranca.

O produto atual nao termina em "video pronto". Ele cobre criacao do job, pipeline multimidia, gates de qualidade/factualidade/visual/monetizacao, aprovacao humana, agenda de publicacao, calendario, metadados de upload e integracao OAuth com YouTube.

## Estado atual

- Hub SSR em `http://127.0.0.1:8080`, com lista paginada de jobs, detalhe focado em aprovar e agendar, dashboard de publicacao e calendario mensal.
- Worker em thread, iniciado no lifespan do FastAPI, responsavel pelo pipeline e tambem pela publicacao agendada quando o modo YouTube esta em `api`.
- Banco padrao em SQLite e artefatos em `data/artifacts/<job_id>/`.
- Render principal padrao via Remotion; FFmpeg permanece como caminho legado apenas por configuracao explicita.
- Integracao real com YouTube disponivel por OAuth e upload via API quando o modo API esta ligado no Hub.
- Politica de retencao automatica para artefatos temporarios: jobs continuam visiveis no hub mesmo depois da limpeza dos arquivos pesados.
- Arquitetura modularizada para manutencao local: `JobOrchestrator` coordena lifecycle, lease, retry, eventos e worker; pipelines, providers, contexto do hub e publicacao ficam em modulos donos.
- Testes divididos por dominio para reduzir o custo de regressao e evitar depender de uma suite e2e monolitica para mudancas locais.
- Roteiros agora usam explicitamente `hook`, `loop`, `body_beats`, `payoff` e `ending`; o `full_narration` deve concatenar esses blocos sem perder a tensao nem o fechamento.
- A revisao visual automatica roda por padrao no gate de monetizacao quando aparece `visual_review_required`; se a IA visual confirmar os assets, o relatorio e reconstruido com `visual_review_confirmed`.
- A mesma revisao visual pode remover divida visual de jobs em backlog; se ainda restar revisao factual/editorial, o job fica pendente e o ciclo tenta outro candidato para o mesmo slot.

## Comeco rapido

```bash
git clone https://github.com/marcoscoelhov/shortsflow.git
cd shortsflow

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

cp .env.example .env

cd remotion
npm install
npm run typecheck
cd ..
```

Para rodar sem custo de API:

```env
SHORTSFLOW_USE_MOCK_PROVIDERS=true
SHORTSFLOW_DATABASE_URL=sqlite:///data/shortsflow_render.db
SHORTSFLOW_DATA_DIR=data
```

Para subir o app:

```bash
scripts/install_systemd_service.sh
```

O servico systemd fixa o hub em `127.0.0.1:8080`, reinicia em falhas, roda um
port guard antes do start e habilita `shortsflow-hub-reload.path` para reiniciar
o hub quando arquivos versionados do app mudarem. O instalador renderiza as
units de `deploy/systemd/` com o caminho real do checkout. Para desenvolvimento
manual sem systemd:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Validacao minima:

```bash
curl http://127.0.0.1:8080/healthz
```

## Fluxo do produto

1. `POST /jobs` cria um job.
2. O worker processa `input_gate`, `topic_plan`, `script`, `scene_plan`, `asset_generation`, `tts`, `subtitle_alignment`, `background_music`, `render`, `monetization_readiness_gate` e `publish_to_review_hub`.
3. Durante roteiro e fact pack, assuntos cotidianos de baixo risco podem usar conhecimento comum com linguagem conservadora; ausencia de fact pack nao bloqueia sozinha, mas claims inventados, unsafe ou source IDs falsos continuam bloqueaveis.
4. A primeira cena recebe tratamento de **hook visual**: precisa ser legivel em menos de um segundo, sem texto renderizado e sem entregar o payoff cedo demais.
5. O job termina em `monetization_review`, `blocked_for_monetization` ou `ready_for_upload`.
6. O Hub mostra diagnosticos e artefatos; a decisao humana final de publicacao/revisao acontece no YouTube Studio.
7. Job aprovado vira `approved_for_publish`.
8. O operador pode salvar metadados de upload, agendar data e hora, publicar imediatamente, ou reabrir para republicacao depois de um publish errado.
9. O calendario tambem permite escolher um dia e agendar um job aprovado que ainda nao esteja publicado nem tenha agenda ativa.
10. Quando o modo YouTube esta em `api`, o worker consome agendas vencidas e faz o upload automaticamente.
11. Quando o modo esta em `manual`, o hub continua util para aprovacao, agenda local e registro de publicacao manual.

## Entradas do hub

O formulario principal aceita tres modos:

- `Tema`: assunto bruto. Se ficar vazio, o app tenta buscar tendencia real automaticamente e registra a origem no job.
- `Titulo completo`: promessa editorial fornecida pelo operador, que o app usa como direcao central.
- `Roteiro pronto`: texto rotulado fornecido por uma pessoa e preservado como fonte editorial.

O formato canonico de `Roteiro pronto` e:

```text
Titulo: ...
Hook: ...
Loop: ...
Beats:
- ...
- ...
Payoff: ...
Fechamento: ...
Hashtags: #opcional #opcional
```

Nesse modo, `Titulo` vira metadado, a narracao usa `Hook`, `Loop`, `Beats`, `Payoff` e `Fechamento`, e o app exige confirmacao humana de factualidade antes de aceitar o job. `Loop` e tensao narrativa, nao claim factual a ser mapeada como fonte.

### Prompt viral do Hub

O prompt viral salvo no Hub orienta a camada editorial dos jobs gerados: tipo de hook, ritmo de retencao, escalada dos beats, payoff tardio, tom, SEO e formato semantico do roteiro. Para a lane diaria de **Tema Automatico** (`automatic_topic`), ele deve ser tratado como contrato auditavel aplicado sobre o recorte operacional de astronomia/universo/planetas.

Ele nao troca a origem do job, nao muda credenciais, nao amplia o nicho permitido, nao habilita fallback entre lanes, nao liga publicacao automatica e nao ignora gates de factualidade, direitos, qualidade, visual ou monetizacao. Se o prompt pedir formato externo diferente, o app continua usando o JSON interno obrigatorio.

Detalhes finais de artifact, nomes de campos e reason codes para `automatic_topic` foram validados no smoke E2E (2 ready_for_upload + 1 gate fail com reason acionavel; job_origin=automatic_topic, creation_via=daily_cycle, viral_prompt_source=hub_settings, policy=cosmos). UI pode ainda nao exibir default/custom do prompt em todos lugares; trate como follow-up de UX.

Exemplos curtos para astronomia:

- Bom: `Abra com um paradoxo visual verificavel sobre planetas; crie 3 beats em escalada, sem numeros precisos se nao houver fonte; guarde a explicacao principal para o payoff final.`
- Ruim: `Faca qualquer tema viral, use clickbait, diga que cientistas provaram algo chocante e publique mesmo se o gate reclamar.`

## Estados principais

### Jobs

| Status | Significado |
| --- | --- |
| `queued` | Job criado e aguardando worker. |
| `running` | Pipeline em execucao. |
| `monetization_review` | Render pronto, mas ainda ha diagnosticos operacionais pendentes no Hub. |
| `blocked_for_monetization` | Houve bloqueio de compliance, factualidade, direitos ou qualidade. |
| `ready_for_upload` | Passou nos hard gates e esta pronto para upload/agendamento; revisao final fica no YouTube Studio. |
| `approved_for_publish` | Marcado no Hub como liberado para agenda/publicacao. |
| `published` | Publicado e registrado pelo hub. |
| `rejected` | Reprovado na revisao humana. |
| `failed` | Falha geral no pipeline. |

Tambem existem falhas especificas por etapa, como `script_quality_failed`, `scene_plan_quality_failed`, `asset_quality_failed`, `subtitle_quality_failed` e `render_quality_failed`.

### Agenda de publicacao

| Status | Significado |
| --- | --- |
| `scheduled` | Slot salvo e aguardando horario. |
| `publishing` | Upload em andamento pelo worker. |
| `publish_failed` | Tentativa de publicacao falhou. |
| `published` | Publicacao concluida e registrada. |
| `cancelled` | Agenda limpa ou reaberta para republicacao. |

## Configuracao

O `.env.example` e intencionalmente pequeno. Ele deve guardar boot, infraestrutura e segredos: URL do app, diretorio de dados, banco, chaves de provedores, OAuth do YouTube e Tailnet.

Ajustes operacionais nao secretos ficam no Hub de Revisao, em Configurações:

- LLM principal, fallback, reparo, planejador de cenas e rascunho.
- prompt viral global: contrato editorial para hook, retencao, payoff, tom, SEO e formato semantico dos roteiros gerados.
- gerador de imagens visivel como leitura operacional; hoje, em execucao real, e MiniMax.
- musica de fundo, banco local e fallback para API.
- modo de publicacao, API do YouTube, notificacao de inscritos, publicacao cruzada no TikTok e limite diario de retropostagem.
- horario do ciclo diario, horario padrao de publicacao, janela da agenda, tentativas e score minimo.

O Hub persiste esses valores como sobreposicoes operacionais no banco. Use `Restaurar .env` no modal para limpar as sobreposicoes e voltar aos defaults do ambiente/codigo.

O lease de jobs tem piso operacional longo para passos reais de midia, como imagem, TTS e render. Isso evita que o worker recupere o mesmo job enquanto uma etapa legitima esta demorando e o SQLite pulou heartbeats por lock local.

Quando `SHORTSFLOW_HUB_AUTH_TOKEN` esta configurado, navegacao `GET`/`HEAD` pode usar o cookie `shortsflow_hub_token`, mas mutacoes `POST` exigem `x-shortsflow-hub-token` ou `Authorization: Bearer <token>`. O token do TikTok e manual: o Hub nao gerencia OAuth ou refresh. Metricas de origem de trafego, dispositivo, impressoes e CTR continuam pendentes ate existir adapter real da YouTube Reporting API.

### MiniMax para imagens

A geracao de imagens usa a mesma chave resolvida de texto MiniMax como credencial primaria:

```env
SHORTSFLOW_MINIMAX_TEXT_API_KEY=...
SHORTSFLOW_MINIMAX_IMAGE_API_KEY=...
SHORTSFLOW_MINIMAX_IMAGE_ASPECT_RATIO=9:16
```

`SHORTSFLOW_MINIMAX_IMAGE_API_KEY` e a **Chave Dedicada de Imagem**. Ela so e usada quando a chave de texto retorna limite de provedor, como quota, saldo, credito ou rate limit. Timeout, erro de conexao e `5xx` nao disparam troca de chave. Se nao houver chave de texto configurada, a chave dedicada de imagem e usada diretamente.

### TTS para narracao

Em execucao real atual, o TTS primario operacional pode ser Edge TTS. O Hub permite trocar o TTS primario entre Gemini TTS, ElevenLabs e Edge TTS; a saida continua sendo normalizada para WAV local e `raw.srt` para preservar o contrato das etapas de legendas, mixagem e render.

```env
SHORTSFLOW_TTS_PRIMARY_PROVIDER=edge_tts
SHORTSFLOW_GEMINI_API_KEY=...
SHORTSFLOW_GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
SHORTSFLOW_GEMINI_TTS_VOICE_NAME=Kore
SHORTSFLOW_GEMINI_TTS_VOICE_ROTATION_ENABLED=true
SHORTSFLOW_GEMINI_TTS_STYLE_PROMPT="Narre em portugues brasileiro natural, com ritmo humano de documentario curto, sem soar sintetico ou robotico."
```

Se Gemini TTS falhar ou nao tiver chave, o pipeline tenta ElevenLabs; se ElevenLabs falhar, cai para Edge TTS e registra o fallback nos metadados da narracao. Gemini TTS, ElevenLabs e Edge TTS podem passar como narracao publicavel quando direitos comerciais estiverem confirmados; Edge TTS configurado como primario nao bloqueia elegibilidade automatizada por nome. Quando a rotacao Gemini esta ativa, `SHORTSFLOW_GEMINI_TTS_VOICE_NAME` vira fallback e o provider escolhe uma voz Gemini pelo perfil de narrador do roteiro.

Valide chave e creditos do Gemini TTS com um smoke test isolado:

```bash
.venv/bin/python scripts/smoke_gemini_tts.py
```

O teste so passa quando o provider final e `gemini_tts` e `fallback_used=False`; qualquer queda para ElevenLabs ou Edge retorna exit code diferente de zero e imprime o motivo do fallback sem expor a chave.

Para recuperar um job que ficou bloqueado por TTS tecnico de baixa qualidade ou provider realmente nao publicavel, use o reparo dirigido a partir da etapa de TTS:

```bash
.venv/bin/python scripts/reprocess_job_from_step.py <job_id> --from-step tts
```

Esse comando preserva roteiro e assets, gera nova narração e recalcula legendas, mixagem, render e monetização. No Hub, jobs com `technical_tts_provider_not_publishable` também mostram a ação **Reprocessar TTS e render**; esse codigo nao deve ser emitido apenas porque o provider e `edge_tts` primario.

```env
SHORTSFLOW_TTS_PRIMARY_PROVIDER=elevenlabs
SHORTSFLOW_ELEVENLABS_API_KEY=...
SHORTSFLOW_ELEVENLABS_VOICE_ID=...
SHORTSFLOW_ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

Se `SHORTSFLOW_TTS_PRIMARY_PROVIDER=edge_tts`, o app ignora Gemini e ElevenLabs e usa Edge TTS diretamente como voz primaria publicavel conforme configuracao de direitos.

## Render principal

O backend operacional padrao e Remotion, alinhado ao contrato atual de acabamento premium. O worker chama o binario local em `remotion/node_modules/.bin/remotion`, por isso o setup precisa instalar as dependencias Node do subprojeto antes de rodar Jobs de Video.

Valide Remotion depois de instalar dependencias:

```bash
cd remotion
npm run typecheck
```

Configuracao padrao:

```env
SHORTSFLOW_PRIMARY_BACKEND=remotion
```

O caminho FFmpeg ainda existe para manutencao e diagnostico, mas nao deve ser tratado como default operacional.

No startup, o Hub registra aviso se o runtime Remotion estiver incompleto. `/healthz` tambem expõe `render.remotion_ready` e os itens ausentes.

## YouTube e OAuth

Para upload real via API, coloque apenas credenciais no `.env`:

```env
SHORTSFLOW_USE_MOCK_PROVIDERS=false
SHORTSFLOW_YOUTUBE_CLIENT_ID=...
SHORTSFLOW_YOUTUBE_CLIENT_SECRET=...
SHORTSFLOW_YOUTUBE_CHANNEL_ID=...
```

Depois de subir o app:

1. abra `/youtube/connect`
2. conclua o OAuth do canal
3. verifique o token salvo em `data/youtube_oauth_token.json`
4. no Hub, abra `Configurações` e ligue modo `API` e `API YouTube ativa`
5. use o hub para aprovar, agendar ou publicar

Quando `SHORTSFLOW_YOUTUBE_OAUTH_REDIRECT_URI` estiver vazio, o app usa a URL atual do hub como callback efetivo.

## Artefatos e retencao

Cada job grava arquivos em `data/artifacts/<job_id>/`.

Exemplos comuns:

```text
request.json
topic_plan.json
script.json
scene_plan.json
events.jsonl
render/final.mp4
render/poster.jpg
publish_package.json
publication_schedule.json
youtube_publish_attempts.json
```

O worker tambem executa uma limpeza periodica de artefatos temporarios:

- falha critica: `24h`
- job corrigivel ou reaproveitavel: `7 dias`
- job pronto para publicar ou com agenda ativa: `21 dias`

Essa limpeza remove os arquivos pesados, mas preserva o job no banco e no hub. Quando isso acontece, o detalhe do job mostra aviso de retencao e usa `retention_cleanup.json` para manter metadados e historico basico.

## Interface

Rotas principais:

- `/`: home do hub com formulario, resumo do fluxo e jobs
- `/publication-hub`: centro de publicacao
- `/calendar`: calendario de slots programados e publicados, com atalho para agendar jobs aprovados livres
- `/jobs/{job_id}`: detalhe do job, revisao, agenda, metadados e performance
- `/youtube/connect`: inicio do OAuth
- `/healthz`: healthcheck

## Testes

Lane rapida Ponytail/operacional — barata, sem pipeline pesado, cobre harness de teste, contratos `automatic_topic`, source isolation, Hub/auth/refresh e contrato viral estruturado:

```bash
.venv/bin/python scripts/shortsflow_fast_lane.py
```

Gate estatico Ponytail Ultra — falha se os contratos de simplicidade operacional cairem abaixo de 9.5:

```bash
.venv/bin/python scripts/ponytail_ultra_gate.py
```

Suite principal antes de commit/push:

```bash
.venv/bin/python -m pytest -q
```

A suite esta dividida por dominio. Use a suite completa antes de commit/push e rode fatias focadas durante manutencao:

```bash
.venv/bin/python -m pytest -q tests/test_pipeline_script.py
.venv/bin/python -m pytest -q tests/test_pipeline_assets.py
.venv/bin/python -m pytest -q tests/test_hub_publication.py
.venv/bin/python -m pytest -q tests/test_orchestrator_flow.py
.venv/bin/python -m pytest -q tests/test_providers_integrations.py
```

A cobertura principal inclui:

- pipeline completo ate review
- UI do hub
- aprovacao e agenda
- publish manual e via API
- OAuth do YouTube
- retencao de artefatos

Codigo legado que saiu do runtime ativo fica temporariamente em `legacy/` para auditoria e exclusao futura. Nada ali deve ser importado por app, testes, CLI ou scripts.

## Arquitetura e manutencao por IA

A documentacao de arquitetura fica em:

- [docs/explicacao-para-leigos.md](docs/explicacao-para-leigos.md): explicacao simples do que o app faz e por que existem gates.
- [docs/app.md](docs/app.md): mapa tecnico de modulos, estados, rotas, persistencia e operacao.
- [docs/modularization-plan.md](docs/modularization-plan.md): status da modularizacao forte, contratos preservados e proximos cortes nao bloqueantes.
- [docs/adr/0004-ai-friendly-modular-orchestrator-boundaries.md](docs/adr/0004-ai-friendly-modular-orchestrator-boundaries.md): decisao de manter o orquestrador como casca compatível e delegar dominios para modulos donos.

## Exposicao por Tailscale

Mantendo o app local em uma porta `127.0.0.1`:

```bash
tailscale serve --bg http://127.0.0.1:8080
```

Valide a URL final com:

```bash
curl https://<hostname>.<tailnet>/healthz
```

## Documentacao tecnica

- [docs/explicacao-para-leigos.md](docs/explicacao-para-leigos.md): visao simples para pessoas nao tecnicas
- [docs/app.md](docs/app.md): arquitetura, estados, rotas, persistencia e operacao tecnica
- [docs/runbook-inicializacao.md](docs/runbook-inicializacao.md): passos operacionais para subir, validar e usar o hub
