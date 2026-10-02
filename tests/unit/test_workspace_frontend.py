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
        "scannerZeroAndSearch",
        "saveFeedbackAndDuplicateGuard",
        "savedSnapshotRaceAndPrecision",
        "pausedLogsDiscardInFlightAndAllowManualRefresh",
        "settingsDraftAndSaveProtectAgainstOldLoads",
        "monitorUsesSingleStatusPayload",
        "detailsRetainDisclosureAndYesNoMapping",
    ],
)
def test_operational_workspace_flows(case: str) -> None:
    if not NODE:
        pytest.skip("Node.js is required for the isolated workspace behavior checks")
    completed = subprocess.run(
        [NODE, str(ROOT / "tests/frontend/workspace.cjs"), case],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
