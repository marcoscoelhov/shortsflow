# Legacy quarantine

This directory stores code that was removed from the active runtime but kept temporarily for audit before final deletion.

Rules:

- Nothing under `legacy/` is imported by the app, tests, CLI or scripts.
- Do not add new dependencies on this directory.
- If a snippet is needed again, move the behavior back into the current owner module instead of importing from here.
- Delete entries after one stable release cycle when no rollback or reference is needed.

Current entries:

- `sidebar-hidden-controls/`: old hidden sidebar controls replaced by modal-based hub controls.
- `provider-facade/app_providers_init.py`: old `app.providers` re-export facade replaced by direct provider-module imports.
- `tests/test_e2e_compat_anchor.py`: old empty compatibility anchor for the split domain test suite.
