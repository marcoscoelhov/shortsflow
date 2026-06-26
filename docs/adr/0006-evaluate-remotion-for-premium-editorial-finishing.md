# Evaluate Remotion for Premium Editorial Finishing

ShortsFlow will evaluate Remotion as a candidate for **Acabamento Editorial Premium** by generating a **Versao Premium Paralela** from a **Plano de Acabamento Editorial**, while keeping the existing `render/final.mp4` flow intact during the trial. Remotion should become the main renderer only if it wins the **Prova Comparativa de Acabamento** across comparable **Jobs de Video** and passes the **Gate de Acabamento Premium** without regressing the existing publication-ready media contracts.

**Consequences**

- The first integration must produce parallel artifacts for comparison, not replace `render/final.mp4`.
- The premium renderer consumes a dedicated finishing plan instead of reading database state directly.
- Human comparison decides perceived premium quality; automated gates decide technical eligibility.
- FFmpeg remains the operational fallback until Remotion is promoted by evidence.
- Remotion licensing must be validated before using it as the main renderer for recurring commercial production.
- The trial must not depend on paid Remotion components or paid third-party visual elements; free dependencies are allowed only when explicitly justified.
- The first trial must preserve stable scene framing; zoom, pan and push effects stay blocked until a visual audit proves they do not introduce jitter.
- The first implementation should add a finishing plan generator, an isolated Remotion subproject, a Python CLI wrapper, a premium finishing gate, a manual Hub action, a comparison view and focused tests.
- If Remotion wins the trial, promotion should happen in two phases: Remotion becomes the default renderer for new **Jobs de Video** while FFmpeg remains the automatic fallback, then FFmpeg can later be reduced to a legacy/manual path after stability is proven.
