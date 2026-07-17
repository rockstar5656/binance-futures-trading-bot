class TradingBotError(Exception):
    """Base class for all application-specific errors."""


class ValidationError(TradingBotError):
    """Raised when user-supplied CLI input fails validation."""


class ConfigurationError(TradingBotError):
    """Raised when required configuration (e.g. API keys) is missing/invalid."""


class NetworkError(TradingBotError):
    """Raised when a request to Binance could not complete (timeout, DNS, etc.)."""


class BinanceAPIError(TradingBotError):
    """
    Raised when Binance's API returns an error response.

    Binance error payloads look like: {"code": -2010, "msg": "Account has
    insufficient balance..."}. We carry both through so the caller can log
    and/or branch on the numeric code if needed.
    """

    def __init__(self, code: int, msg: str, status_code: int | None = None):
        self.code = code
        self.msg = msg
        self.status_code = status_code
        super().__init__(f"Binance API error {code}: {msg}")
