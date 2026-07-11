from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings

AIRTABLE_API_BASE_URL = "https://api.airtable.com/v0"
AIRTABLE_MAX_PAGE_SIZE = 100
AIRTABLE_RATE_LIMIT_STATUS = 429


@dataclass(frozen=True)
class AirtableReadyScriptRecord:
    record_id: str
    raw_text: str
    fields: dict[str, Any]
    score: float | None = None



@dataclass
class AirtableReadyScriptSyncResult:
    fetched: int = 0
    eligible: int = 0
    imported: int = 0
    skipped: int = 0
    marked_imported: int = 0
    marked_error: int = 0
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "eligible": self.eligible,
            "imported": self.imported,
            "skipped": self.skipped,
            "marked_imported": self.marked_imported,
            "marked_error": self.marked_error,
            "dry_run": self.dry_run,
            "errors": self.errors,
        }


class AirtableReadyScriptClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token = settings.airtable_api_token
        self.base_id = settings.airtable_base_id
        self.table_id = settings.airtable_table_id

    def configured(self) -> bool:
        return bool(self.settings.airtable_enabled and self.token and self.base_id and self.table_id)

    def list_ready_records(self, *, limit: int | None = None) -> list[AirtableReadyScriptRecord]:
        if not self.configured():
            raise RuntimeError("Airtable não configurado: confira SHORTSFLOW_AIRTABLE_* no .env")

        output: list[AirtableReadyScriptRecord] = []
        offset: str | None = None
        with httpx.Client(timeout=self.settings.airtable_timeout_sec) as client:
            while True:
                payload = self._list_page(client, offset=offset)
                for record in payload.get("records", []):
                    normalized = self._record_from_airtable(record)
                    if normalized is None:
                        continue
                    output.append(normalized)
                    if limit is not None and len(output) >= limit:
                        return output
                offset = payload.get("offset")
                if not offset:
                    return output

    def mark_imported(self, record_id: str, *, imported_count: int) -> None:
        fields: dict[str, Any] = {
            self.settings.airtable_status_field: self.settings.airtable_imported_status,
        }
        if self.settings.airtable_imported_at_field:
            fields[self.settings.airtable_imported_at_field] = datetime.now(UTC).isoformat()
        if self.settings.airtable_import_count_field:
            fields[self.settings.airtable_import_count_field] = imported_count
        self._patch_record(record_id, fields)

    def mark_error(self, record_id: str, error: str) -> None:
        fields: dict[str, Any] = {
            self.settings.airtable_status_field: self.settings.airtable_error_status,
        }
        if self.settings.airtable_import_error_field:
            fields[self.settings.airtable_import_error_field] = error[:1000]
        self._patch_record(record_id, fields)

    def _list_page(self, client: httpx.Client, *, offset: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"pageSize": min(self.settings.airtable_page_size, AIRTABLE_MAX_PAGE_SIZE)}
        if self.settings.airtable_view:
            params["view"] = self.settings.airtable_view
        if self.settings.airtable_ready_status:
            params["filterByFormula"] = f"{{{self.settings.airtable_status_field}}}='{self.settings.airtable_ready_status}'"
        if offset:
            params["offset"] = offset
        response = client.get(self._table_url(), headers=self._headers(), params=params)
        if response.status_code == AIRTABLE_RATE_LIMIT_STATUS:
            raise RuntimeError("Airtable rate limit 429; aguarde e tente novamente")
        if response.status_code >= 400:
            raise RuntimeError(f"Airtable list_records falhou: http_status={response.status_code}; body={response.text[:500]}")
        return response.json()

    def _patch_record(self, record_id: str, fields: dict[str, Any]) -> None:
        with httpx.Client(timeout=self.settings.airtable_timeout_sec) as client:
            response = client.patch(
                f"{self._table_url()}/{record_id}",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"fields": fields, "typecast": True},
            )
        if response.status_code == AIRTABLE_RATE_LIMIT_STATUS:
            raise RuntimeError("Airtable rate limit 429 ao marcar registro")
        if response.status_code >= 400:
            raise RuntimeError(f"Airtable update_record falhou: http_status={response.status_code}; body={response.text[:500]}")

    def _record_from_airtable(self, record: dict[str, Any]) -> AirtableReadyScriptRecord | None:
        record_id = str(record.get("id") or "").strip()
        fields = dict(record.get("fields") or {})
        if not record_id:
            return None
        raw_text = self._raw_script_from_fields(fields)
        if not raw_text:
            return None
        score = self._numeric_field(fields, self.settings.airtable_score_field)
        if score is not None and score < self.settings.airtable_min_score:
            return None
        return AirtableReadyScriptRecord(record_id=record_id, raw_text=raw_text, fields=fields, score=score)

    def _raw_script_from_fields(self, fields: dict[str, Any]) -> str:
        script_field = self.settings.airtable_script_field
        if script_field and fields.get(script_field):
            return str(fields[script_field]).strip()

        beats = [str(fields.get(field_name) or "").strip() for field_name in self.settings.airtable_beat_fields]
        beats = [beat for beat in beats if beat]
        parts = [
            f"Título: {str(fields.get(self.settings.airtable_title_field) or '').strip()}",
            f"Hook: {str(fields.get(self.settings.airtable_hook_field) or '').strip()}",
            f"Loop: {str(fields.get(self.settings.airtable_loop_field) or '').strip()}",
            "Beats:",
            *[f"- {beat}" for beat in beats],
            f"Payoff: {str(fields.get(self.settings.airtable_payoff_field) or '').strip()}",
            f"Fechamento: {str(fields.get(self.settings.airtable_closing_field) or '').strip()}",
            f"Hashtags: {str(fields.get(self.settings.airtable_hashtags_field) or '').strip()}",
        ]
        text = "\n".join(parts).strip()
        required_values = [fields.get(self.settings.airtable_title_field), fields.get(self.settings.airtable_hook_field), fields.get(self.settings.airtable_loop_field), fields.get(self.settings.airtable_payoff_field), fields.get(self.settings.airtable_closing_field)]
        if not all(str(value or "").strip() for value in required_values) or not beats:
            return ""
        return text

    def _numeric_field(self, fields: dict[str, Any], field_name: str | None) -> float | None:
        if not field_name or field_name not in fields:
            return None
        value = fields.get(field_name)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise RuntimeError(f"Campo Airtable {field_name!r} não é numérico: {value!r}")

    def _table_url(self) -> str:
        return f"{AIRTABLE_API_BASE_URL}/{self.base_id}/{self.table_id}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
