"""Central settings for Version 4 services."""

from __future__ import annotations

import os
from pathlib import Path

VERSION = "v4.0.0"
BASE_DIR = Path(__file__).resolve().parent.parent
ZETA_WEB_HOST = os.environ.get("ZETA_WEB_HOST", "0.0.0.0")
ZETA_WEB_PORT = int(os.environ.get("ZETA_WEB_PORT", "8767"))
VICTORIA_WEB_HOST = os.environ.get("VICTORIA_WEB_HOST", "0.0.0.0")
VICTORIA_WEB_PORT = int(os.environ.get("VICTORIA_WEB_PORT", "8768"))
ZETA_WEB_PUBLIC_HOSTPORT = os.environ.get("ZETA_UI_HOSTPORT", "10.246.51.38:8767")
# Each concurrent live rig stream pins one thread; raised to cover ~50 simultaneous users.
ZETA_MAX_STREAMS = int(os.environ.get("ZETA_MAX_STREAMS", "60"))