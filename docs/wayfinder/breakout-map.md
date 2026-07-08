---
title: Provar um Short Breakout no ShortsFlow
labels: [wayfinder:map]
status: open
created: 2026-07-02
tracker: local-markdown
---

# Provar um Short Breakout no ShortsFlow

## Notes

Objetivo: provar o motor de um canal com 1 Short breakout antes de expandir superfície.

Fonte operacional: `docs/CONTROL.md`.

Definição atual de breakout: `10.000+ views` ou `10x current mature median`, o que for maior. Baseline atual: `191.5` views maduras. Alvo secundário: `600+` views maduras.

Escopo atual: 1 canal YouTube Shorts, pt-BR, cosmos/astronomia, 1 vídeo forte/dia, sem multi-nicho, sem redesign, sem deploy externo.

Skills úteis por sessão: `wayfinder`, `shortsflow-loop-orchestrator`, `shortsflow-youtube-publication-validation`, `shortsflow-job-artifact-audit`.

Local tracker:
- Tickets ficam em `docs/wayfinder/tickets/`.
- `status: open|claimed|closed` no frontmatter.
- `blocked_by:` lista nomes de tickets, não ids.
- Frontier = tickets `open` sem `blocked_by` aberto.

## Decisions so far

<!-- Uma linha por ticket fechado. Não duplicar detalhe: linkar o ticket. -->

- [Definir janela mínima de maturação para julgar performance](tickets/001-definir-janela-minima-de-maturacao.md) — usar 72h pós-publicação para baseline/breakout; 7d só para confirmação borderline.
- [Auditar cobertura atual de publicação e métricas disponíveis](tickets/002-auditar-cobertura-e-metricas-disponiveis.md) — julho/cosmos tem 10 schedules com YouTube ID, mas 0 maduros em 72h; baseline local bruto atual é mediana 182 e precisa de filtro oficial antes de atualizar meta.
- [Verificar se o produto tem anti-slop checker](tickets/007-verificar-anti-slop-checker.md) — há anti-slop real em gates de roteiro/viralidade/auditoria, mas o Ponytail gate está presente e impossível de passar como escrito (`8.6/8.6` com corte `>=9.5`).

## Fog

- Se os vídeos cosmos publicados não tiverem amostra madura suficiente, ainda não dá para saber se o gargalo é tema, hook, retenção visual, agenda, ou só janela de maturação.
- Se houver breakout, ainda falta decidir quais aprendizados viram rotina e quais eram sorte/tema único.
- Se a mediana madura ficar abaixo de 600 após amostra suficiente, provavelmente será preciso revisar seleção de tema ou arquitetura de retenção antes de mexer em plataforma/canal.

## Child tickets

Frontier inicial:

- [Definir janela mínima de maturação para julgar performance](tickets/001-definir-janela-minima-de-maturacao.md) ✅ fechado
- [Auditar cobertura atual de publicação e métricas disponíveis](tickets/002-auditar-cobertura-e-metricas-disponiveis.md) ✅ fechado
- [Verificar se o produto tem anti-slop checker](tickets/007-verificar-anti-slop-checker.md) ✅ fechado
- [Desenhar placar mínimo de breakout](tickets/003-desenhar-placar-minimo-de-breakout.md)
- [Comparar pacote editorial dos jobs cosmos agendados](tickets/004-comparar-pacote-editorial-dos-jobs-cosmos.md)

Bloqueados:

- [Decidir primeiro ajuste editorial pós-amostra madura](tickets/005-decidir-primeiro-ajuste-editorial-pos-amostra.md) — bloqueado por janela/métricas/editorial.
- [Converter aprendizado em uma próxima ação Kanban](tickets/006-converter-aprendizado-em-acao-kanban.md) — bloqueado por decisão de ajuste.
