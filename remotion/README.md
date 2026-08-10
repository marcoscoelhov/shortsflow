# ShortsFlow Remotion

Subprojeto isolado que gera o `render/final.mp4` com **Acabamento Editorial Premium**.

Remotion e o unico renderer de video do ShortsFlow. O Hub chama o binario local em `remotion/node_modules/.bin/remotion`; ele nao baixa dependencias durante a execucao do worker.

Uso local:

```bash
cd remotion
npm install
npm run typecheck
npm run render -- /caminho/para/render/final.mp4 --props /caminho/para/render/edit_plan.json
```

Use `npm run typecheck` para validar TypeScript sem disparar render.
