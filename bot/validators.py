from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bot.exceptions import ValidationError

VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LIMIT"}
VALID_TIME_IN_FORCE = {"GTC", "IOC", "FOK"}

# Binance USDT-M futures symbols are uppercase alphanumeric, e.g. BTCUSDT,
# ETHUSDT, 1000SHIBUSDT. This is intentionally permissive (exact validity
# is ultimately confirmed by exchangeInfo / the order call itself); its
# job is to catch obvious typos like lowercase or embedded whitespace.
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")


@dataclass(frozen=True)
class OrderRequest:
    """A validated, normalized order ready to be sent to the client layer."""

    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "GTC"


def validate_symbol(symbol: str) -> str:
    if not symbol or not symbol.strip():
        raise ValidationError("Symbol must not be empty.")
    normalized = symbol.strip().upper()
    if not _SYMBOL_PATTERN.match(normalized):
        raise ValidationError(
            f"Invalid symbol format: '{symbol}'. Expected something like "
            "'BTCUSDT' (5-20 uppercase alphanumeric characters)."
        )
    return normalized


def validate_side(side: str) -> str:
    normalized = (side or "").strip().upper()
    if normalized not in VALID_SIDES:
        raise ValidationError(
            f"Invalid side: '{side}'. Must be one of {sorted(VALID_SIDES)}."
        )
    return normalized


def validate_order_type(order_type: str) -> str:
    normalized = (order_type or "").strip().upper()
    if normalized not in VALID_ORDER_TYPES:
        raise ValidationError(
            f"Invalid order type: '{order_type}'. Must be one of "
            f"{sorted(VALID_ORDER_TYPES)}."
        )
    return normalized


def validate_positive_decimal(value: str, field_name: str) -> Decimal:
    """Parse a string into a strictly-positive Decimal, or raise ValidationError."""
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field_name} must be provided.")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(
            f"{field_name} must be a valid number, got '{value}'."
        ) from exc
    if parsed <= 0:
        raise ValidationError(f"{field_name} must be greater than 0, got {parsed}.")
    return parsed


def validate_time_in_force(tif: str) -> str:
    normalized = (tif or "GTC").strip().upper()
    if normalized not in VALID_TIME_IN_FORCE:
        raise ValidationError(
            f"Invalid time_in_force: '{tif}'. Must be one of "
            f"{sorted(VALID_TIME_IN_FORCE)}."
        )
    return normalized


def build_order_request(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: str | None = None,
    stop_price: str | None = None,
    time_in_force: str = "GTC",
) -> OrderRequest:
    """
    Validate all raw CLI inputs together and return a normalized OrderRequest.

    This is the single entry point the CLI layer should call -- it performs
    every individual field check plus the cross-field rules (e.g. LIMIT
    orders require a price).
    """
    v_symbol = validate_symbol(symbol)
    v_side = validate_side(side)
    v_type = validate_order_type(order_type)
    v_quantity = validate_positive_decimal(quantity, "quantity")
    v_tif = validate_time_in_force(time_in_force)

    v_price: Decimal | None = None
    v_stop_price: Decimal | None = None

    if v_type == "LIMIT":
        if price is None or str(price).strip() == "":
            raise ValidationError("price is required for LIMIT orders.")
        v_price = validate_positive_decimal(price, "price")

    elif v_type == "STOP_LIMIT":
        if price is None or str(price).strip() == "":
            raise ValidationError("price is required for STOP_LIMIT orders.")
        if stop_price is None or str(stop_price).strip() == "":
            raise ValidationError("stop_price is required for STOP_LIMIT orders.")
        v_price = validate_positive_decimal(price, "price")
        v_stop_price = validate_positive_decimal(stop_price, "stop_price")

    else:  # MARKET
        if price is not None and str(price).strip() != "":
            raise ValidationError(
                "price must not be supplied for MARKET orders (it's ignored "
                "by the exchange and likely indicates a mistake)."
            )

    return OrderRequest(
        symbol=v_symbol,
        side=v_side,
        order_type=v_type,
        quantity=v_quantity,
        price=v_price,
        stop_price=v_stop_price,
        time_in_force=v_tif,
    )
