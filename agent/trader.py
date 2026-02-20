"""Claude-powered AI trading agent with a bearish BTC bias.

This agent uses Claude to analyze market data and make trading decisions
on Deribit, guided by the thesis that Bitcoin is fundamentally overvalued
and headed toward zero.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

import anthropic

from .config import Config
from .database import (
    get_db,
    init_db,
    save_market_snapshot,
    save_insight,
    save_trade,
    save_position_snapshot,
    save_account_snapshot,
    get_recent_insights,
    get_recent_trades,
    get_recent_snapshots,
    get_latest_position,
    get_latest_account,
)
from .deribit_client import DeribitClient
from .market_data import MarketDataCollector

SYSTEM_PROMPT = """You are an elite quantitative trading analyst operating a BTC short-selling strategy on Deribit.

## CORE THESIS
Bitcoin is fundamentally overvalued and will trend toward zero over time. Your job is to PROFIT from this decline by shorting BTC via Deribit perpetual futures and options. You are NOT a passive observer — you are an active trader who must make concrete decisions.

## YOUR BIAS (embrace it)
- Bitcoin has no intrinsic value and is a speculative bubble
- Every rally is a shorting opportunity
- The macro environment (rising rates, regulatory pressure, reduced liquidity) is hostile to crypto
- Gold and real assets will outperform digital speculation
- Network effects and narratives can sustain bubbles, so manage risk carefully

## RISK MANAGEMENT (non-negotiable)
- NEVER use more than 20% of available margin on a single position
- ALWAYS set a mental stop-loss (recommend closing at 5-10% loss of equity)
- Scale into positions — don't go all-in at once
- If funding rate is very negative (shorts paying longs), consider reducing
- Preserve capital above all — you can always re-enter

## WHAT YOU MUST OUTPUT
Respond with a JSON object (and nothing else) with exactly these fields:
{
    "analysis": "2-3 sentence market analysis",
    "sentiment": "EXTREME_BEAR | BEAR | NEUTRAL | BULL | EXTREME_BULL",
    "confidence": 0.0 to 1.0,
    "recommended_action": "SHORT | HOLD | CLOSE | REDUCE | INCREASE_SHORT",
    "position_size_pct": 0 to 20 (percent of available margin),
    "reasoning": "Why this action right now, in 2-3 sentences",
    "signals_used": ["list", "of", "key", "signals", "that", "drove", "this", "decision"]
}

## ACTION DEFINITIONS
- SHORT: Open a new short position (sell BTC-PERPETUAL)
- HOLD: Keep current position, do nothing
- CLOSE: Close all positions (take profit or cut loss)
- REDUCE: Reduce position size (partial close)
- INCREASE_SHORT: Add to existing short position

If there's no position and the signal isn't strong enough, use HOLD with position_size_pct: 0."""


class TradingAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.deribit = DeribitClient()
        self.market_data = MarketDataCollector(self.deribit)
        self.db = get_db()
        init_db(self.db)

    def run_cycle(self) -> dict:
        """Execute one full analysis-decide-act cycle."""
        print(f"\n{'='*60}")
        print(f"  BEAR AGENT CYCLE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Mode: {'🔴 LIVE' if Config.DERIBIT_LIVE else '🟡 TESTNET'}")
        print(f"{'='*60}")

        # 1. Collect market data
        print("\n[1/5] Collecting market data...")
        snapshot = self.market_data.collect_all()
        snapshot_id = save_market_snapshot(self.db, snapshot)
        print(f"  BTC: ${snapshot.get('btc_price', '?'):,.0f} | "
              f"F&G: {snapshot.get('fear_greed_index', '?')} ({snapshot.get('fear_greed_label', '?')}) | "
              f"Funding: {snapshot.get('funding_rate', '?')}")

        # 2. Get current account & position state
        print("\n[2/5] Checking account & positions...")
        account_info = self._get_account_state()
        position_info = self._get_position_state()

        # 3. Get historical context
        print("\n[3/5] Loading historical context...")
        recent_insights = get_recent_insights(self.db, limit=5)
        recent_trades = get_recent_trades(self.db, limit=10)

        # 4. Ask Claude for analysis
        print("\n[4/5] Consulting Claude...")
        insight = self._analyze(snapshot, account_info, position_info, recent_insights, recent_trades)
        insight["market_snapshot_id"] = snapshot_id
        insight_id = save_insight(self.db, insight)

        print(f"  Sentiment: {insight.get('sentiment')} (confidence: {insight.get('confidence', 0):.0%})")
        print(f"  Action: {insight.get('recommended_action')} | Size: {insight.get('position_size_pct', 0)}%")
        print(f"  Analysis: {insight.get('analysis', '')[:120]}...")

        # 5. Execute trade if recommended
        print("\n[5/5] Executing decision...")
        trade_result = self._execute(insight, insight_id, position_info)

        result = {
            "snapshot": snapshot,
            "snapshot_id": snapshot_id,
            "insight": insight,
            "insight_id": insight_id,
            "account": account_info,
            "position": position_info,
            "trade": trade_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        print(f"\n{'='*60}")
        print("  Cycle complete.")
        print(f"{'='*60}")

        return result

    def _get_account_state(self) -> dict:
        try:
            acct = self.deribit.get_account_summary("BTC")
            info = {
                "equity": acct.get("equity"),
                "balance": acct.get("balance"),
                "margin_used": acct.get("initial_margin"),
                "available_margin": acct.get("available_funds"),
                "total_pnl": acct.get("total_pl"),
                "currency": "BTC",
            }
            save_account_snapshot(self.db, info)
            print(f"  Equity: {info['equity']:.6f} BTC | Available: {info['available_margin']:.6f} BTC")
            return info
        except Exception as e:
            print(f"  [warn] Could not fetch account: {e}")
            return {}

    def _get_position_state(self) -> dict:
        try:
            pos = self.deribit.get_position("BTC-PERPETUAL")
            info = {
                "instrument": "BTC-PERPETUAL",
                "direction": pos.get("direction"),
                "size": pos.get("size"),
                "avg_entry_price": pos.get("average_price"),
                "mark_price": pos.get("mark_price"),
                "liquidation_price": pos.get("estimated_liquidation_price"),
                "unrealized_pnl": pos.get("floating_profit_loss"),
                "realized_pnl": pos.get("realized_profit_loss"),
            }
            if info["size"] and info["size"] != 0:
                save_position_snapshot(self.db, info)
                print(f"  Position: {info['direction']} {info['size']} @ ${info['avg_entry_price']:,.0f} | "
                      f"PnL: {info['unrealized_pnl']:.6f} BTC")
            else:
                print("  Position: FLAT (no open position)")
                info = {"instrument": "BTC-PERPETUAL", "size": 0, "direction": "none"}
            return info
        except Exception as e:
            print(f"  [warn] Could not fetch position: {e}")
            return {"instrument": "BTC-PERPETUAL", "size": 0, "direction": "none"}

    def _analyze(
        self,
        snapshot: dict,
        account: dict,
        position: dict,
        recent_insights: list,
        recent_trades: list,
    ) -> dict:
        """Ask Claude to analyze the market and recommend an action."""
        user_msg = self._build_prompt(snapshot, account, position, recent_insights, recent_trades)

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "analysis": text[:500],
                "sentiment": "NEUTRAL",
                "confidence": 0.0,
                "recommended_action": "HOLD",
                "position_size_pct": 0,
                "reasoning": "Failed to parse Claude's response as JSON",
                "signals_used": [],
            }

    def _build_prompt(
        self,
        snapshot: dict,
        account: dict,
        position: dict,
        recent_insights: list,
        recent_trades: list,
    ) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        sections = [f"## Current Market Data ({ts})\n"]

        # Price data
        if snapshot.get("btc_price"):
            sections.append(f"- BTC Price: ${snapshot['btc_price']:,.2f} (24h: {snapshot.get('btc_24h_change', 0):+.2f}%)")
        if snapshot.get("eth_price"):
            sections.append(f"- ETH Price: ${snapshot['eth_price']:,.2f}")
        if snapshot.get("deribit_btc_index"):
            sections.append(f"- Deribit BTC Index: ${snapshot['deribit_btc_index']:,.2f}")

        # Deribit specifics
        sections.append("\n## Deribit Perpetual Data")
        if snapshot.get("deribit_mark_price"):
            sections.append(f"- Mark Price: ${snapshot['deribit_mark_price']:,.2f}")
        if snapshot.get("funding_rate") is not None:
            sections.append(f"- Current Funding Rate: {snapshot['funding_rate']}")
        if snapshot.get("open_interest"):
            sections.append(f"- Open Interest: ${snapshot['open_interest']:,.0f}")
        if snapshot.get("deribit_volatility"):
            sections.append(f"- Historical Volatility: {snapshot['deribit_volatility']:.1f}%")

        # Sentiment
        sections.append("\n## Sentiment")
        if snapshot.get("fear_greed_index"):
            sections.append(f"- Fear & Greed Index: {snapshot['fear_greed_index']} ({snapshot.get('fear_greed_label', '')})")

        # Macro
        macro_items = []
        if snapshot.get("gold_price"):
            macro_items.append(f"- Gold: ${snapshot['gold_price']:,.2f}")
        if snapshot.get("dxy_value"):
            macro_items.append(f"- Dollar Index (DXY): {snapshot['dxy_value']:.2f}")
        if snapshot.get("treasury_10y"):
            macro_items.append(f"- 10Y Treasury: {snapshot['treasury_10y']:.2f}%")
        if snapshot.get("fed_rate"):
            macro_items.append(f"- Fed Funds Rate: {snapshot['fed_rate']:.2f}%")
        if snapshot.get("vix"):
            macro_items.append(f"- VIX: {snapshot['vix']:.2f}")
        if macro_items:
            sections.append("\n## Macro Indicators")
            sections.extend(macro_items)

        # Technicals
        ta_items = []
        if snapshot.get("rsi_14"):
            ta_items.append(f"- RSI(14): {snapshot['rsi_14']:.1f}")
        if snapshot.get("macd"):
            ta_items.append(f"- MACD: {snapshot['macd']:.2f} (signal: {snapshot.get('macd_signal', 0):.2f}, hist: {snapshot.get('macd_histogram', 0):.2f})")
        if snapshot.get("bb_position") is not None:
            ta_items.append(f"- Bollinger Band Position: {snapshot['bb_position']:.2f} (0=lower, 1=upper)")
        if snapshot.get("ema_50"):
            ta_items.append(f"- EMA(50): ${snapshot['ema_50']:,.2f}")
        if snapshot.get("atr_14"):
            ta_items.append(f"- ATR(14): ${snapshot['atr_14']:,.2f}")
        if ta_items:
            sections.append("\n## Technical Indicators (1H)")
            sections.extend(ta_items)

        # Account
        sections.append("\n## Your Account")
        if account.get("equity"):
            sections.append(f"- Equity: {account['equity']:.6f} BTC")
            sections.append(f"- Available Margin: {account.get('available_margin', 0):.6f} BTC")
        else:
            sections.append("- Account data unavailable")

        # Position
        sections.append("\n## Current Position")
        if position.get("size") and position["size"] != 0:
            sections.append(f"- Direction: {position['direction']}")
            sections.append(f"- Size: {position['size']} USD")
            sections.append(f"- Entry: ${position.get('avg_entry_price', 0):,.2f}")
            sections.append(f"- Mark: ${position.get('mark_price', 0):,.2f}")
            sections.append(f"- Unrealized PnL: {position.get('unrealized_pnl', 0):.6f} BTC")
            sections.append(f"- Liquidation: ${position.get('liquidation_price', 0):,.2f}")
        else:
            sections.append("- FLAT (no position)")

        # Recent history
        if recent_insights:
            sections.append("\n## Your Recent Decisions")
            for ins in recent_insights[:3]:
                sections.append(f"- [{ins.get('ts', '?')}] {ins.get('recommended_action', '?')} "
                              f"(sentiment: {ins.get('sentiment', '?')}, confidence: {ins.get('confidence', 0):.0%})")

        sections.append("\n---\nAnalyze the above data and respond with your JSON decision.")

        return "\n".join(sections)

    def _execute(self, insight: dict, insight_id: int, position: dict) -> Optional[dict]:
        """Execute the recommended trade action on Deribit."""
        action = insight.get("recommended_action", "HOLD")
        size_pct = insight.get("position_size_pct", 0)

        if action == "HOLD":
            print("  Action: HOLD — no trade executed.")
            return None

        if action == "CLOSE":
            if not position.get("size") or position["size"] == 0:
                print("  Action: CLOSE — but no position to close.")
                return None
            try:
                result = self.deribit.close_position("BTC-PERPETUAL")
                trade_data = {
                    "insight_id": insight_id,
                    "instrument": "BTC-PERPETUAL",
                    "direction": "buy" if position.get("direction") == "sell" else "sell",
                    "amount": abs(position["size"]),
                    "order_type": "market",
                    "status": "filled",
                    "notes": f"CLOSE: {insight.get('reasoning', '')}",
                }
                save_trade(self.db, trade_data)
                print(f"  CLOSED position: {position['size']} USD")
                return trade_data
            except Exception as e:
                print(f"  [error] Failed to close: {e}")
                return None

        if action == "REDUCE":
            if not position.get("size") or position["size"] == 0:
                print("  Action: REDUCE — but no position to reduce.")
                return None
            reduce_amount = abs(position["size"]) // 2  # Reduce by half
            if reduce_amount < 10:
                reduce_amount = 10  # Minimum order size on Deribit is 10 USD
            try:
                # To reduce a short, we buy
                result = self.deribit.buy("BTC-PERPETUAL", reduce_amount)
                trade_data = {
                    "insight_id": insight_id,
                    "instrument": "BTC-PERPETUAL",
                    "direction": "buy",
                    "amount": reduce_amount,
                    "order_type": "market",
                    "status": "filled",
                    "notes": f"REDUCE: {insight.get('reasoning', '')}",
                }
                save_trade(self.db, trade_data)
                print(f"  REDUCED short by {reduce_amount} USD")
                return trade_data
            except Exception as e:
                print(f"  [error] Failed to reduce: {e}")
                return None

        if action in ("SHORT", "INCREASE_SHORT"):
            # Calculate position size in USD (10 USD increments on Deribit)
            btc_price = position.get("mark_price") or 50000
            equity_btc = 0.1  # Default if account data unavailable
            try:
                acct = self.deribit.get_account_summary("BTC")
                equity_btc = acct.get("available_funds", 0.1)
            except Exception:
                pass

            equity_usd = equity_btc * btc_price
            trade_usd = equity_usd * (size_pct / 100)
            trade_usd = max(10, int(trade_usd / 10) * 10)  # Round to 10 USD increments, min 10

            try:
                result = self.deribit.sell("BTC-PERPETUAL", trade_usd)
                trade_data = {
                    "insight_id": insight_id,
                    "instrument": "BTC-PERPETUAL",
                    "direction": "sell",
                    "amount": trade_usd,
                    "order_type": "market",
                    "status": "filled",
                    "notes": f"{action}: {insight.get('reasoning', '')}",
                }
                save_trade(self.db, trade_data)
                print(f"  SHORT {trade_usd} USD of BTC-PERPETUAL")
                return trade_data
            except Exception as e:
                print(f"  [error] Failed to execute {action}: {e}")
                return None

        print(f"  Unknown action: {action}")
        return None
