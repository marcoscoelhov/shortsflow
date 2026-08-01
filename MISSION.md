# Mission: Operar o ShortsFlow remotamente com segurança

## Why
Trabalhar em qualquer computador leve sem gastar CPU local, mantendo geração, providers e renderização na VPS. Conseguir evoluir o código sem colocar o ambiente que produz os vídeos em risco.

## Success looks like
- Distinguir claramente desenvolvimento, staging e produção.
- Enviar mudanças pelo GitHub e validar o comportamento na VPS.
- Promover somente mudanças verificadas para o ambiente de produção.
- Continuar o trabalho em outro computador após autenticar GitHub e Tailscale.

## Constraints
- A máquina local não deve renderizar vídeos nem executar jobs pesados.
- Segredos, banco e artefatos permanecem na VPS.
- O fluxo deve exigir pouca operação manual depois do primeiro acesso.

## Out of scope
- Distribuir um único job entre várias máquinas.
- Sincronizar SQLite ou artefatos de mídia pelo GitHub.
- Implantar alterações não commitadas diretamente em produção.
