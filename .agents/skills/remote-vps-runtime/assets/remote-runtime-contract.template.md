# Remote runtime contract

## Authority

- Source of truth: `<GitHub repository>`
- Real runtime: `<VPS hostname>`
- Local policy: `<mock/cheap tests only; real execution fails closed>`

## Environments

| Environment | Branch | URL | Service | Data | Deploy identity |
|---|---|---|---|---|---|
| staging | `<branch>` | `<Tailscale URL>` | `<unit>` | `<path>` | `<tag/user>` |
| production | `<branch>` | `<Tailscale URL>` | `<unit>` | `<path>` | `<tag/user>` |

## Developer interface

- Submit production: `<command>`
- Validate exact staging SHA: `<command>`
- Resume deployed revision: `<command>`
- Bootstrap a new PC: `<command>`

## Runtime guarantees

- Health schema: `<environment, revision, provider mode, worker, admission>`
- Global heavy capacity: `<lock and priority>`
- Staging limits: `<disk, RAM, artifacts, TTL>`
- Isolation: `<DB, artifacts, env, service>`

## Delivery

- Deploy input: `<full commit SHA>`
- Activation: `<atomic mechanism>`
- Verification: `<health and representative check>`
- Rollback: `<automatic and manual path>`
- Retained releases: `<count>`
- Production approval: `<GitHub environment/reviewer>`

## Recovery

- Daily backups: `<count>`
- Weekly backups: `<count>`
- Predeploy backups: `<count>`
- Restore drill: `<command and cadence>`
- Reconciliation snapshots: `<location and verification>`

## Acceptance gates

- [ ] Local real execution fails closed
- [ ] New PC bootstrap works without copied SSH keys
- [ ] Staging deploys exact SHA
- [ ] Staging real E2E artifact approved
- [ ] Production requires human approval
- [ ] Rollback tested
- [ ] Backup restoration tested
