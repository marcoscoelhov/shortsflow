from __future__ import annotations

import argparse
import os
import signal
import socket
import time
from pathlib import Path


LISTEN_STATE = "0A"


def _tcp_listen_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        if not table.exists():
            continue
        for line in table.read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10 or fields[3] != LISTEN_STATE:
                continue
            _, port_hex = fields[1].rsplit(":", 1)
            if int(port_hex, 16) == port:
                inodes.add(fields[9])
    return inodes


def _pids_for_inodes(inodes: set[str]) -> set[int]:
    pids: set[int] = set()
    if not inodes:
        return pids
    for proc_entry in Path("/proc").iterdir():
        if not proc_entry.name.isdigit():
            continue
        fd_dir = proc_entry / "fd"
        try:
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    pids.add(int(proc_entry.name))
                    break
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return pids


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _cwd(pid: int) -> Path | None:
    try:
        return Path(os.readlink(f"/proc/{pid}/cwd")).resolve()
    except OSError:
        return None


def _is_yts_render_process(pid: int, repo_root: Path) -> bool:
    cmdline = _cmdline(pid)
    cwd = _cwd(pid)
    if cwd is None:
        return False
    try:
        in_repo = cwd == repo_root or repo_root in cwd.parents
    except RuntimeError:
        in_repo = False
    return in_repo and "uvicorn" in cmdline and "app.main:app" in cmdline


def _wait_until_free(port: int, timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _tcp_listen_inodes(port):
            return True
        time.sleep(0.2)
    return not _tcp_listen_inodes(port)


def _assert_bind_available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))


def release_port(host: str, port: int, repo_root: Path, timeout_sec: float, force: bool) -> int:
    inodes = _tcp_listen_inodes(port)
    pids = _pids_for_inodes(inodes)
    if not pids:
        _assert_bind_available(host, port)
        print(f"port_guard: {host}:{port} is available")
        return 0

    foreign: list[int] = []
    owned: list[int] = []
    for pid in sorted(pids):
        if _is_yts_render_process(pid, repo_root):
            owned.append(pid)
        else:
            foreign.append(pid)

    if foreign and not force:
        for pid in foreign:
            print(f"port_guard: refusing to kill foreign pid={pid} cmd={_cmdline(pid)!r}")
        return 2

    targets = owned + foreign
    for pid in targets:
        print(f"port_guard: terminating pid={pid} cmd={_cmdline(pid)!r}")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    if not _wait_until_free(port, timeout_sec):
        for pid in targets:
            print(f"port_guard: killing stubborn pid={pid} cmd={_cmdline(pid)!r}")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not _wait_until_free(port, 3.0):
            print(f"port_guard: {host}:{port} is still occupied")
            return 3

    _assert_bind_available(host, port)
    print(f"port_guard: {host}:{port} is available")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Release the YTS Render hub port before systemd starts uvicorn.")
    parser.add_argument("--host", default=os.environ.get("YTS_APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("YTS_APP_PORT", "8080")))
    parser.add_argument("--repo-root", default=os.environ.get("YTS_REPO_ROOT", os.getcwd()))
    parser.add_argument("--timeout-sec", type=float, default=15.0)
    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("YTS_PORT_GUARD_FORCE", "").lower() in {"1", "true", "yes"},
        help="Allow killing non-YTS processes on the target port.",
    )
    args = parser.parse_args()
    return release_port(
        host=args.host,
        port=args.port,
        repo_root=Path(args.repo_root).resolve(),
        timeout_sec=args.timeout_sec,
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
