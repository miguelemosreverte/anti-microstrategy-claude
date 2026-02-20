"""Deribit REST API client for trading BTC perpetual futures and options."""

import time
import requests
from typing import Optional

from .config import Config


class DeribitClient:
    def __init__(self):
        self.base_url = Config.DERIBIT_BASE_URL
        self.client_id = Config.DERIBIT_CLIENT_ID
        self.client_secret = Config.DERIBIT_CLIENT_SECRET
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        self.session = requests.Session()
        self.is_live = Config.DERIBIT_LIVE

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the Deribit API."""
        url = f"{self.base_url}/{method}"
        resp = self.session.get(url, params=params or {}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise Exception(f"Deribit API error: {data['error']}")
        return data.get("result", data)

    def _private_request(self, method: str, params: Optional[dict] = None) -> dict:
        """Make an authenticated request."""
        self._ensure_auth()
        p = dict(params or {})
        p["access_token"] = self.access_token  # Deribit accepts token as param
        # For private endpoints, use GET with params
        url = f"{self.base_url}/{method}"
        resp = self.session.get(url, params=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise Exception(f"Deribit API error: {data['error']}")
        return data.get("result", data)

    def _ensure_auth(self):
        """Authenticate or refresh token if expired."""
        if self.access_token and time.time() < self.token_expiry - 30:
            return
        result = self._request(
            "public/auth",
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        self.access_token = result["access_token"]
        self.token_expiry = time.time() + result["expires_in"]

    # ---- Public Market Data (no auth needed) ----

    def get_index_price(self, index: str = "btc_usd") -> dict:
        return self._request("public/get_index_price", {"index_name": index})

    def get_ticker(self, instrument: str = "BTC-PERPETUAL") -> dict:
        return self._request("public/ticker", {"instrument_name": instrument})

    def get_order_book(self, instrument: str = "BTC-PERPETUAL", depth: int = 5) -> dict:
        return self._request(
            "public/get_order_book",
            {"instrument_name": instrument, "depth": depth},
        )

    def get_instruments(self, currency: str = "BTC", kind: str = "future") -> list:
        return self._request(
            "public/get_instruments",
            {"currency": currency, "kind": kind},
        )

    def get_funding_rate(self, instrument: str = "BTC-PERPETUAL") -> dict:
        return self._request(
            "public/get_funding_rate_value",
            {"instrument_name": instrument, "start_timestamp": int((time.time() - 28800) * 1000), "end_timestamp": int(time.time() * 1000)},
        )

    def get_historical_volatility(self, currency: str = "BTC") -> list:
        return self._request(
            "public/get_historical_volatility", {"currency": currency}
        )

    def get_chart_data(
        self,
        instrument: str = "BTC-PERPETUAL",
        resolution: str = "60",  # minutes
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> dict:
        now_ms = int(time.time() * 1000)
        return self._request(
            "public/get_tradingview_chart_data",
            {
                "instrument_name": instrument,
                "resolution": resolution,
                "start_timestamp": start_ms or (now_ms - 86400 * 1000),
                "end_timestamp": end_ms or now_ms,
            },
        )

    # ---- Private (authenticated) ----

    def get_account_summary(self, currency: str = "BTC") -> dict:
        return self._private_request(
            "private/get_account_summary",
            {"currency": currency, "extended": "true"},
        )

    def get_positions(self, currency: str = "BTC") -> list:
        return self._private_request(
            "private/get_positions", {"currency": currency}
        )

    def get_position(self, instrument: str = "BTC-PERPETUAL") -> dict:
        return self._private_request(
            "private/get_position", {"instrument_name": instrument}
        )

    def get_open_orders(self, instrument: str = "BTC-PERPETUAL") -> list:
        return self._private_request(
            "private/get_open_orders_by_instrument",
            {"instrument_name": instrument},
        )

    def buy(
        self,
        instrument: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
        label: str = "bear-agent",
    ) -> dict:
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": order_type,
            "label": label,
        }
        if price and order_type == "limit":
            params["price"] = price
        return self._private_request("private/buy", params)

    def sell(
        self,
        instrument: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
        label: str = "bear-agent",
    ) -> dict:
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": order_type,
            "label": label,
        }
        if price and order_type == "limit":
            params["price"] = price
        return self._private_request("private/sell", params)

    def close_position(
        self, instrument: str, order_type: str = "market"
    ) -> dict:
        return self._private_request(
            "private/close_position",
            {"instrument_name": instrument, "type": order_type},
        )

    def cancel_all(self) -> int:
        return self._private_request("private/cancel_all")

    def get_trade_history(
        self, instrument: str = "BTC-PERPETUAL", count: int = 20
    ) -> list:
        return self._private_request(
            "private/get_user_trades_by_instrument",
            {"instrument_name": instrument, "count": count, "sorting": "desc"},
        )
