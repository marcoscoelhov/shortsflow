from __future__ import annotations

from fastapi import Request


def content_length_exceeds(request: Request, max_bytes: int) -> bool:
    raw = request.headers.get("content-length")
    if raw is None:
        return False
    try:
        return int(raw) > max_bytes
    except ValueError:
        return False


async def read_request_body_limited(request: Request, max_bytes: int) -> bytes | None:
    receive = request._receive
    received_bytes = 0
    chunks: list[bytes] = []

    while True:
        message = await receive()
        if message.get("type") == "http.request":
            chunk = message.get("body") or b""
            received_bytes += len(chunk)
            if received_bytes > max_bytes:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        elif message.get("type") == "http.disconnect":
            break

    return b"".join(chunks)


def replay_request_body(request: Request, body: bytes) -> None:
    sent = False

    async def receive_replay():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive_replay
