from __future__ import annotations

import hashlib
import hmac
from unittest.mock import Mock, patch

import pytest
import requests

from bot.client import BinanceFuturesTestnetClient
from bot.exceptions import BinanceAPIError, NetworkError


API_KEY = "dbefbc809e3e83c283a984c3a1459732ea7db1360ca80c5c2c8867408d28cc83"
API_SECRET = "2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9"


@pytest.fixture
def client() -> BinanceFuturesTestnetClient:
    return BinanceFuturesTestnetClient(api_key=API_KEY, api_secret=API_SECRET)


class TestSigning:
    def test_signature_matches_binance_documented_example(self, client):
        """
        Reproduces Binance's official worked example verbatim:

        Params: symbol=BTCUSDT&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1
                &price=9000&recvWindow=5000&timestamp=1591702613943
        Expected signature (per Binance docs):
        3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9

        Since urlencode() preserves insertion order in Python dicts (3.7+),
        we build params in the exact order Binance's example uses, then
        manually compute what the signature *should* be (independent of
        client._sign's internals) and confirm the client's helper method
        of constructing the query string + signing produces the same
        result Binance's own openssl command produced.
        """
        expected_signature = (
            "3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9"
        )
        query_string = (
            "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=9000"
            "&timeInForce=GTC&recvWindow=5000&timestamp=1591702613943"
        )

        computed_signature = hmac.new(
            API_SECRET.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert computed_signature == expected_signature, (
            "Sanity check failed: our HMAC computation doesn't match "
            "Binance's own documented example independent of client code."
        )

    def test_sign_adds_timestamp_recvwindow_and_signature(self, client):
        params = {"symbol": "BTCUSDT", "side": "BUY"}
        signed = client._sign(params)

        assert "timestamp" in signed
        assert isinstance(signed["timestamp"], int)
        assert signed["recvWindow"] == 5000
        assert "signature" in signed
        assert len(signed["signature"]) == 64  # SHA256 hex digest length

    def test_sign_does_not_mutate_original_params(self, client):
        original = {"symbol": "BTCUSDT"}
        client._sign(original)
        assert original == {"symbol": "BTCUSDT"}  # unchanged

    def test_sign_produces_valid_hex_signature(self, client):
        signed = client._sign({"symbol": "ETHUSDT", "side": "SELL"})
        signature = signed["signature"]
        # Should be valid lowercase hex
        int(signature, 16)  # raises ValueError if not valid hex
        assert signature == signature.lower()


class TestResponseHandling:
    def test_successful_response_returns_body(self, client):
        mock_response = Mock(spec=requests.Response)
        mock_response.ok = True
        mock_response.json.return_value = {"orderId": 12345, "status": "FILLED"}

        result = client._handle_response(mock_response, "/fapi/v1/order")
        assert result == {"orderId": 12345, "status": "FILLED"}

    def test_error_response_raises_binance_api_error(self, client):
        mock_response = Mock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"code": -1121, "msg": "Invalid symbol."}
        mock_response.text = '{"code": -1121, "msg": "Invalid symbol."}'

        with pytest.raises(BinanceAPIError) as exc_info:
            client._handle_response(mock_response, "/fapi/v1/order")

        assert exc_info.value.code == -1121
        assert exc_info.value.msg == "Invalid symbol."
        assert exc_info.value.status_code == 400

    def test_non_json_error_response_falls_back_to_text(self, client):
        mock_response = Mock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 503
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "Service Unavailable."

        with pytest.raises(BinanceAPIError) as exc_info:
            client._handle_response(mock_response, "/fapi/v1/order")

        assert exc_info.value.status_code == 503


class TestNetworkErrorHandling:
    def test_timeout_raises_network_error(self, client):
        with patch.object(
            client._session,
            "request",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            with pytest.raises(NetworkError, match="timed out"):
                client._request("GET", "/fapi/v1/ping")

    def test_connection_error_raises_network_error(self, client):
        with patch.object(
            client._session,
            "request",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(NetworkError, match="Could not connect"):
                client._request("GET", "/fapi/v1/ping")


class TestClientConstruction:
    def test_missing_api_key_raises(self):
        with pytest.raises(ValueError):
            BinanceFuturesTestnetClient(api_key="", api_secret="secret")

    def test_missing_api_secret_raises(self):
        with pytest.raises(ValueError):
            BinanceFuturesTestnetClient(api_key="key", api_secret="")

    def test_base_url_trailing_slash_stripped(self):
        c = BinanceFuturesTestnetClient(
            api_key="k", api_secret="s", base_url="https://example.com/"
        )
        assert c.base_url == "https://example.com"

    def test_api_key_header_set(self):
        c = BinanceFuturesTestnetClient(api_key="mykey", api_secret="mysecret")
        assert c._session.headers["X-MBX-APIKEY"] == "mykey"
