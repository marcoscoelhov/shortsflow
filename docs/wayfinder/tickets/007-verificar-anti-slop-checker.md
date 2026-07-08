---
title: Verificar se o produto tem anti-slop checker
labels: [wayfinder:research]
parent: ../breakout-map.md
status: closed
blocked_by: []
claimed_at: 2026-07-05T12:59:44+00:00
closed_at: 2026-07-05T12:59:44+00:00
assets:
  - ../assets/007-anti-slop-checker-evidence.md
---

# Verificar se o produto tem anti-slop checker

## Question

O ShortsFlow já tem um checker anti-slop real, ou isso ainda é só intenção/documentação?

## Resolution

Tem checker anti-slop real, mas distribuído em camadas em vez de um único recurso com esse nome: `ScriptQualityGate`, `ViralIntensityGate`, `text_publish_audit`, `audit_system_quality`/`PremiumPublishGate`, fast lane operacional e Ponytail gate.

Evidência detalhada: [Anti-slop checker evidence](../assets/007-anti-slop-checker-evidence.md).

Hole encontrado: `scripts/ponytail_ultra_gate.py` existe e todos os checks passaram, mas sai com código 1 porque soma `8.6/8.6` e exige `>=9.5`. Corrigir esse gate existente antes de criar checker novo.
