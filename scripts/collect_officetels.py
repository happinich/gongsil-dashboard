#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gongsil_mvp.collector import collect_officetels
from gongsil_mvp.config import DISTRICTS, load_settings
from gongsil_mvp.notify import send_pending_telegram_alerts
from gongsil_mvp.storage import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Gangnam/Seocho officetel listings from Gongsil.")
    parser.add_argument("--district", action="append", choices=DISTRICTS, help="District to collect. Repeatable.")
    parser.add_argument("--complex-name", action="append", help="Complex/building name to collect. Repeatable.")
    parser.add_argument("--all-districts", action="store_true", help="Search all supported districts instead of configured collection districts.")
    parser.add_argument("--max-pages", type=int, default=1, help="Pages per district/complex. One page is 30 listings.")
    parser.add_argument("--no-details", action="store_true", help="Skip newly found detail pages.")
    parser.add_argument("--notify", action="store_true", help="Send pending Telegram alerts after collection.")
    args = parser.parse_args()

    settings = load_settings(require_credentials=True)
    init_db(settings.db_path)
    districts = tuple(args.district) if args.district else (DISTRICTS if args.all_districts else settings.collection_districts)
    complex_names = tuple(args.complex_name) if args.complex_name else settings.complex_names
    results = collect_officetels(
        settings=settings,
        districts=districts,
        max_pages=max(1, args.max_pages),
        fetch_details=not args.no_details,
        complex_names=complex_names,
    )
    for result in results:
        target = f"{result.district} / {result.complex_name}" if result.complex_name else result.district
        print(
            f"{target}: pages={result.pages_fetched}, "
            f"seen={result.listings_seen}, new={result.new_listings}, price_changes={result.price_changes}, "
            f"details={result.detail_pages_fetched}"
        )
    if args.notify:
        notify_result = send_pending_telegram_alerts(settings)
        print(
            f"telegram: sent={notify_result.sent}, "
            f"skipped={notify_result.skipped}, failed={notify_result.failed}"
        )


if __name__ == "__main__":
    main()
