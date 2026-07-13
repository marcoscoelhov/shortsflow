---
title: Desenhar placar mínimo de breakout
labels: [wayfinder:prototype]
parent: ../breakout-map.md
status: closed
claimed_by: hermes-default
claimed_at: 2026-07-11T13:17:00Z
closed_at: 2026-07-11T13:17:00Z
blocked_by: []
---

# Desenhar placar mínimo de breakout

## Question

Qual é o menor placar operacional que mostra se o ShortsFlow está perto de breakout sem virar dashboard novo?

Prototipar em markdown/terminal: mature median, melhor Short, distância até breakout, agenda futura, e uma próxima ação. Reusar dados existentes; sem UI nova.

## Resolution

Protótipo: [Placar mínimo de breakout](../assets/003-breakout-scoreboard-prototype.md).

Decisão: usar este placar textual no `CONTROL.md`/briefings, sem dashboard novo. Ele mostra apenas mediana madura, melhor Short, distância até breakout, cobertura de agenda e uma única próxima ação. Estado atual: mediana madura 506, melhor Short 853, meta 10.000 e 2/3 slots futuros; a prioridade é restaurar o terceiro slot e só então aprender com a amostra madura.
