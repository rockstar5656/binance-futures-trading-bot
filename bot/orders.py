from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.client import BinanceFuturesTestnetClient
from bot.exceptions import BinanceAPIError, NetworkError
from bot.logging_config import get_logger
from bot.validators import OrderRequest

logger = get_logger("orders")


@dataclass(frozen=True)
class OrderResult:
    """Normalized, CLI-friendly view of a Binance order response."""

    success: bool
    order_id: int | None
    symbol: str | None
    status: str | None
    side: str | None
    order_type: str | None
    executed_qty: str | None
    orig_qty: str | None
    avg_price: str | None
    price: str | None
    raw_response: dict[str, Any]
    error_message: str | None = None


def _order_params_from_request(request: OrderRequest) -> dict[str, Any]:
    """Translate a validated OrderRequest into Binance new_order() kwargs."""
    params: dict[str, Any] = {
        "symbol": request.symbol,
        "side": request.side,
        "type": request.order_type if request.order_type != "STOP_LIMIT" else "STOP",
        "quantity": str(request.quantity),
    }

    if request.order_type == "LIMIT":
        params["price"] = str(request.price)
        params["timeInForce"] = request.time_in_force

    elif request.order_type == "STOP_LIMIT":
        # Binance futures calls this order type "STOP" (stop-limit; a stop
        # order that becomes a limit order once the stop price is hit).
        params["price"] = str(request.price)
        params["stopPrice"] = str(request.stop_price)
        params["timeInForce"] = request.time_in_force

    # MARKET orders need only symbol/side/type/quantity -- nothing else to add.

    return params


def place_order(
    client: BinanceFuturesTestnetClient, request: OrderRequest
) -> OrderResult:
    """
    Place an order on Binance Futures Testnet and return a normalized result.

    Does not raise on exchange-level rejection (e.g. insufficient balance,
    invalid symbol) -- those are captured into OrderResult.success=False
    with error_message set, so the CLI can present a clean failure message.
    Network-layer problems (timeouts, DNS) are allowed to propagate, since
    those represent the request never having been meaningfully attempted.
    """
    params = _order_params_from_request(request)

    logger.info(
        "Placing order | symbol=%s side=%s type=%s quantity=%s price=%s "
        "stop_price=%s tif=%s",
        request.symbol,
        request.side,
        request.order_type,
        request.quantity,
        request.price,
        request.stop_price,
        request.time_in_force,
    )

    try:
        response = client.new_order(**params)
    except BinanceAPIError as exc:
        logger.error(
            "Order rejected by Binance | symbol=%s side=%s type=%s | "
            "code=%s msg=%s",
            request.symbol,
            request.side,
            request.order_type,
            exc.code,
            exc.msg,
        )
        return OrderResult(
            success=False,
            order_id=None,
            symbol=request.symbol,
            status=None,
            side=request.side,
            order_type=request.order_type,
            executed_qty=None,
            orig_qty=None,
            avg_price=None,
            price=None,
            raw_response={},
            error_message=f"[{exc.code}] {exc.msg}",
        )
    except NetworkError as exc:
        # Let the CLI layer catch and report this -- a network failure
        # means we don't know whether the order was placed, which is a
        # meaningfully different situation from an explicit rejection.
        logger.error("Network failure while placing order: %s", exc)
        raise

    logger.info(
        "Order accepted | orderId=%s status=%s symbol=%s",
        response.get("orderId"),
        response.get("status"),
        response.get("symbol"),
    )

    return OrderResult(
        success=True,
        order_id=response.get("orderId"),
        symbol=response.get("symbol"),
        status=response.get("status"),
        side=response.get("side"),
        order_type=response.get("type"),
        executed_qty=response.get("executedQty"),
        orig_qty=response.get("origQty"),
        avg_price=response.get("avgPrice"),
        price=response.get("price"),
        raw_response=response,
        error_message=None,
    )
