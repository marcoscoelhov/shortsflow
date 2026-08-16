#!/usr/bin/env python3
"""
Grok 4.5 faz o reviewer gate dos quality_failed jobs.
Avalia se os resultados do recovery são seguros e se os
jobs restantes podem ser aprovados ou precisam de mais ação.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SHORTSFLOW_USE_MOCK_PROVIDERS", "false")

from app.db import SessionLocal
from app.models import Job, ErrorLog
from app.providers.llm import LLMProviderRegistry
from app.providers.errors import ProviderFailure
from app import domain_contracts as dc

registry = LLMProviderRegistry()
judge = registry.gate_judge_provider()

if not judge:
    print("ERRO: Grok 4.5 indisponível")
    sys.exit(1)

quality_statuses = ['script_quality_failed', 'asset_quality_failed',
                    'scene_plan_quality_failed', 'subtitle_quality_failed',
                    'visual_contract_quality_failed']

db = SessionLocal()
all_jobs = []
for st in quality_statuses:
    all_jobs.extend(db.query(Job).filter(Job.status == st).all())
db.close()

print(f"🔍 Grok 4.5 revisando {len(all_jobs)} quality_failed jobs")
print()

aprovados = 0
rejeitados = 0
precisa_reparo = 0

for j in all_jobs:
    qs = j.quality_summary or {}
    s = qs.get("script", {})
    hook = s.get("hook_score", "?")
    
    print(f"  [{j.status[:25]:25s}] {j.job_id[:12]:12s} hook={hook} → ", end="", flush=True)

    # Grok avalia se o job é recuperável ou deve ser descartado
    payload = {
        "job_id": j.job_id,
        "status": j.status,
        "quality_summary": qs,
        "gate_kind": "growth_score",
    }
    try:
        result = judge.judge_quality_gate("growth_score", payload)
        passed = bool(result.get("passed"))
        conf = float(result.get("confidence", 0.0))
        reasons = result.get("reasons", [])
    except Exception as e:
        print(f"⚠️ ERRO: {str(e)[:60]}")
        precisa_reparo += 1
        continue

    if passed:
        # Grok aprovou - pode tentar reprocessar ou aprovar direto
        # Mas como é reviewer gate, só registramos a avaliação
        print(f"✅ APROVADO (conf={conf:.2f})")
        aprovados += 1
    else:
        print(f"❌ REJEITADO (conf={conf:.2f} razão={reasons[:2]})")
        rejeitados += 1

print()
print("=" * 60)
print(f"RESUMO: ✅ {aprovados} aprovados | ❌ {rejeitados} rejeitados | ⚠️ {precisa_reparo} erro")
print()
print("Jobs aprovados → podem ser reprocessados via backlog recovery")
print("Jobs rejeitados → precisam de revisão manual ou descarte")
print("=" * 60)