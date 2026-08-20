#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path
import shutil
import sqlite3
import tempfile


RETENTION = {"daily": 7, "weekly": 4}

_CHANNEL_INSTANCE_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _is_safe_channel_instance_slug(value: str) -> bool:
    """Return True for safe lowercase channel-instance slugs (e.g. "jarvis", "channel-a")."""
    return bool(_CHANNEL_INSTANCE_SLUG_RE.match(value))

def _validate_environment(value: str) -> str:
    """Accept standard envs or safe channel instance slug for backup target."""
    normalized = value.strip().lower()
    if normalized in {"development", "staging", "production"} or _is_safe_channel_instance_slug(normalized):
        return normalized
    raise argparse.ArgumentTypeError(
        "environment must be one of development, staging, production "
        "or a safe channel-instance slug like 'jarvis'"
    )


def create_verified_backup(database: Path, backup_dir: Path, *, cadence: str, now: datetime | None = None) -> Path | None:
    if cadence not in RETENTION:
        raise ValueError("cadence must be daily or weekly")
    if not database.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"{cadence}-{timestamp}.db"
    temporary = Path(tempfile.mkstemp(prefix=f".{cadence}-", suffix=".db", dir=backup_dir)[1])
    try:
        with sqlite3.connect(database) as source, sqlite3.connect(temporary) as target:
            source.backup(target)
        with sqlite3.connect(temporary) as verification:
            result = verification.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"backup integrity check failed: {result}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    backups = sorted(backup_dir.glob(f"{cadence}-*.db"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for expired in backups[RETENTION[cadence] :]:
        expired.unlink()
    return destination


def verify_backup(path: Path) -> None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"backup integrity check failed: {result}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shortsflow-backup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("environment", type=_validate_environment)
    create.add_argument("cadence", choices=sorted(RETENTION))
    verify = subparsers.add_parser("verify")
    verify.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "verify":
        verify_backup(args.path)
        print(f"verified {args.path}")
        return 0
    database = Path(f"/srv/shortsflow/{args.environment}/data/shortsflow.db")
    backup_dir = Path(f"/var/backups/shortsflow/{args.environment}")
    destination = create_verified_backup(database, backup_dir, cadence=args.cadence)
    print(destination or "database not created yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
