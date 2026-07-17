from __future__ import annotations

from unittest.mock import Mock

import pytest

from bot.exceptions import BinanceAPIError, NetworkError
from bot.orders import _order_params_from_request, place_order
from bot.validators import build_order_request


class TestOrderParamsFromRequest:
    def test_market_order_params(self):
        req = build_order_request(
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.01"
        )
        params = _order_params_from_request(req)
        assert params == {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": "0.01",
        }
        # MARKET orders must not send price/timeInForce
        assert "price" not in params
        assert "timeInForce" not in params

    def test_limit_order_params(self):
        req = build_order_request(
            symbol="ETHUSDT",
            side="SELL",
            order_type="LIMIT",
            quantity="1.5",
            price="3000",
            time_in_force="IOC",
        )
        params = _order_params_from_request(req)
        assert params == {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "quantity": "1.5",
            "price": "3000",
            "timeInForce": "IOC",
        }

    def test_stop_limit_order_params_maps_to_stop_type(self):
        req = build_order_request(
            symbol="BTCUSDT",
            side="BUY",
            order_type="STOP_LIMIT",
            quantity="0.01",
            price="65000",
            stop_price="64500",
        )
        params = _order_params_from_request(req)
        # Binance's actual order type for stop-limit is "STOP", not "STOP_LIMIT"
        assert params["type"] == "STOP"
        assert params["price"] == "65000"
        assert params["stopPrice"] == "64500"
        assert params["timeInForce"] == "GTC"


class TestPlaceOrder:
    def test_successful_market_order(self):
        mock_client = Mock()
        mock_client.new_order.return_value = {
            "orderId": 28457,
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "side": "BUY",
            "type": "MARKET",
            "executedQty": "0.01",
            "origQty": "0.01",
            "avgPrice": "60123.40",
            "price": "0",
        }
        req = build_order_request(
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.01"
        )

        result = place_order(mock_client, req)

        assert result.success is True
        assert result.order_id == 28457
        assert result.status == "FILLED"
        assert result.executed_qty == "0.01"
        assert result.avg_price == "60123.40"
        assert result.error_message is None
        mock_client.new_order.assert_called_once_with(
            symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.01"
        )

    def test_successful_limit_order(self):
        mock_client = Mock()
        mock_client.new_order.return_value = {
            "orderId": 99001,
            "symbol": "ETHUSDT",
            "status": "NEW",
            "side": "SELL",
            "type": "LIMIT",
            "executedQty": "0.0",
            "origQty": "2.0",
            "avgPrice": "0.00",
            "price": "3500.00",
        }
        req = build_order_request(
            symbol="ETHUSDT",
            side="SELL",
            order_type="LIMIT",
            quantity="2.0",
            price="3500.00",
        )

        result = place_order(mock_client, req)

        assert result.success is True
        assert result.status == "NEW"
        assert result.price == "3500.00"

    def test_binance_rejection_returns_failed_result_not_exception(self):
        """
        Exchange-level rejections (bad symbol, insufficient balance, etc.)
        should be captured into OrderResult, not raised -- this lets the
        CLI print a clean failure message instead of a traceback.
        """
        mock_client = Mock()
        mock_client.new_order.side_effect = BinanceAPIError(
            code=-2019, msg="Margin is insufficient."
        )
        req = build_order_request(
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="100"
        )

        result = place_order(mock_client, req)

        assert result.success is False
        assert result.order_id is None
        assert "-2019" in result.error_message
        assert "Margin is insufficient" in result.error_message

    def test_network_error_propagates(self):
        """
        Unlike exchange rejections, network failures mean we don't know
        the outcome -- these should propagate so the caller treats them
        distinctly (order may or may not have gone through).
        """
        mock_client = Mock()
        mock_client.new_order.side_effect = NetworkError("Connection refused")
        req = build_order_request(
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.01"
        )

        with pytest.raises(NetworkError):
            place_order(mock_client, req)

    def test_missing_avg_price_in_response_handled_gracefully(self):
        """Some order types/states may not include avgPrice; shouldn't crash."""
        mock_client = Mock()
        mock_client.new_order.return_value = {
            "orderId": 1,
            "symbol": "BTCUSDT",
            "status": "NEW",
            "side": "BUY",
            "type": "LIMIT",
            "executedQty": "0",
            "origQty": "1",
            "price": "50000",
            # no avgPrice key at all
        }
        req = build_order_request(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1",
            price="50000",
        )

        result = place_order(mock_client, req)
        assert result.success is True
        assert result.avg_price is None
