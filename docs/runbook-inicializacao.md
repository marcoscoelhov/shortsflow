# Runbook de Inicializacao

Este runbook serve para retomar o projeto, subir o hub e validar o fluxo atual de geracao, aprovacao e publicacao.

Para uma visao nao tecnica do produto, leia tambem [explicacao-para-leigos.md](explicacao-para-leigos.md). Em resumo: o app pega uma ideia, titulo ou roteiro de Short, gera o pacote de video vertical, aplica gates de seguranca/publicacao e deixa uma pessoa revisar, aprovar, agendar e publicar.

## 1. Entrar no projeto

```bash
cd /root/shortsflow
git status --short --branch
```

## 2. Preparar o ambiente Python

Se a venv ja existir:

```bash
source .venv/bin/activate
```

Se estiver em maquina nova:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 3. Preparar `.env`

Copie o exemplo:

```bash
cp .env.example .env
```

### Mock local

```env
SHORTSFLOW_USE_MOCK_PROVIDERS=true
SHORTSFLOW_DATABASE_URL=sqlite:///data/shortsflow.db
SHORTSFLOW_DATA_DIR=data
```

### Providers reais

```env
SHORTSFLOW_USE_MOCK_PROVIDERS=false
SHORTSFLOW_OPENAI_API_KEY=...
SHORTSFLOW_MINIMAX_TEXT_API_KEY=...
SHORTSFLOW_MINIMAX_IMAGE_API_KEY=...
```

Para imagem, a chave de texto MiniMax e usada primeiro. `SHORTSFLOW_MINIMAX_IMAGE_API_KEY` funciona como chave dedicada de imagem e entra apenas quando a chave de texto retorna quota, saldo, credito ou rate limit. Se a chave de texto estiver vazia, a dedicada de imagem e usada diretamente.

### Upload real no YouTube

```env
SHORTSFLOW_YOUTUBE_CLIENT_ID=...
SHORTSFLOW_YOUTUBE_CLIENT_SECRET=...
SHORTSFLOW_YOUTUBE_CHANNEL_ID=...
```

Depois de subir o hub, ajuste LLM principal, musica, automacao, modo de publicacao e API do YouTube no modal `Configurações`. Mudancas no Hub nao exigem editar `.env`; mudancas de segredos ou URLs de boot ainda exigem reiniciar o `uvicorn`.

## 4. Subir o hub

Padrao operacional com systemd:

```bash
scripts/install_systemd_service.sh
```

O servico fixa o hub em `127.0.0.1:8080` e executa um port guard antes do
start. O guard libera a porta somente quando o processo ocupando `8080`
parece ser uma instancia anterior do proprio ShortsFlow; processos de outro
app fazem o start falhar em vez de serem mortos silenciosamente. O instalador
tambem habilita `shortsflow-hub-reload.path`, que observa `app/`, `scripts/`,
`deploy/systemd/`, `.env` e `pyproject.toml` e reinicia o hub quando esses
arquivos mudam. As units versionadas em `deploy/systemd/` sao renderizadas pelo
instalador com o caminho real do checkout.

Para operacao manual sem systemd:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Nao use uma porta alternativa para o hub principal sem atualizar tambem
Tailscale, `SHORTSFLOW_APP_URL` e os links operacionais. Se `8080` estiver ocupada,
identifique o dono da porta antes de subir outro hub:

```bash
ss -ltnp '( sport = :8080 )'
```

## 5. Validar que iniciou corretamente

Com systemd:

```bash
systemctl status shortsflow-hub.service --no-pager
```

```bash
curl http://127.0.0.1:8080/healthz
```

Resposta esperada:

```json
{"status":"ok","app":"ShortsFlow","bind":"127.0.0.1:8080","tailnet_url":"https://shorts-hub.example.ts.net","render":{"primary_backend":"remotion","remotion_ready":true,"remotion_missing_items":[]}}
```

Se estiver usando outra porta, ajuste a URL do `curl`.

## 6. Abrir o hub

- Home: `http://127.0.0.1:8080/`
- Centro de publicacao: `http://127.0.0.1:8080/publication-hub`
- Calendario: `http://127.0.0.1:8080/calendar`

## 7. Criar um job

Pelo navegador, use o formulario da home.

Modos disponiveis no hub:

- `Tema`: preencha um assunto ou deixe vazio para o app buscar tendencia real automaticamente.
- `Titulo completo`: use quando ja existe uma promessa editorial pronta, mas o app ainda deve gerar o roteiro.
- `Roteiro pronto`: use texto rotulado e confirme que os fatos ja foram revisados antes do envio.

Formato de `Roteiro pronto`:

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

Nesse modo, `Loop` faz parte da narracao como tensao editorial. `Payoff` e a virada/explicacao do ultimo terco. Os fatos declarados ficam nos beats e no payoff, e a narracao final deve concatenar `Hook + Loop + Beats + Payoff + Fechamento`.

Via `curl`:

```bash
curl -i -X POST http://127.0.0.1:8080/jobs \
  -F seed_theme="polvos" \
  -F target_duration_sec=50 \
  -F tone="intrigante_direto" \
  -F cta_style="none"
```

O `location` aponta para `/jobs/<job_id>`.

## 8. Acompanhar o estado correto

O job nao vai mais para `waiting_review`.

Estados esperados depois do pipeline:

- `monetization_review`
- `blocked_for_monetization`
- `ready_for_upload`

`monetization_review` nao significa necessariamente erro. Pode indicar que falta revisao visual, factual, editorial ou publish audit. A automacao consegue remover algumas pendencias visuais com revisao auxiliar, mas nao publica automaticamente se ainda restar revisao factual/manual.

Se o job ficar bom para revisar, abra `/jobs/<job_id>` e siga o fluxo:

1. assistir ao video
2. aprovar ou rejeitar
3. se aprovado, agendar ou publicar

## 9. Conectar o YouTube, quando necessario

Se o objetivo for upload real via API:

1. abra `http://127.0.0.1:8080/youtube/connect`
2. conclua o OAuth na conta do canal
3. confirme que surgiu `data/youtube_oauth_token.json`
4. volte ao hub e confira o bloco de integracao

Se `SHORTSFLOW_YOUTUBE_OAUTH_REDIRECT_URI` estiver vazio, o app usa a URL atual do hub como callback.

Importante: o token OAuth fica dentro de `SHORTSFLOW_DATA_DIR`. Se voce subir uma validacao isolada com outro diretorio, por exemplo `SHORTSFLOW_DATA_DIR=data-real-validation`, esse ambiente nao vai enxergar `data/youtube_oauth_token.json` e o hub vai reportar "Canal ainda nao conectado por OAuth". Isso nao significa que o token principal foi perdido.

Validacao segura do token principal, sem publicar video:

```bash
.venv/bin/python - <<'PY'
from app.config import get_settings
from app.youtube_api import YouTubePublisher

settings = get_settings()
youtube = YouTubePublisher(settings)
credentials = youtube._load_credentials(refresh=True)
status = youtube.connection_status()
print("token_file_exists", settings.youtube_token_path.exists())
print("credentials_valid", bool(getattr(credentials, "valid", False)))
print("connected", status.connected)
print("missing_items", status.missing_items)
PY
```

## 10. Agendar ou publicar

Voce pode agendar por dois caminhos:

- detalhe do job em `/jobs/<job_id>`
- calendario em `/calendar`, usando o botao `+` do dia desejado

O calendario lista para agendamento apenas jobs em `approved_for_publish` sem agenda ativa e ainda nao publicados.

### Modo manual

- o hub serve para aprovacao, agenda local e registro da publicacao
- `Publicar agora` exige `youtube_video_id` ou `youtube_url`
- a agenda automatica nao e executada pelo worker em `manual`

### Modo API

- jobs aprovados podem entrar em agenda
- quando o horario chega, o worker muda a agenda para `publishing` e sobe o video
- falha de upload vira `publish_failed`

## 11. Onde ficam os artefatos

Cada job grava em:

```text
data/artifacts/<job_id>/
```

Arquivos comuns:

```text
script.json
scene_plan.json
asset_visual_gate.json
visual_review_report.json
render/final.mp4
render/poster.jpg
render/remotion.log
render/edit_plan.json
premium_finishing_report.json
publish_package.json
publication_schedule.json
youtube_publish_attempts.json
events.jsonl
```

`render/ffmpeg.log` ainda pode aparecer quando o backend legado FFmpeg for forçado por configuracao, mas o caminho operacional padrao e Remotion.

## 12. Retencao automatica

O worker tambem limpa artefatos temporarios:

- falha critica: 24h
- job corrigivel: 7 dias
- pronto para publicar ou com agenda ativa: 21 dias

Importante:

- isso remove arquivos pesados
- nao apaga o job do banco
- o hub continua abrindo o job, mas pode mostrar banner de artefatos expirados

Se um job antigo abrir sem video local, isso pode ser retencao normal, nao corrupcao.

## 13. Testes

Suite completa:

```bash
.venv/bin/python -m pytest -q
```

Fatiamento recomendado:

```bash
.venv/bin/python -m pytest -q tests/test_pipeline_script.py
.venv/bin/python -m pytest -q tests/test_pipeline_assets.py
.venv/bin/python -m pytest -q tests/test_hub_publication.py
.venv/bin/python -m pytest -q tests/test_orchestrator_flow.py
.venv/bin/python -m pytest -q tests/test_providers_integrations.py
```

Se mexer em hub, agenda, publicacao, automacao, revisao visual ou retencao, rode `tests/test_hub_publication.py` e a suite completa antes de commit. Se mexer em prompts/qualidade visual, rode tambem `tests/test_pipeline_assets.py`; se mexer em fact pack, roteiro, loop/payoff ou politica factual, rode `tests/test_pipeline_script.py`. Testes novos devem entrar na suite de dominio correspondente, nao em uma suite e2e monolitica.

## 14. Expor via Tailscale

Mantendo o app local:

```bash
tailscale serve --bg http://127.0.0.1:8080
```

Valide:

```bash
curl https://<hostname>.<tailnet>/healthz
```

## 15. Encerrar

Com systemd:

```bash
systemctl stop shortsflow-hub.service
```

No terminal do `uvicorn` manual, use `Ctrl+C`.

Se um processo manual ficou em background:

```bash
ps -ef | rg 'uvicorn|app.main'
kill <pid>
```
