# Runbook Operacional: automatic_topic (Tema Automático)

**Lane isolada**: `automatic_topic` roda no slot ~18:00 BRT (fixo). Não cai silenciosamente para `ready_script_bank` nem fallback determinístico. Se não houver pauta válida no nicho, o slot fica vazio (agenda hole reportável via watchdog). Nicho-alvo: astronomia/universo/planetas (cosmos_curiosity_pool).

DeepSeek v4 Flash é o padrão barato para draft/gate. Fallback/pro só por exceção explícita (premium_review).

Não documenta credenciais cruas. Validado com smoke E2E (t_8c8e2606) + observabilidade (t_7ac0dfae).

## 1. Verificar último job automatic_topic

Comando verificado (usa DB default + artifacts):

```bash
cd /root/shortsflow
.venv/bin/python -c '
import sqlite3, json
conn = sqlite3.connect("data/shortsflow_render.db")
cur = conn.cursor()
cur.execute("""
SELECT j.job_id, j.status, j.job_origin, j.creation_via, j.failure_reason, j.created_at,
       t.seed_theme
FROM jobs j LEFT JOIN topic_requests t ON t.job_id = j.job_id
WHERE j.job_origin = "automatic_topic"
ORDER BY j.created_at DESC LIMIT 1
""")
row = cur.fetchone()
if row:
    print("job_id:", row[0])
    print("status:", row[1], "origin:", row[2], "via:", row[3])
    print("theme:", row[6])
    print("created:", row[5])
    print("failure_reason:", row[4])
else:
    print("Nenhum job de automatic_topic no DB")
'
```

Inspecione artefatos chave (sempre gerados):

```bash
JOB=...  # do comando acima
ls data/artifacts/$JOB/
cat data/artifacts/$JOB/job_origin.json
cat data/artifacts/$JOB/structured_viral_contract.json | python -m json.tool | head -20
python -c '
import json,sys
p="data/artifacts/'$JOB'/topic_plan.json"
d=json.load(open(p)) if open(p).read().strip() else {}
print("niche:", d.get("quality_metrics",{}))
' 2>/dev/null || echo "sem topic_plan"
```

- source/creation_via: "automatic_topic" / "daily_cycle"
- niche/subniche: de quality_metrics ou niche_contract
- viral_prompt_source: "hub_settings" (ou default)
- artifact final: render/final.mp4 se ready_for_upload

Ver attempts/reason_code (score_report é JSON):

```bash
.venv/bin/python -c '
import sqlite3, json
conn = sqlite3.connect("data/shortsflow_render.db")
cur = conn.cursor()
cur.execute("""
SELECT attempt_id, source, status, job_id, score_report, error, created_at
FROM automation_attempts
WHERE source = "automatic_topic"
ORDER BY created_at DESC LIMIT 5
""")
for r in cur.fetchall():
    sr = json.loads(r[4]) if r[4] else {}
    rc = sr.get("reason_code")
    print(r[0][:8], r[2], "job=", r[3], "reason_code=", rc)
    if r[5]: print("  err:", str(r[5])[:80])
'
```

## 2. Distinguir sucesso / rejeição / falha / fallback

- **Sucesso**: status="ready_for_upload", reason_code=null (ou ausente), final.mp4 existe, viral_prompt_source=hub_settings, gates incluem script_quality + viral_intensity + text_publish_audit. Monetization final_status=ready_for_upload.

- **Rejeição editorial normal**: status=script_quality_failed (ou visual_contract_quality_failed etc), reason_code="gate_rejected", e.g. "script: script quality gate failed: sentence_too_long" (do smoke). Sem final.mp4. Ação normal de gate.

- **Falha operacional**: reason_code="generation_failed", status=failed ou exception em error do attempt. Ver events.jsonl ou logs do worker.

- **Fallback prevented**: attempt status="not_eligible", reason_code="fallback_prevented". Isso é **positivo** — significa que o guardião de lane funcionou e impediu contaminação por ready_script.

- **viral_prompt_missing/defaulted**: aparece quando "source=default_explicit" no notes ou viral_prompt.source != "hub_settings". Prompt usado é o DEFAULT (genérico).

- **no_topic**: seed_theme vazio no payload antes de criar job.

- **niche_rejected**: notes tem policy diferente de "cosmos_astronomia_universo_first".

Use summary do smoke como referência de campos reais:

```bash
cat data-kanban/automatic_topic_smoke/automatic_topic_smoke_summary.json | python -m json.tool
```

## 3. Ações por reason code (sem ruído)

- **no_topic**: Sem candidato cosmos válido. Ver `app/automation_topics.py` (COSMOS_CURIOSITY_POOL). Rode smoke ou force tema manual. Não force.

- **niche_rejected**: Contaminação de notes/policy. Investigar criação do payload. Não deve ocorrer em operação normal.

- **viral_prompt_missing/defaulted**: Configure prompt viral específico para astronomia no Hub (POST /hub/prompt ou edição direta de data/hub_settings.json). Exemplo bom: "Abra com paradoxo espacial específico; 3-5 beats; payoff no último terço; linguagem conservadora; evite 'você sabia'".

- **generation_failed**: Erro de execução (LLM, asset, render). Cheque exception no attempt.error + events.jsonl no artifact_dir. Rode `python -m app.cli automation-run --force` após correção se necessário.

- **gate_rejected**: Gate de qualidade (script/viral/factual/editorial) reprovou. Normal para manter padrão alto. Olhe quality_summary["failure_diagnosis"] ou script_rejected.json. Não force aprovação manual sem correção.

- **fallback_prevented**: Lane protegida. Resulta em slot 18h sem job. Ação: investigar causa upstream (sem tema aceitável no nicho). Reporta hole de agenda (watchdog alerta). **NÃO desative o guardião**.

Alinhado com preferência: alerta só em falhas reais, holes de agenda, decisões ou confirmações de publish.

## 4. Rodar smoke / check manual local (tema astronômico + prompt viral)

Smoke E2E verificado (usa data isolado, providers, valida source/niche/prompt/reason/artifact):

```bash
cd /root/shortsflow
.venv/bin/python scripts/smoke_automatic_topic_e2e.py --data-dir data-test/auto-topic-check
# inspeciona sem limpar se quiser:
# .venv/bin/python scripts/smoke_automatic_topic_e2e.py --data-dir data-test/auto-topic-check --keep-data
cat data-test/auto-topic-check/automatic_topic_smoke_summary.json
```

Para setar prompt viral custom (astronomia) antes de smoke ou run:

```bash
.venv/bin/python -c '
from app.hub_prompt import save_viral_prompt_template, hub_settings_path
from app.config import get_settings
settings = get_settings()
prompt = """Smoke real automatic_topic astronomia.
Obrigatório para passar no gate:
- abrir com paradoxo espacial específico, nunca com "você sabia"
- usar loop aberto em até duas frases
- manter linguagem conservadora quando fact_pack estiver desligado
Retenção:
- cada beat precisa aumentar surpresa visual
- payoff no último terço deve recontextualizar o hook
SEO:
- título começa com planeta, universo, estrela ou fenômeno espacial quando natural
Tom:
- pt-BR direto, intrigante, sem aula morna
Proibido:
- banco de roteiros prontos
- fallback determinístico local"""
save_viral_prompt_template(hub_settings_path(settings.data_dir), prompt)
print("viral prompt set for astronomy")
'
```

Rodar ciclo manual (pode criar job real se enabled; use data isolado quando possível):

```bash
.venv/bin/python -m app.cli automation-run --force
```

Ver resultado no DB/artifacts imediatamente após.

Testes focados pós-edits:

```bash
.venv/bin/python -m pytest -q tests/test_hub_publication.py::test_automatic_topic_payload_rejection_reason_codes tests/test_hub_publication.py::test_automatic_topic_attempt_rejects_ready_script_origin_fallback -q
.venv/bin/python -m pytest -q tests/test_astronomy_niche_contract.py -q
```

## 5. Onde NÃO mexer

- Não ative fallback_provider geral (deve ficar disabled). DeepSeek v4 Flash default para tudo normal; v4-pro só via SHORTSFLOW_LLM_PREMIUM_REVIEW_* para casos premium explícitos.

- Não remova checagens em `app/automation.py`: _automatic_topic_payload_rejection_reason, job_origin guard, AUTOMATION_REASON_FALLBACK_PREVENTED.

- Não mude slot 18h para source ready_script_bank.

- Não use ready_script_bank como substituto silencioso de falha em automatic_topic.

- Não sugira deploy externo (validar só local).

- Não ignore holes de agenda: use watchdog para detectar.

- Preserve: automatic_topic_policy=cosmos_astronomia_universo_first nos notes; job_origin=automatic_topic; creation_via=daily_cycle.

Comandos e campos documentados foram validados por execução real + artefatos do smoke (commit 1e2e41a) e evidência dos parent cards.

Se precisar de mais contexto, leia:
- scripts/smoke_automatic_topic_e2e.py
- app/automation.py (AUTOMATION_REASON_*, _automatic_topic_payload)
- data-kanban/automatic_topic_smoke/automatic_topic_smoke_summary.json
- tests/test_hub_publication.py (testes de reason codes e isolamento)
