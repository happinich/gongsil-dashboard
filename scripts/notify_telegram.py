#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gongsil_mvp.config import load_settings
from gongsil_mvp.notify import send_pending_telegram_alerts
from gongsil_mvp.storage import init_db


def main() -> None:
    settings = load_settings(require_credentials=False)
    init_db(settings.db_path)
    result = send_pending_telegram_alerts(settings)
    print(f"telegram: sent={result.sent}, skipped={result.skipped}, failed={result.failed}")


if __name__ == "__main__":
    main()
