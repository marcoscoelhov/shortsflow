from __future__ import annotations

from urllib.parse import urlencode

from fastapi.responses import RedirectResponse


def safe_return_to(return_to: str | None, default: str = "/") -> str:
    target = (return_to or "").strip()
    if not target or not target.startswith("/") or target.startswith("//") or any(char in target for char in "\r\n"):
        return default
    return target


def redirect_back(return_to: str | None, params: dict[str, str] | None = None, default: str = "/") -> RedirectResponse:
    target = safe_return_to(return_to, default=default)
    if params:
        path, fragment_separator, fragment = target.partition("#")
        separator = "&" if "?" in path else "?"
        target = f"{path}{separator}{urlencode(params)}"
        if fragment_separator:
            target = f"{target}#{fragment}"
    return RedirectResponse(url=target, status_code=303)
