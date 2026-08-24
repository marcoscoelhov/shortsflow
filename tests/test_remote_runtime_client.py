from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.remote_runtime import RemoteRuntimeClient, RemoteRuntimeError, resume_deployed_revision


@dataclass
class FakeResponse:
    status: int
    headers: dict[str, str]
    body: bytes = b""

    def json(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8")) if self.body else {}


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> FakeResponse:
        self.requests.append((method, url, headers or {}, body))
        return self.responses.pop(0)


class FailingTransport:
    def request(self, method, url, *, headers=None, body=None):  # noqa: ANN001, ANN201
        raise RemoteRuntimeError("runtime remoto indisponivel")


def test_remote_job_submission_returns_tailnet_job_url() -> None:
    transport = FakeTransport([FakeResponse(status=303, headers={"location": "/jobs/job-123"})])
    client = RemoteRuntimeClient("https://prod.example.ts.net", transport=transport)

    result = client.submit_job(theme="Por que o gelo estala?", target_duration_sec=45)

    assert result.job_id == "job-123"
    assert result.job_url == "https://prod.example.ts.net/jobs/job-123"
    assert result.request_id
    assert transport.requests[0][0:2] == ("POST", "https://prod.example.ts.net/jobs")
    assert transport.requests[0][2]["Idempotency-Key"] == result.request_id
    assert b"seed_theme=Por+que+o+gelo+estala%3F" in (transport.requests[0][3] or b"")
    assert b"cta_style=soft" in (transport.requests[0][3] or b"")


def test_remote_microdrama_submission_preserves_editorial_lane() -> None:
    transport = FakeTransport([FakeResponse(status=303, headers={"location": "/jobs/drama-123"})])
    client = RemoteRuntimeClient("https://staging.example.ts.net", transport=transport)

    client.submit_job(
        theme="A carta da mãe que chegou vinte anos tarde",
        target_duration_sec=120,
        niche_id="fiction_microdrama",
        requested_angle="A filha descobre quem escondeu as cartas.",
    )

    body = transport.requests[0][3] or b""
    assert b"niche_id=fiction_microdrama" in body
    assert b"target_duration_sec=120" in body
    assert b"tone=drama_chocante_reviravolta" in body
    assert b"requested_angle=A+filha+descobre+quem+escondeu+as+cartas." in body


def test_remote_experiment_submission_uses_its_editorial_tone() -> None:
    transport = FakeTransport([FakeResponse(status=303, headers={"location": "/jobs/experiment-123"})])
    client = RemoteRuntimeClient("https://staging.example.ts.net", transport=transport)

    client.submit_job(
        theme="Duas escolhas impossíveis na montanha",
        target_duration_sec=45,
        niche_id="survival_decisions",
    )

    body = transport.requests[0][3] or b""
    assert b"niche_id=survival_decisions" in body
    assert b"tone=narrativo_misterioso" in body


def test_remote_submission_rejects_duration_outside_editorial_lane() -> None:
    transport = FakeTransport([])
    client = RemoteRuntimeClient("https://staging.example.ts.net", transport=transport)

    with pytest.raises(ValueError, match="fiction_microdrama.*100.*150"):
        client.submit_job(
            theme="A carta da mãe que chegou vinte anos tarde",
            target_duration_sec=45,
            niche_id="fiction_microdrama",
        )

    assert transport.requests == []


def test_transport_failure_reports_reusable_idempotency_key() -> None:
    client = RemoteRuntimeClient("https://prod.example.ts.net", transport=FailingTransport())

    with pytest.raises(RemoteRuntimeError, match="request_id=fixed-request"):
        client.submit_job(theme="tema", request_id="fixed-request")


def test_staging_validation_fails_closed_on_revision_mismatch() -> None:
    transport = FakeTransport(
        [
            FakeResponse(
                status=200,
                headers={},
                body=json.dumps({"runtime": {"environment": "staging", "revision": "deployed-sha"}}).encode(),
            )
        ]
    )
    client = RemoteRuntimeClient("https://staging.example.ts.net", transport=transport)

    with pytest.raises(RemoteRuntimeError, match="expected-sha"):
        client.require_revision("expected-sha", environment="staging")


def test_wait_for_job_returns_only_after_remote_terminal_status() -> None:
    transport = FakeTransport(
        [
            FakeResponse(status=200, headers={}, body=json.dumps({"job": {"status": "running"}}).encode()),
            FakeResponse(
                status=200,
                headers={},
                body=json.dumps({"job": {"status": "ready_for_upload"}, "render": {"video_url": "/video.mp4"}}).encode(),
            ),
        ]
    )
    client = RemoteRuntimeClient("https://prod.example.ts.net", transport=transport)

    result = client.wait_for_job("job-123", poll_seconds=0)

    assert result["job"]["status"] == "ready_for_upload"
    assert len(transport.requests) == 2


@pytest.mark.parametrize("terminal_status", ["monetization_review", "blocked_for_monetization"])
def test_wait_for_job_recognizes_review_terminal_statuses(terminal_status: str) -> None:
    transport = FakeTransport(
        [FakeResponse(status=200, headers={}, body=json.dumps({"job": {"status": terminal_status}}).encode())]
    )

    result = RemoteRuntimeClient("https://prod.example.ts.net", transport=transport).wait_for_job(
        "job-123", poll_seconds=0
    )

    assert result["job"]["status"] == terminal_status


def test_resume_deployed_revision_creates_sha_pinned_branch(tmp_path: Path) -> None:
    revision = "a" * 40
    client = RemoteRuntimeClient(
        "https://staging.example.ts.net",
        transport=FakeTransport(
            [FakeResponse(status=200, headers={}, body=json.dumps({"runtime": {"environment": "staging", "revision": revision}}).encode())]
        ),
    )
    calls: list[list[str]] = []

    def fake_git(args: list[str], cwd: Path) -> str:
        calls.append(args)
        if args == ["status", "--porcelain"]:
            return ""
        if args == ["branch", "--format=%(refname:short)"]:
            return "main\n"
        return ""

    branch = resume_deployed_revision("staging", client=client, repo_path=tmp_path, git_runner=fake_git)

    assert branch == "resume/staging-aaaaaaaaaaaa"
    assert ["switch", "-c", branch, revision] in calls
