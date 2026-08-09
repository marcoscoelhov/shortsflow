from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.check_staging_promotion import assert_safe_staging_promotion


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    marker = repo / "history.txt"
    marker.write_text(f"{marker.read_text() if marker.exists() else ''}{message}\n", encoding="utf-8")
    _git(repo, "add", "history.txt")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def promotion_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "ShortsFlow Tests")
    _git(repo, "config", "user.email", "tests@shortsflow.invalid")
    main_revision = _commit(repo, "main")
    _git(repo, "branch", "staging")
    _git(repo, "switch", "staging")
    staged_revision = _commit(repo, "validated staging")
    _git(repo, "update-ref", "refs/remotes/origin/main", main_revision)
    _git(repo, "update-ref", "refs/remotes/origin/staging", staged_revision)
    return repo, main_revision, staged_revision


def test_accepts_same_staged_sha_that_fast_forwards_main(promotion_repo: tuple[Path, str, str]) -> None:
    repo, _main_revision, staged_revision = promotion_repo

    assert_safe_staging_promotion(staged_revision, repo=repo)


def test_rejects_feature_sha_not_reachable_from_staging(promotion_repo: tuple[Path, str, str]) -> None:
    repo, main_revision, _staged_revision = promotion_repo
    _git(repo, "switch", "--detach", main_revision)
    feature_revision = _commit(repo, "unstaged feature")

    with pytest.raises(RuntimeError, match="not reachable from refs/remotes/origin/staging"):
        assert_safe_staging_promotion(feature_revision, repo=repo)


def test_rejects_staged_sha_that_cannot_fast_forward_main(promotion_repo: tuple[Path, str, str]) -> None:
    repo, main_revision, staged_revision = promotion_repo
    _git(repo, "switch", "--detach", main_revision)
    divergent_main = _commit(repo, "divergent main")
    _git(repo, "update-ref", "refs/remotes/origin/main", divergent_main)

    with pytest.raises(RuntimeError, match="would not fast-forward refs/remotes/origin/main"):
        assert_safe_staging_promotion(staged_revision, repo=repo)


def test_deploy_workflow_guards_main_before_production_environment() -> None:
    workflow = Path(".github/workflows/deploy-remote-runtime.yml").read_text(encoding="utf-8")

    assert "promotion-guard:" in workflow
    assert "needs: [test, promotion-guard]" in workflow
    assert workflow.index("promotion-guard:") < workflow.index("environment:")
    assert "scripts/check_staging_promotion.py" in workflow


def test_promotion_workflow_pushes_exact_sha_without_force() -> None:
    workflow = Path(".github/workflows/promote-staging.yml").read_text(encoding="utf-8")

    assert "environment: production" in workflow
    assert 'git push origin "${REVISION}:refs/heads/main"' in workflow
    assert "--force" not in workflow
    assert "scripts/check_staging_promotion.py" in workflow
