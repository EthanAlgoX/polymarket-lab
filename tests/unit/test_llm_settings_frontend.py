from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


@pytest.mark.parametrize(
    "case",
    [
        "saveResponseRace",
        "deleteResponseRace",
        "pendingReadAfterSave",
        "environmentFallback",
        "missingKeyRemoval",
        "dirtyForm",
        "newProviderNeedsKey",
        "failedMutationPreservesDraft",
    ],
)
def test_llm_settings_privacy_and_request_ordering(case: str) -> None:
    if not NODE:
        pytest.skip("Node.js is required for the isolated JavaScript settings checks")
    completed = subprocess.run(
        [NODE, str(ROOT / "tests/frontend/settings.cjs"), case],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
