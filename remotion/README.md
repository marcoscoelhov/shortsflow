# YTS Render Remotion

Subprojeto isolado para gerar o render principal Remotion e a **Versao Premium Paralela** da prova de **Acabamento Editorial Premium**.

O render principal operacional do YTS Render usa `YTS_RENDER_PRIMARY_BACKEND=remotion` por padrao. O Hub chama o binario local em `remotion/node_modules/.bin/remotion`; ele nao baixa dependencias durante a execucao do worker.

Uso local:

```bash
cd remotion
npm install
npm run typecheck
npm run render -- /caminho/para/render/premium.mp4 --props /caminho/para/render/edit_plan.json
```

Use `npm run typecheck` para validar TypeScript sem disparar render.
