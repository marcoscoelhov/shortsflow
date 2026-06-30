# PRD — ShortsFlow

## 1. Resumo

ShortsFlow é uma fábrica local de YouTube Shorts em pt-BR. O operador entrega uma ideia, um título ou um roteiro pronto; o app transforma isso em um pacote publicável: pauta, roteiro, cenas, imagens, narração, legendas, música, render vertical, checklist de qualidade, revisão humana, agendamento e publicação no YouTube.

O produto não é apenas um gerador de vídeo. O diferencial é cobrir o ciclo inteiro entre “tenho uma ideia de Short” e “tenho um vídeo revisado, aprovado, agendado/publicado e mensurável”.

## 2. Objetivo do produto

Criar um sistema local, auditável e barato para produzir Shorts virais com qualidade operacional suficiente para um canal real, reduzindo trabalho manual repetitivo sem abrir mão de revisão humana nos pontos de risco.

### Resultado esperado

Ao final de um job bem-sucedido, o operador deve ter:

- vídeo vertical `9:16` pronto em `render/final.mp4`;
- título, descrição e hashtags;
- roteiro estruturado em hook, loop, beats, payoff e fechamento;
- cenas e assets visuais coerentes;
- narração em português brasileiro;
- legendas sincronizadas;
- música/trilha mixada;
- relatórios de qualidade, monetização e publicação;
- histórico de etapas e eventos;
- estado de revisão/aprovação;
- agenda de publicação;
- upload real via YouTube API quando configurado.

## 3. Usuários e atores

### Operador / criador

Pessoa que cria ideias, revisa vídeos, aprova, agenda, publica e acompanha performance.

Necessidades:

- criar vídeos rapidamente por tema, título ou roteiro pronto;
- ver o status de cada job sem abrir terminal;
- entender por que um job falhou ou foi bloqueado;
- assistir ao vídeo final antes de publicar;
- editar metadados de upload;
- agendar/publicar com segurança;
- recuperar backlog aproveitável;
- manter cobertura futura do canal.

### Sistema automático

Worker, ciclo diário, watchdog e rotinas de recuperação.

Responsabilidades:

- processar jobs em background;
- preencher agenda futura quando a automação estiver ligada;
- não misturar lanes editoriais diferentes;
- registrar tentativas, falhas e artefatos;
- evitar publicação automática de conteúdo bloqueado;
- recuperar jobs travados ou quase prontos quando for seguro.

### Revisor humano

Pode ser o próprio operador. Deve entrar no ponto final: assistir, aprovar, rejeitar, refazer, agendar ou publicar.

## 4. Escopo funcional

### 4.1 Criação de jobs

O Hub deve aceitar três modos de entrada:

1. **Tema** (`theme`): assunto bruto, exemplo: “por que o gelo estala no copo?”.
2. **Título completo** (`title`): promessa editorial já definida pelo operador.
3. **Roteiro pronto** (`script`): texto estruturado fornecido por pessoa humana.

Formato canônico de roteiro pronto:

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

Regras para roteiro pronto:

- aceitar roteiro pronto sem checklist factual separado;
- preservar o conteúdo fornecido, sem reescrever automaticamente;
- usar `Titulo` como metadado, não como narração;
- montar narração em `Hook -> Loop -> Beats -> Payoff -> Fechamento`;
- tratar `Loop` como tensão narrativa, não como claim factual;
- bloquear desvios graves de formato ou duração antes de consumir mídia.

### 4.2 Pipeline de produção

Cada job deve passar por uma máquina de estados auditável. Etapas mínimas:

| Etapa | Responsabilidade |
| --- | --- |
| `input_gate` | Validar entrada básica. |
| `topic_plan` | Criar pauta, ângulo, promessa, entidades, termos de busca e títulos candidatos. |
| `script` | Criar ou preservar roteiro, aplicar gate textual e reparar quando cabível. |
| `scene_plan` | Dividir roteiro em cenas e definir intenção visual de cada cena. |
| `asset_generation` | Gerar/selecionar imagens verticais e validar coerência semântica. |
| `tts` | Gerar narração pt-BR e normalizar áudio. |
| `subtitle_alignment` | Gerar legendas sincronizadas. |
| `background_music` | Selecionar/gerar trilha aprovada e mixar áudio. |
| `render` | Montar MP4 vertical via Remotion por padrão. |
| `monetization_readiness_gate` | Consolidar visual, repetição, metadados e riscos técnicos de publicação. |
| `publish_to_review_hub` | Persistir pacote de publicação e expor no Hub. |

Cada etapa deve registrar:

- status atual;
- tentativas/retries;
- timestamps;
- eventos em log auditável;
- artefatos JSON ou mídia no diretório do job;
- motivo claro em caso de falha.

### 4.3 Estados de job

Estados principais:

| Estado | Significado |
| --- | --- |
| `queued` | Job criado e aguardando worker. |
| `running` | Pipeline em execução. |
| `monetization_review` | Render pronto, mas exige revisão humana/operacional. |
| `blocked_for_monetization` | Bloqueio hard de qualidade, render, áudio, visual ou publicação. |
| `ready_for_upload` | Passou nos hard gates e pode ser aprovado/agendado. |
| `approved_for_publish` | Aprovado no Hub para publicação/agendamento. |
| `published` | Publicado e registrado. |
| `rejected` | Rejeitado por revisão humana. |
| `failed` | Falha geral. |

Falhas específicas também devem existir:

- `script_quality_failed`;
- `scene_plan_quality_failed`;
- `asset_quality_failed`;
- `subtitle_quality_failed`;
- `render_quality_failed`.

### 4.4 Hub web

O app deve expor um Hub SSR via FastAPI + templates HTML.

Superfícies obrigatórias:

- Home com formulário de criação e resumo operacional;
- fila/lista paginada de jobs;
- detalhe do job com vídeo, status, artefatos, relatório e ações;
- calendário mensal de programados/publicados/aprovados livres;
- centro de publicação/crescimento;
- biblioteca de roteiros prontos;
- configurações operacionais;
- healthcheck `/healthz`;
- JSON compacto de job em `/api/jobs/{job_id}`.

A UI deve privilegiar operação real, não estética vazia:

- mostrar o próximo passo acionável;
- separar alerta técnico de alerta editorial;
- não esconder bloqueios;
- não exigir terminal para revisar/aprovar/agendar;
- funcionar bem em tela mobile.

### 4.5 Revisão, aprovação e publicação

O operador deve conseguir:

- assistir ao vídeo final;
- aprovar;
- rejeitar;
- refazer job;
- editar título, descrição e hashtags;
- agendar publicação futura;
- publicar agora;
- limpar agenda;
- reabrir publicação incorreta;
- registrar publicação manual quando o modo API não estiver ativo.

Estados de agenda:

| Estado | Significado |
| --- | --- |
| `scheduled` | Slot salvo e aguardando horário. |
| `publishing` | Upload em andamento. |
| `publish_failed` | Tentativa falhou. |
| `published` | Upload/publicação concluído. |
| `cancelled` | Agenda limpa/reaberta. |

Regras críticas:

- publicação imediata deve ser pública quando o operador pedir “publica agora”;
- agendamento nativo do YouTube aparece como `privacyStatus=private` com `publishAt` futuro — isso é correto;
- não confiar só no SQLite para dizer que algo está no YouTube: validar pela API quando a pergunta envolver publicação real;
- datas e horários devem usar `America/Sao_Paulo`.

### 4.6 YouTube

Integração via OAuth com YouTube Data API.

O app deve suportar:

- conectar/desconectar conta;
- verificar status de conexão;
- fazer upload via API quando habilitado;
- agendar vídeo com `publishAt` futuro;
- publicar imediatamente;
- registrar URL e `youtube_video_id`;
- buscar vídeo por ID para validar status real;
- operar também em modo manual, sem API.

Escopos/conceitos separados:

- publicação/upload;
- leitura Data API;
- Analytics;
- Reporting API futura.

### 4.7 TikTok

Suporte opcional a publicação cruzada.

Requisitos mínimos:

- token manual configurado por ambiente;
- canal `tiktok` separado do YouTube;
- retropostagem controlada;
- limite diário de retropostagem;
- registro de falhas de API;
- não implementar OAuth/refresh do TikTok no Hub na versão base.

### 4.8 Automação diária

O sistema deve ter ciclo diário acionável por CLI e systemd timer, separado do processo web.

Objetivo:

- manter cobertura futura do canal;
- preencher slots usando backlog pronto quando possível;
- gerar novos jobs quando necessário;
- autoaprovar somente jobs que passaram nos critérios configurados;
- agendar no primeiro dia vago;
- registrar lacunas quando não houver candidato seguro.

Regras:

- timezone padrão: `America/Sao_Paulo`;
- horário padrão de publicação: `11:00`;
- janela futura configurável;
- tentativas máximas configuráveis;
- score mínimo configurável;
- lock por data local para evitar ciclos concorrentes;
- lane `ready_script_bank` separada de `automatic_topic`;
- `automatic_topic` deve ficar no nicho configurado, hoje focado em astronomia/universo/planetas quando essa política estiver ativa;
- não cair silenciosamente de uma lane para outra.

### 4.9 Watchdog e recuperação

O app deve ter rotinas nativas para:

- detectar jobs `queued`, `running` ou `publishing` travados;
- detectar baixa cobertura futura;
- detectar erros recorrentes;
- registrar alertas acionáveis;
- recuperar backlog quase pronto;
- tentar outro candidato quando um job reparado ainda exigir revisão manual.

Alertas devem ser silenciosos quando não houver ação relevante.

### 4.10 Performance e crescimento

O Hub deve permitir registrar ou sincronizar métricas de performance.

Métricas úteis:

- views;
- average view percentage / retenção;
- subscribers gained;
- likes;
- shares;
- comments;
- RPM quando disponível;
- notas manuais.

O score de crescimento deve ser simples e auditável:

- retenção como sinal principal;
- views/subscribers/shares como desempate/contexto;
- não fingir que há dados de impressões, CTR, origem de tráfego ou dispositivo sem adapter real da YouTube Reporting API.

## 5. Requisitos editoriais

### 5.1 Estrutura viral

Roteiros devem seguir o contrato:

- `title` / `Titulo`;
- `hook` / `Hook`;
- `loop` / `Loop`;
- `body_beats` / `Beats`;
- `payoff` / `Payoff`;
- `ending` / `Fechamento`;
- hashtags/metadados.

A narração final deve concatenar fielmente:

```text
Hook + Loop + Beats + Payoff + Fechamento
```

Critérios de qualidade:

- hook compreensível no primeiro segundo;
- curiosidade clara;
- beats em escalada;
- payoff no último terço;
- fechamento informativo, não frase genérica;
- duração alvo entre 45 e 55 segundos;
- pt-BR natural;
- sem tom didático arrastado.

### 5.2 Política editorial

O app deve equilibrar viralidade com segurança.

Regras:

- não usar Wikipedia como fonte confiável para claims sensíveis;
- temas médicos, financeiros, jurídicos, técnicos, históricos ou perigosos exigem linguagem conservadora e/ou fonte forte;
- números precisos, datas e estatísticas não devem ser inventados;
- ausência de fact pack não bloqueia sozinha assuntos cotidianos de baixo risco;
- source IDs inventados são bloqueio;
- claims falsos, inseguros ou sem suporte devem bloquear ou ir para revisão.

### 5.3 Política visual

Imagens devem:

- ser verticais `9:16`;
- evitar texto renderizado, marcas, pseudo-letras, telas e layouts poluídos;
- representar semanticamente a cena;
- dar atenção especial à primeira cena como “hook visual”;
- não entregar o payoff cedo demais;
- ter contraste e leitura rápida.

### 5.4 Monetização/publicabilidade

O gate final deve consolidar:

- qualidade de imagem/áudio;
- disclosure de conteúdo gerado por IA;
- consistência editorial;
- repetição/similaridade;
- visual review;
- metadados;
- qualidade técnica do render;
- riscos de plataforma.

Gates editoriais podem ser diagnóstico por padrão, mas hard blockers técnicos não devem ser ignorados.

## 6. Requisitos técnicos

### 6.1 Stack

- Python 3.12+;
- FastAPI;
- Jinja2/SSR;
- SQLAlchemy;
- SQLite com WAL;
- Uvicorn;
- Pydantic/Pydantic Settings;
- Remotion como renderer principal;
- FFmpeg como backend legado/manutenção;
- pytest para testes;
- systemd para serviço/timer em produção local.

### 6.2 Persistência

Persistir em SQLite:

- jobs;
- topic requests;
- topic plans;
- scripts;
- scene plans;
- scene assets;
- narração;
- legendas;
- música;
- renders;
- reviews;
- agendas;
- eventos;
- retries;
- snapshots de analytics;
- configurações operacionais não secretas.

Artefatos pesados devem ficar em:

```text
data/artifacts/<job_id>/
```

Exemplos:

- `topic_plan.json`;
- `structured_viral_contract.json`;
- `script.json`;
- `scene_plan.json`;
- imagens;
- áudio bruto/normalizado;
- `raw.srt`;
- trilha mixada;
- `render/final.mp4`;
- `render/poster.jpg`;
- `render/remotion.log`;
- `render/edit_plan.json`;
- `premium_finishing_report.json`;
- `monetization_report.json`;
- `publish_package.json`;
- `events.jsonl`.

### 6.3 Configuração

Camadas:

1. `.env`: infraestrutura, segredos e boot.
2. Hub: ajustes operacionais não secretos.
3. defaults do código.

Configurações de Hub devem incluir:

- LLM principal;
- fallback de LLM;
- LLM de reparo;
- planejador de cenas;
- prompt viral global;
- TTS primário;
- música/fonte local;
- modo de publicação;
- YouTube API ligada/desligada;
- TikTok ligado/desligado;
- automação diária;
- horário de publicação;
- score mínimo;
- janela de cobertura;
- coleta de performance.

Segredos nunca devem ir para tabela de configurações do Hub.

### 6.4 Providers

O app deve suportar providers substituíveis para:

- LLM/texto;
- imagens;
- TTS;
- música;
- visão/revisão visual.

Providers reais atuais esperados:

- DeepSeek para texto/gates baratos;
- MiniMax para imagem quando configurado;
- Edge TTS como opção barata publicável;
- Gemini/ElevenLabs como opções de TTS quando configuradas;
- banco local de música como padrão;
- YouTube Data API para publicação.

Modo de teste deve conseguir rodar com mocks determinísticos e sem custo de API.

### 6.5 Render

Remotion é o render principal.

Requisitos:

- saída pública continua `render/final.mp4`;
- poster em `render/poster.jpg` quando possível;
- logs e plano de edição salvos;
- healthcheck deve indicar se Remotion está pronto;
- setup deve instalar dependências Node no subprojeto `remotion/`;
- FFmpeg permanece disponível apenas como caminho legado explícito.

### 6.6 Concorrência e confiabilidade

- worker em background no app web para jobs normais;
- CLI/timer separado para automação diária;
- lease de job com timeout longo para etapas caras;
- SQLite busy timeout configurado;
- WAL habilitado;
- retries por etapa;
- recuperação de jobs travados;
- idempotência onde houver publicação/agendamento;
- logs claros sem vazar credenciais.

## 7. Rotas mínimas

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/` | Home do Hub. |
| `GET` | `/jobs` | Fila/lista de jobs. |
| `POST` | `/jobs` | Criar job. |
| `GET` | `/jobs/{job_id}` | Detalhe e revisão. |
| `GET` | `/api/jobs/{job_id}` | Status JSON compacto. |
| `POST` | `/jobs/{job_id}/review` | Aprovar, rejeitar ou refazer. |
| `POST` | `/jobs/{job_id}/publish-metadata` | Salvar metadados. |
| `POST` | `/jobs/{job_id}/schedule` | Agendar/limpar agenda. |
| `POST` | `/jobs/{job_id}/publish` | Publicar agora/registrar publicação. |
| `POST` | `/jobs/{job_id}/reopen-publication` | Reabrir publicação. |
| `POST` | `/jobs/{job_id}/performance` | Registrar métricas. |
| `GET` | `/calendar` | Calendário. |
| `POST` | `/calendar/schedule` | Agendar por calendário. |
| `GET` | `/publication-hub` | Centro de publicação/crescimento. |
| `GET` | `/library` | Banco de roteiros prontos. |
| `GET` | `/settings` | Configurações operacionais. |
| `POST` | `/automation/toggle` | Ligar/pausar automação. |
| `POST` | `/automation/run` | Rodar ciclo sob demanda. |
| `GET` | `/youtube/connect` | Iniciar OAuth. |
| `GET` | `/youtube/oauth/callback` | Finalizar OAuth. |
| `POST` | `/youtube/disconnect` | Remover token. |
| `GET` | `/healthz` | Healthcheck. |

## 8. Requisitos não funcionais

### Segurança

- Nunca imprimir tokens ou segredos em logs/respostas;
- autenticação opcional no Hub por token;
- requisições mutantes devem exigir header/token quando auth estiver ativa;
- cookies de navegação não devem autorizar mutações por si só;
- validar URLs internas para evitar SSRF em chamadas locais;
- não publicar conteúdo bloqueado por hard blocker.

### Operação local

- rodar em `127.0.0.1:8080` por padrão;
- suportar systemd service;
- suportar systemd timer para automação;
- healthcheck rápido;
- logs via journalctl;
- funcionar com SQLite local;
- permitir modo mock sem chaves externas.

### Custo

- evitar fallback caro silencioso;
- permitir fallback de LLM desabilitado;
- banco local de música por padrão;
- fact pack opcional;
- Edge TTS como caminho barato publicável;
- não disparar geração real cara sem intenção explícita do operador.

### Auditabilidade

- cada decisão relevante deve deixar artefato ou evento;
- bloquear com reason code acionável;
- separar blocker técnico de alerta editorial;
- preservar histórico mesmo depois de limpar artefatos pesados.

## 9. Fora de escopo da versão base

- editor de vídeo visual completo estilo CapCut;
- multiusuário com permissões complexas;
- SaaS multi-tenant;
- pagamentos/assinaturas;
- mobile app nativo;
- OAuth/refresh completo do TikTok;
- adapter real da YouTube Reporting API;
- publicação automática sem gates;
- dependência obrigatória de serviços cloud para rodar localmente;
- checagem factual acadêmica para todo tema.

## 10. Critérios de aceite

Uma implementação é considerada equivalente em qualidade quando cumprir estes cenários:

### Cenário A — job por roteiro pronto

1. Operador cola roteiro no formato canônico.
2. App aceita o roteiro pronto sem checklist factual separado.
3. Job é criado como `queued`.
4. Worker processa pipeline.
5. `full_narration` preserva Hook, Loop, Beats, Payoff e Fechamento.
6. Render final existe em `data/artifacts/<job_id>/render/final.mp4`.
7. Hub mostra vídeo, metadados, relatório e ação de aprovação.

### Cenário B — job por tema

1. Operador informa tema bruto.
2. App cria pauta estruturada.
3. Roteiro tem hook, loop, beats, payoff e fechamento.
4. Cenas e imagens são geradas/selecionadas.
5. TTS, legenda, música e render são produzidos.
6. Job termina em `monetization_review`, `ready_for_upload` ou bloqueio explicado.

### Cenário C — bloqueio editorial

1. Roteiro contém claim arriscado sem suporte.
2. Gate identifica problema.
3. Job não é publicado automaticamente.
4. Hub mostra motivo acionável.
5. Operador consegue refazer ou corrigir.

### Cenário D — aprovação e agendamento

1. Job pronto é aprovado no Hub.
2. Operador agenda para data/hora em BRT.
3. SQLite registra `scheduled`.
4. Quando YouTube API está ativa, vídeo é criado/agendado no YouTube.
5. Validação por API mostra `privacyStatus=private` e `publishAt` futuro.

### Cenário E — publicação imediata

1. Operador pede publicar agora.
2. App garante visibilidade pública.
3. Upload é feito via API quando configurado.
4. Job vira `published`.
5. YouTube confirma `privacyStatus=public`.

### Cenário F — automação diária

1. Timer/CLI roda ciclo diário.
2. Sistema evita execução duplicada por data local.
3. Procura backlog pronto antes de gerar novo conteúdo.
4. Não mistura lane de banco de roteiros com tema automático.
5. Agenda apenas candidatos que passam hard gates.
6. Registra lacunas quando não há candidato seguro.

### Cenário G — modo mock

1. Sem chaves externas, testes rodam com providers mock.
2. Pipeline e Hub continuam testáveis.
3. Não há custo de API.
4. Testes determinísticos passam.

## 11. Métricas de sucesso

Produto:

- número de Shorts prontos por semana;
- dias futuros cobertos na agenda;
- percentual de jobs que chegam a `ready_for_upload`;
- taxa de bloqueios por causa;
- tempo médio de ideia até vídeo revisável;
- retenção média dos vídeos publicados;
- viewed vs swiped away quando disponível;
- vídeos publicados sem intervenção manual pesada.

Operação:

- jobs travados detectados;
- falhas recorrentes agrupadas;
- custo médio por vídeo;
- taxa de fallback caro;
- número de publicações validadas no YouTube real.

## 12. Padrão de qualidade para avaliar outras LLMs

Ao pedir para outra LLM construir um app baseado neste PRD, avalie se ela:

- entende que o produto é pipeline + Hub + publicação, não só “gerar vídeo com IA”;
- mantém revisão humana e gates de segurança;
- separa estados de job, agenda e publicação;
- usa artefatos auditáveis;
- oferece modo mock barato;
- trata YouTube agendado corretamente como privado com `publishAt` futuro;
- não inventa métricas/Reporting API que não existem;
- não coloca segredo em banco/config pública;
- não mistura automação web com timer sem lock;
- não troca Remotion/renderer por mágica genérica sem contrato de saída;
- escreve testes para o fluxo principal;
- mantém o sistema local, simples e operável.

Se a solução entregue pela LLM for só um script que chama uma API de vídeo e baixa um MP4, ela falhou o PRD.

## 13. Handoff técnico sugerido

Implementar em fatias pequenas:

1. Modelo de dados + estados + diretórios de artefatos.
2. Hub mínimo com criação/lista/detalhe.
3. Pipeline mock ponta a ponta.
4. Roteiro estruturado e gates textuais.
5. Assets, TTS, legendas e música.
6. Render Remotion.
7. Revisão/aprovação/agendamento.
8. YouTube OAuth/upload.
9. Automação diária via CLI/timer.
10. Watchdog/backlog recovery.
11. Analytics/performance.
12. Polimento mobile e operacional.

A cada fatia, deixar um teste determinístico que falhe se o contrato principal quebrar.
