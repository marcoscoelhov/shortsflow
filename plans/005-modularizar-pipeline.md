# Plano 005: Modularizar o pipeline sem mudar contratos

> **Executor Terra**: use `gpt-5.6-terra` com raciocinio `high`. Este plano e
> refactor-only: primeiro caracterize, depois mova. Atualize `plans/README.md`.
>
> **Drift check**: `git diff --stat 08fbea1 -- app/orchestrator.py app/automation.py app/pipelines app/providers app/quality/premium_publish_gate.py app/hub_context.py app/templates/job_detail.html app/static/styles.css docs/wayfinder tests`

## Status

- **Prioridade**: P1
- **Esforco**: XL
- **Risco**: HIGH
- **Depende de**: 001, 002, 004
- **Categoria**: architecture / maintainability
- **Planejado em**: `08fbea1`, 2026-07-13

## Por que importa

Arquivos de 800-1.500 linhas concentram lifecycle, regras editoriais, IO e
adaptadores. Isso aumenta o contexto necessario para manutencao por IA e torna
facil alterar contratos acidentalmente. O objetivo e criar modulos coesos, nao
apenas distribuir linhas.

## Estado atual

- `app/automation.py` tem 1.476 linhas; monetization pipeline 1.318;
  `app/orchestrator.py` 1.237; fact pack 1.010; script repair 994; LLM 945.
- `app/orchestrator.py:126-199` duplica constantes visuais ativas em
  `app/pipelines/image_assets.py`.
- Regeneracao de cena no orchestrator conhece internals de assets, gates e
  artefatos, inclusive chamada privada.
- `styles.css` tem 6.932 linhas e `job_detail.html` 994.
- Step names, estados, artefatos e chaves de `quality_summary` sao contratos.

## Escopo

**Pode alterar**: modulos acima, adicionar pacotes internos e wrappers de
compatibilidade, templates/CSS correspondentes, referencias residuais em
`docs/wayfinder/` e testes de caracterizacao.

**Nao alterar**: comportamento observavel, URLs, nomes importados externamente,
ordem dos steps, formato de artefatos, thresholds ou schema de banco.

## Git

- Branch: `advisor/005-modular-pipeline`
- Um commit por extracao; nunca misture extracao mecanica e mudanca comportamental.

## Regras de desenho

- Alvo recomendado: modulos de runtime abaixo de 600 linhas; 800 e teto de
  alerta, nao meta. Excecoes geradas/declarativas devem ser justificadas.
- Cada modulo deve ter uma responsabilidade e API publica curta.
- Evite `utils.py`, imports circulares, service locator e classes que apenas
  renomeiam funcoes.
- Wrappers antigos permanecem por uma release quando forem importados por testes
  ou extensoes locais.

## Passos

### 1. Congelar contratos com characterization tests

Capture ordem de steps, transicoes, retry, lease, eventos, nomes/hash de
artefatos, `quality_summary` e resultado de regeneracao de cena. Use fixtures
deterministicas e golden JSON pequenos, sem snapshot de HTML inteiro.

**Verificar**: testes falham ao renomear intencionalmente um contrato e passam
antes da primeira extracao.

### 2. Limpar duplicacao morta

Remova do orchestrator as constantes visuais sem uso, mantendo a unica fonte em
`image_assets.py`. Extraia `SceneRegenerationService` que recebe interfaces
publicas de asset/gate/artifact; elimine chamada privada entre modulos.

Remova comentarios residuais `ponytail:` do runtime e atualize documentos
Wayfinder que afirmam que `scripts/ponytail_ultra_gate.py` ainda existe. Preserve
historico Git; nao substitua esse nome por um novo gate equivalente.

**Verificar**: regeneracao completa, parcial e retry geram mesmos artefatos e
eventos; `rg` encontra uma unica definicao das constantes.

### 3. Reduzir o orchestrator a lifecycle shell

Deixe o orchestrator coordenar claim, lease, step registry, retry e dispatch.
Mova comandos de process/reprocess/regenerate para handlers e servicos de
aplicacao. Nenhum handler deve depender do singleton global.

**Verificar**: shell fica abaixo do teto e testes de concorrencia do 002 passam.

### 4. Separar dominios editoriais grandes

Divida automation em trigger/eligibility/scheduling/import. Divida monetization
em audit, packaging e readiness. Separe fact-pack retrieval, normalization,
evidence e verification. Separe script repair por diagnostico, plano e apply.
Mantenha funcoes facade nos caminhos antigos.

**Verificar**: cada extracao isolada preserva signatures e suite; nao crie
dependencia reversa de dominio para FastAPI/Jinja.

### 5. Separar providers por responsabilidade

Divida LLM em protocol, request builder, clients e routing; TTS em protocol,
normalization, clients e audio postprocess. Mantenha IO e politicas editoriais
fora dos clients. Prepare as interfaces que o Plano 008 registrara.

**Verificar**: mocks atuais continuam validos; timeout/fallback/custo mantem
telemetria e semantica.

### 6. Fatiar Hub e CSS por superficie

Extraia context builders por pagina e partials do job detail. Separe CSS em
tokens/base/layout/components/pages com uma ordem de import explicita. Nao
redesenhe a UI nesta fase nem adicione pipeline frontend.

**Verificar**: screenshots desktop/mobile das paginas principais nao exibem
regressao, overflow ou estilos faltantes.

### 7. Aplicar guardrail leve

Adicione script/check que lista arquivos de runtime acima de 800 linhas e falha
apenas para novos crescimentos nao justificados. Nao aplique limite cego a
fixtures, migrations, dados ou arquivos gerados.

## Pronto quando

- [ ] Nenhum modulo de runtime tocado excede 800 linhas sem justificativa.
- [ ] Orchestrator contem lifecycle, nao regras de asset/editorial.
- [ ] Nao ha imports circulares nem chamadas privadas entre dominios.
- [ ] Contratos caracterizados permanecem identicos.
- [ ] Suite, Ruff, typecheck e smoke visual passam a cada extracao.

## Pare se

- Uma extracao exigir alterar estado, artefato ou schema; crie plano separado.
- Golden tests mascararem dados volateis em vez de testar contrato.
- O novo pacote aumentar acoplamento ou depender do singleton global.

## Manutencao

Revise coesao e API, nao apenas contagem de linhas. Novos providers e nichos
devem depender das interfaces extraidas, nunca reabrir condicionais centrais.
