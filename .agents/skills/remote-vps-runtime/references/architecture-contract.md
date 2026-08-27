# Architecture contract

## Responsibility split

| Concern | Laptop | GitHub | VPS staging | VPS production |
|---|---|---|---|---|
| Edit source | yes | stores commits | no | no |
| Cheap deterministic tests | yes | yes | optional | no |
| Real providers | no | no | yes | yes |
| Heavy jobs | no | no | validation | canonical |
| Runtime state | no | no | isolated | isolated |
| Approval | proposes | records gate | evidence | human-approved |

Git commits move code. APIs move job requests and status. Artifact URLs move outputs. Backups protect state. These paths must not be collapsed into directory synchronization.

## Minimal interfaces

The local CLI needs only:

- `job`: submit to production and optionally wait;
- `validate`: assert staging SHA equals local `HEAD`, submit, and wait;
- `resume`: fetch the deployed SHA and make it available as a local branch;
- optionally `status`: inspect without mutation.

The runtime needs only:

- a health endpoint containing status, environment, revision, provider mode, worker state, and admission state;
- a job submission endpoint returning a stable job ID;
- a job detail endpoint that exposes state and artifacts.

The deploy boundary needs environment plus exact commit SHA. Everything else comes from protected environment configuration and the immutable repository revision.

Require an idempotency key on job submission and persist the key-to-job mapping. After a network timeout, query or wait by that key before retrying. Authorize submission and artifact reads with operator SSH, Tailscale Serve when it is up, or a scoped application credential. Keep the app on loopback.

## State machine

```text
commit pushed
  -> canonical tests
  -> immutable release prepared
  -> drain old worker
  -> predeploy backup
  -> atomic activation
  -> health + SHA verification
       -> success: prune old releases
       -> failure: atomic rollback + restart
```

## Admission

Measure free disk, available memory, staging artifact bytes, drain state, and global heavy-slot state. Staging should clean expired artifacts before checking its cap. If still above any configured threshold, reject or defer with explicit reasons.

Use one machine-wide lock for GPU/CPU-heavy work. When production is waiting, staging must not acquire the next slot. Do not attempt to preempt an already-running render unless the provider and pipeline explicitly support safe checkpoints.

A production waiter must hold a live marker or lock for its entire wait, not only one polling attempt. Staging checks before and after acquiring the heavy lock. Clean stale markers after process death and test the race and starvation behavior.

## Reconciliation

Before choosing an authoritative code state:

1. capture local and VPS Git bundles;
2. capture binary diffs and untracked files;
3. verify bundle restoration;
4. commit preserved dirty source onto named recovery branches;
5. merge deliberately and run the full suite;
6. leave runtime artifacts and secrets outside commits.

Never use a destructive reset to make the two machines appear consistent.
