---
name: remote-vps-runtime
description: Design, implement, audit, or explain an application workflow where GitHub is the source of truth, laptops are thin development clients, and all real provider calls or compute-heavy jobs run on a VPS. Use for new apps that need frictionless setup on multiple PCs, Tailscale access without copied SSH keys, isolated staging and production, SHA-pinned deploys, capacity admission, backups, rollback, or remote job/resume CLIs.
---

# Remote VPS Runtime

Build the smallest safe remote-runtime seam that keeps local development fast while making the VPS the only real execution environment. Reuse the contract and templates in this skill, but adapt names, ports, health fields, resource limits, and job payloads to the target repository.

## Non-negotiable invariants

- Treat GitHub as the source of truth for code. Never synchronize mutable working directories bidirectionally.
- Treat the VPS as runtime state, not a second source repository.
- Permit laptops to edit code and run deterministic tests with mock providers.
- Fail closed if a laptop tries to invoke real providers or a heavy render locally.
- Deploy an exact 40-character commit SHA into an immutable release directory.
- Keep staging and production isolated by service, data directory, database, environment file, and deploy identity.
- Share scarce accelerators through an explicit global lock. Give production the next available slot.
- Require a healthy endpoint that identifies both environment and deployed revision.
- Activate releases with an atomic pointer switch, health-check them, and roll back automatically.
- Keep production promotion behind a human approval gate.
- Use Tailscale identities and policy; do not distribute a reusable private SSH key to developer PCs.
- Define application authorization explicitly. A private URL alone is not authorization; prefer verified Tailscale Serve identity/capability headers on a loopback-only backend or a scoped application token.
- Make expensive job submission idempotent so a timeout and retry cannot duplicate provider spend.

Read [references/architecture-contract.md](references/architecture-contract.md) before designing or changing the runtime. Read [references/security-and-operations.md](references/security-and-operations.md) when the work touches access, CI, backups, capacity, or production.

## Workflow

### 1. Discover before changing

Inspect repository instructions, dirty worktrees, branches, current deployment, services, data locations, provider configuration, resource capacity, Tailscale state, and CI configuration. Preserve divergent VPS and local work with verifiable snapshots before reconciliation.

Do not copy secrets into Git. Do not replace a working production service before staging has produced an approved real artifact.

### 2. Record a repository-specific contract

Copy [assets/remote-runtime-contract.template.md](assets/remote-runtime-contract.template.md) into the repository documentation and resolve every placeholder. Explicitly decide:

- production and staging URLs;
- branch-to-environment mapping;
- CLI operations for submit, validate, status, and resume;
- health and revision schema;
- provider policy by environment;
- global capacity and priority behavior;
- retention, backup, rollback, and release counts;
- CI identities and human approval boundary.

Prefer `feature -> staging -> main`. A staging validation command must reject a local SHA that differs from the deployed SHA.

### 3. Implement test-first at stable seams

Start with contract tests for:

1. remote client routing and no-redirect behavior;
2. exact revision validation;
3. environment/revision health identity;
4. admission decisions and production priority;
5. atomic activation, health failure, and rollback;
6. retention and backup boundaries.

Keep the application-specific pipeline behind a small remote client and a small server-side admission coordinator. Avoid leaking SSH, systemd, or filesystem concepts through business modules.

### 4. Provision staging without disturbing production

Create dedicated runtime and deploy users. Install protected environment files outside release directories. Start staging on separate ports and state paths. Apply resource controls and expose it only through Tailscale.

Validate with mock tests first, then one real-provider end-to-end artifact on the exact commit. Give the user a Tailscale URL and pause for visual approval.

### 5. Promote deliberately

Configure protected GitHub environments. Let staging deploy automatically after canonical tests. Require human approval for production. Promote the same reviewed commit rather than rebuilding from an unreviewed working tree.

After activation, verify environment, SHA, dependencies, provider mode, storage, and a representative job. Retain the active release plus three prior releases unless the repository contract says otherwise.

### 6. Make every new PC boring

Provide one idempotent bootstrap script that verifies Git, the language runtime, GitHub authentication if required, and Tailscale login; installs the local CLI; links this versioned skill into the personal skill directory; and checks both remote health identities.

The normal developer loop should be:

```text
clone -> bootstrap -> edit -> cheap tests -> commit/push -> staging deploy -> validate -> review -> promote
```

`resume-code` means resolving the deployed revision and creating a new SHA-pinned local branch from Git. It must refuse a dirty checkout or a divergent existing branch and never reset or overwrite work. Keep job recovery separately named as `status`, `wait`, or `retry`; ask which meaning the user intends when “resume” is ambiguous. It does not mean copying files back from the VPS.

## Completion gate

Do not call the migration complete until all of these are true:

- snapshots can restore every reconciled source state;
- canonical tests pass on the consolidated source;
- a new PC can bootstrap without a copied SSH key;
- local real execution fails closed;
- staging and production report distinct identities and exact SHAs;
- staging produced a real artifact and the user approved it;
- production deploy has a human gate and a tested rollback;
- database migrations are backward-compatible with the rollback window, or rollback includes a tested data restore;
- backups and retention are observable;
- operational documentation teaches submit, validate, resume, deploy, rollback, and recovery.

If live access or human approval is missing, stop at the corresponding gate and report what is already verified versus what remains external.
