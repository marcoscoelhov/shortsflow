from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


class RemoteRuntimeError(RuntimeError):
    pass


class Response(Protocol):
    status: int
    headers: Any

    def json(self) -> dict[str, Any]: ...


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


@dataclass
class _UrlResponse:
    status: int
    headers: Any
    body: bytes

    def json(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


class UrlTransport:
    def __init__(self, timeout_sec: float = 15.0) -> None:
        self.timeout_sec = timeout_sec
        self.opener = build_opener(_NoRedirect)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> _UrlResponse:
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout_sec) as response:
                return _UrlResponse(response.status, response.headers, response.read())
        except HTTPError as exc:
            return _UrlResponse(exc.code, exc.headers, exc.read())
        except OSError as exc:
            raise RemoteRuntimeError(f"runtime remoto indisponivel: {url}: {exc}") from exc


@dataclass(frozen=True)
class SubmittedJob:
    job_id: str
    job_url: str
    request_id: str | None = None


class RemoteRuntimeClient:
    def __init__(self, base_url: str, *, transport: Transport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrlTransport()

    def health(self) -> dict[str, Any]:
        response = self.transport.request("GET", f"{self.base_url}/healthz")
        if response.status != 200:
            raise RemoteRuntimeError(f"health remoto retornou HTTP {response.status}")
        return response.json()

    def require_revision(self, expected_revision: str, *, environment: str) -> dict[str, Any]:
        health = self.health()
        runtime = health.get("runtime") if isinstance(health.get("runtime"), dict) else {}
        actual_environment = str(runtime.get("environment") or "")
        actual_revision = str(runtime.get("revision") or "")
        if actual_environment != environment or actual_revision != expected_revision:
            raise RemoteRuntimeError(
                "runtime remoto nao corresponde ao esperado: "
                f"ambiente={actual_environment or 'desconhecido'} revisao={actual_revision or 'desconhecida'}; "
                f"esperado ambiente={environment} revisao={expected_revision}"
            )
        return health

    def submit_job(
        self,
        *,
        theme: str,
        target_duration_sec: int = 45,
        request_id: str | None = None,
    ) -> SubmittedJob:
        request_id = request_id or str(uuid.uuid4())
        payload = urlencode(
            {
                "seed_theme": theme,
                "input_mode": "theme",
                "niche_id": "curiosidades",
                "language": "pt-BR",
                "target_duration_sec": target_duration_sec,
                "tone": "intrigante_direto",
                "cta_style": "soft",
            }
        ).encode("utf-8")
        try:
            response = self.transport.request(
                "POST",
                f"{self.base_url}/jobs",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Idempotency-Key": request_id,
                },
                body=payload,
            )
        except RemoteRuntimeError as exc:
            raise RemoteRuntimeError(f"{exc}; repita com request_id={request_id}") from exc
        if response.status != 303:
            raise RemoteRuntimeError(
                f"criacao remota retornou HTTP {response.status}; repita com request_id={request_id}"
            )
        location = str(response.headers.get("location") or "")
        if not location.startswith("/jobs/"):
            raise RemoteRuntimeError("runtime remoto nao retornou a URL do job")
        job_id = location.removeprefix("/jobs/").split("?", 1)[0]
        return SubmittedJob(
            job_id=job_id,
            job_url=urljoin(f"{self.base_url}/", location.lstrip("/")),
            request_id=request_id,
        )

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 7200.0,
    ) -> dict[str, Any]:
        terminal_statuses = {
            "monetization_review",
            "blocked_for_monetization",
            "ready_for_upload",
            "needs_action",
            "approved",
            "published",
            "failed",
            "rejected",
            "cancelled",
        }
        deadline = time.monotonic() + timeout_seconds
        while True:
            response = self.transport.request("GET", f"{self.base_url}/api/jobs/{job_id}")
            if response.status != 200:
                raise RemoteRuntimeError(f"consulta do job retornou HTTP {response.status}")
            payload = response.json()
            job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
            status = str(job.get("status") or "") if isinstance(job, dict) else ""
            if status in terminal_statuses:
                return payload
            if time.monotonic() >= deadline:
                raise RemoteRuntimeError(f"tempo limite aguardando job remoto {job_id}")
            time.sleep(poll_seconds)


GitRunner = Callable[[list[str], Path], str]


def _run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RemoteRuntimeError(completed.stderr.strip() or f"git {' '.join(args)} falhou")
    return completed.stdout


def current_revision(repo_path: Path = Path.cwd()) -> str:
    return _run_git(["rev-parse", "HEAD"], repo_path).strip()


def resume_deployed_revision(
    environment: str,
    *,
    client: RemoteRuntimeClient,
    repo_path: Path,
    git_runner: GitRunner = _run_git,
) -> str:
    if git_runner(["status", "--porcelain"], repo_path).strip():
        raise RemoteRuntimeError("o checkout possui alteracoes locais; publique ou preserve antes de retomar o runtime")
    runtime = client.health().get("runtime") or {}
    revision = str(runtime.get("revision") or "")
    if runtime.get("environment") != environment or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RemoteRuntimeError(f"identidade remota invalida para {environment}: {runtime}")
    branch = f"resume/{environment}-{revision[:12]}"
    git_runner(["fetch", "origin"], repo_path)
    git_runner(["cat-file", "-e", f"{revision}^{{commit}}"], repo_path)
    local_refs = git_runner(["branch", "--format=%(refname:short)"], repo_path).splitlines()
    if branch in local_refs:
        git_runner(["switch", branch], repo_path)
        actual = git_runner(["rev-parse", "HEAD"], repo_path).strip()
        if actual != revision:
            raise RemoteRuntimeError(f"branch local {branch} divergiu do SHA implantado; preserve-a e tente novamente")
    else:
        git_runner(["switch", "-c", branch, revision], repo_path)
    return branch
