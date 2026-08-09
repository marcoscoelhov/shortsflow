from __future__ import annotations

from types import SimpleNamespace

from app import cli
from app.remote_runtime import SubmittedJob


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.required_revision: tuple[str, str] | None = None
        self.submitted: tuple[str, int] | None = None
        self.instances.append(self)

    def require_revision(self, revision: str, *, environment: str):
        self.required_revision = (revision, environment)
        return {}

    def submit_job(self, *, theme: str, target_duration_sec: int, request_id: str | None = None) -> SubmittedJob:
        self.submitted = (theme, target_duration_sec)
        return SubmittedJob(job_id="job-123", job_url=f"{self.base_url}/jobs/job-123", request_id=request_id or "generated")


def test_job_command_always_targets_remote_production(monkeypatch, capsys) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(cli, "RemoteRuntimeClient", FakeClient)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            remote_production_url="https://prod.example.ts.net",
            remote_staging_url="https://staging.example.ts.net",
        ),
    )

    cli.main(["job", "--theme", "Por que o gelo estala?", "--duration", "35"])

    client = FakeClient.instances[0]
    assert client.base_url == "https://prod.example.ts.net"
    assert client.submitted == ("Por que o gelo estala?", 35)
    assert "https://prod.example.ts.net/jobs/job-123" in capsys.readouterr().out


def test_validate_command_checks_staging_revision_before_submission(monkeypatch, capsys) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(cli, "RemoteRuntimeClient", FakeClient)
    monkeypatch.setattr(cli, "current_revision", lambda: "abc123")
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            remote_production_url="https://prod.example.ts.net",
            remote_staging_url="https://staging.example.ts.net",
        ),
    )

    cli.main(["validate", "--theme", "Teste remoto", "--duration", "45"])

    client = FakeClient.instances[0]
    assert client.base_url == "https://staging.example.ts.net"
    assert client.required_revision == ("abc123", "staging")
    assert client.submitted == ("Teste remoto", 45)
    assert "job-123" in capsys.readouterr().out
