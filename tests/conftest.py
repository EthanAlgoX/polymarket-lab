from __future__ import annotations

import os

os.environ["PMS_ENABLE_LIVE_SCANNER"] = "false"
os.environ["PMS_DATABASE_URL"] = "sqlite:///:memory:"
