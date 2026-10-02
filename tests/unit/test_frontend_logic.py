from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.translation import source_chunks

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


@pytest.mark.parametrize(
    "case",
    [
        "catalogRace",
        "detailQueuedParameters",
        "opportunitySearch",
        "refreshRecoveryAndPagination",
        "duplicateSimulation",
        "calculationSourcesAndInvalidState",
        "settingSaveIsSingleAndHonest",
        "verifiedScannerMix",
        "unavailableMarketStopsDetail",
    ],
)
def test_frontend_request_and_record_logic(case: str) -> None:
    if not NODE:
        pytest.skip("Node.js is required for the isolated JavaScript logic checks")
    completed = subprocess.run(
        [NODE, str(ROOT / "tests/frontend/logic.cjs"), case], capture_output=True, text=True, check=False, timeout=10
    )
    assert completed.returncode == 0, completed.stderr


def test_backend_rule_whitelist_matches_browser_utf16_chunks() -> None:
    if not NODE:
        pytest.skip("Node.js is required for the isolated JavaScript logic checks")
    completed = subprocess.run(
        [NODE, str(ROOT / "tests/frontend/logic.cjs"), "translationChunks"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    source = "Source rules 2026. 😀\n" * 1600
    assert source_chunks(source) == json.loads(completed.stdout)
