from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        busy_timeout_ms = int(settings.sqlite_busy_timeout_ms)
        journal_mode = str(settings.sqlite_journal_mode)
        synchronous = str(settings.sqlite_synchronous)
        cursor.execute("PRAGMA busy_timeout=" + str(busy_timeout_ms))
        cursor.execute("PRAGMA journal_mode=" + journal_mode)
        cursor.execute("PRAGMA synchronous=" + synchronous)
        cursor.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_job_metadata_columns()


def _ensure_job_metadata_columns() -> None:
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("jobs")}
    column_specs = {
        "job_origin": "VARCHAR DEFAULT 'unknown'",
        "creation_via": "VARCHAR DEFAULT 'unknown'",
    }
    missing = [(name, ddl) for name, ddl in column_specs.items() if name not in existing]
    if not missing:
        return
    with engine.begin() as connection:
        for name, ddl in missing:
            connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
