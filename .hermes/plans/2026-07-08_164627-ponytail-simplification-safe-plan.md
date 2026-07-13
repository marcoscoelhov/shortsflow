# ShortsFlow Ponytail Simplification Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Keep Ponytail full active: deletion before addition, fewest files, one small check per non-trivial change.

**Goal:** Apply the safest Ponytail audit cuts to ShortsFlow without changing runtime behavior or breaking the automatic-topic/Hub/publication pipeline.

**Architecture:** Do this as small independent commits ordered by blast radius. Start with dependency-only and native replacements, then tiny duplicate-helper removals, then only the lowest-risk wrapper flattening. Do **not** touch the dirty pre-existing files (`app/watchdog.py`, `tests/test_watchdog.py`) unless Marcos explicitly asks.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Remotion/React, pytest, npm/tsc.

---

## Current Context

- Repo: `/root/shortsflow`
- Current dirty tree before this plan:
  - `app/watchdog.py`
  - `tests/test_watchdog.py`
- Audit found likely deletions:
  - Python deps: `anthropic`, `aiofiles`, `imageio` unused in app/scripts/tests.
  - Remotion deps: `@remotion/captions` only used as a type; `@remotion/media` only supplies `Audio` which Remotion exports.
  - Duplicate helpers: `music_bank._path_from_file_uri`, repeated `_float`, `_clamp`, `_text_list`, timeout runner.
  - Larger risky items: provider inheritance, BasePipeline proxies, publication/pipeline wrapper flattening.

## Non-goals / Guardrails

Do **not** implement the whole audit in one pass. Skip these until after safe cuts land:

- Do not flatten `BasePipeline` yet.
- Do not flatten `PublicationOperations` yet.
- Do not rewrite TTS provider inheritance yet.
- Do not remove LLM providers (`openai`, `xai`, `gemini`, `qwen`) yet; config/env/runtime expectations may exist.
- Do not touch external deploy, YouTube credentials, or generated runtime data.

Reason: those are high-blast-radius and not needed to get immediate Ponytail gain.

## Verification Baseline

Run before first implementation commit:

```bash
cd /root/shortsflow
git status --short --branch
.venv/bin/python -m py_compile $(find app scripts -name '*.py' -print)
npm --prefix remotion run --silent typecheck
.venv/bin/python -m pytest -q tests/test_config.py tests/test_port_guard.py tests/test_production_readiness.py
```

Expected:
- `git status` still shows only pre-existing dirty files unless the implementer has changed something.
- `py_compile` passes.
- Remotion typecheck passes before we touch imports.
- Focused pytest passes. If a pre-existing failure appears, stop and report it before changing code.

---

## Task 1: Remove dead Python dependencies only

**Objective:** Delete Python dependencies that the codebase does not import.

**Files:**
- Modify: `pyproject.toml:6-25`
- Maybe modify lock file only if repo has one and package manager requires it.

**Step 1: Reconfirm imports**

Run:

```bash
cd /root/shortsflow
.venv/bin/python - <<'PY'
from pathlib import Path
import ast, collections
root = Path('.')
imports = collections.Counter()
for base in ['app', 'scripts', 'tests']:
    for path in Path(base).rglob('*.py'):
        tree = ast.parse(path.read_text(errors='ignore'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.name.split('.')[0]] += 1
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports[node.module.split('.')[0]] += 1
for dep in ['aiofiles', 'anthropic', 'imageio']:
    print(dep, imports[dep])
PY
```

Expected:

```text
aiofiles 0
anthropic 0
imageio 0
```

**Step 2: Edit `pyproject.toml`**

Delete these lines from `[project].dependencies`:

```toml
  "aiofiles==24.1.0",
  "anthropic==0.67.0",
  "imageio==2.37.0",
```

Keep:

```toml
  "imageio-ffmpeg==0.6.0",
```

**Step 3: Verify**

Run:

```bash
cd /root/shortsflow
.venv/bin/python -m py_compile $(find app scripts -name '*.py' -print)
.venv/bin/python -m pytest -q tests/test_config.py tests/test_providers_integrations.py
```

Expected: pass.

**Step 4: Commit if requested**

Only if Marcos asks to commit:

```bash
git add pyproject.toml
git commit -m "chore: remove unused python dependencies"
```

---

## Task 2: Replace Remotion media/captions deps with native/local types

**Objective:** Remove two Remotion-side dependencies without changing rendered output.

**Files:**
- Modify: `remotion/src/PremiumShort.tsx:1-4`
- Modify: `remotion/package.json:10-17`
- Modify: lock file under `remotion/` if present.

**Step 1: Inspect current import**

Current target shape likely is:

```tsx
import React, {useMemo} from 'react';
import type {Caption as RemotionCaption} from '@remotion/captions';
import {Audio} from '@remotion/media';
import {AbsoluteFill, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
```

**Step 2: Replace imports and type**

Change to:

```tsx
import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

type RemotionCaption = {
  text: string;
  startMs: number;
  endMs: number;
  timestampMs?: number;
  confidence?: number | null;
};
```

If TypeScript reports fields are different, inspect actual local caption access in `PremiumShort.tsx` and define only the fields used. Do not import a package for a type.

**Step 3: Remove deps**

From `remotion/package.json`, delete:

```json
"@remotion/captions": "4.0.481",
"@remotion/media": "4.0.481",
```

Do not touch core `remotion`, `@remotion/cli`, React, or TypeScript.

**Step 4: Verify**

Run:

```bash
cd /root/shortsflow
npm --prefix remotion run --silent typecheck
```

Expected: pass.

Optional frame smoke if available and fast:

```bash
cd /root/shortsflow
npm --prefix remotion run --silent render -- --frames=1
```

If render command requires props and fails for missing props, do not expand this task; typecheck is enough for this dependency cut.

**Step 5: Commit if requested**

```bash
git add remotion/package.json remotion/src/PremiumShort.tsx remotion/package-lock.json
# include lock only if changed/existing
git commit -m "chore: use native remotion audio and local caption type"
```

---

## Task 3: Delete duplicate file URI parser in music bank

**Objective:** Reuse existing `app.utils.path_from_uri` instead of custom parsing.

**Files:**
- Modify: `app/music_bank.py`
- Test: smallest existing music-bank/import test if present; otherwise use `py_compile` and targeted provider tests.

**Step 1: Find usages**

Run:

```bash
cd /root/shortsflow
python - <<'PY'
from pathlib import Path
for i, line in enumerate(Path('app/music_bank.py').read_text().splitlines(), 1):
    if '_path_from_file_uri' in line or 'audio_uri' in line:
        print(f'{i}: {line}')
PY
```

Expected: `_path_from_file_uri` defined near bottom and called for `audio_uri`.

**Step 2: Modify import**

In `app/music_bank.py`, add `path_from_uri` to the existing util import or create it if absent:

```python
from app.utils import file_sha256, path_from_uri, stable_hash
```

Use the actual existing import line; do not reorder unrelated imports.

**Step 3: Replace helper call**

Replace:

```python
source_path = _path_from_file_uri(str(payload.get("audio_uri") or ""))
```

with:

```python
raw_audio_uri = str(payload.get("audio_uri") or "")
source_path = path_from_uri(raw_audio_uri) if raw_audio_uri else None
```

Preserve the existing `None` branch behavior.

**Step 4: Delete helper**

Delete:

```python
def _path_from_file_uri(value: str) -> Path | None:
    if value.startswith("file://"):
        return Path(value.removeprefix("file://"))
    if value:
        return Path(value)
    return None
```

**Step 5: Verify**

Run:

```bash
cd /root/shortsflow
.venv/bin/python -m py_compile app/music_bank.py app/providers/music.py
.venv/bin/python -m pytest -q tests/test_providers_integrations.py
```

Expected: pass.

**Step 6: Commit if requested**

```bash
git add app/music_bank.py
git commit -m "refactor: reuse file uri parser in music bank"
```

---

## Task 4: Centralize tiny duplicate numeric/text helpers only where already repeated

**Objective:** Remove repeated leaf helpers without adding a new abstraction layer.

**Files:**
- Modify: `app/utils.py`
- Modify: only files that already define identical helpers:
  - `app/quality/growth_score_gate.py`
  - `app/quality/visual_impact_gate.py`
  - `app/quality/metadata_ctr_gate.py`
  - `app/quality/asset_visual_gate.py`
  - `app/quality/visual_contract_gate.py`
  - maybe `app/quality/premium_publish_gate.py`, `app/quality/llm_judge.py` if exact signatures fit.
- Tests: focused quality gate tests.

**Step 1: Add tiny helpers to `app/utils.py`**

Append near existing text helpers, not at file bottom:

```python
def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def float_or(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ascii_lower(text: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKD", str(text or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower(),
    ).strip()


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]
```

Also add `import unicodedata` if `app/utils.py` does not already have it.

Ponytail rule: if this adds more lines than it deletes in a target file, skip that target.

**Step 2: Replace only exact matches**

Examples:

```python
from app.utils import clamp01, float_or
```

Replace `_clamp(x)` with `clamp01(x)`.
Replace `_float(x, default)` with `float_or(x, default)`.
Replace `_text_list(x)` with `text_list(x)` only where semantics are identical.

Do not force `ascii_lower` into modules with custom normalization semantics unless the output is identical enough for existing tests.

**Step 3: Delete replaced local helpers**

Delete only helpers whose all usages in that file were replaced.

**Step 4: Verify focused gates**

Run:

```bash
cd /root/shortsflow
.venv/bin/python -m pytest -q \
  tests/test_growth_quality_gates.py \
  tests/test_viral_intensity_gate.py \
  tests/test_scene_gate.py \
  tests/test_asset_visual_gate.py \
  tests/test_llm_judge.py
```

Expected: pass.

**Step 5: Verify compile**

```bash
cd /root/shortsflow
.venv/bin/python -m py_compile $(find app -name '*.py' -print)
```

Expected: pass.

**Step 6: Commit if requested**

```bash
git add app/utils.py app/quality/*.py
git commit -m "refactor: reuse tiny quality gate helpers"
```

---

## Task 5: Consolidate timeout runner without changing LLM behavior

**Objective:** Replace duplicate custom thread+queue timeout helpers with one utility.

**Files:**
- Modify: `app/utils.py`
- Modify: `app/providers/llm_routing.py`
- Modify: `app/pipelines/script_audit.py`
- Modify: `app/pipelines/script_pipeline.py` only if it delegates to the old helper.
- Tests: provider + script pipeline focused tests.

**Step 1: Add utility**

In `app/utils.py`, add:

```python
import concurrent.futures


def call_with_timeout(func: Any, timeout_sec: float) -> Any:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        return future.result(timeout=timeout_sec)
```

Important: this waits for executor shutdown. If the current behavior intentionally abandons stuck daemon threads, do **not** use this exact helper for LLM calls. In that case, skip Task 5 and keep current code; correctness beats line count.

**Step 2: Decide if behavior is safe**

Before editing, check whether existing code relies on daemon thread abandonment:

- `app/providers/llm_routing.py` currently starts daemon threads and raises timeout without joining forever.
- `app/pipelines/script_audit.py` also starts daemon threads.

If remote LLM calls can hang beyond timeout, `ThreadPoolExecutor` context manager may block on shutdown. If so, do not implement this task. Record as deferred, not a code change.

**Step 3: Only if safe, replace calls**

Replace local `_run_primary_with_timeout` and `_call_with_timeout` internals with `call_with_timeout` or delete wrappers where possible.

**Step 4: Verify**

Run:

```bash
cd /root/shortsflow
.venv/bin/python -m pytest -q tests/test_pipeline_script.py tests/test_providers_integrations.py
.venv/bin/python -m py_compile app/providers/llm_routing.py app/pipelines/script_audit.py app/pipelines/script_pipeline.py
```

Expected: pass.

**Ponytail likely decision:** Skip this task unless a quick spike proves no shutdown hang. A duplicated 20-line daemon timeout helper is ugly but safer than changing timeout semantics around provider calls.

---

## Task 6: Run full validation bundle

**Objective:** Prove safe cuts did not break the app.

**Files:** none.

**Step 1: Python compile**

```bash
cd /root/shortsflow
.venv/bin/python -m py_compile $(find app scripts -name '*.py' -print)
```

Expected: pass.

**Step 2: Remotion typecheck**

```bash
cd /root/shortsflow
npm --prefix remotion run --silent typecheck
```

Expected: pass.

**Step 3: Focused pytest**

```bash
cd /root/shortsflow
.venv/bin/python -m pytest -q \
  tests/test_config.py \
  tests/test_providers_integrations.py \
  tests/test_growth_quality_gates.py \
  tests/test_scene_gate.py \
  tests/test_asset_visual_gate.py \
  tests/test_pipeline_script.py
```

Expected: pass. If `tests/test_pipeline_script.py` is slow, run specific tests touched by helper replacements first, then full file.

**Step 4: Full pytest if focused passes**

```bash
cd /root/shortsflow
.venv/bin/python -m pytest -q
```

Expected: pass or known pre-existing failures only. If full suite fails, rerun failing tests isolated before blaming the patch.

**Step 5: Diff checks**

```bash
cd /root/shortsflow
git diff --check
git status --short --branch
```

Expected:
- no whitespace errors;
- only intended files changed plus pre-existing `app/watchdog.py` and `tests/test_watchdog.py`.

---

## Task 7: Stop point and report

**Objective:** Avoid turning simplification into a refactor project.

Report:

- deps removed;
- lines removed/added from `git diff --stat`;
- tests actually run and result;
- skipped audit items and why.

Run:

```bash
cd /root/shortsflow
git diff --stat
```

Suggested final summary format:

```text
Ponytail safe pass done.
Cut: <deps/files/helpers>.
Verified: <commands>.
Skipped: BasePipeline/publication flattening/provider inheritance — high blast radius, do only when touching those flows for real work.
```

---

## Execution Order Summary

1. Baseline checks.
2. Remove dead Python deps.
3. Remove Remotion deps via native/local type.
4. Reuse `path_from_uri` in `music_bank.py`.
5. Centralize only tiny exact-match helpers if net-negative lines.
6. Skip timeout helper unless behavior-safe.
7. Full validation and report.

## Risk Ranking

- Low: dependency deletion after import scan.
- Low: Remotion `Audio` native import + local type, if typecheck passes.
- Low: `music_bank` helper deletion using existing robust parser.
- Medium: quality helper centralization; run focused gates.
- High: timeout runner consolidation; likely skip.
- High: provider inheritance/BasePipeline/publication flattening; explicitly out of this pass.
