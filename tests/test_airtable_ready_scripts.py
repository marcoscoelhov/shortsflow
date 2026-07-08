from __future__ import annotations

from app.airtable_ready_scripts import AirtableReadyScriptClient, AirtableReadyScriptRecord
from app.automation import AutomationService
from app.config import Settings
from app.models import ReadyScriptItem
from tests.e2e_support import SessionLocal, orchestrator
from sqlalchemy import select


def test_airtable_ready_script_client_builds_script_from_split_fields() -> None:
    settings = Settings(
        airtable_enabled=True,
        airtable_api_token="pat_test",
        airtable_base_id="app_test",
        airtable_table_id="tbl_test",
        airtable_script_field="Roteiro",
    )
    client = AirtableReadyScriptClient(settings)

    record = client._record_from_airtable(
        {
            "id": "rec_future_ready",
            "fields": {
                "Título": "A LUA MENTE NO HORIZONTE",
                "Hook": "A Lua não cresceu.",
                "Loop": "Então por que parece gigante?",
                "Beat 1": "Perto do horizonte, ela aparece ao lado de prédios e árvores.",
                "Beat 2": "Essas referências enganam a escala percebida pelo cérebro.",
                "Beat 3": "O tamanho aparente quase não muda naquela noite.",
                "Beat 4": "A virada é que o cenário muda a comparação, não a Lua.",
                "Payoff": "A Lua gigante é uma armadilha de percepção.",
                "Fechamento": "O céu engana usando coisas da Terra.",
                "Hashtags": "#lua #astronomia #shorts",
            },
        }
    )

    assert record is not None
    assert "Título: A LUA MENTE NO HORIZONTE" in record.raw_text
    assert "- A virada é que o cenário muda a comparação" in record.raw_text
    assert record.fact_check_confirmed is True


def test_airtable_sync_imports_only_client_eligible_future_records(monkeypatch) -> None:
    service = AutomationService(orchestrator)
    imported_records: list[str] = []

    class FakeAirtableClient:
        def __init__(self, _settings):
            pass

        def list_ready_records(self, *, limit=None):
            return [
                AirtableReadyScriptRecord(
                    record_id="rec_future_ready_import",
                    raw_text="""Título: AIRTABLE FUTURO NÃO PUXA NOVO MANUAL
Hook: Só entra o que virar Ready.
Loop: Como evitamos puxar roteiros antigos?
Beats:
- Registros manuais antigos ficam com outro status.
- A sincronização usa só a fila futura marcada como Ready.
- O parser transforma campos aprovados em roteiro do banco.
- Depois o Airtable é marcado para não repetir.
Payoff: O status é a fronteira entre histórico e sincronização.
Fechamento: Manual antigo fica quieto; futuro Ready entra no fluxo.
Hashtags: #shorts #automacao""",
                    fields={},
                    fact_check_confirmed=True,
                )
            ]

        def mark_imported(self, record_id, *, imported_count):
            imported_records.append(f"{record_id}:{imported_count}")

        def mark_error(self, record_id, error):
            raise AssertionError(error)

    monkeypatch.setattr("app.automation.AirtableReadyScriptClient", FakeAirtableClient)
    monkeypatch.setattr(orchestrator.settings, "airtable_mark_imported", True)

    result = service.sync_airtable_ready_scripts()

    assert result.imported == 1
    assert result.marked_imported == 1
    assert imported_records == ["rec_future_ready_import:1"]
    with SessionLocal() as session:
        row = session.scalar(select(ReadyScriptItem).where(ReadyScriptItem.source == "airtable:rec_future_ready_import"))
    assert row is not None
    assert row.status == "available"
