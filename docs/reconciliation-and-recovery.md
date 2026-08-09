# Reconciliação e recuperação

## Snapshot da migração inicial

Em 2026-08-01, antes de escolher uma base autoritativa, os estados local e da
VPS foram preservados em:

- local: `/home/marcos/.local/state/shortsflow-reconcile/20260801T151344Z`;
- VPS: `/root/shortsflow-recovery/20260801T151345Z`;
- cópia local do snapshot VPS: subdiretório `vps-copy` do snapshot local.

Cada snapshot contém bundle Git, status/log, patch binário, arquivos não
rastreados e checksums SHA-256. Os dois bundles passaram por `git bundle verify`.
Branches de recuperação foram criadas com os prefixos `recovery/local-` e
`recovery/vps-`. A árvore suja da VPS foi normalizada nos commits `1e49b71` e
`3087795`; a base consolidada está no merge `92a6586`.

## Restaurar código

1. Copie o snapshot para um host limpo sem modificar o original.
2. Execute `git bundle verify <arquivo.bundle>`.
3. Clone o bundle para um diretório temporário.
4. Aplique o patch binário somente sobre o commit registrado no snapshot.
5. Extraia o tar de arquivos não rastreados sem sobrescrever arquivos existentes.
6. Compare `git status`, `git log` e os checksums registrados.

Nunca use reset destrutivo para “igualar” local e VPS. Preserve primeiro uma
branch nomeada e faça merge ou cherry-pick revisável.

## Restaurar estado do runtime

Código vem do GitHub e releases. Estado vem dos backups por ambiente:

```bash
sudo shortsflow-backup verify /var/backups/shortsflow/production/daily-<timestamp>.db
sudo systemctl stop shortsflow-production.service
sudo cp /var/backups/shortsflow/production/daily-<timestamp>.db \
  /srv/shortsflow/production/data/shortsflow.db
sudo chown shortsflow-production:shortsflow-production \
  /srv/shortsflow/production/data/shortsflow.db
sudo systemctl start shortsflow-production.service
```

Faça a restauração primeiro em staging quando o objetivo for um exercício. Os
backups mantêm sete diários, quatro semanais e três predeploy. Secrets têm cópia
cifrada separada; não entram em bundles Git nem nos backups SQLite.

## Rollback de release

O deploy restaura automaticamente o link `current` e o SHA do environment file
se o health check falhar. Para rollback manual, selecione um dos três releases
anteriores, atualize atomicamente `current`, escreva o SHA correspondente em
`/etc/shortsflow/<ambiente>-release.env`, reinicie e confirme `/healthz`.

Se houve migração de schema incompatível, restaure também o backup predeploy
correspondente. Migrações normais devem permanecer compatíveis com a janela de
quatro releases.
