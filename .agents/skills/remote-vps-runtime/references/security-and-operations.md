# Security and operations

## Access and CI

- Operator interactive access is SSH that already works. Tailscale is an extra lock for Serve/HTTPS and for GitHub Actions, not a fail-closed business gate.
- If Tailscale is down, the operator uses SSH. Never fall back to rendering real jobs on a laptop.
- Use ephemeral, tagged OAuth identities for CI when Tailscale is used (`tailscale ssh deploy@host`).
- Use different CI tags and Unix deploy users for staging and production.
- Restrict each tag to the minimum destination, port, SSH user, and environment.
- Keep OAuth credentials in environment-scoped GitHub secrets.
- Protect one production GitHub environment with a required human reviewer. Do not add a second self-approval environment.
- Keep the app on `127.0.0.1`. Do not open extra public ports. Do not bind the app off loopback.
- Avoid `StrictHostKeyChecking=no` and broad passwordless access from untrusted networks.

Keep tailnet policy deny-by-default when Tailscale is in use. Separate network grants from SSH rules: the operator may reach the private HTTPS service and approved SSH accounts; `tag:ci-staging` may SSH only as the staging deploy user; `tag:ci-production` may SSH only as the production deploy user. Make the VPS tag owner distinct from both CI tag owners.

Start from [the deny-by-default template](../assets/tailscale-policy.template.hujson), replace principals for the actual tailnet, and merge it deliberately with existing policy instead of overwriting the admin console blindly.

## Secrets

Keep provider keys in root-owned environment files outside `/opt/.../releases`. A release may contain a generated file with non-secret deployment identity such as the commit SHA. Never archive `.env` into a release or backup it alongside public source artifacts.

Store a separately encrypted recovery copy of secrets in a secret manager or offline vault and test reconstructing environment files. Database backups must never silently become the secret backup.

## Releases and rollback

Use one release directory per SHA and an atomic `current` symlink. A deploy should fail before activation if checkout, dependency installation, or capacity checks fail. Once activated, verify the health endpoint and exact SHA. On failure, restore the previous symlink and service before returning an error.

Verify that staging SHAs are reachable from the protected staging branch and production SHAs from the protected main branch. Prefer fast-forward promotion of the exact staging-approved SHA. Schema changes must remain readable by every retained release, or the rollback procedure must restore the matching predeploy database backup.

Keep active plus three prior releases by default. Do not prune the rollback target.

## Data protection

Use application-consistent database backups. For SQLite, use its backup API rather than copying a live database file. Keep production and staging backups separate. A reasonable default is seven daily, four weekly, and three predeploy backups. Test restoration, not just creation.

## Capacity defaults for a small VPS

Start conservatively and measure:

- one global heavy-job slot;
- production next-slot priority;
- staging admission floor of 15 GiB free disk;
- staging admission floor of 2 GiB available RAM;
- staging artifact cap of 5 GiB;
- staging TTL of seven days;
- lower CPU/IO weight and a memory ceiling for staging.

These are policy defaults, not universal sizing advice. A smaller host may need staging disabled while production is busy. A larger host may raise limits only after observing provider, encoder, and vision-service peaks.

## Operational checks

After every deploy, record or expose:

- environment and SHA;
- service health and restart count;
- worker enabled state;
- provider/mock mode;
- disk, memory, artifact usage, and admission reasons;
- last successful backup;
- active and rollback release targets.
