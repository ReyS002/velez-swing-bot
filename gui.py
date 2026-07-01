from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for local runs
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.ui.app import run


if __name__ == "__main__":
    run()
