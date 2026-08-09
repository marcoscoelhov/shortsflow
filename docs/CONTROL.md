# ShortsFlow Control

Last updated: 2026-07-31T21:25:28+00:00

## Product North Star

Build ShortsFlow into a faceless vertical-video operating system: AI-generated, AI-operated production for 9:16 videos, starting with YouTube Shorts and expanding to TikTok/other compatible platforms.

The app must eventually manage multiple channels, each with its own niche, dashboard, metrics, quality gates, scheduling, publication, and performance feedback loop.

## Current Business North Star

Prove the engine can produce at least one breakout/viral short on one channel before expanding surface area.

- Minimum proof: 1 video reaches viral breakout status.
- Working viral definition until Marcos overrides it: `10,000+ views` or `10x current mature median`, whichever is higher.
- Current mature median: 396 views from 39 reliable real YouTube Analytics snapshots on 2026-07-31.
- Secondary health target: 600+ mature median views.
- Cadence: 1 strong cosmos/astronomy video/day.
- Scope now: one YouTube Shorts channel, winner-model visual/extreme cosmos topics.
- Source now: curated cosmos seed bank.

## Capability Ladder

1. **Prove one-channel engine**: reliable idea → script → assets → narration → render → quality audit → schedule → YouTube feedback.
2. **Stabilize control loop**: dashboard/CONTROL/Kanban show objective, progress, bottleneck, and one next action.
3. **Generalize channel model**: channel profile = niche, prompts, quality thresholds, schedule, metrics, platform accounts.
4. **Add platform abstraction**: publish package maps to YouTube Shorts first, then TikTok/others without changing generation core.
5. **Scale operator mode**: multiple dashboards/channels, portfolio metrics, per-channel decisions, automated discard/repair/publish policies.

## Active Experiment

`automatic_topic` must prefer topics with:

- visual impossibility in the first second;
- cosmic scale or extreme object;
- concrete consequence/risk/paradox;
- specific real object early in title/hook;
- no repeated dead title template.

## Current Evidence

- Analytics refreshed on 2026-07-31: 79 videos, 39 reliable mature snapshots, 17,717 total views.
- Breakout not reached: best video has 882 views; current target is 10,000 views.
- Mature median is 396 views, still below the 600+ secondary health target.
- Current top repeat pattern: concrete cosmic paradox + visual object — Lua no horizonte, Vênus mais quente que Mercúrio, Marte vermelho/ferrugem, anéis de Saturno e som de buraco negro/NASA.
- Rendering can reach `ready_for_upload`; automatic generation still shows repeated `gate_rejected` and premium-audit gaps, but the latest watchdog reports 4 future scheduled slots and no recovery needed. Premium audit score below target is diagnostic; technical blockers are not.
- CEO/operator brief loop exists weekly on Discord and must read this file first.

## Policy Reconciliation — 2026-07-31

- Luna `high` generates/plans; Grok 4.5 `high` judges gates; general fallback remains disabled.
- Premium audit score is diagnostic and distinct from the `0.82` autoapproval score.
- Premium preflight must fail closed and run before approval, scheduling or publication on every platform.
- Local or remote Qwen is diagnostic-only: it cannot approve gates, confirm human review, schedule, or publish. `survival_decisions` always requires human review, including pilots.
- The survival dry-run is not the persistent experiment/feedback loop from Plan 009.
- Canonical record: `docs/adr/0002-reconcile-2026-07-31-publication-vision-and-llm-policy.md`.

## Last Production Run

- Job: `b1bb2c65-25b9-47ff-86e3-1b9632f4a9ce`
- Title: `Buraco negro não grava som. NASA criou áudio com ondas de pressão`
- Source: P0 cosmos sprint / real production providers
- Final status: `approved_for_publish`
- Autoapproval: 0.963, eligible=true
- Monetization: `ready_for_upload`, no hard blockers
- Video: 1080x1920, H.264/AAC, 46.03s
- Final file: `/root/shortsflow/data/artifacts/b1bb2c65-25b9-47ff-86e3-1b9632f4a9ce/render/final.mp4`

## Last YouTube Schedule Confirmation

- Schedule ID: `b559a7c6-944b-4f74-bacc-ad53c6b35457`
- YouTube video ID: `hcNz3BaAlc4`
- URL: `https://www.youtube.com/watch?v=hcNz3BaAlc4`
- Local slot: `2026-07-04T11:00 America/Sao_Paulo`
- YouTube API verified: `privacyStatus=private`, `publishAt=2026-07-04T14:00:00Z`, `uploadStatus=processed`
- Confirmation artifact: `/root/shortsflow/data/youtube_schedule_confirm_b1bb2c65.json`

## Previous Good Run

- Job: `f4c46dcd-5363-4395-aa8f-4893006ceb3d`
- Source: real `automatic_topic` after audit patch
- Generation status: `ready_for_upload`
- Publish package: `ready_for_publish`
- Autoapproval: 0.963, eligible=true
- Audit: `overall_min_score=9.4`, `passed_target=true`
- YouTube video ID: `I9ddt_ZYAA4`
- Local slot: `2026-07-03T11:00 America/Sao_Paulo`
- Confirmation artifact: `/root/shortsflow/data/youtube_schedule_confirm_f4c46dcd.json`

## Last Cancelled Candidate

- Job: `8182528b-8743-4457-801f-6bccc06375c0`
- Title: `Gota do Príncipe Rupert: resiste a pancadas, mas explode na cauda`
- Decision: **cancelled before publication** — off-scope for current cosmos/astronomy lane.
- YouTube video ID: `M4FTY5HdhzU`
- Cancellation artifact: `/root/shortsflow/data-kanban/viral_sprint_h1_20260701-182713/cancel_offscope_schedule_8182528b.json`

## Current Bottleneck

Publication safety hardening is the immediate bottleneck before the next automated pilot: YouTube schedule/publish paths still bypass premium preflight, the premium audit does not yet convert every technical blocker into a reason, and fresh visual attempts do not fully validate local provider/model provenance. Performance learning remains the business bottleneck after these safety gaps close.

## Next Task

Single next task: close and regression-test the three publication-safety gaps above without changing niche or editorial strategy; then let the 4-slot scheduled cosmos queue mature and rerun the weekly Analytics sync/report.

Acceptance:

- maintain 1 strong cosmos/astronomy scheduled or published video/day;
- keep at least 3 future scheduled slots; do not force generation while coverage remains healthy;
- execute premium preflight in YouTube approval/schedule/publish paths;
- reject audit-reported hard blockers even when the premium score is diagnostic;
- require approved local provider/model provenance with no fallback before automatic visual confirmation;
- do not change niche/strategy before mature evidence exists;
- check YouTube performance for scheduled videos after they mature;
- update baseline/median only from real performance evidence;
- if performance stalls after enough mature samples, revise topic selection instead of adding platform surface.

## Not Now

- multi-nicho;
- radar/trends automation;
- redesign;
- large refactor;
- external deploy.
