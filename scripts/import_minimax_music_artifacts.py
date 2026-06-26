#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.music_bank import import_minimax_music_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import approved MiniMax background music artifacts into the local music bank.")
    parser.add_argument("--artifacts-dir", type=Path, default=None, help="Artifacts directory. Defaults to ShortsFlow artifacts dir.")
    parser.add_argument("--bank-dir", type=Path, default=None, help="Music bank directory. Defaults to SHORTSFLOW_MUSIC_BANK_DIR.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of tracks to import.")
    parser.add_argument("--force", action="store_true", help="Overwrite imported track files and manifest entries.")
    args = parser.parse_args()

    settings = get_settings()
    result = import_minimax_music_artifacts(
        artifacts_dir=args.artifacts_dir or settings.artifacts_dir,
        bank_dir=args.bank_dir or settings.music_bank_dir,
        limit=args.limit,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
