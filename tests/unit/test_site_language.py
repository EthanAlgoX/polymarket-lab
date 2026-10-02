from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_english_defaults_api_gate_and_locale_races() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for frontend language behavior checks")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, str(root / "tests/frontend/language.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
