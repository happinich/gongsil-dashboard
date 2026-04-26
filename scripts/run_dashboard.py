#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gongsil_mvp.web_app import main

if __name__ == "__main__":
    main()
