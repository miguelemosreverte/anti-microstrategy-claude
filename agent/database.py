"""SQLite database for storing market snapshots, agent insights, and trade history."""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional

from .config import Config


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or Config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    """Create all tables if they don't exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            btc_price REAL,
            btc_24h_change REAL,
            btc_volume_24h REAL,
            eth_price REAL,
            funding_rate REAL,
            open_interest REAL,
            fear_greed_index INTEGER,
            fear_greed_label TEXT,
            deribit_btc_index REAL,
            deribit_volatility REAL,
            gold_price REAL,
            dxy_value REAL,
            treasury_10y REAL,
            fed_rate REAL,
            raw_data TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            market_snapshot_id INTEGER REFERENCES market_snapshots(id),
            analysis TEXT NOT NULL,
            sentiment TEXT CHECK(sentiment IN ('EXTREME_BEAR', 'BEAR', 'NEUTRAL', 'BULL', 'EXTREME_BULL')),
            confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
            recommended_action TEXT CHECK(recommended_action IN ('SHORT', 'HOLD', 'CLOSE', 'REDUCE', 'INCREASE_SHORT')),
            position_size_pct REAL,
            reasoning TEXT,
            signals_used TEXT
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            insight_id INTEGER REFERENCES agent_insights(id),
            instrument TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('buy', 'sell')),
            amount REAL NOT NULL,
            price REAL,
            order_type TEXT DEFAULT 'market',
            order_id TEXT,
            status TEXT DEFAULT 'pending',
            pnl REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            instrument TEXT NOT NULL,
            direction TEXT,
            size REAL,
            avg_entry_price REAL,
            mark_price REAL,
            liquidation_price REAL,
            unrealized_pnl REAL,
            realized_pnl REAL,
            raw_data TEXT
        );

        CREATE TABLE IF NOT EXISTS account_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            equity REAL,
            balance REAL,
            margin_used REAL,
            available_margin REAL,
            total_pnl REAL,
            currency TEXT DEFAULT 'BTC',
            raw_data TEXT
        );
    """
    )
    conn.commit()


def save_market_snapshot(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO market_snapshots
           (btc_price, btc_24h_change, btc_volume_24h, eth_price,
            funding_rate, open_interest, fear_greed_index, fear_greed_label,
            deribit_btc_index, deribit_volatility, gold_price, dxy_value,
            treasury_10y, fed_rate, raw_data)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("btc_price"),
            data.get("btc_24h_change"),
            data.get("btc_volume_24h"),
            data.get("eth_price"),
            data.get("funding_rate"),
            data.get("open_interest"),
            data.get("fear_greed_index"),
            data.get("fear_greed_label"),
            data.get("deribit_btc_index"),
            data.get("deribit_volatility"),
            data.get("gold_price"),
            data.get("dxy_value"),
            data.get("treasury_10y"),
            data.get("fed_rate"),
            json.dumps(data),
        ),
    )
    conn.commit()
    return cur.lastrowid


def save_insight(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO agent_insights
           (market_snapshot_id, analysis, sentiment, confidence,
            recommended_action, position_size_pct, reasoning, signals_used)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            data.get("market_snapshot_id"),
            data.get("analysis", ""),
            data.get("sentiment"),
            data.get("confidence"),
            data.get("recommended_action"),
            data.get("position_size_pct"),
            data.get("reasoning"),
            json.dumps(data.get("signals_used", [])),
        ),
    )
    conn.commit()
    return cur.lastrowid


def save_trade(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO trades
           (insight_id, instrument, direction, amount, price,
            order_type, order_id, status, notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            data.get("insight_id"),
            data["instrument"],
            data["direction"],
            data["amount"],
            data.get("price"),
            data.get("order_type", "market"),
            data.get("order_id"),
            data.get("status", "pending"),
            data.get("notes"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def save_position_snapshot(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO positions
           (instrument, direction, size, avg_entry_price, mark_price,
            liquidation_price, unrealized_pnl, realized_pnl, raw_data)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            data.get("instrument"),
            data.get("direction"),
            data.get("size"),
            data.get("avg_entry_price"),
            data.get("mark_price"),
            data.get("liquidation_price"),
            data.get("unrealized_pnl"),
            data.get("realized_pnl"),
            json.dumps(data),
        ),
    )
    conn.commit()
    return cur.lastrowid


def save_account_snapshot(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO account_snapshots
           (equity, balance, margin_used, available_margin, total_pnl, currency, raw_data)
           VALUES (?,?,?,?,?,?,?)""",
        (
            data.get("equity"),
            data.get("balance"),
            data.get("margin_used"),
            data.get("available_margin"),
            data.get("total_pnl"),
            data.get("currency", "BTC"),
            json.dumps(data),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_insights(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM agent_insights ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_trades(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_snapshots(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_position(conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM positions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_latest_account(conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM account_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
