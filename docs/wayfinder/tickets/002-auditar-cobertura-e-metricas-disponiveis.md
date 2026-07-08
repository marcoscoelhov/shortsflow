---
title: Auditar cobertura atual de publicação e métricas disponíveis
labels: [wayfinder:research]
parent: ../breakout-map.md
status: closed
claimed_at: 2026-07-03T18:05:37+00:00
closed_at: 2026-07-03T18:07:11+00:00
blocked_by: []
---

# Auditar cobertura atual de publicação e métricas disponíveis

## Question

Quais Jobs de Video cosmos já estão publicados/agendados, quais têm `youtube_video_id`, quais já têm métricas maduras, e qual é o estado real do baseline/mediana?

Criar um resumo curto com IDs, datas locais, views, retenção quando disponível, e lacunas. Não inferir performance sem fonte local/API.

## Resolution

Resumo detalhado: [Auditoria de cobertura de publicação e métricas — 2026-07-03](../assets/002-publication-metrics-audit.md).

Resposta curta:

- A sprint julho/cosmos tem `10` schedules desde `2026-07-01`; todos têm `youtube_video_id`.
- `4/10` já têm snapshot local de Analytics, todos ainda com `0` views no snapshot salvo.
- `0/10` estão maduros pela regra de 72h; não há base madura para decidir mudança editorial agora.
- Histórico local bruto de `youtube_analytics_snapshots`: `37` jobs com views, mediana `182`, máximo `1199`.
- `docs/CONTROL.md` registra baseline `191.5`, mas essa fotografia atual não reproduz exatamente o número; precisa fixar o filtro oficial antes de atualizar meta.

Decisão: manter geração/agendamento já cobertos e esperar maturação; só sincronizar Analytics pendente. Não mexer em nicho/prompt antes da janela mínima.
