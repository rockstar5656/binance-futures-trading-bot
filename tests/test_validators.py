from __future__ import annotations

from decimal import Decimal

import pytest

from bot.exceptions import ValidationError
from bot.validators import (
    build_order_request,
    validate_order_type,
    validate_positive_decimal,
    validate_side,
    validate_symbol,
    validate_time_in_force,
)


class TestValidateSymbol:
    def test_valid_symbol_uppercased(self):
        assert validate_symbol("btcusdt") == "BTCUSDT"

    def test_valid_symbol_already_upper(self):
        assert validate_symbol("ETHUSDT") == "ETHUSDT"

    def test_whitespace_stripped(self):
        assert validate_symbol("  BTCUSDT  ") == "BTCUSDT"

    def test_empty_symbol_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_symbol("")

    def test_whitespace_only_symbol_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_symbol("   ")

    def test_symbol_with_embedded_space_raises(self):
        with pytest.raises(ValidationError, match="Invalid symbol format"):
            validate_symbol("BTC USDT")

    def test_symbol_too_short_raises(self):
        with pytest.raises(ValidationError, match="Invalid symbol format"):
            validate_symbol("BTC")

    def test_symbol_with_special_chars_raises(self):
        with pytest.raises(ValidationError, match="Invalid symbol format"):
            validate_symbol("BTC-USDT")

    def test_long_symbol_with_digits_allowed(self):
        # e.g. 1000SHIBUSDT is a real Binance futures symbol
        assert validate_symbol("1000shibusdt") == "1000SHIBUSDT"


class TestValidateSide:
    @pytest.mark.parametrize("raw,expected", [
        ("BUY", "BUY"),
        ("buy", "BUY"),
        ("Buy", "BUY"),
        ("SELL", "SELL"),
        ("sell", "SELL"),
    ])
    def test_valid_sides(self, raw, expected):
        assert validate_side(raw) == expected

    def test_invalid_side_raises(self):
        with pytest.raises(ValidationError, match="Invalid side"):
            validate_side("HOLD")

    def test_empty_side_raises(self):
        with pytest.raises(ValidationError, match="Invalid side"):
            validate_side("")


class TestValidateOrderType:
    @pytest.mark.parametrize("raw,expected", [
        ("MARKET", "MARKET"),
        ("market", "MARKET"),
        ("LIMIT", "LIMIT"),
        ("limit", "LIMIT"),
        ("stop_limit", "STOP_LIMIT"),
    ])
    def test_valid_types(self, raw, expected):
        assert validate_order_type(raw) == expected

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError, match="Invalid order type"):
            validate_order_type("ICEBERG")


class TestValidatePositiveDecimal:
    def test_valid_integer_string(self):
        assert validate_positive_decimal("5", "quantity") == Decimal("5")

    def test_valid_decimal_string(self):
        assert validate_positive_decimal("0.001", "quantity") == Decimal("0.001")

    def test_zero_raises(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            validate_positive_decimal("0", "quantity")

    def test_negative_raises(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            validate_positive_decimal("-1.5", "quantity")

    def test_non_numeric_raises(self):
        with pytest.raises(ValidationError, match="must be a valid number"):
            validate_positive_decimal("abc", "quantity")

    def test_empty_raises(self):
        with pytest.raises(ValidationError, match="must be provided"):
            validate_positive_decimal("", "quantity")

    def test_none_raises(self):
        with pytest.raises(ValidationError, match="must be provided"):
            validate_positive_decimal(None, "price")

    def test_field_name_appears_in_error(self):
        with pytest.raises(ValidationError, match="price"):
            validate_positive_decimal("-1", "price")


class TestValidateTimeInForce:
    def test_default_is_gtc(self):
        assert validate_time_in_force("") == "GTC"
        assert validate_time_in_force(None) == "GTC"

    @pytest.mark.parametrize("raw,expected", [
        ("GTC", "GTC"), ("ioc", "IOC"), ("Fok", "FOK"),
    ])
    def test_valid_values(self, raw, expected):
        assert validate_time_in_force(raw) == expected

    def test_invalid_raises(self):
        with pytest.raises(ValidationError, match="Invalid time_in_force"):
            validate_time_in_force("GTX")


class TestBuildOrderRequest:
    def test_valid_market_order(self):
        req = build_order_request(
            symbol="btcusdt", side="buy", order_type="market", quantity="0.01"
        )
        assert req.symbol == "BTCUSDT"
        assert req.side == "BUY"
        assert req.order_type == "MARKET"
        assert req.quantity == Decimal("0.01")
        assert req.price is None

    def test_valid_limit_order(self):
        req = build_order_request(
            symbol="ETHUSDT",
            side="SELL",
            order_type="LIMIT",
            quantity="1.5",
            price="3000.50",
        )
        assert req.order_type == "LIMIT"
        assert req.price == Decimal("3000.50")
        assert req.time_in_force == "GTC"

    def test_limit_order_missing_price_raises(self):
        with pytest.raises(ValidationError, match="price is required for LIMIT"):
            build_order_request(
                symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity="0.01"
            )

    def test_limit_order_empty_price_raises(self):
        with pytest.raises(ValidationError, match="price is required for LIMIT"):
            build_order_request(
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity="0.01",
                price="",
            )

    def test_market_order_with_price_raises(self):
        with pytest.raises(ValidationError, match="must not be supplied for MARKET"):
            build_order_request(
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity="0.01",
                price="50000",
            )

    def test_stop_limit_requires_both_price_and_stop_price(self):
        with pytest.raises(ValidationError, match="price is required"):
            build_order_request(
                symbol="BTCUSDT",
                side="BUY",
                order_type="STOP_LIMIT",
                quantity="0.01",
                stop_price="64000",
            )

    def test_stop_limit_requires_stop_price(self):
        with pytest.raises(ValidationError, match="stop_price is required"):
            build_order_request(
                symbol="BTCUSDT",
                side="BUY",
                order_type="STOP_LIMIT",
                quantity="0.01",
                price="65000",
            )

    def test_valid_stop_limit_order(self):
        req = build_order_request(
            symbol="BTCUSDT",
            side="BUY",
            order_type="STOP_LIMIT",
            quantity="0.01",
            price="65000",
            stop_price="64500",
        )
        assert req.price == Decimal("65000")
        assert req.stop_price == Decimal("64500")

    def test_invalid_quantity_propagates(self):
        with pytest.raises(ValidationError, match="quantity"):
            build_order_request(
                symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="-5"
            )

    def test_invalid_symbol_propagates(self):
        with pytest.raises(ValidationError, match="Symbol"):
            build_order_request(
                symbol="", side="BUY", order_type="MARKET", quantity="1"
            )

    def test_result_is_frozen(self):
        req = build_order_request(
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="1"
        )
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            req.symbol = "ETHUSDT"
