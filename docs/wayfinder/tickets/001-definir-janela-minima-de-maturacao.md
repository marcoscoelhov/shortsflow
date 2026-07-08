---
title: Definir janela mínima de maturação para julgar performance
labels: [wayfinder:grilling]
parent: ../breakout-map.md
status: closed
claimed_at: 2026-07-02T23:01:06+00:00
closed_at: 2026-07-02T23:01:06+00:00
blocked_by: []
---

# Definir janela mínima de maturação para julgar performance

## Question

Qual é a menor janela segura para tratar um Job de Video publicado como maduro o bastante para entrar no cálculo de mediana, breakout e decisão editorial?

Considerar o horário padrão 11:00 America/Sao_Paulo, métricas reais disponíveis no projeto, e evitar mudar estratégia antes de evidência madura.

## Resolution

Usar **72h após publicação** como janela mínima para entrar no cálculo operacional de mediana/breakout.

Regra lazy:

- `<72h`: acompanhar, não decidir estratégia.
- `>=72h`: pode entrar no baseline/mediana e no placar de breakout.
- `>=7d`: usar como confirmação se o resultado estiver perto do limite ou contradisser tendência.

Motivo: 72h evita mexer cedo demais e basta para a decisão atual: continuar cosmos vs ajustar tema/hook. Sete dias só quando a decisão for borderline.
