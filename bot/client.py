from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import requests

from bot.exceptions import BinanceAPIError, NetworkError
from bot.logging_config import get_logger

logger = get_logger("client")

DEFAULT_BASE_URL = "https://testnet.binancefuture.com"
DEFAULT_TIMEOUT_SECONDS = 10
RECV_WINDOW_MS = 5000


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of params with the signature masked, for safe logging."""
    redacted = dict(params)
    if "signature" in redacted:
        redacted["signature"] = "***REDACTED***"
    return redacted


class BinanceFuturesTestnetClient:
    """
    Thin, explicit wrapper around the Binance Futures Testnet REST API.

    Handles:
      - HMAC-SHA256 request signing for SIGNED endpoints
      - Adding timestamp / recvWindow as Binance requires
      - Consistent error translation into our exception hierarchy
      - Structured logging of every request and response
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret must both be non-empty")

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": self.api_key})

    # -- signing -----------------------------------------------------------

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Attach timestamp, recvWindow, and an HMAC-SHA256 signature."""
        signed_params = dict(params)
        signed_params["timestamp"] = int(time.time() * 1000)
        signed_params["recvWindow"] = RECV_WINDOW_MS

        query_string = urlencode(signed_params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed_params["signature"] = signature
        return signed_params

    # -- core request ---------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """
        Perform an HTTP request against the Futures Testnet API.

        Raises:
            NetworkError: connection/timeout/DNS-level failures.
            BinanceAPIError: the exchange responded with an error payload
                (non-2xx status, or a 200 that still contains a Binance
                error code in edge cases).
        """
        url = f"{self.base_url}{path}"
        params = params or {}

        if signed:
            params = self._sign(params)

        logger.debug(
            "REQUEST %s %s | params=%s", method, path, _redact(params)
        )

        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.error("Request to %s timed out after %ss", path, self.timeout)
            raise NetworkError(
                f"Request to {path} timed out after {self.timeout}s"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error while calling %s: %s", path, exc)
            raise NetworkError(
                f"Could not connect to Binance Futures Testnet ({exc})"
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected network error while calling %s: %s", path, exc)
            raise NetworkError(f"Network error calling {path}: {exc}") from exc

        logger.debug(
            "RESPONSE %s %s | status=%s | body=%s",
            method,
            path,
            response.status_code,
            response.text,
        )

        return self._handle_response(response, path)

    @staticmethod
    def _handle_response(response: requests.Response, path: str) -> dict[str, Any]:
        """Parse the response and raise BinanceAPIError on failure statuses."""
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.ok:
            return body

        # Binance error bodies look like {"code": -1121, "msg": "Invalid symbol."}
        code = body.get("code", response.status_code)
        msg = body.get("msg", response.text or "Unknown error")
        logger.error(
            "Binance API error on %s | status=%s | code=%s | msg=%s",
            path,
            response.status_code,
            code,
            msg,
        )
        raise BinanceAPIError(code=code, msg=msg, status_code=response.status_code)

    # -- public endpoints (used to validate connectivity / server time) ----

    def ping(self) -> dict[str, Any]:
        """GET /fapi/v1/ping -- connectivity check, no auth required."""
        return self._request("GET", "/fapi/v1/ping")

    def get_server_time(self) -> dict[str, Any]:
        """GET /fapi/v1/time -- used for basic connectivity/clock checks."""
        return self._request("GET", "/fapi/v1/time")

    def get_exchange_info(self) -> dict[str, Any]:
        """GET /fapi/v1/exchangeInfo -- symbol metadata (used for validation)."""
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def get_symbol_price(self, symbol: str) -> dict[str, Any]:
        """GET /fapi/v1/ticker/price -- latest price for a symbol."""
        return self._request(
            "GET", "/fapi/v1/ticker/price", params={"symbol": symbol}
        )

    # -- account / trading (SIGNED endpoints) -------------------------------

    def get_account_info(self) -> dict[str, Any]:
        """GET /fapi/v2/account -- balances, positions, permissions. Signed."""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def new_order(self, **kwargs: Any) -> dict[str, Any]:
        """
        POST /fapi/v1/order -- place a new order. Signed.

        kwargs are passed straight through as query params, e.g.:
            symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.01"
        Only non-None values are sent, so callers can freely pass
        price=None for MARKET orders without polluting the request.
        """
        params = {k: v for k, v in kwargs.items() if v is not None}
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def get_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        """GET /fapi/v1/order -- query a specific order's current status. Signed."""
        return self._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )
