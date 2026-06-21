# Separate Visual Contract From Scene Planning

We generate a **Contrato Visual do Roteiro** after the approved script and before the **Plano de Cenas**, instead of asking the scene planner to infer visual promise, loop tension, beat progression and payoff reveal directly from the script every time. This keeps the metaprompt free to produce varied **Roteiros Virais Estruturados** while giving scene planning and asset validation a stable semantic contract: the plan must respect the contract before image generation, generated assets must be checked against it, and real runs fail closed when the contract cannot be generated or validated.

**Consequences**

- `visual_contract.json` is an audit artifact between `script.json` and `scene_plan.json`.
- A weak hook image is treated as a visual contract or validation failure, not just an aesthetic issue.
- Retry behavior is split: regenerate the **Plano de Cenas** when it violates the contract, regenerate only the asset when the image violates an otherwise valid plan.
- The provider-facing **Especificacao Visual da Cena** stays compact and concrete because MiniMax `image-01` receives one prompt string, not a separate negative prompt contract, and rejects prompts over its character limit.
- The first scene must keep explicit first-frame-hook language, avoid revealing the later payoff, and carry no-text/no-brand/no-panel constraints even when the prompt is compacted for provider limits.
