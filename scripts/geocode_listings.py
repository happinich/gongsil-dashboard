#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gongsil_mvp.config import load_settings
from gongsil_mvp.geocode import geocode_pending_listings
from gongsil_mvp.storage import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode stored Gongsil listings.")
    parser.add_argument("--limit", type=int, default=100, help="Number of listings to geocode.")
    args = parser.parse_args()

    settings = load_settings(require_credentials=False)
    init_db(settings.db_path)
    success, failed = geocode_pending_listings(settings, limit=max(1, args.limit))
    print(f"geocode: success={success}, failed={failed}")


if __name__ == "__main__":
    main()
