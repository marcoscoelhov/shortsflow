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
from app.music_bank import populate_builtin_music_bank


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate the local approved music bank with built-in synthetic tracks.")
    parser.add_argument("--bank-dir", type=Path, default=None, help="Music bank directory. Defaults to SHORTSFLOW_MUSIC_BANK_DIR.")
    parser.add_argument("--force", action="store_true", help="Regenerate built-in tracks and overwrite their manifest entries.")
    parser.add_argument("--duration-seconds", type=int, default=75, help="Duration for each generated track.")
    args = parser.parse_args()

    settings = get_settings()
    bank_dir = args.bank_dir or settings.music_bank_dir
    result = populate_builtin_music_bank(bank_dir, force=args.force, duration_seconds=args.duration_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
