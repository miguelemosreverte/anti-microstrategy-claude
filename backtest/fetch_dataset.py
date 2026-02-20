#!/usr/bin/env python3
"""
Download historical market data and build a labeled dataset for backtesting.

Fetches 30 days of:
- BTC OHLCV (1-hour candles) from Deribit public API (no auth needed)
- BTC funding rate history from Deribit
- Fear & Greed Index history from Alternative.me
- Deribit BTC index price history

All data is saved as a single JSON file in datasets/ with labels:
- For each hourly candle, we label the NEXT 24h return (forward-looking)
- This lets us evaluate: "if the agent shorted here, would it have profited?"
"""

import json
import time
import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

DERIBIT_BASE = "https://www.deribit.com/api/v2"
DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")


def fetch_deribit_ohlcv(days: int = 30, resolution: str = "60") -> pd.DataFrame:
    """Fetch hourly OHLCV candles from Deribit public API."""
    print(f"  Fetching {days} days of BTC-PERPETUAL OHLCV ({resolution}min candles)...")
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 86400 * 1000)

    all_data = {"ticks": [], "open": [], "high": [], "low": [], "close": [], "volume": []}

    # Deribit returns max ~720 candles per request, so we chunk
    chunk_ms = 720 * int(resolution) * 60 * 1000
    cursor = start_ms

    while cursor < now_ms:
        end = min(cursor + chunk_ms, now_ms)
        resp = requests.get(
            f"{DERIBIT_BASE}/public/get_tradingview_chart_data",
            params={
                "instrument_name": "BTC-PERPETUAL",
                "resolution": resolution,
                "start_timestamp": cursor,
                "end_timestamp": end,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})

        if result and "ticks" in result and len(result["ticks"]) > 0:
            for key in all_data:
                all_data[key].extend(result[key])

        cursor = end + 1
        time.sleep(0.3)  # Rate limit courtesy

    df = pd.DataFrame(all_data)
    df["timestamp"] = pd.to_datetime(df["ticks"], unit="ms", utc=True)
    df = df.sort_values("timestamp").drop_duplicates(subset="timestamp").reset_index(drop=True)
    print(f"    Got {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    return df


def fetch_deribit_funding_history(days: int = 30) -> pd.DataFrame:
    """Fetch funding rate history from Deribit."""
    print(f"  Fetching {days} days of BTC-PERPETUAL funding rate history...")
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 86400 * 1000)

    resp = requests.get(
        f"{DERIBIT_BASE}/public/get_funding_rate_history",
        params={
            "instrument_name": "BTC-PERPETUAL",
            "start_timestamp": start_ms,
            "end_timestamp": now_ms,
        },
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json().get("result", [])

    if not result:
        print("    No funding rate data returned")
        return pd.DataFrame()

    df = pd.DataFrame(result)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"    Got {len(df)} funding rate entries")
    return df


def fetch_fear_greed_history(days: int = 30) -> pd.DataFrame:
    """Fetch Fear & Greed Index history from Alternative.me."""
    print(f"  Fetching {days} days of Fear & Greed Index...")
    resp = requests.get(
        f"https://api.alternative.me/fng/?limit={days + 1}",
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])

    records = []
    for entry in data:
        records.append({
            "timestamp": pd.Timestamp(int(entry["timestamp"]), unit="s", tz="UTC"),
            "fear_greed_value": int(entry["value"]),
            "fear_greed_label": entry["value_classification"],
        })

    df = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    print(f"    Got {len(df)} Fear & Greed entries")
    return df


def compute_technicals(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to OHLCV dataframe."""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD(12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands(20, 2)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_middle"] = bb_mid
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = (close - df["bb_lower"]) / bb_range.replace(0, np.nan)

    # EMA(50)
    df["ema_50"] = close.ewm(span=50, adjust=False).mean()

    # ATR(14)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # 24h return (percentage change over next 24 candles = 24 hours)
    df["return_24h"] = close.shift(-24) / close - 1
    # 8h return (for shorter-term signal)
    df["return_8h"] = close.shift(-8) / close - 1

    # Label: would a short have been profitable in the next 24h?
    df["short_profitable_24h"] = (df["return_24h"] < 0).astype(int)
    # How much profit (in %) for a short over 24h
    df["short_pnl_24h_pct"] = -df["return_24h"] * 100

    return df


def merge_funding_rates(ohlcv: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    """Merge funding rates into OHLCV by nearest timestamp."""
    if funding.empty:
        ohlcv["funding_rate"] = np.nan
        return ohlcv

    # Funding rates come every 8h; forward-fill to hourly
    funding = funding.set_index("timestamp")[["interest_8h"]].rename(
        columns={"interest_8h": "funding_rate"}
    )
    ohlcv = ohlcv.set_index("timestamp")
    ohlcv = ohlcv.join(funding, how="left")
    ohlcv["funding_rate"] = ohlcv["funding_rate"].ffill()
    ohlcv = ohlcv.reset_index()
    return ohlcv


def merge_fear_greed(ohlcv: pd.DataFrame, fg: pd.DataFrame) -> pd.DataFrame:
    """Merge daily Fear & Greed into hourly OHLCV by date."""
    if fg.empty:
        ohlcv["fear_greed_value"] = np.nan
        ohlcv["fear_greed_label"] = ""
        return ohlcv

    fg["date"] = fg["timestamp"].dt.date
    ohlcv["date"] = ohlcv["timestamp"].dt.date

    fg_daily = fg.drop_duplicates(subset="date", keep="last")[
        ["date", "fear_greed_value", "fear_greed_label"]
    ]

    ohlcv = ohlcv.merge(fg_daily, on="date", how="left")
    ohlcv["fear_greed_value"] = ohlcv["fear_greed_value"].ffill()
    ohlcv["fear_greed_label"] = ohlcv["fear_greed_label"].ffill()
    ohlcv = ohlcv.drop(columns=["date"])
    return ohlcv


def build_dataset(days: int = 30) -> str:
    """Build the complete labeled dataset and save to JSON."""
    print(f"\n{'='*60}")
    print(f"  Building {days}-day labeled dataset")
    print(f"{'='*60}\n")

    # Fetch all data
    ohlcv = fetch_deribit_ohlcv(days=days)
    funding = fetch_deribit_funding_history(days=days)
    fg = fetch_fear_greed_history(days=days)

    # Merge
    print("\n  Merging datasets...")
    df = merge_funding_rates(ohlcv, funding)
    df = merge_fear_greed(df, fg)

    # Compute technicals and labels
    print("  Computing technical indicators and labels...")
    df = compute_technicals(df)

    # Summary stats
    total_candles = len(df)
    labeled = df["short_profitable_24h"].notna().sum()
    short_win_rate = df["short_profitable_24h"].mean() * 100 if labeled > 0 else 0
    avg_return = df["return_24h"].mean() * 100 if labeled > 0 else 0
    max_price = df["close"].max()
    min_price = df["close"].min()
    start_price = df["close"].iloc[0]
    end_price = df["close"].iloc[-1]
    period_return = (end_price / start_price - 1) * 100

    summary = {
        "total_candles": int(total_candles),
        "labeled_candles": int(labeled),
        "date_range": {
            "start": str(df["timestamp"].iloc[0]),
            "end": str(df["timestamp"].iloc[-1]),
        },
        "price_range": {"min": float(min_price), "max": float(max_price)},
        "start_price": float(start_price),
        "end_price": float(end_price),
        "period_return_pct": round(float(period_return), 2),
        "short_win_rate_24h_pct": round(float(short_win_rate), 2),
        "avg_24h_return_pct": round(float(avg_return), 4),
    }

    print(f"\n  Dataset Summary:")
    print(f"    Candles: {total_candles} ({labeled} labeled)")
    print(f"    Period: {summary['date_range']['start']} → {summary['date_range']['end']}")
    print(f"    Price: ${min_price:,.0f} – ${max_price:,.0f}")
    print(f"    Period return: {period_return:+.2f}%")
    print(f"    Short win rate (24h): {short_win_rate:.1f}%")

    # Convert to serializable format
    df["timestamp"] = df["timestamp"].astype(str)
    records = df.replace({np.nan: None}).to_dict(orient="records")

    dataset = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "days": days,
            "instrument": "BTC-PERPETUAL",
            "exchange": "Deribit",
            "resolution": "1h",
        },
        "summary": summary,
        "candles": records,
    }

    # Save
    os.makedirs(DATASETS_DIR, exist_ok=True)
    filename = f"btc-perpetual-{days}d-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    filepath = os.path.join(DATASETS_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    # Also save as "latest"
    latest_path = os.path.join(DATASETS_DIR, "latest.json")
    with open(latest_path, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    print(f"\n  Saved: {filepath}")
    print(f"  Saved: {latest_path}")

    return filepath


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    build_dataset(days)
