from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from scripts.runtime_backup import create_verified_backup, verify_backup


def test_daily_backup_is_restorable_and_keeps_seven(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO jobs VALUES ('job-1')")
    backup_dir = tmp_path / "backups"
    start = datetime(2026, 8, 1, tzinfo=UTC)

    for offset in range(9):
        destination = create_verified_backup(database, backup_dir, cadence="daily", now=start + timedelta(days=offset))
        assert destination is not None
        verify_backup(destination)

    backups = sorted(backup_dir.glob("daily-*.db"))
    assert len(backups) == 7
    with sqlite3.connect(backups[-1]) as connection:
        assert connection.execute("SELECT id FROM jobs").fetchone() == ("job-1",)


def test_backup_does_not_copy_environment_secrets(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs (id TEXT)")

    create_verified_backup(database, tmp_path / "backups", cadence="weekly")

    assert not list((tmp_path / "backups").glob("*.env"))
