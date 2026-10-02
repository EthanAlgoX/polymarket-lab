from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


@pytest.mark.parametrize(
    "case",
    ["appliedCatalogAndStatusIsolation", "inspectDeepLinksAndFocus", "honestPreviewAndInitialError"],
)
def test_catalog_redesign_preserves_verified_scope(case: str) -> None:
    if not NODE:
        pytest.skip("Node.js is required for the isolated JavaScript logic checks")
    completed = subprocess.run(
        [NODE, str(ROOT / "tests/frontend/research.cjs"), case], capture_output=True, text=True, check=False, timeout=10
    )
    assert completed.returncode == 0, completed.stderr
