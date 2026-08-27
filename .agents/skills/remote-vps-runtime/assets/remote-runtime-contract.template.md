# Remote runtime contract

## Authority

- Source of truth: `<GitHub repository>`
- Real runtime: `<VPS hostname>`
- Local policy: `<mocks on the laptop; real jobs on the VPS; guidance, not a required check>`

## Environments

| Environment | Branch | URL | Service | Data | Deploy identity |
|---|---|---|---|---|---|
| staging | `<branch>` | `<Tailscale URL or SSH tunnel to 127.0.0.1>` | `<unit>` | `<path>` | `<tag/user>` |
| production | `<branch>` | `<Tailscale URL or SSH tunnel to 127.0.0.1>` | `<unit>` | `<path>` | `<tag/user>` |

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
- Production approval: `<one GitHub environment named production; watch a real staging video first>`

## Recovery

- Daily backups: `<count>`
- Weekly backups: `<count>`
- Predeploy backups: `<count>`
- Restore drill: `<command and cadence>`
- Reconciliation snapshots: `<location and verification>`

## Acceptance gates

- [ ] Real jobs stay on the VPS; laptops use mocks
- [ ] Operator SSH works; Tailscale is extra, not fail-closed
- [ ] Staging deploys exact SHA
- [ ] Staging real E2E artifact approved
- [ ] Production requires human approval
- [ ] Rollback tested
- [ ] Backup restoration tested
