# ShortsFlow Architecture Cleanup Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Use Codex CLI as preferred executor for implementation where useful, but Hermes must independently review diffs and run verification.

**Goal:** Align ShortsFlow architecture with Marcos's decisions: isolated automatic-topic lane, Edge TTS as primary publishable voice, no active fact-pack policy, final human review in YouTube Studio, reduced god-files, centralized contracts, and smaller Hub routers.

**Architecture:** This is a staged cleanup, not a rewrite. First lock product policy and restore a clean test baseline. Then refactor large modules behind existing public contracts. Preserve step names, job statuses, artifact names, Hub behavior, local-only operation, DeepSeek low-cost routing, Remotion render, SQLite data, and systemd-local runtime.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite WAL, Jinja2, pytest, Remotion/Node for render, DeepSeek/Qwen/OpenAI-compatible LLM providers, Edge TTS, MiniMax image, local systemd services.

---

## Non-Negotiable Product Decisions

These decisions are canonical for this plan:

1. `automatic_topic` is isolated. It must not silently fall back to `ready_script_bank`.
2. Fix current baseline failures and documentation drift.
3. Documentation must match runtime behavior.
4. Edge TTS is the primary configured narrator and is not a publish-blocker by itself.
5. The active fact-pack policy is removed. Do not require fact-pack as a policy gate.
6. Human review for final publish decision happens in YouTube Studio, not as a mandatory internal ShortsFlow gate.
7. Refactor large files without changing public contracts.
8. Centralize status/reason/artifact/source constants.
9. Extract routers from `app/main.py` while preserving Hub behavior.

## Global Constraints

- Repo: `/root/shortsflow`.
- Do not suggest or introduce external deploy.
- Do not expose secrets or print `.env` values.
- Preserve runtime contracts:
  - step names from `JobOrchestrator._steps()`;
  - terminal/operational statuses;
  - artifact filenames;
  - `quality_summary` high-level keys;
  - Hub routes unless the task explicitly preserves redirects via router extraction.
- Keep tests deterministic and cheap; use mock providers in tests.
- Do not import anything from `legacy/` into runtime, tests, CLI, or scripts.
- Existing working tree is dirty. Each agent must inspect relevant diffs before editing and avoid unrelated changes.

## Baseline Evidence From Diagnosis

Current known issues to resolve:

```text
pytest focused baseline:
94 passed, 1 failed
failed: tests/test_orchestrator_flow.py::test_automation_keeps_auto_topic_lane_separate_from_ready_script_bank
```

Failure cause:

```text
18:00 automatic_topic currently has fallback_source=ready_script_bank
```

Current runtime config observed:

```text
llm_primary_provider=deepseek
llm_script_draft_provider=deepseek
llm_repair_provider=deepseek
llm_scene_provider=deepseek
llm_gate_judge_provider=deepseek
llm_gate_judge_model=deepseek-v4-flash
llm_fallback_provider=disabled
tts_primary_provider=edge_tts
render_primary_backend=remotion
auto_visual_review_enabled=False
fact_pack_enabled=False
youtube_publish_mode=api
youtube_api_enabled=True
watchdog_enabled=True
```

Current health endpoint observed OK:

```text
/providers.mode=production
/providers.llm_primary=deepseek
/providers.tts_primary=edge_tts
/render.remotion_ready=true
```

Known hygiene issue:

```text
git diff --check fails on tests/test_pipeline_script.py: blank line at EOF
```

---

# Phase 1 — Policy and Baseline

## Task 1: Isolate the automatic-topic lane

**Objective:** Make `automatic_topic` fail visibly instead of silently filling with `ready_script_bank`.

**Agent:** Agent 1 — Automation Policy / Lane Isolation

**Files:**
- Modify: `app/automation.py`
- Modify: `tests/test_orchestrator_flow.py` only if assertions need tightening
- Possibly Modify: `docs/app.md`, but prefer leaving docs to Task 3

**Required behavior:**

```text
11:00 source=ready_script_bank fallback=None
18:00 source=automatic_topic fallback=None
```

**Step 1: Inspect current implementation and dirty diff**

Run:

```bash
git diff -- app/automation.py tests/test_orchestrator_flow.py
python - <<'PY'
from app.automation import AutomationService
from app.orchestrator import orchestrator
s=AutomationService(orchestrator)
for t in s._automation_publish_times():
    print(t, s._automation_publish_source_for_time(t), s._automation_fallback_source_for_time(t))
PY
```

Expected before fix:

```text
18:00 automatic_topic ready_script_bank
```

**Step 2: Write/confirm failing test**

The existing test should express the desired policy:

```python
def test_automation_keeps_auto_topic_lane_separate_from_ready_script_bank() -> None:
    from app.automation import AUTOMATION_SOURCE_READY_SCRIPT, PublishPlan

    service = AutomationService(orchestrator)
    assert service._automation_fallback_source_for_time("18:00") is None
    plan = PublishPlan(
        slot=PublishSlot(local_date=datetime(2026, 6, 22).date(), local_time="18:00", timezone="UTC"),
        source=service._automation_publish_source_for_time("18:00"),
        fallback_source=service._automation_fallback_source_for_time("18:00"),
    )

    assert plan.source == "automatic_topic"
    assert AUTOMATION_SOURCE_READY_SCRIPT not in plan.sources
```

Run:

```bash
python -m pytest tests/test_orchestrator_flow.py::test_automation_keeps_auto_topic_lane_separate_from_ready_script_bank -q
```

Expected before fix: FAIL.

**Step 3: Implement minimal policy change**

In `AutomationService._automation_fallback_source_for_time`, remove automatic-topic fallback logic. The implementation should return `None` unless a future explicit source has a documented fallback. For now:

```python
def _automation_fallback_source_for_time(self, publish_time: str) -> str | None:
    return None
```

If keeping parsing for future clarity, ensure secondary slot still returns `None`.

**Step 4: Verify focused behavior**

Run:

```bash
python - <<'PY'
from app.automation import AutomationService
from app.orchestrator import orchestrator
s=AutomationService(orchestrator)
for t in s._automation_publish_times():
    print(t, 'source=', s._automation_publish_source_for_time(t), 'fallback=', s._automation_fallback_source_for_time(t))
PY
python -m pytest tests/test_orchestrator_flow.py::test_automation_keeps_auto_topic_lane_separate_from_ready_script_bank -q
python -m pytest tests/test_orchestrator_flow.py -q
```

Expected after fix:

```text
11:00 source= ready_script_bank fallback= None
18:00 source= automatic_topic fallback= None
```

**Step 5: Report**

Report files changed, commands run, and exact pytest output.

---

## Task 2: Fix repository hygiene baseline

**Objective:** Remove current whitespace/lint baseline blocker without changing behavior.

**Agent:** Agent 1 may do this immediately after Task 1, or Integration Reviewer may do it if isolated.

**Files:**
- Modify: `tests/test_pipeline_script.py`

**Step 1: Reproduce hygiene failure**

Run:

```bash
git diff --check
```

Expected before fix:

```text
tests/test_pipeline_script.py:3781: new blank line at EOF.
```

**Step 2: Remove trailing blank line at EOF only**

Do not edit test logic. Remove only the trailing blank line.

**Step 3: Verify**

Run:

```bash
git diff --check
```

Expected: no output, exit 0.

---

## Task 3: Align product/runtime documentation

**Objective:** Make README and docs reflect Marcos's decisions and runtime reality.

**Agent:** Agent 2 — Runtime Policy Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/app.md`
- Modify: `docs/modularization-plan.md` only if needed
- Do not modify generated artifacts or runtime DB

**Step 1: Search for stale language**

Run:

```bash
rg -n "fact_pack|fact-pack|Edge TTS|edge_tts|emerg|bloque|manual review|human review|YouTube Studio|ready_script_bank|automatic_topic|fallback" README.md docs app tests
```

Use `search_files` if operating through Hermes tools.

**Step 2: Update TTS policy docs**

Replace stale statements that say Edge TTS is emergency/blocking. The docs must say:

```text
Edge TTS is the configured primary narrator in the current local runtime and is not a publish blocker by itself. Rights/commercial-use policy is controlled by the app settings and AI-generated commercial rights confirmation, not by treating Edge as emergency-only.
```

Preserve notes about Gemini/ElevenLabs as optional providers/fallbacks if still true in code.

**Step 3: Remove active fact-pack policy language**

Docs must say:

```text
ShortsFlow no longer has an active fact-pack-required policy gate. Factual quality gates still reject clearly unsafe or false claims, but absence of fact_pack is not by itself a policy blocker.
```

Do not claim that source quality is unimportant. The gate remains conservative for risky/false claims.

**Step 4: Document YouTube Studio review policy**

Docs must say:

```text
ShortsFlow prepares, audits, schedules, and uploads packages, but the final human publish/review decision is expected in YouTube Studio. Internal Hub review surfaces diagnostics and operational state; it should not be described as a mandatory final human-review gate.
```

**Step 5: Document lane isolation**

Docs must say:

```text
The daily automation lanes are intentionally separate: ready_script_bank and automatic_topic do not silently replace each other. A failed automatic-topic lane should surface as an operational gap/alert, not be masked by bank content.
```

**Step 6: Verify docs-only diff**

Run:

```bash
git diff -- README.md docs/app.md docs/modularization-plan.md
git diff --check
```

Expected: only intended doc edits.

---

# Phase 2 — Quality Gate Policy

## Task 4: Remove fact-pack-required policy from script and monetization gates

**Objective:** Stop treating missing fact-pack as a standalone policy blocker.

**Agent:** Agent 3 — Quality Gates / Monetization Policy

**Files:**
- Modify: `app/quality/script_gate.py`
- Modify: `app/pipelines/script_pipeline.py`
- Modify: `app/pipelines/script_fact_pack.py` if it emits policy-only blockers
- Modify: `app/pipelines/script_repair.py` if it repairs solely because fact-pack is absent
- Modify: `app/pipelines/monetization_pipeline.py`
- Modify: `scripts/audit_system_quality.py`
- Modify tests under `tests/test_pipeline_script.py`, `tests/test_hub_publication.py`, `tests/test_growth_quality_gates.py` as needed

**Step 1: Locate policy blockers**

Search:

```bash
rg -n "fact_pack_missing|fact_pack_required|fact-pack|required.*fact|missing_for_factual|factual_topic|fact_pack_enabled" app tests scripts
```

**Step 2: Add or update tests first**

Write/update tests that prove:

- A script is not failed solely because `fact_pack` is missing.
- A clearly false/high-risk claim can still fail by factual quality reason, not by missing fact-pack policy.
- The audit does not report missing fact-pack as a target-score blocker.

Suggested test names:

```python
def test_script_gate_does_not_require_fact_pack_policy_when_disabled(): ...
def test_script_gate_still_rejects_clear_false_claim_without_fact_pack_policy(): ...
def test_audit_does_not_penalize_missing_fact_pack_as_policy_gap(): ...
```

Run selected tests and confirm RED if code still has policy blocker.

**Step 3: Remove policy-only blockers**

Remove or downgrade reason codes like:

```text
fact_pack_missing_for_factual_topic
fact_pack_source_ids_missing
high_risk_claims_need_fact_pack_grounding
```

Only remove them as hard policy blockers. If useful diagnostically, they can become warnings/notes such as:

```text
factual_grounding_not_provided
```

But the absence alone must not block.

**Step 4: Preserve factual safety**

Do not remove checks for:

- obvious falsehood;
- unsupported medical/engineering high-risk advice;
- invented source IDs when source IDs are explicitly present;
- hallucinated metadata;
- off-topic content.

If needed, rename blockers to factual-quality blockers not fact-pack policy blockers.

**Step 5: Verify**

Run:

```bash
python -m pytest tests/test_pipeline_script.py tests/test_hub_publication.py tests/test_growth_quality_gates.py -q
```

Report exact failures if old expectations remain.

---

## Task 5: Make Edge TTS primary publishable and non-blocking

**Objective:** Align monetization/readiness with Edge as the accepted primary narrator.

**Agent:** Agent 3, after Task 4

**Files:**
- Modify: `app/pipelines/monetization_pipeline.py`
- Modify: `app/providers/tts.py` only if metadata mislabels Edge as fallback/emergency
- Modify: `app/config.py` if defaults need explicit confirmation
- Modify tests:
  - `tests/test_pipeline_assets.py`
  - `tests/test_hub_publication.py`
  - `tests/test_premium_finishing.py`

**Step 1: Locate TTS blockers**

Run:

```bash
rg -n "technical_tts_provider_not_publishable|edge_tts|Edge TTS|fallback_used|narration_publishability|commercial_rights" app tests
```

**Step 2: Add/update tests first**

Tests should prove:

- `edge_tts` narration is not blocked solely by provider name.
- `edge_tts` configured as primary does not emit `technical_tts_provider_not_publishable`.
- `synthetic_wav`/`espeak_ng` remain technical fallbacks and can still block.

Suggested assertions:

```python
blockers = orchestrator.monetization_pipeline.narration_publishability_blockers(
    SimpleNamespace(provider="edge_tts", provider_metadata={"fallback_used": False})
)
assert "technical_tts_provider_not_publishable" not in blockers
```

**Step 3: Implement policy**

Ensure `TECHNICAL_TTS_PROVIDERS` does not include `edge_tts`. Edge should be in AI/commercial-rights providers if required by rights registry.

**Step 4: Verify**

Run:

```bash
python -m pytest tests/test_pipeline_assets.py tests/test_hub_publication.py tests/test_premium_finishing.py -q
```

---

## Task 6: Remove mandatory internal human-review gate and align with YouTube Studio review

**Objective:** ShortsFlow should not block publishability merely because internal human review is pending; final human review is in YouTube Studio.

**Agent:** Agent 3

**Files:**
- Modify: `app/pipelines/monetization_pipeline.py`
- Modify: `app/publication_ops.py` if review state blocks publication incorrectly
- Modify: `app/hub_publication_context.py` if UI text says mandatory final review
- Modify tests:
  - `tests/test_hub_publication.py`
  - `tests/test_orchestrator_flow.py`

**Step 1: Locate internal review requirements**

Search:

```bash
rg -n "manual_required|needs_manual_review|human_review|review_required|monetization_review|ready_for_upload|YouTube Studio" app tests docs
```

**Step 2: Define behavior in tests**

Expected behavior:

- Pipeline can reach `ready_for_upload` if quality/rights/render pass.
- Hub can show diagnostics and publish package status, but not require internal human approval as a quality-gate prerequisite.
- Final review language should point to YouTube Studio.

**Step 3: Implement minimal changes**

Remove internal mandatory review from blockers/manual_required if it only exists as final human decision. Keep real blockers:

- failed quality gates;
- missing rights config;
- broken render;
- missing video file;
- invalid publish metadata.

**Step 4: Verify**

Run:

```bash
python -m pytest tests/test_hub_publication.py tests/test_orchestrator_flow.py -q
```

---

# Phase 3 — Contract Centralization

## Task 7: Create domain contract modules for statuses, reasons, artifacts, and sources

**Objective:** Reduce typo drift by centralizing public strings while preserving exact string values.

**Agent:** Agent 7 — Domain Contracts

**Files:**
- Create: `app/domain/__init__.py`
- Create: `app/domain/job_status.py`
- Create: `app/domain/schedule_status.py`
- Create: `app/domain/quality_reasons.py`
- Create: `app/domain/artifacts.py`
- Create: `app/domain/automation_sources.py`
- Modify consumers gradually in `app/automation.py`, `app/orchestrator.py`, `app/pipelines/*`, `app/publication_ops.py`, `app/hub_context.py`
- Tests: `tests/test_config.py`, `tests/test_orchestrator_flow.py`, `tests/test_hub_publication.py`

**Step 1: Add constants without changing consumers**

Create constants with exact values:

```python
# app/domain/job_status.py
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_READY_FOR_UPLOAD = "ready_for_upload"
JOB_STATUS_APPROVED_FOR_PUBLISH = "approved_for_publish"
JOB_STATUS_PUBLISHED = "published"
JOB_STATUS_BLOCKED_FOR_MONETIZATION = "blocked_for_monetization"
JOB_STATUS_MONETIZATION_REVIEW = "monetization_review"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_REJECTED = "rejected"
SCRIPT_QUALITY_FAILED = "script_quality_failed"
SCENE_PLAN_QUALITY_FAILED = "scene_plan_quality_failed"
ASSET_QUALITY_FAILED = "asset_quality_failed"
SUBTITLE_QUALITY_FAILED = "subtitle_quality_failed"
RENDER_QUALITY_FAILED = "render_quality_failed"
```

```python
# app/domain/automation_sources.py
AUTOMATION_SOURCE_READY_SCRIPT = "ready_script_bank"
AUTOMATION_SOURCE_AUTO_TOPIC = "automatic_topic"
```

```python
# app/domain/artifacts.py
ARTIFACT_FACT_PACK = "fact_pack.json"
ARTIFACT_SCRIPT = "script.json"
ARTIFACT_SCENE_PLAN = "scene_plan.json"
ARTIFACT_MONETIZATION_REPORT = "monetization_report.json"
ARTIFACT_PUBLISH_PACKAGE = "publish_package.json"
ARTIFACT_PUBLICATION_SCHEDULE = "publication_schedule.json"
ARTIFACT_EVENTS = "events.jsonl"
```

**Step 2: Add tests for constants preserving values**

Create/update a small test in `tests/test_config.py` or new `tests/test_domain_contracts.py`:

```python
def test_domain_contract_constants_preserve_public_values():
    from app.domain.job_status import JOB_STATUS_READY_FOR_UPLOAD
    from app.domain.automation_sources import AUTOMATION_SOURCE_AUTO_TOPIC
    assert JOB_STATUS_READY_FOR_UPLOAD == "ready_for_upload"
    assert AUTOMATION_SOURCE_AUTO_TOPIC == "automatic_topic"
```

Run and pass.

**Step 3: Replace imports in one domain at a time**

Start with `automation_sources`, then statuses. Do not mass-replace blindly.

**Step 4: Verify**

Run:

```bash
python -m pytest tests/test_config.py tests/test_orchestrator_flow.py tests/test_hub_publication.py -q
```

---

# Phase 4 — Large File Refactors

## Task 8: Refactor automation into planner/source/approval/recovery modules

**Objective:** Reduce `app/automation.py` size and isolate automation responsibilities without behavior drift.

**Agent:** Agent 5 — Automation Refactor

**Files:**
- Modify: `app/automation.py`
- Create package or modules, preferred:
  - `app/automation_schedule.py` or `app/automation/schedule_planner.py`
  - `app/automation_sources.py` or `app/automation/source_selector.py`
  - `app/automation_autoapproval.py` or `app/automation/autoapproval.py`
  - `app/automation_recovery.py` or `app/automation/recovery.py`
- Preserve current imports where tests expect `from app.automation import AutomationService`
- Tests: `tests/test_orchestrator_flow.py`, `tests/test_backlog_recovery.py`, `tests/test_watchdog.py`

**Important:** Avoid name conflict with existing `app/automation.py` if converting to package. Safer first step: create sibling modules like `automation_schedule.py`, then later convert package only if necessary.

**Step 1: Identify cohesive extraction targets**

Start with pure functions/classes that need minimal owner state:

- publish time normalization;
- vacant slot planning;
- source selection;
- autoapproval score helpers;
- failure classification/recovery helpers.

**Step 2: Add tests around extracted behavior before moving**

Use existing tests and add focused tests if needed:

```python
def test_automation_source_selector_keeps_auto_topic_isolated(): ...
def test_automation_generation_attempts_are_per_slot(): ...
```

**Step 3: Extract one module at a time**

Recommended first module:

```python
# app/automation_schedule.py
@dataclass(frozen=True)
class PublishSlot: ...
@dataclass(frozen=True)
class PublishPlan: ...

def automation_publish_times(primary: str, secondary: str) -> list[str]: ...
def automation_publish_source_for_time(publish_time: str, primary_time: str, secondary_time: str) -> str: ...
def automation_fallback_source_for_time(publish_time: str, primary_time: str, secondary_time: str) -> str | None:
    return None
```

Keep compatibility reexports in `app/automation.py` if tests import `PublishSlot` or `PublishPlan` from it.

**Step 4: Verify after each extraction**

Run:

```bash
python -m pytest tests/test_orchestrator_flow.py -q
```

Then broader:

```bash
python -m pytest tests/test_orchestrator_flow.py tests/test_backlog_recovery.py tests/test_watchdog.py -q
```

---

## Task 9: Refactor LLM/TTS providers into smaller modules

**Objective:** Reduce `app/providers/llm.py` and keep DeepSeek routing stable.

**Agent:** Agent 4 — Provider Refactor

**Files:**
- Modify: `app/providers/llm.py`
- Create suggested modules:
  - `app/providers/llm_protocols.py`
  - `app/providers/llm_mock.py`
  - `app/providers/llm_minimax.py`
  - `app/providers/llm_openai_compatible.py`
  - `app/providers/llm_routing.py`
  - `app/providers/llm_prompts.py`
- Modify: `app/providers/registry.py` only if import paths change
- Modify: `app/providers/tts.py` only for small cleanup, not as main scope
- Tests: `tests/test_providers_integrations.py`, `tests/test_pipeline_assets.py`, `tests/test_pipeline_script.py`

**Step 1: Lock behavior with tests**

Ensure tests cover:

```python
def test_llm_quality_judge_candidates_use_premium_only_for_explicit_exception(): ...
def test_deepseek_json_completion_uses_json_response_format(): ...
def test_llm_registry_uses_deepseek_for_repair_and_scene_defaults(): ...
```

**Step 2: Extract protocols and mock provider first**

Move `LLMProvider` and `MockCreativeProvider` into dedicated modules. Keep backward-compatible imports in `llm.py` if needed.

**Step 3: Extract OpenAI-compatible providers**

Move DeepSeek/Qwen/XAI/OpenAI-compatible shared logic into a module that preserves:

```text
response_format={"type":"json_object"}
max_tokens=settings.llm_json_max_tokens
system prompt explicitly says JSON
```

**Step 4: Extract routing policy**

Move `LLMProviderRegistry` and/or `ResilientCreativeProvider` candidate selection only after provider classes are stable.

**Step 5: Verify behavior**

Run:

```bash
python -m pytest tests/test_providers_integrations.py tests/test_pipeline_assets.py tests/test_pipeline_script.py -q
python - <<'PY'
from app.providers.llm import ResilientCreativeProvider
p=ResilientCreativeProvider()
print('normal_roles', [role for role,_ in p._quality_judge_candidates('script', {'review_tier':'normal'})])
print('premium_roles', [role for role,_ in p._quality_judge_candidates('growth_score', {'review_tier':'premium','growth_score':'promising'})])
PY
```

Expected:

```text
normal_roles ['gate_judge', 'repair']
premium_roles ['premium_review', 'gate_judge', 'repair']
```

---

## Task 10: Extract FastAPI routers from `app/main.py`

**Objective:** Reduce `main.py` while preserving Hub behavior and routes.

**Agent:** Agent 6 — Hub/API Router Refactor

**Files:**
- Modify: `app/main.py`
- Create suggested routers:
  - `app/routes/jobs.py`
  - `app/routes/publication.py`
  - `app/routes/settings.py`
  - `app/routes/youtube.py`
  - `app/routes/competitive_scout.py`
  - `app/routes/calendar.py`
- Existing: `app/routes/health.py`
- Tests: `tests/test_hub_publication.py`, maybe `tests/test_orchestrator_flow.py`

**Step 1: Inventory routes**

Run:

```bash
python - <<'PY'
import ast
p='app/main.py'
t=ast.parse(open(p).read())
for n in t.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        decos=[ast.unparse(d) for d in n.decorator_list]
        route_decos=[d for d in decos if d.startswith('app.')]
        if route_decos:
            print(n.lineno, n.name, route_decos)
PY
```

**Step 2: Extract one router at a time**

Start with lowest-risk clusters:

1. settings routes;
2. YouTube OAuth routes;
3. competitive scout routes;
4. publication/calendar routes;
5. job routes last.

Keep shared dependencies explicit. Do not hide too much in globals.

**Step 3: Preserve route paths and redirects**

For each moved route, tests should still hit the same URL.

**Step 4: Verify after each cluster**

Run:

```bash
python -m pytest tests/test_hub_publication.py -q
curl -fsS http://127.0.0.1:8080/healthz
```

If the service is not restarted during test, also verify app import:

```bash
python - <<'PY'
from app.main import app
print(len(app.routes))
PY
```

---

# Phase 5 — Final Integration Gate

## Task 11: Final integration review and verification

**Objective:** Verify all changes satisfy Marcos's decisions and did not break runtime contracts.

**Agent:** Agent 8 — Integration Reviewer

**Files:**
- Review all modified files.
- Do not implement new features unless fixing integration regressions.

**Step 1: Review diff summary**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected:

```text
git diff --check exits 0
```

**Step 2: Review policy compliance**

Search for contradictions:

```bash
rg -n "fact_pack_missing_for_factual_topic|fact_pack_required|Edge TTS.*emerg|technical_tts_provider_not_publishable|ready_script_bank.*fallback|automatic_topic.*fallback|needs_manual_review|manual_required" app tests README.md docs scripts
```

Expected:

- No active fact-pack-required blockers.
- No Edge-as-emergency-blocker policy.
- No automatic-topic fallback to ready-script bank.
- No internal final human review as mandatory publish gate.

**Step 3: Run focused test suite**

Run:

```bash
python -m pytest \
  tests/test_config.py \
  tests/test_providers_integrations.py \
  tests/test_orchestrator_flow.py \
  tests/test_pipeline_script.py \
  tests/test_pipeline_assets.py \
  tests/test_hub_publication.py \
  -q
```

If this is too slow but still within local constraints, run it anyway. If a failure is unrelated/flaky, capture exact failure and classify.

**Step 4: Verify health and routing**

Run:

```bash
curl -fsS http://127.0.0.1:8080/healthz
python - <<'PY'
from app.config import get_settings
s=get_settings()
for k in ['llm_primary_provider','llm_gate_judge_provider','llm_gate_judge_model','tts_primary_provider','render_primary_backend','fact_pack_enabled','auto_visual_review_enabled']:
    print(f'{k}={getattr(s,k)}')
PY
```

Expected:

```text
llm_primary_provider=deepseek
llm_gate_judge_provider=deepseek
llm_gate_judge_model=deepseek-v4-flash
tts_primary_provider=edge_tts
render_primary_backend=remotion
fact_pack_enabled=False
```

**Step 5: Verify LLM routing policy**

Run:

```bash
python - <<'PY'
from app.providers.llm import ResilientCreativeProvider
p=ResilientCreativeProvider()
print('normal_roles', [role for role,_ in p._quality_judge_candidates('script', {'review_tier':'normal'})])
print('premium_roles', [role for role,_ in p._quality_judge_candidates('growth_score', {'review_tier':'premium','growth_score':'promising'})])
PY
```

Expected:

```text
normal_roles ['gate_judge', 'repair']
premium_roles ['premium_review', 'gate_judge', 'repair']
```

**Step 6: Audit known good job**

Run:

```bash
PYTHONPATH=. python scripts/audit_system_quality.py 812fafef-a9a3-4160-99ef-e070d9909d6b --json
```

Expected:

- No fact-pack-missing policy blocker.
- Edge TTS accepted as configured primary.
- Visual review wording aligned with cost-first/no internal human final gate.

**Step 7: Final report**

Report:

```text
- Files changed
- Tests run with exact output summary
- Health output summary
- Remaining risks/blockers
- Whether ready to commit
```

---

# Agent Dispatch Map

Use this map when dispatching subagents/Codex.

## Agent 1 — Automation Policy / Lane Isolation

**Goal:** Implement Tasks 1 and 2.

**Success criteria:**

```text
18:00 source=automatic_topic fallback=None
pytest tests/test_orchestrator_flow.py -q passes or only unrelated failures documented
git diff --check passes
```

## Agent 2 — Runtime Policy Docs

**Goal:** Implement Task 3.

**Success criteria:** Docs match decisions; `git diff --check` passes.

## Agent 3 — Quality Gates / Monetization Policy

**Goal:** Implement Tasks 4, 5, and 6.

**Success criteria:** Tests for script/assets/hub publication pass; no active fact-pack-required policy; Edge TTS accepted.

## Agent 4 — Provider Refactor

**Goal:** Implement Task 9.

**Success criteria:** Provider tests pass; routing roles remain unchanged.

## Agent 5 — Automation Refactor

**Goal:** Implement Task 8.

**Success criteria:** Automation tests pass; public imports preserved.

## Agent 6 — Hub/API Router Refactor

**Goal:** Implement Task 10.

**Success criteria:** Hub publication tests pass; route paths preserved; health import works.

## Agent 7 — Domain Contracts

**Goal:** Implement Task 7.

**Success criteria:** Constants preserve exact public values; focused tests pass.

## Agent 8 — Integration Reviewer

**Goal:** Implement Task 11.

**Success criteria:** Final focused suite, health, audit, diff check complete.

---

# Recommended Execution Order

```text
1. Agent 1 — Automation lane + hygiene
2. Agent 3 — Quality gates policy
3. Agent 2 — Docs alignment
4. Agent 7 — Domain constants
5. Agent 5 — Automation refactor
6. Agent 4 — Provider refactor
7. Agent 6 — Router refactor
8. Agent 8 — Integration review
```

Avoid parallel implementation across agents that touch the same files. Safe partial parallelism only after Phase 1:

```text
Agent 4 and Agent 6 may run in parallel if Agent 7 is done and neither touches automation/quality gates.
```

---

# Final Acceptance Checklist

- [ ] `automatic_topic` has no silent fallback to `ready_script_bank`.
- [ ] Edge TTS is documented and implemented as primary non-blocking narrator.
- [ ] No active fact-pack-required policy gate remains.
- [ ] Internal Hub review is not described or enforced as final human publish gate; final review is in YouTube Studio.
- [ ] `app/automation.py`, `app/providers/llm.py`, and `app/main.py` are smaller or have clear extraction path with preserved behavior.
- [ ] Status/source/artifact constants exist and preserve public string values.
- [ ] `git diff --check` passes.
- [ ] Focused pytest suite passes or unrelated legacy failures are explicitly scoped.
- [ ] `/healthz` returns OK.
- [ ] Known good job audit does not contradict new policy.
