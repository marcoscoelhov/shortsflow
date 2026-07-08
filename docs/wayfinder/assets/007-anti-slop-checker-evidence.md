# Anti-slop checker evidence

Checked at: 2026-07-05T12:59:44+00:00

## Verdict

ShortsFlow has anti-slop checks, but not as one product feature named `anti-slop checker`.

It exists as layered gates:

1. `app/quality/script_gate.py` — deterministic script anti-slop gate.
   - Blocks generic openings, leaked markup/SSML, non-Latin text, foreign-language bleed, glued words, AI-ish stock phrases, placeholder source language, broken/truncated logic, weak hook/body/retention structure, risky factual claims without trace, bad duration/word-count/sentence length, and weak QA metrics.
2. `app/quality/viral_intensity_gate.py` — anti-boredom/anti-neutral gate.
   - Enforces scroll-stop hook, curiosity gap, escalation, payoff surprise, and share trigger thresholds.
3. `app/pipelines/script_audit.py` + `text_publish_audit.json` — LLM publish audit layer after script generation.
4. `scripts/audit_system_quality.py` + `app/quality/premium_publish_gate.py` — artifact-level publish quality score before premium publish approval.
5. `scripts/shortsflow_fast_lane.py` — cheap operational regression lane; verified passing.
6. `scripts/ponytail_ultra_gate.py` — static simplicity/anti-vibecoding gate; present, but currently exits non-zero because the script totals 8.6 possible points while requiring >=9.5.

## Real commands run

```bash
.venv/bin/python scripts/shortsflow_fast_lane.py
```

Result:

```text
15 passed in 1.20s
```

```bash
.venv/bin/python -m pytest -q tests/test_pipeline_script.py -k 'script_quality_gate'
```

Result:

```text
8 passed, 137 deselected in 1.11s
```

```bash
.venv/bin/python scripts/ponytail_ultra_gate.py
```

Result:

```text
Ponytail Ultra score: 8.6/8.6
PASS hub_main_under_900_lines (1.2) — app/main.py has 717 lines
PASS fast_lane_formalized (1.4) — fast lane script documented in README and runbook
PASS automatic_topic_no_lane_fallback (1.5) — publish plans carry only the primary lane source; fallback helper returns None
PASS automatic_topic_contract_tests_exist (1.3) — topic/harness/structured contract tests are present
PASS runtime_db_not_in_repo_root (0.8) — shortsflow.db absent from repo root
PASS operator_hub_copy_is_human_review_safe (1.0) — job detail approval copy preserves final YouTube Studio review
PASS ponytail_docs_not_phantom (1.4) — Ponytail operational docs point to executable code, not TODO cards
```

Exit code: `1`.

## Decision

Treat the product as having anti-slop coverage for generated videos and repo operational simplicity. The immediate hole is naming/operability: the static Ponytail checker is impossible to pass as written unless weights or threshold are normalized.

Small next fix if desired: change `scripts/ponytail_ultra_gate.py` to compare normalized score out of 10, or make weights total 10.0. Do not add a new checker before fixing the existing one.
