"""
Backtesting engine with sliding-window cross-validation.

The engine:
1. Loads the labeled dataset
2. Creates train/test splits using sliding windows (like time-series CV)
3. Feeds the "training" window (25 days) to the Claude agent as context
4. Asks the agent to make decisions for each candle in the "test" window (5 days)
5. Evaluates PnL against actual price movements
6. Aggregates results across all folds for robust evaluation
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")

# The agent system prompt (same bearish bias as live)
BACKTEST_SYSTEM_PROMPT = """You are an elite quantitative trading analyst backtesting a BTC short-selling strategy on Deribit.

## CORE THESIS
Bitcoin is fundamentally overvalued and will trend toward zero over time. You profit from declines by shorting BTC perpetual futures.

## RISK MANAGEMENT (non-negotiable)
- NEVER use more than 20% of available margin on a single position
- Scale into positions — don't go all-in at once
- If funding rate is very negative (shorts paying longs), consider reducing
- Preserve capital above all

## WHAT YOU MUST OUTPUT
For EACH test candle provided, respond with a JSON array where each element has:
{
    "candle_index": <index in the test set>,
    "action": "SHORT | HOLD | CLOSE | REDUCE | INCREASE_SHORT",
    "position_size_pct": 0 to 20,
    "confidence": 0.0 to 1.0,
    "reasoning": "1-sentence reason"
}

Respond with ONLY the JSON array. No markdown, no explanation outside the array."""


def load_dataset(path: Optional[str] = None) -> dict:
    """Load the labeled dataset."""
    path = path or os.path.join(DATASETS_DIR, "latest.json")
    with open(path) as f:
        return json.load(f)


def create_sliding_windows(
    candles: list,
    train_days: int = 25,
    test_days: int = 5,
    stride_hours: int = 48,
) -> list:
    """
    Create train/test splits using a sliding window.

    Like time-series cross-validation:
    - Window 1: train on days 0-24,  test on days 25-29
    - Window 2: train on days 2-26,  test on days 27-31
    - etc.

    stride_hours controls overlap: 48 = shift by 2 days each fold.
    """
    train_candles = train_days * 24
    test_candles = test_days * 24
    total_needed = train_candles + test_candles

    if len(candles) < total_needed:
        raise ValueError(
            f"Need at least {total_needed} candles ({train_days}+{test_days} days), "
            f"got {len(candles)}"
        )

    windows = []
    start = 0
    while start + total_needed <= len(candles):
        train_end = start + train_candles
        test_end = train_end + test_candles

        windows.append({
            "fold_id": len(windows),
            "train_start_idx": start,
            "train_end_idx": train_end,
            "test_start_idx": train_end,
            "test_end_idx": min(test_end, len(candles)),
            "train_candles": candles[start:train_end],
            "test_candles": candles[train_end:test_end],
            "train_period": {
                "start": candles[start]["timestamp"],
                "end": candles[train_end - 1]["timestamp"],
            },
            "test_period": {
                "start": candles[train_end]["timestamp"],
                "end": candles[min(test_end, len(candles)) - 1]["timestamp"],
            },
        })

        start += stride_hours

    return windows


def summarize_train_window(candles: list) -> str:
    """Create a concise summary of the training window for the agent."""
    if not candles:
        return "No training data available."

    prices = [c["close"] for c in candles if c.get("close")]
    start_price = prices[0]
    end_price = prices[-1]
    max_price = max(prices)
    min_price = min(prices)
    period_return = (end_price / start_price - 1) * 100

    # Daily summaries (take every 24th candle)
    daily_summaries = []
    for i in range(0, len(candles), 24):
        chunk = candles[i : i + 24]
        if not chunk:
            continue
        day_open = chunk[0]["close"]
        day_close = chunk[-1]["close"]
        day_high = max(c["high"] for c in chunk if c.get("high"))
        day_low = min(c["low"] for c in chunk if c.get("low"))
        day_vol = sum(c.get("volume", 0) or 0 for c in chunk)
        day_return = (day_close / day_open - 1) * 100

        # Get indicators from last candle of the day
        last = chunk[-1]
        rsi = last.get("rsi_14")
        macd_h = last.get("macd_histogram")
        fg = last.get("fear_greed_value")
        funding = last.get("funding_rate")

        daily_summaries.append(
            f"  {chunk[0]['timestamp'][:10]}: "
            f"O={day_open:,.0f} H={day_high:,.0f} L={day_low:,.0f} C={day_close:,.0f} "
            f"({day_return:+.1f}%) Vol={day_vol:,.0f}"
            + (f" RSI={rsi:.0f}" if rsi else "")
            + (f" MACD_H={macd_h:.0f}" if macd_h else "")
            + (f" F&G={fg}" if fg else "")
            + (f" Fund={funding:.6f}" if funding else "")
        )

    # Last candle details
    last = candles[-1]

    lines = [
        f"## TRAINING DATA: {len(candles)} hourly candles ({len(candles)//24} days)",
        f"Period: {candles[0]['timestamp']} → {candles[-1]['timestamp']}",
        f"Price range: ${min_price:,.0f} – ${max_price:,.0f}",
        f"Period return: {period_return:+.2f}%",
        f"Start: ${start_price:,.0f} → End: ${end_price:,.0f}",
        "",
        "### Daily OHLCV Summary",
    ]
    lines.extend(daily_summaries)

    lines.extend([
        "",
        "### Latest Technical Indicators",
        f"- RSI(14): {last.get('rsi_14', 'N/A')}",
        f"- MACD: {last.get('macd', 'N/A')} (signal: {last.get('macd_signal', 'N/A')}, hist: {last.get('macd_histogram', 'N/A')})",
        f"- BB Position: {last.get('bb_position', 'N/A')} (0=lower, 1=upper)",
        f"- EMA(50): {last.get('ema_50', 'N/A')}",
        f"- ATR(14): {last.get('atr_14', 'N/A')}",
        f"- Funding Rate: {last.get('funding_rate', 'N/A')}",
        f"- Fear & Greed: {last.get('fear_greed_value', 'N/A')} ({last.get('fear_greed_label', '')})",
    ])

    return "\n".join(lines)


def format_test_candles(candles: list) -> str:
    """Format test candles as a table for the agent (WITHOUT future-looking labels)."""
    lines = [
        "## TEST CANDLES (make a decision for each)",
        "You are seeing these candles one at a time as they arrive. Decide for each.",
        "",
        "| idx | timestamp | open | high | low | close | volume | rsi_14 | macd_hist | bb_pos | funding |",
        "|-----|-----------|------|------|-----|-------|--------|--------|-----------|--------|---------|",
    ]

    for i, c in enumerate(candles):
        lines.append(
            f"| {i} | {c['timestamp'][:16]} | "
            f"{c.get('open', 0):,.0f} | {c.get('high', 0):,.0f} | "
            f"{c.get('low', 0):,.0f} | {c.get('close', 0):,.0f} | "
            f"{c.get('volume', 0):,.0f} | "
            f"{c.get('rsi_14', ''):} | "
            f"{c.get('macd_histogram', ''):} | "
            f"{c.get('bb_position', ''):} | "
            f"{c.get('funding_rate', ''):} |"
        )

    return "\n".join(lines)


def rule_based_strategy(test_candles: list) -> list:
    """
    Deterministic rule-based strategy as a baseline / fallback when no API key is set.

    Rules (bearish bias):
    - If RSI > 65: SHORT (overbought = shorting opportunity)
    - If RSI > 70 and already short: INCREASE_SHORT
    - If RSI < 30: CLOSE (oversold = take profit on short)
    - If MACD histogram crosses below zero: SHORT
    - If BB position > 0.85: SHORT (near upper band)
    - If BB position < 0.15: CLOSE (near lower band)
    - Otherwise: HOLD
    """
    decisions = []
    has_position = False

    for i, c in enumerate(test_candles):
        rsi = c.get("rsi_14")
        macd_h = c.get("macd_histogram")
        bb_pos = c.get("bb_position")

        action = "HOLD"
        size = 0
        confidence = 0.3
        reason = "No clear signal"

        if rsi is not None:
            if rsi > 70 and has_position:
                action = "INCREASE_SHORT"
                size = 5
                confidence = 0.7
                reason = f"RSI overbought at {rsi:.0f}, adding to short"
            elif rsi > 65 and not has_position:
                action = "SHORT"
                size = 10
                confidence = 0.6
                reason = f"RSI elevated at {rsi:.0f}, opening short"
                has_position = True
            elif rsi < 30 and has_position:
                action = "CLOSE"
                confidence = 0.65
                reason = f"RSI oversold at {rsi:.0f}, taking profit"
                has_position = False

        if action == "HOLD" and bb_pos is not None:
            if bb_pos > 0.85 and not has_position:
                action = "SHORT"
                size = 8
                confidence = 0.55
                reason = f"Price near upper BB ({bb_pos:.2f}), shorting"
                has_position = True
            elif bb_pos < 0.15 and has_position:
                action = "CLOSE"
                confidence = 0.55
                reason = f"Price near lower BB ({bb_pos:.2f}), closing"
                has_position = False

        if action == "HOLD" and macd_h is not None and not has_position:
            if macd_h < -50:
                action = "SHORT"
                size = 8
                confidence = 0.5
                reason = f"MACD histogram negative ({macd_h:.0f}), trend bearish"
                has_position = True

        decisions.append({
            "candle_index": i,
            "action": action,
            "position_size_pct": size,
            "confidence": confidence,
            "reasoning": reason,
        })

    return decisions


def query_agent(train_summary: str, test_candles_str: str, test_candles_raw: list = None) -> list:
    """Ask Claude via CLI to make trading decisions, or fall back to rules."""

    prompt = f"""{BACKTEST_SYSTEM_PROMPT}

{train_summary}

---

{test_candles_str}

---

INSTRUCTIONS:
- You have just seen 25 days of historical context above.
- Now you see the test candles arriving in real-time.
- For EACH test candle, decide: SHORT, HOLD, CLOSE, REDUCE, or INCREASE_SHORT.
- You start FLAT (no position). Track your position state mentally.
- Respond with ONLY a JSON array of decisions. One per candle."""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            print(f"  [warn] claude CLI failed (rc={result.returncode}), falling back to rules")
            if result.stderr:
                print(f"  [stderr] {result.stderr[:200]}")
            return rule_based_strategy(test_candles_raw or [])

        text = result.stdout.strip()

        # Extract JSON from possible markdown fences
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        # Try to find JSON array in the output
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start : end + 1]

        decisions = json.loads(text)
        if isinstance(decisions, list):
            return decisions
    except subprocess.TimeoutExpired:
        print("  [warn] claude CLI timed out (300s), falling back to rules")
        return rule_based_strategy(test_candles_raw or [])
    except Exception as e:
        print(f"  [warn] Claude failed ({e}), falling back to rules")
        return rule_based_strategy(test_candles_raw or [])

    return rule_based_strategy(test_candles_raw or [])


def simulate_pnl(decisions: list, test_candles: list) -> dict:
    """
    Simulate trading PnL based on agent decisions and actual price movements.

    Rules:
    - Start with 1.0 BTC equity
    - SHORT: open short at candle close price, size = position_size_pct% of equity
    - HOLD: do nothing
    - CLOSE: close all positions at candle close price
    - REDUCE: close half the position
    - INCREASE_SHORT: add to short position
    - PnL is calculated as: size_btc * (entry_price - current_price) / current_price (inverse perp)
    """
    equity = 1.0  # Starting equity in BTC
    position_size_usd = 0.0  # Negative = short
    entry_price = 0.0
    total_realized_pnl = 0.0
    trades = []
    equity_curve = [{"candle_idx": -1, "equity": equity, "timestamp": "start"}]

    decision_map = {d.get("candle_index", d.get("candle_idx", i)): d for i, d in enumerate(decisions)}

    for i, candle in enumerate(test_candles):
        price = candle["close"]
        if not price:
            continue

        decision = decision_map.get(i, {"action": "HOLD", "position_size_pct": 0})
        action = decision.get("action", "HOLD")
        size_pct = decision.get("position_size_pct", 0)

        # Calculate unrealized PnL if we have a position
        unrealized_pnl = 0.0
        if position_size_usd != 0 and entry_price > 0:
            # For inverse perpetual: PnL = size_usd * (1/entry - 1/current)
            unrealized_pnl = abs(position_size_usd) * (1 / entry_price - 1 / price)
            if position_size_usd < 0:  # Short
                unrealized_pnl = -unrealized_pnl

        if action == "SHORT" and position_size_usd == 0:
            # Open new short
            notional = equity * price * (size_pct / 100)
            position_size_usd = -notional
            entry_price = price
            trades.append({
                "candle_idx": i,
                "action": "SHORT",
                "price": price,
                "size_usd": notional,
                "timestamp": candle["timestamp"],
            })

        elif action == "INCREASE_SHORT" and position_size_usd <= 0:
            # Add to short
            notional = equity * price * (size_pct / 100)
            if position_size_usd == 0:
                entry_price = price
            else:
                # Weighted average entry
                total_size = abs(position_size_usd) + notional
                entry_price = (abs(position_size_usd) * entry_price + notional * price) / total_size
            position_size_usd -= notional
            trades.append({
                "candle_idx": i,
                "action": "INCREASE_SHORT",
                "price": price,
                "size_usd": notional,
                "timestamp": candle["timestamp"],
            })

        elif action == "CLOSE" and position_size_usd != 0:
            # Close position
            pnl = abs(position_size_usd) * (1 / entry_price - 1 / price)
            if position_size_usd < 0:
                pnl = -pnl
            total_realized_pnl += pnl
            equity += pnl
            trades.append({
                "candle_idx": i,
                "action": "CLOSE",
                "price": price,
                "pnl_btc": pnl,
                "timestamp": candle["timestamp"],
            })
            position_size_usd = 0
            entry_price = 0

        elif action == "REDUCE" and position_size_usd != 0:
            # Close half
            half = position_size_usd / 2
            pnl = abs(half) * (1 / entry_price - 1 / price)
            if position_size_usd < 0:
                pnl = -pnl
            total_realized_pnl += pnl
            equity += pnl
            position_size_usd -= half
            trades.append({
                "candle_idx": i,
                "action": "REDUCE",
                "price": price,
                "pnl_btc": pnl,
                "timestamp": candle["timestamp"],
            })

        # Update equity curve
        current_equity = equity + unrealized_pnl
        equity_curve.append({
            "candle_idx": i,
            "equity": current_equity,
            "timestamp": candle["timestamp"],
            "price": price,
            "action": action,
        })

    # Final: close any open position at last price
    if position_size_usd != 0 and test_candles:
        final_price = test_candles[-1]["close"]
        pnl = abs(position_size_usd) * (1 / entry_price - 1 / final_price)
        if position_size_usd < 0:
            pnl = -pnl
        total_realized_pnl += pnl
        equity += pnl
        trades.append({
            "candle_idx": len(test_candles) - 1,
            "action": "FINAL_CLOSE",
            "price": final_price,
            "pnl_btc": pnl,
        })

    # Compute metrics
    start_price = test_candles[0]["close"] if test_candles else 0
    end_price = test_candles[-1]["close"] if test_candles else 0
    btc_return = (end_price / start_price - 1) * 100 if start_price else 0
    agent_return = (equity - 1.0) * 100

    return {
        "starting_equity": 1.0,
        "final_equity": equity,
        "total_realized_pnl": total_realized_pnl,
        "agent_return_pct": round(agent_return, 4),
        "btc_return_pct": round(btc_return, 4),
        "alpha_pct": round(agent_return - btc_return, 4),  # agent vs buy-and-hold
        "num_trades": len(trades),
        "trades": trades,
        "equity_curve": equity_curve,
        "test_period": {
            "start": test_candles[0]["timestamp"] if test_candles else "",
            "end": test_candles[-1]["timestamp"] if test_candles else "",
        },
        "price": {
            "start": start_price,
            "end": end_price,
        },
    }


def run_backtest(
    dataset_path: Optional[str] = None,
    train_days: int = 25,
    test_days: int = 5,
    stride_hours: int = 48,
    max_folds: Optional[int] = None,
) -> dict:
    """
    Run the full backtest with sliding-window cross-validation.

    Returns aggregated results across all folds.
    """
    dataset = load_dataset(dataset_path)
    candles = dataset["candles"]
    windows = create_sliding_windows(candles, train_days, test_days, stride_hours)

    if max_folds:
        windows = windows[:max_folds]

    print(f"\n{'='*60}")
    print(f"  BACKTEST: {len(windows)} folds, {train_days}d train / {test_days}d test")
    print(f"  Dataset: {dataset['summary']['date_range']['start'][:10]} → {dataset['summary']['date_range']['end'][:10]}")
    print(f"  BTC period return: {dataset['summary']['period_return_pct']:+.2f}%")
    print(f"{'='*60}")

    results = []

    for w in windows:
        fold_id = w["fold_id"]
        print(f"\n--- Fold {fold_id + 1}/{len(windows)} ---")
        print(f"  Train: {w['train_period']['start'][:10]} → {w['train_period']['end'][:10]}")
        print(f"  Test:  {w['test_period']['start'][:10]} → {w['test_period']['end'][:10]}")

        # Summarize training data
        train_summary = summarize_train_window(w["train_candles"])

        # Format test candles (without labels)
        test_str = format_test_candles(w["test_candles"])

        # Query agent
        print("  Querying Claude...")
        decisions = query_agent(train_summary, test_str, w["test_candles"])
        print(f"  Got {len(decisions)} decisions")

        # Simulate PnL
        pnl_result = simulate_pnl(decisions, w["test_candles"])

        fold_result = {
            "fold_id": fold_id,
            "train_period": w["train_period"],
            "test_period": w["test_period"],
            "decisions": decisions,
            "pnl": pnl_result,
        }

        results.append(fold_result)

        print(f"  Agent return: {pnl_result['agent_return_pct']:+.4f}%")
        print(f"  BTC return:   {pnl_result['btc_return_pct']:+.4f}%")
        print(f"  Alpha:        {pnl_result['alpha_pct']:+.4f}%")
        print(f"  Trades:       {pnl_result['num_trades']}")

        time.sleep(1)  # Rate limit courtesy

    # Aggregate
    agent_returns = [r["pnl"]["agent_return_pct"] for r in results]
    btc_returns = [r["pnl"]["btc_return_pct"] for r in results]
    alphas = [r["pnl"]["alpha_pct"] for r in results]
    trade_counts = [r["pnl"]["num_trades"] for r in results]

    winning_folds = sum(1 for a in agent_returns if a > 0)
    alpha_positive_folds = sum(1 for a in alphas if a > 0)

    aggregate = {
        "total_folds": len(results),
        "winning_folds": winning_folds,
        "win_rate_pct": round(winning_folds / len(results) * 100, 1) if results else 0,
        "alpha_positive_folds": alpha_positive_folds,
        "alpha_positive_rate_pct": round(alpha_positive_folds / len(results) * 100, 1) if results else 0,
        "avg_agent_return_pct": round(sum(agent_returns) / len(agent_returns), 4) if agent_returns else 0,
        "avg_btc_return_pct": round(sum(btc_returns) / len(btc_returns), 4) if btc_returns else 0,
        "avg_alpha_pct": round(sum(alphas) / len(alphas), 4) if alphas else 0,
        "max_agent_return_pct": round(max(agent_returns), 4) if agent_returns else 0,
        "min_agent_return_pct": round(min(agent_returns), 4) if agent_returns else 0,
        "avg_trades_per_fold": round(sum(trade_counts) / len(trade_counts), 1) if trade_counts else 0,
        "total_trades": sum(trade_counts),
    }

    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Folds:          {aggregate['total_folds']}")
    print(f"  Win rate:       {aggregate['win_rate_pct']}% ({aggregate['winning_folds']}/{aggregate['total_folds']})")
    print(f"  Alpha+ rate:    {aggregate['alpha_positive_rate_pct']}% ({aggregate['alpha_positive_folds']}/{aggregate['total_folds']})")
    print(f"  Avg agent ret:  {aggregate['avg_agent_return_pct']:+.4f}%")
    print(f"  Avg BTC ret:    {aggregate['avg_btc_return_pct']:+.4f}%")
    print(f"  Avg alpha:      {aggregate['avg_alpha_pct']:+.4f}%")
    print(f"  Total trades:   {aggregate['total_trades']}")

    return {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "train_days": train_days,
            "test_days": test_days,
            "stride_hours": stride_hours,
            "dataset": dataset.get("metadata", {}),
        },
        "aggregate": aggregate,
        "folds": results,
    }
