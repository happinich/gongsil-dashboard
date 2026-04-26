from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Vercel's project filesystem is read-only at runtime. Keep the working
# SQLite DB in /tmp, and optionally seed it from a bundled local snapshot.
os.environ.setdefault("GONGSIL_DB", "/tmp/gongsil.sqlite3")

from gongsil_mvp.config import load_settings
from gongsil_mvp.storage import init_db
from gongsil_mvp.web_app import DashboardHandler


def _prepare_handler() -> None:
    settings = load_settings(require_credentials=False)
    bundled_db = PROJECT_ROOT / "data" / "gongsil.sqlite3"
    runtime_db = settings.db_path

    if not runtime_db.exists() and bundled_db.exists():
        runtime_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_db, runtime_db)

    init_db(runtime_db)
    DashboardHandler.db_path = runtime_db
    DashboardHandler.settings = settings


_prepare_handler()


class handler(DashboardHandler):
    pass
