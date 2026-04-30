# Sprint 1: Pipeline Audit

## Current Pipeline

The runtime pipeline is implemented by `JobOrchestrator._steps()`:

1. `input_gate`
2. `topic_plan`
3. `script`
4. `scene_plan`
5. `asset_generation`
6. `tts`
7. `subtitle_alignment`
8. `render`
9. `publish_to_review_hub`

Artifacts are persisted under `data/artifacts/<job_id>/` through `StorageManager`.
Database state is stored in the SQLAlchemy models in `app/models.py`.

## Integration Points

- LLM generation currently happens through `ProviderRegistry.creative`.
- Topic planning, script generation, and scene planning are the LLM-owned stages.
- The script stage is the first high-leverage quality gate, because bad text later contaminates scenes, TTS, subtitles, and render.
- Asset selection already has scoring, but current behavior can still continue with low semantic scores in production.
- Render validation is currently mostly implicit through successful ffmpeg execution.

## Failures Observed In Exported Jobs

- Mixed language in scripts and subtitles, including English words inside pt-BR narration.
- SSML/markup leaked into subtitles, such as `</prosody`.
- Suspicious glued words and malformed phrases.
- Script attempts can fail and later complete under the same job event stream, making audit history hard to read.
- Assets can have `semantic_threshold_pass: false` and still reach review.
- Some generated image prompts are too generic for the narration beat.
- Final renders are technically valid, but encoding quality is low for 1080x1920 YouTube Shorts.

## Sprint 1 Scope Closed

This sprint establishes the implementation map and defines where Sprint 2 and Sprint 3 should patch the code:

- Provider abstraction belongs in `app/providers.py`.
- Script validation belongs in `app/quality/script_gate.py`.
- The script gate must be called from `JobOrchestrator._step_script()` before persistence and before scene generation.
- Fallback should be provider-level, but quality validation must be deterministic app code.

