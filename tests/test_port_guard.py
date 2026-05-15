from __future__ import annotations

import socket
from pathlib import Path

from scripts.yts_port_guard import release_port


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_port_guard_accepts_free_port() -> None:
    port = _free_port()

    result = release_port(
        host="127.0.0.1",
        port=port,
        repo_root=Path("/tmp/definitely-not-yts-render"),
        timeout_sec=0.1,
        force=False,
    )

    assert result == 0


def test_port_guard_refuses_foreign_listener_without_force() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = int(sock.getsockname()[1])

        result = release_port(
            host="127.0.0.1",
            port=port,
            repo_root=Path("/tmp/definitely-not-yts-render"),
            timeout_sec=0.1,
            force=False,
        )

    assert result == 2
