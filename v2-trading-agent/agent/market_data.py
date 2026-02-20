"""Aggregate market data from free public APIs to feed the AI trading agent."""

import time
import requests
import pandas as pd
import numpy as np
from typing import Optional

from .config import Config
from .deribit_client import DeribitClient


class MarketDataCollector:
    """Pulls data from CoinGecko, Alternative.me, FRED, Deribit, and CryptoCompare."""

    def __init__(self, deribit: DeribitClient):
        self.deribit = deribit
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def collect_all(self) -> dict:
        """Collect a full market snapshot from all available sources."""
        snapshot = {}

        # Each call is wrapped in try/except so one failure doesn't kill the whole snapshot
        collectors = [
            ("crypto_prices", self._get_crypto_prices),
            ("fear_greed", self._get_fear_greed),
            ("deribit_data", self._get_deribit_data),
            ("macro_data", self._get_macro_data),
            ("technicals", self._get_technicals),
        ]

        for name, fn in collectors:
            try:
                result = fn()
                snapshot.update(result)
            except Exception as e:
                print(f"  [warn] Failed to collect {name}: {e}")

        return snapshot

    def _get_crypto_prices(self) -> dict:
        """BTC and ETH prices from CoinGecko (no key required for basic calls)."""
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        }
        if Config.COINGECKO_API_KEY:
            params["x_cg_demo_api_key"] = Config.COINGECKO_API_KEY

        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        btc = data.get("bitcoin", {})
        eth = data.get("ethereum", {})

        return {
            "btc_price": btc.get("usd"),
            "btc_24h_change": btc.get("usd_24h_change"),
            "btc_volume_24h": btc.get("usd_24h_vol"),
            "btc_market_cap": btc.get("usd_market_cap"),
            "eth_price": eth.get("usd"),
            "eth_24h_change": eth.get("usd_24h_change"),
        }

    def _get_fear_greed(self) -> dict:
        """Crypto Fear & Greed Index from Alternative.me (no key needed)."""
        resp = self.session.get(
            "https://api.alternative.me/fng/?limit=1", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        entry = data.get("data", [{}])[0]
        return {
            "fear_greed_index": int(entry.get("value", 0)),
            "fear_greed_label": entry.get("value_classification", ""),
        }

    def _get_deribit_data(self) -> dict:
        """Deribit-specific data: index price, perpetual ticker, funding rate."""
        result = {}

        # BTC index price
        idx = self.deribit.get_index_price("btc_usd")
        result["deribit_btc_index"] = idx.get("index_price")

        # BTC perpetual ticker
        ticker = self.deribit.get_ticker("BTC-PERPETUAL")
        result["deribit_mark_price"] = ticker.get("mark_price")
        result["deribit_best_bid"] = ticker.get("best_bid_price")
        result["deribit_best_ask"] = ticker.get("best_ask_price")
        result["open_interest"] = ticker.get("open_interest")
        result["funding_rate"] = ticker.get("current_funding")
        result["deribit_volume_24h"] = ticker.get("stats", {}).get("volume_usd")

        # Historical volatility
        try:
            vol = self.deribit.get_historical_volatility("BTC")
            if vol and len(vol) > 0:
                # Returns list of [timestamp, volatility] pairs
                result["deribit_volatility"] = vol[-1][1] if isinstance(vol[-1], list) else vol[-1]
        except Exception:
            pass

        return result

    def _get_macro_data(self) -> dict:
        """Macro indicators from FRED (requires free API key)."""
        if not Config.FRED_API_KEY:
            return {}

        result = {}
        series_map = {
            "gold_price": "GOLDAMGBD228NLBM",
            "dxy_value": "DTWEXBGS",
            "treasury_10y": "DGS10",
            "fed_rate": "DFF",
            "vix": "VIXCLS",
        }

        for field, series_id in series_map.items():
            try:
                resp = self.session.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": Config.FRED_API_KEY,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                obs = resp.json().get("observations", [])
                if obs and obs[0].get("value") != ".":
                    result[field] = float(obs[0]["value"])
            except Exception:
                pass

        return result

    def _get_technicals(self) -> dict:
        """Compute technical indicators from Deribit OHLCV data using pure pandas."""
        try:
            chart = self.deribit.get_chart_data(
                instrument="BTC-PERPETUAL",
                resolution="60",  # 1h candles
            )

            if not chart or "close" not in chart:
                return {}

            df = pd.DataFrame(
                {
                    "open": chart["open"],
                    "high": chart["high"],
                    "low": chart["low"],
                    "close": chart["close"],
                    "volume": chart["volume"],
                }
            )

            if len(df) < 26:
                return {}

            close = df["close"]
            high = df["high"]
            low = df["low"]
            result = {}

            # RSI(14)
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            if pd.notna(rsi.iloc[-1]):
                result["rsi_14"] = round(float(rsi.iloc[-1]), 4)

            # MACD(12, 26, 9)
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            histogram = macd_line - signal_line
            if pd.notna(macd_line.iloc[-1]):
                result["macd"] = round(float(macd_line.iloc[-1]), 2)
                result["macd_signal"] = round(float(signal_line.iloc[-1]), 2)
                result["macd_histogram"] = round(float(histogram.iloc[-1]), 2)

            # Bollinger Bands(20, 2)
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std
            if pd.notna(bb_mid.iloc[-1]):
                result["bb_middle"] = round(float(bb_mid.iloc[-1]), 4)
                result["bb_upper"] = round(float(bb_upper.iloc[-1]), 4)
                result["bb_lower"] = round(float(bb_lower.iloc[-1]), 4)
                bb_range = result["bb_upper"] - result["bb_lower"]
                if bb_range > 0:
                    result["bb_position"] = round(
                        (float(close.iloc[-1]) - result["bb_lower"]) / bb_range, 4
                    )

            # EMA(50)
            if len(df) >= 50:
                ema50 = close.ewm(span=50, adjust=False).mean()
                if pd.notna(ema50.iloc[-1]):
                    result["ema_50"] = round(float(ema50.iloc[-1]), 4)

            # ATR(14)
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            if pd.notna(atr.iloc[-1]):
                result["atr_14"] = round(float(atr.iloc[-1]), 4)

            return result

        except Exception as e:
            print(f"  [warn] Technical analysis failed: {e}")
            return {}
