from __future__ import annotations

import os

from bot.client import DEFAULT_BASE_URL
from bot.exceptions import ConfigurationError

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is an optional convenience; env vars set some other
    # way (export, docker, CI secrets, etc.) work fine without it.
    pass


def load_credentials() -> tuple[str, str, str]:
    """
    Return (api_key, api_secret, base_url) from environment variables.

    Required:
        BINANCE_TESTNET_API_KEY
        BINANCE_TESTNET_API_SECRET
    Optional:
        BINANCE_TESTNET_BASE_URL (defaults to the standard testnet URL)
    """
    api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "").strip()
    api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "").strip()
    base_url = os.environ.get("BINANCE_TESTNET_BASE_URL", DEFAULT_BASE_URL).strip()

    missing = []
    if not api_key:
        missing.append("BINANCE_TESTNET_API_KEY")
    if not api_secret:
        missing.append("BINANCE_TESTNET_API_SECRET")

    if missing:
        raise ConfigurationError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. Set them directly or create a .env "
            "file -- see README.md for instructions."
        )

    return api_key, api_secret, base_url
