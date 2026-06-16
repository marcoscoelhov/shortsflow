# YTS Render Remotion

Subprojeto isolado para gerar a **Versao Premium Paralela** da prova de **Acabamento Editorial Premium**.

Uso local:

```bash
cd remotion
npm install
npm run typecheck
npm run render -- /caminho/para/render/premium.mp4 --props /caminho/para/render/edit_plan.json
```

O Hub chama o binario local em `remotion/node_modules/.bin/remotion`; ele nao baixa dependencias durante a acao manual.
Use `npm run typecheck` para validar TypeScript sem disparar render.
