from __future__ import annotations

from fastapi import HTTPException, UploadFile


MAX_READY_SCRIPT_IMPORT_CHARS = 200_000
MAX_READY_SCRIPT_IMPORT_BODY_BYTES = 1_000_000


async def ready_script_import_text(ready_script_batch: str, ready_script_file: UploadFile | None) -> str:
    file_text = ""
    if ready_script_file and ready_script_file.filename:
        file_text = await _read_upload_text_limited(
            ready_script_file,
            max_chars=MAX_READY_SCRIPT_IMPORT_CHARS,
            max_bytes=MAX_READY_SCRIPT_IMPORT_BODY_BYTES,
        )
    raw_text = "\n\n".join(part for part in [ready_script_batch, file_text] if part and part.strip())
    if len(raw_text) > MAX_READY_SCRIPT_IMPORT_CHARS:
        raise HTTPException(status_code=413, detail="lote de roteiros prontos excede o limite permitido")
    return raw_text


async def _read_upload_text_limited(upload: UploadFile, *, max_chars: int, max_bytes: int) -> str:
    raw = await upload.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail="arquivo de roteiros prontos excede o limite permitido")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="arquivo de roteiros prontos deve usar UTF-8") from exc
    if len(text) > max_chars:
        raise HTTPException(status_code=413, detail="arquivo de roteiros prontos excede o limite permitido")
    return text
