# ShortsFlow PR1-PR5 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the operational gaps identified in the ShortsFlow audit without a risky rewrite.

**Architecture:** Add small, testable operational capabilities around the existing FastAPI/CLI/watchdog/backlog systems. Keep publication safety rules conservative: automation may repair recoverable jobs, but human-checkpoint jobs stay blocked.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, Jinja templates, systemd/Tailscale operational checks, Remotion typecheck.

## Global Constraints

- Do not print, commit, or persist real secrets; report only boolean presence for tokens.
- Preserve mock-provider deterministic tests.
- Keep fallback costs controlled; do not enable expensive LLM fallback by default.
- Keep changes bite-sized and covered by tests.
- Do not publish or schedule `needs_checkpoint` jobs automatically.
- Run fast lane and full test suite before completion.

---

### Task 1: Production Readiness CLI

**Files:**
- Create: `app/production_readiness.py`
- Modify: `app/cli.py`
- Test: `tests/test_production_readiness.py`

**Interfaces:**
- Produces: `ProductionReadinessCheck`, `ProductionReadinessReport`, `ProductionReadinessService.evaluate()`.
- CLI command: `.venv/bin/python -m app.cli production-readiness --json`.

- [ ] Write failing tests for missing Hub token, bad Tailserve route, and JSON CLI output.
- [ ] Implement readiness checks for Hub token, YouTube connection, future schedule coverage, provider/mock settings, Remotion readiness, and optional Tailscale serve status parser.
- [ ] Wire CLI command.
- [ ] Run focused tests and commit.

### Task 2: Watchdog Recovery Planning

**Files:**
- Modify: `app/watchdog.py`
- Modify: `app/backlog_recovery.py`
- Modify: `app/cli.py`
- Test: `tests/test_watchdog_recovery.py`, `tests/test_backlog_recovery.py`

**Interfaces:**
- Produces: `AutomationWatchdog.recovery_plan(report)` and CLI `automation-watchdog --recover`.
- Recovery never mutates `needs_checkpoint` candidates.

- [ ] Write failing tests showing low coverage recommends safe recovery and checkpoint candidates are reported but not repaired.
- [ ] Add recovery summary metadata to watchdog output.
- [ ] Add `--recover` to run reactive backlog recovery after evaluating watchdog.
- [ ] Run focused tests and commit.

### Task 3: Script Provider Failure Classification

**Files:**
- Modify: `app/providers/llm_routing.py`
- Test: `tests/test_providers_integrations.py`, `tests/test_pipeline_script.py`

**Interfaces:**
- Produces deterministic provider/model de-duplication and clearer failure metadata for empty/timeout script generation.

- [ ] Extend tests around duplicate provider/model retries and empty script responses.
- [ ] Keep one attempt per provider/model identity.
- [ ] Attach provider failure reasons into final `ProviderFailure` message without adding deterministic fake fallback.
- [ ] Run focused tests and commit.

### Task 4: Maintenance Dashboard Context and Hub UI

**Files:**
- Modify: `app/automation.py`
- Modify: `app/hub_context.py` or publication context module if that owns dashboard context.
- Modify: `app/templates/publication_dashboard.html`
- Test: `tests/test_hub_publication.py`

**Interfaces:**
- Produces dashboard fields: future scheduled count, last watchdog status, actionable checkpoint count, near-publishable count, and next recommended action.

- [ ] Write failing template/context test for maintenance status section.
- [ ] Add compact maintenance summary to shared publication dashboard context.
- [ ] Render “o que fazer agora” with safe action labels.
- [ ] Run focused tests and commit.

### Task 5: Policy Boundary Extraction (Opportunistic, No Rewrite)

**Files:**
- Create: `app/policies/publication_policy.py`
- Modify: `app/backlog_recovery.py` only if the extraction reduces local complexity.
- Test: `tests/test_publication_policy.py`, existing backlog tests.

**Interfaces:**
- Produces: `classify_recovery_gate(evidence_text: str, duplicate_risk: bool) -> RecoveryGateDecision`.

- [ ] Write failing tests for factual/rights risk, duplicate risk, correctable risk, and safe near-publishable path.
- [ ] Extract only the policy constants and classification helper used by backlog recovery.
- [ ] Preserve existing backlog behavior.
- [ ] Run focused tests and commit.

### Final Verification

- [ ] Run `.venv/bin/python scripts/shortsflow_fast_lane.py`.
- [ ] Run `.venv/bin/python -m pytest -q`.
- [ ] Run `.venv/bin/python -m py_compile $(find app scripts -name '*.py' -print)`.
- [ ] Run `npm --prefix remotion run --silent typecheck`.
- [ ] Run `git diff --check`.
- [ ] Run `curl -fsS http://127.0.0.1:8080/healthz` after service restart if runtime code changed.
- [ ] Report commits, verification output, and remaining external config items such as Hub token value not set.
