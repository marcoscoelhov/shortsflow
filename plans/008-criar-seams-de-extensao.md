# Plano 008: Criar extensoes tipadas e plugins internos

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Nao implemente
> carregamento arbitrario de codigo ou instalacao dinamica. Atualize
> `plans/README.md`.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/providers app/pipelines app/publication_workflow_ops.py app/youtube_publication_ops.py app/automation.py app/config.py tests`

## Status

- **Prioridade**: P2
- **Esforco**: L
- **Risco**: MED
- **Depende de**: 005, 006
- **Categoria**: architecture / extensibility
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Providers e origens variam por canal, mas hoje registros concretos e branches
ficam no core. A solucao inicial deve permitir substituicao testavel sem criar
um sistema de plugins remoto, instalavel e dificil de proteger.

## Limite core/extensao

Permanece no core: estados, leases, retries, StepExecution, contratos de
Script/Scene/Artifact/PublishPackage, gates obrigatorios, review humano e
idempotencia de publicacao.

Vira extensao tipada:

- `LLMProvider`, `ImageProvider`, `TTSProvider`, `MusicProvider`, `VisionProvider`
- `TopicSource` e `ScriptImporter`
- `PublicationChannel`
- `RenderBackend` interno

`NichePolicy` permanece configuracao declarativa do core, nao plugin executavel.

## Escopo

**Pode alterar**: protocolos/factories, registries, providers, importers,
publication adapters, config/health UI, mocks e testes.

**Nao alterar**: estados/artefatos, instalar plugins por upload/pip, executar
entry points desconhecidos, mover gates obrigatorios para extensoes ou expor
segredos em manifests.

## Git

- Branch: `advisor/008-typed-extensions`
- Commits: contracts; registry; LLM migration; importer; channels/render.

## Passos

### 1. Definir contratos pequenos

Use `Protocol`/ABCs com input/output tipados, capability metadata, timeout,
erros normalizados e health check. Core fornece request context com job/profile,
deadline e telemetry sink, nunca Session SQLAlchemy.

**Verificar**: contract tests comuns rodam contra mocks e implementacoes locais.

### 2. Criar registry explicito

Registry e construido no startup a partir de config permitida e factories
conhecidas. Descriptor interno inclui key, tipo, capabilities e requisitos de
config, sem token. Falha de configuracao e antecipada e legivel.

**Verificar**: chave desconhecida falha no startup/test; duas implementacoes da
mesma key nao sobrescrevem silenciosamente.

### 3. Migrar LLM primeiro

Substitua registry/branches hardcoded por factory tipada, preservando routing,
fallback, timeout e custo. Corrija o timeout que abandona thread sem cancelar:
prefira client com timeout/cancelamento real; fallback so inicia depois que a
tentativa anterior terminou ou foi cancelada de forma observavel.

**Verificar**: timeout nao deixa request concorrente vivo nem duplica cobranca;
telemetria identifica attempt/provider/fallback.

### 4. Migrar importadores e fontes

Implemente `ScriptImporter` para entrada manual/banco atual e Airtable, e
`TopicSource` para fontes de pauta. Toda entrada retorna dado normalizado,
proveniencia e trust level; validacao factual continua no core.

**Verificar**: importer malicioso nao injeta policy; deduplicacao e profile scope
sao aplicados depois da normalizacao.

### 5. Adaptar canais de publicacao

Extraia YouTube por ultimo, depois do claim atomico do 002. `PublicationChannel`
recebe PublishPackage imutavel e idempotency key, devolve receipt normalizado.
Nao permita que adapter decida readiness ou pule review.

**Verificar**: contract test simula timeout apos sucesso remoto e retry recupera
receipt sem segunda publicacao.

### 6. Encapsular render backend

Remotion continua default. FFmpeg permanece manutencao/fallback explicito e
ferramenta de audio/probe. Ambos devem produzir o mesmo contrato minimo de
render receipt e diagnostics, sem prometer equivalencia visual.

### 7. Expor saude sem segredos

Painel/config mostra extensoes selecionadas, capabilities e health redigido por
perfil. Nao mostra env values. Alteracao de binding exige validacao e audit log.

## Testes obrigatorios

- Contract suite por familia de extensao.
- Registry desconhecido, duplicado e config incompleta.
- Timeout/cancel/fallback sem trabalho residual.
- Idempotency de PublicationChannel.
- Importer com payload hostil e proveniencia.
- Health/log/snapshot sem secrets.

## Pronto quando

- [ ] Core nao possui branch por nome de provider migrado.
- [ ] Toda extensao possui mock deterministico e contract tests.
- [ ] Nao existe carregamento dinamico de codigo nao confiavel.
- [ ] Gate/readiness continuam no core.
- [ ] Suite e smoke de provider passam.

## Pare se

- O contrato precisar expor Session/model interno.
- Um adapter exigir controlar estados do core.
- A migracao mudar output editorial sem benchmark do Plano 004.

## Manutencao

Adicionar provider deve significar implementar contrato e registrar factory.
So considere plugin instalavel quando houver demanda externa, sandbox, assinatura,
compatibilidade de versao e processo de upgrade/rollback definidos.
