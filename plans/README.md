# Planos de Implementacao ShortsFlow

Gerado pela skill `improve` em 2026-07-13, no commit `08fbea1`.

Estes planos foram escritos para execucao por `gpt-5.6-terra` com raciocinio
`high`, sempre em worktree/branch isolada. O executor deve ler o plano inteiro,
executar cada verificacao e atualizar o status abaixo. Nao executar dois planos
que alterem o banco ou o pipeline ao mesmo tempo.

O relatorio mestre e [000-shortsflow-auditoria-completa.md](000-shortsflow-auditoria-completa.md).

## Ordem e status

| Plano | Titulo | Prioridade | Esforco | Depende de | Status |
|---|---|---:|---:|---|---|
| 001 | Estabilizar a verificacao canonica | P0 | M | - | TODO |
| 002 | Endurecer autenticacao, leases e publicacao | P0 | L | 001 | TODO |
| 003 | Adotar migracoes e corrigir consultas quentes | P1 | L | 001, 002 | TODO |
| 004 | Versionar e compor o prompt mestre | P0 | L | 001, 003 | TODO |
| 005 | Reduzir modulos acima do limite de contexto | P1 | XL | 001, 002, 004 | TODO |
| 006 | Introduzir perfis de canal e nicho | P1 | XL | 003, 004, 005 | TODO |
| 007 | Criar paineis multinicho realmente isolados | P2 | L | 006 | TODO |
| 008 | Formalizar pontos internos de extensao | P2 | L | 005, 006 | TODO |
| 009 | Fechar o ciclo de experimentos de retencao | P2 | XL | 004, 006, 007 | TODO |

Status validos: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED: <motivo>`,
`REJECTED: <motivo>`.

## Dependencias

- `001` e obrigatorio antes de qualquer refatoracao: sem baseline verde o Terra
  nao consegue distinguir regressao nova de interferencia da suite.
- `002` vem antes da expansao porque upload duplicado, lease roubado e confianca
  indevida em roteiro importado ampliariam o risco em varios canais.
- `003` cria o mecanismo de migracao necessario para as novas entidades.
- `004` define ownership e versionamento de prompt antes de um perfil de canal
  apontar para prompts distintos.
- `005` reduz o contexto dos hotspots antes de adicionar a dimensao de perfil.
- `006` cria isolamento no dominio; `007` apenas o expoe como paineis.
- `008` evita que providers/importadores/canais voltem a inflar o core.
- `009` usa perfil, prompt e painel para experimentar agressividade com evidencia.

## Regras globais para o Terra

1. Criar uma branch `advisor/NNN-<slug>` em uma worktree separada.
2. Nao alterar nomes de steps, estados publicos, chaves de `quality_summary` ou
   nomes de artefatos sem migracao e teste de compatibilidade.
3. Fazer commits Conventional Commits pequenos; nao fazer push nem abrir PR.
4. Manter providers reais desligados nos testes e nao publicar conteudo externo.
5. Interromper quando um plano exigir arquivo fora do escopo ou quando o drift
   check mostrar mudanca estrutural que invalide os trechos citados.
6. Antes do drift check, rode `git status --short`; os comandos com o commit-base
   comparam tambem mudancas locais e nao autorizam descartar trabalho existente.

## Achados considerados e rejeitados

- Remover FFmpeg inteiro: rejeitado. Ele ainda e dependencia de audio, probe e
  backend explicito de manutencao; somente o render legado pode ser isolado.
- Transformar gates centrais em plugins dinamicos: rejeitado. Factualidade,
  direitos, integridade de render e contrato de estados pertencem ao core.
- Criar um painel FastAPI separado por nicho: rejeitado. Duplicaria rotas e
  estado; os paineis devem ser escopos do mesmo Hub sobre `ChannelProfile`.
- Carregar plugins arbitrarios por filesystem/entry point agora: adiado. O app
  precisa primeiro de interfaces tipadas e registro explicito.
- Remover as duas copias do video de review TikTok: rejeitado por enquanto.
  Uma atende o Hub privado e outra o GitHub Pages publico.
