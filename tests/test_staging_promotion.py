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


def test_accepts_staged_merge_commit_that_still_fast_forwards_main(
    promotion_repo: tuple[Path, str, str],
) -> None:
    repo, main_revision, _staged_revision = promotion_repo
    _git(repo, "switch", "--detach", main_revision)
    (repo / "parallel.txt").write_text("parallel staged work\n", encoding="utf-8")
    _git(repo, "add", "parallel.txt")
    _git(repo, "commit", "-m", "parallel staged work")
    merged_revision = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "staging")
    _git(repo, "merge", "--no-ff", merged_revision, "-m", "reconcile staged work")
    staged_revision = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/staging", staged_revision)

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
    assert "expected_revision:" in workflow
    assert '"${CANDIDATE_SHA}" != "${EXPECTED_REVISION}"' in workflow


def test_promotion_workflow_pushes_exact_sha_without_force() -> None:
    workflow = Path(".github/workflows/promote-staging.yml").read_text(encoding="utf-8")
    deploy_workflow = Path(".github/workflows/deploy-remote-runtime.yml").read_text(encoding="utf-8")

    assert "environment: staging" in workflow
    assert "\n  validate-promotion:" in workflow
    assert "\n  promote:" in workflow
    assert "\n  authorize-promotion:" not in workflow
    assert "environment: production-promotion" not in workflow
    assert workflow.index("\n  validate-promotion:") < workflow.index("\n  promote:")
    promote_job = workflow.split("\n  promote:", 1)[1]
    assert "needs: validate-promotion" in promote_job
    assert "needs: authorize-promotion" not in promote_job
    assert "environment:" not in promote_job
    assert "tailscale/github-action@v4" in workflow
    assert "https://srv769897.tailc97b69.ts.net:8443/healthz" in workflow
    assert 'r["environment"] == "staging"' in workflow
    assert 'r["revision"] == os.environ["REVISION"]' in workflow
    assert 'git push origin "${REVISION}:refs/heads/main"' in workflow
    assert "actions: write" in workflow
    assert 'gh workflow run deploy-remote-runtime.yml --ref main -f expected_revision="${REVISION}"' in workflow
    assert "--force" not in workflow
    assert "scripts/check_staging_promotion.py" in workflow
    assert "shortsflow-deploy" not in workflow
    assert "github.ref_name == 'main' && 'production'" in deploy_workflow
    assert "environment: production-promotion" not in deploy_workflow
