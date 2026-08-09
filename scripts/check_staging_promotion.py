#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess


REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return completed


def assert_safe_staging_promotion(
    revision: str,
    *,
    repo: Path,
    staging_ref: str = "refs/remotes/origin/staging",
    main_ref: str = "refs/remotes/origin/main",
) -> None:
    if not REVISION_RE.fullmatch(revision):
        raise ValueError("revision must be a full 40-character lowercase Git SHA")
    _git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
    if _git(repo, "show-ref", "--verify", "--quiet", staging_ref, check=False).returncode:
        raise RuntimeError(f"staging ref is unavailable: {staging_ref}")
    if _git(repo, "show-ref", "--verify", "--quiet", main_ref, check=False).returncode:
        raise RuntimeError(f"main ref is unavailable: {main_ref}")
    if _git(repo, "merge-base", "--is-ancestor", revision, staging_ref, check=False).returncode:
        raise RuntimeError(f"revision {revision} is not reachable from {staging_ref}")
    if _git(repo, "merge-base", "--is-ancestor", main_ref, revision, check=False).returncode:
        raise RuntimeError(f"revision {revision} would not fast-forward {main_ref}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail unless a revision was staged and can fast-forward main without changing its SHA."
    )
    parser.add_argument("revision")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--staging-ref", default="refs/remotes/origin/staging")
    parser.add_argument("--main-ref", default="refs/remotes/origin/main")
    args = parser.parse_args(argv)
    assert_safe_staging_promotion(
        args.revision,
        repo=args.repo,
        staging_ref=args.staging_ref,
        main_ref=args.main_ref,
    )
    print(f"safe staging promotion: {args.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
