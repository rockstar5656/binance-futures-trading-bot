from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="trading_bot_test_logs_")
os.environ["TRADING_BOT_LOG_FILE"] = str(Path(_tmp_dir) / "test_run.log")
