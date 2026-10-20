"""Shared test setup: puts src/ on the import path. `from helpers import src` in each test file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / 'src'
sys.path.insert(0, str(src))
