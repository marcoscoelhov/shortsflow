# Remotion as Primary Renderer

ShortsFlow will use Remotion as the primary renderer for new **Jobs de Video**. The render stage keeps the public media contract at `render/final.mp4` and `render/poster.jpg`, but its operational artifacts are now Remotion-first: `render/remotion.log`, `render/edit_plan.json` and `premium_finishing_report.json`.

This supersedes the trial posture from ADR-0006 for the main render path. FFmpeg remains in the codebase as an explicit legacy maintenance backend through `SHORTSFLOW_PRIMARY_BACKEND=ffmpeg`, but it is not the default operational path.

**Consequences**

- Local and production setup must install Node dependencies in `remotion/` before processing **Jobs de Video**.
- Remotion dependency upgrades are part of the security surface and must be validated with `npm audit --omit=dev` and `npm run typecheck`.
- Python tests may still force the legacy FFmpeg backend where they are testing older media contracts, but at least one focused configuration test must assert that default settings select Remotion.
- Future render fixes should improve the Remotion path first; FFmpeg changes should be scoped to legacy maintenance or migration support.
