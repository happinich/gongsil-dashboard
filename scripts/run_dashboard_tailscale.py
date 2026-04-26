#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Bind to every network interface so Tailscale/Windows devices can reach it.
os.environ.setdefault("HOST", "0.0.0.0")
os.environ.setdefault("PORT", "8000")

from gongsil_mvp.web_app import main


if __name__ == "__main__":
    main()
