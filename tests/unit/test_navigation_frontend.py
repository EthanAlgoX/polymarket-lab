from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_mobile_navigation_keeps_work_surface_accessible() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for frontend navigation checks")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, str(root / "tests/frontend/navigation.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
