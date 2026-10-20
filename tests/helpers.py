"""Shared test setup: puts src/ on the import path. `from helpers import src` in each test file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / 'src'
sys.path.insert(0, str(src))


def fake_opencode(folder):
    """An `opencode` for tests: tests/fake_opencode.py, reading its plan from folder/plan.json and
    logging each call to folder/calls.jsonl. The paths are baked in, because the action passes
    OpenCode only an allowlisted env."""
    folder = Path(folder)
    wrapper = folder / 'opencode'
    wrapper.write_text(
        '#!/bin/sh\n'
        f"OPENCODE_FAKE_PLAN='{folder / 'plan.json'}' OPENCODE_FAKE_CALLS='{folder / 'calls.jsonl'}' "
        f'exec python3 \'{ROOT / "tests" / "fake_opencode.py"}\' "$@"\n'
    )
    wrapper.chmod(0o755)
    return str(wrapper)
