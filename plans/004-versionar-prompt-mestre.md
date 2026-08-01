# Plano 004: Versionar e injetar o prompt mestre

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Trabalhe em
> worktree isolada, preserve artefatos e contratos publicos e atualize
> `plans/README.md` ao terminar.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/hub_prompt.py app/providers/llm.py app/providers/llm_routing.py app/pipelines/script_pipeline.py app/pipelines/topic_pipeline.py app/models.py benchmarks/editorial tests`

## Status

- **Prioridade**: P0
- **Esforco**: L
- **Risco**: HIGH
- **Depende de**: 001, 003
- **Categoria**: editorial / prompts / observability
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

O prompt mestre atual e um JSON global mutavel anexado a `notes`. Isso mistura
instrucao confiavel com contexto do job, dificulta reproduzir um roteiro e
permite contradicoes entre duracao, numero de palavras e estrutura narrativa.
Viralidade exige experimentos versionados, nao edicao silenciosa do prompt.

## Estado atual

- `app/hub_prompt.py:18-24` define uma narrativa diferente da exigida em
  `app/providers/llm.py:497-524`.
- `app/pipelines/script_pipeline.py:540` pede 80-120 palavras, enquanto o
  provider pede 120-140 e outros contratos usam 35-55 ou 45-55 segundos.
- `app/orchestrator.py:288-305` transporta o prompt por `notes`.
- `benchmarks/editorial/benchmark.v1.json` referencia `shorts-retention-v3`,
  mas o runtime usa `app/editorial/retention.py` v4 e nao ha runner canonico.
- Nao existe snapshot imutavel do prompt efetivamente usado em cada roteiro.

## Escopo

**Pode alterar**: `app/hub_prompt.py`, `app/editorial/`, `app/providers/llm*.py`,
`app/pipelines/script_pipeline.py`, `app/pipelines/topic_pipeline.py`, modelos e
migracoes, configuracao do Hub, benchmarks, testes e documentacao.

**Nao alterar**: nomes atuais de steps/artefatos, thresholds factuais sem
benchmark, comportamento de publicacao ou prompts de imagem fora do envelope
necessario para receber metadados editoriais.

## Git

- Branch: `advisor/004-prompt-versioning`
- Commits: modelo/migracao; composer/adapters; snapshot; benchmark e UI.

## Arquitetura obrigatoria

Crie um `PromptEnvelope` tipado e composto nesta ordem:

1. `system_policy`: seguranca, factualidade, formato e regras invariantes.
2. `profile_master`: voz, nicho, publico, idioma, limites e identidade do canal.
3. `retention_contract`: hook, open loop, escalada, payoff e re-hook final.
4. `job_context`: tema, fact pack e roteiro importado, sempre marcado como dado
   nao confiavel e nunca concatenado como instrucao de sistema.
5. `repair_context`: falhas dos gates e trechos a reparar, apenas em retries.

Providers com suporte a roles recebem mensagens separadas. Adapter sem roles
pode serializar secoes delimitadas, mas deve escapar/rotular conteudo nao
confiavel e possuir teste de prompt injection.

## Passos

### 1. Criar versoes imutaveis

Introduza `PromptVersion` com id, profile futuro/opcional, nome, versao,
conteudo estruturado, schema version, hash, status draft/published/retired,
autor e timestamps. Uma versao publicada nao pode ser editada; alteracao cria
nova versao. Migre o prompt global atual para a versao publicada do perfil
default sem apagar configuracao legada na primeira release.

**Verificar**: tentativa de update em published falha; hash e estavel para JSON
semanticamente igual; jobs antigos continuam processaveis.

### 2. Definir um unico contrato de duracao

Crie funcao canonica que converta duracao alvo e faixa de velocidade de fala em
orcamento de palavras. Remova ranges concorrentes dos prompts e gere o valor no
composer. Fixe uma estrutura canonica: hook imediato, loop aberto, 3-5 beats em
escalada, payoff verificavel e encerramento que reabre curiosidade sem inventar
fato.

**Verificar**: testes parametrizados para duracoes suportadas; nenhum prompt
ativo contem ranges hardcoded conflitantes.

### 3. Compor o envelope fora de `notes`

Crie modulos pequenos em `app/editorial/prompts/` para schema, repository,
composer e adapters. Passe `PromptEnvelope` explicitamente pelo pipeline. Deixe
compatibilidade de leitura de `notes` apenas durante migracao, com warning e
teste; nao grave novas instrucoes ali.

**Verificar**: fact pack contendo "ignore as instrucoes" permanece contexto e
nao muda system/profile policy; mocks recebem roles esperadas.

### 4. Persistir proveniencia por job

Grave id, versao, hash e snapshot redigido do envelope em metadados do roteiro
e em `prompt_snapshot.json`. Preserve chaves publicas existentes como
`prompt_version`. Nunca persista segredo, token ou header de provider.

**Verificar**: um roteiro pode ser reproduzido com snapshot + modelo + parametros;
retentar com a mesma versao nao busca o prompt global mais novo.

### 5. Atualizar Hub com publish explicito

Substitua edicao direta por fluxo draft, preview/diff, publish e retire. Mostre
qual versao cada perfil usa e exija confirmacao para promover. Nao permita
editar system policy pelo mesmo campo livre do prompt editorial.

**Verificar**: publicar nova versao afeta apenas jobs criados depois; job em
andamento conserva snapshot.

### 6. Tornar benchmark executavel

Crie runner deterministico para corpus editorial, validando estrutura, fatos,
duracao, repeticao e sinais de retencao. Atualize benchmark para versao v2 e
inclua casos cosmos, roteiro importado, injection e repair. Avaliacao paga deve
ser opt-in por env e nunca parte do pytest default.

**Verificar**: comando documentado produz JSON comparavel e falha quando uma
versao candidata regride limites acordados.

## Testes obrigatorios

- Imutabilidade e concorrencia de publish.
- Composicao/precedencia de todas as camadas.
- Injection em tema, fact pack, notas e roteiro importado.
- Snapshot sem segredos e replay da versao correta.
- Duracao/palavras sem ranges contraditorios.
- Compatibilidade de jobs existentes e provider mocks.

## Pronto quando

- [ ] Nenhum job novo transporta master prompt por `notes`.
- [ ] Toda geracao registra versao, hash e snapshot.
- [ ] Uma unica funcao define o orcamento de palavras.
- [ ] Benchmark v2 roda localmente e compara duas versoes.
- [ ] Suite, Ruff e typecheck passam.

## Pare se

- Um provider nao permitir separar roles e o adapter nao puder preservar limites
  de confianca; documente o provider como nao compativel.
- A migracao exigir reinterpretar prompt de jobs concluidos.
- O benchmark incentivar afirmacoes mais fortes sem suporte do fact pack.

## Manutencao

Mudanca editorial vira nova versao e resultado de benchmark. Nunca promova
prompt automaticamente a partir de uma metrica isolada. O snapshot do job e a
fonte de auditoria; a configuracao atual nao deve reescrever o passado.
