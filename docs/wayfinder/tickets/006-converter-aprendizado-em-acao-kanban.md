---
title: Converter aprendizado em uma próxima ação Kanban
labels: [wayfinder:task]
parent: ../breakout-map.md
status: closed
claimed_by: hermes-default
claimed_at: 2026-07-12T14:37:00Z
closed_at: 2026-07-12T14:38:00Z
blocked_by: []
---

# Converter aprendizado em uma próxima ação Kanban

## Question

Qual é a única próxima ação executável que deve entrar no Kanban depois da primeira decisão editorial madura?

Resultado esperado: um card pequeno, com aceitação verificável, dono/lane sugerida, e sem backlog especulativo.

## Resolution

Criado o card Kanban [Exigir objeto reconhecível no hook de automatic_topic](kanban://t_07364fb6), atribuído à lane `shortsflow`, prioridade 1.

Aceitação: o `automatic_topic` rejeita ou reescreve aberturas sem objeto reconhecível; Lua e Marte passam; tema abstrato sem objeto falha ou é reescrito; testes direcionados passam.
