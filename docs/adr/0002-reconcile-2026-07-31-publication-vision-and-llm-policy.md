# ADR 0002: reconciliar publicação, visão e routing LLM em 2026-07-31

- Status: aceito como decisão operacional; emendado para o piloto de tração em 2026-07-31
- Data: 2026-07-31
- Substitui defaults operacionais anteriores baseados integralmente em DeepSeek

## Contexto

Entre 30 e 31 de julho, o repositório ganhou o piloto opt-in de
`survival_decisions`, acabamento visual por cenário, revisão visual local com
Qwen, geração por GPT-5.6 Luna e julgamento independente por Grok. A pesquisa
produzida no mesmo período registra hipóteses anteriores ou recomendações de
teste; ela não deve ser lida como configuração vigente quando divergir desta
decisão.

## Decisões canônicas

### Scores e publicação

- O **score da auditoria premium** é diagnóstico editorial. Estar abaixo da
  meta não bloqueia sozinho aprovação ou publicação.
- Ausência de artefatos, exceção, payload incompleto/malformado ou evidência
  obrigatória ausente devem falhar fechado.
- Hard blockers técnicos de monetização, render, áudio, visual, factualidade ou
  plataforma nunca viram warnings por causa da política diagnóstica do score.
- O **Score de Autoaprovação** composto, com mínimo operacional `0.82`, é outro
  conceito e continua sendo requisito da automação. Não deve ser chamado de
  score premium.
- A política desejada exige o gate premium imediatamente antes de aprovar,
  agendar ou publicar em qualquer plataforma.

Gap conhecido: no estado revisado em 2026-07-31, os caminhos YouTube de agenda
e publicação ainda não chamam o gate premium, enquanto o TikTok chama. Até esse
bypass ser corrigido e testado, o fluxo não deve ser tratado como pronto para
publicação automática segura.

Gap conhecido adicional: uma auditoria estruturalmente completa ainda pode
carregar `final_status=blocked_for_monetization` ou outros hard blockers sem a
palavra `missing`, e o gate premium atual não os converte em reason. A correção
deve bloquear esses sinais explicitamente sem restaurar um limiar editorial por
nota.

### Autoridade da revisão visual

Atualização de 2026-08-09: a exceção Qwen descrita originalmente abaixo foi
revogada. Qwen local ou remoto é somente diagnóstico e não pode aprovar gates,
confirmar revisão humana, agendar ou publicar; notas de piloto não concedem
autoridade. `survival_decisions` exige revisão humana inclusive nos pilotos.

- `prompt_heuristic` nunca constitui evidência visual real.
- O Qwen local pode coletar evidência com
  `SHORTSFLOW_LOCAL_VISION_RELEASE_APPROVED=false`, mas não pode remover a
  pendência visual nesse estado.
- Para conteúdo cosmos genérico, o eval local, provider/modelo exatos, ausência
  de fallback e cobertura de cenas críticas qualificam a evidência diagnóstica,
  mas não concedem autoridade automática ao Qwen.
- A lane `survival_decisions` exige vision verifier funcional e **revisão
  humana**, inclusive no piloto persistido `niche_traction_minimax_fit_20260731_*`.

Resolvido em 2026-07-31: tentativas visuais novas agora validam provider, modelo,
alinhamento e ausência de fallback antes de contar uma cena como verificada. O
teste regressivo cobre um resultado MiniMax que declara `verification_mode=vision`.

### Routing LLM

- Default operacional vigente: GPT-5.6 Luna com effort `high` para pauta,
  roteiro, reparo e cenas, transportado pela Responses API no endpoint padrão
  da conta OpenCode Go (`https://opencode.ai/zen/go/v1`).
- Juiz independente vigente: Grok 4.5 com effort `high` para gates comuns e
  revisão premium.
- Fallback geral continua desabilitado. DeepSeek permanece provider disponível
  e hipótese de custo para benchmark, não default silencioso.
- A recomendação anterior de DeepSeek para gates baratos é evidência de
  pesquisa superseded pela decisão operacional posterior; uma troca futura
  exige benchmark e nova decisão explícita.

Gap conhecido: o adapter Luna ainda usa JSON object e validação local, não
Structured Outputs com JSON Schema estrito. A documentação não deve afirmar que
schema estrito já está ativo.

### Escopo do piloto de retenção

- `survival_decisions` é uma lane editorial opt-in, hipotética e sem publicação
  automática. No piloto de tração, Qwen fornece apenas evidência diagnóstica e
  não substitui a revisão humana visual.
- `pilot-10k-start --seed <n>` persiste 18 assignments em ordem A/B/C e cria os
  três canários. `--process` gera/renderiza somente esses três, sem aprovar ou
  publicar.
- O alvo de duração do piloto é 40 segundos, com faixa operacional aceita de
  30–50 segundos. Duração dentro da faixa é registrada para análise e não causa
  regeneração; factualidade, integridade técnica e demais hard blockers seguem
  fail-closed.
- `survival-cohort-plan` gera apenas seis seeds determinísticos em dry-run; não
  cria jobs, assignment ou experimento persistido.
- Isso não implementa o loop do Plano 009. Assignment por braço antes da
  geração, retry estável, coortes maduras, propostas aprováveis, rollback e
  painel continuam pendentes.

## Consequências documentais

Documentos operacionais devem apontar para este ADR ao descrever defaults ou
fronteiras de publicação. Pesquisas e planos históricos permanecem preservados,
mas precisam declarar quando foram superseded ou quando descrevem trabalho ainda
não implementado.
