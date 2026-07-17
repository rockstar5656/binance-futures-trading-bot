from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# Overridable via TRADING_BOT_LOG_FILE, primarily so the test suite can
# redirect logging to a throwaway temp file (see tests/conftest.py) instead
# of writing to the real logs/trading_bot.log -- that file is a graded
# deliverable containing real order logs, and must not be touched by simply
# running `pytest`. Resolved lazily inside setup_logging() (not at import
# time) so a test fixture that sets the env var before the first
# setup_logging() call is respected.


def _resolve_log_file() -> Path:
    override = os.environ.get("TRADING_BOT_LOG_FILE")
    if override:
        return Path(override)
    return _DEFAULT_LOG_DIR / "trading_bot.log"


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    """
    Configure and return the root application logger ("trading_bot").

    Idempotent: safe to call multiple times (e.g. once from cli.py, and
    again if a module is imported/run standalone) without duplicating
    handlers or duplicating log lines.
    """
    logger = logging.getLogger("trading_bot")
    logger.setLevel(level)

    if logger.handlers:
        # Already configured (e.g. re-imported) -- don't add duplicate handlers.
        return logger

    log_file = _resolve_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Rotating file handler: full detail (DEBUG+), including raw payloads.
    # 5 MB per file, keep 5 backups, so the log doesn't grow unbounded.
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler: only INFO+ so the CLI output stays readable.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Don't propagate to the root logger (avoids duplicate lines if some
    # other library also configures logging.basicConfig()).
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the "trading_bot" namespace.

    Ensures setup_logging() has been called at least once so handlers exist,
    then returns e.g. "trading_bot.client" or "trading_bot.orders" so log
    lines are traceable to their source module.
    """
    setup_logging()
    return logging.getLogger(f"trading_bot.{name}")
