"""Generate Wall Street Journal-styled HTML reports from trading data."""

import os
import json
from datetime import datetime, timezone
from typing import Optional

from jinja2 import Template

from .config import Config
from .database import (
    get_db,
    get_recent_insights,
    get_recent_trades,
    get_recent_snapshots,
    get_latest_position,
    get_latest_account,
)

WSJ_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BearDAO Trading Report — {{ report_date }}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap');

        :root {
            --wsj-black: #111111;
            --wsj-dark: #222222;
            --wsj-gray: #666666;
            --wsj-light-gray: #999999;
            --wsj-border: #cccccc;
            --wsj-bg: #faf9f6;
            --wsj-white: #ffffff;
            --wsj-red: #b91c1c;
            --wsj-green: #15803d;
            --wsj-blue: #1e40af;
            --wsj-gold: #b8860b;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Source Serif 4', 'Georgia', serif;
            background: var(--wsj-bg);
            color: var(--wsj-black);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }

        /* Header */
        .masthead {
            text-align: center;
            padding: 32px 20px 20px;
            border-bottom: 3px double var(--wsj-black);
            background: var(--wsj-white);
        }
        .masthead-title {
            font-family: 'Playfair Display', serif;
            font-weight: 900;
            font-size: 42px;
            letter-spacing: -0.5px;
            color: var(--wsj-black);
        }
        .masthead-subtitle {
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 3px;
            color: var(--wsj-light-gray);
            margin-top: 6px;
        }
        .masthead-date {
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            color: var(--wsj-gray);
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid var(--wsj-border);
            display: inline-block;
        }

        /* Ticker bar */
        .ticker-bar {
            background: var(--wsj-black);
            color: var(--wsj-white);
            padding: 10px 20px;
            display: flex;
            justify-content: center;
            gap: 40px;
            flex-wrap: wrap;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
        }
        .ticker-item { display: flex; align-items: center; gap: 8px; }
        .ticker-label { color: #aaa; font-weight: 500; }
        .ticker-value { font-weight: 600; }
        .ticker-up { color: #4ade80; }
        .ticker-down { color: #f87171; }

        /* Main content */
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 0 20px;
        }

        /* Lead story */
        .lead-story {
            padding: 40px 0 30px;
            border-bottom: 1px solid var(--wsj-border);
        }
        .lead-headline {
            font-family: 'Playfair Display', serif;
            font-size: 34px;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 10px;
        }
        .lead-deck {
            font-size: 19px;
            color: var(--wsj-gray);
            line-height: 1.5;
            margin-bottom: 16px;
            font-style: italic;
        }
        .lead-body {
            font-size: 17px;
            line-height: 1.8;
            column-count: 2;
            column-gap: 40px;
            column-rule: 1px solid var(--wsj-border);
        }
        .lead-body p { margin-bottom: 14px; text-align: justify; }

        @media (max-width: 700px) {
            .lead-body { column-count: 1; }
            .lead-headline { font-size: 26px; }
        }

        /* Section headers */
        .section-header {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--wsj-light-gray);
            padding: 24px 0 8px;
            border-bottom: 2px solid var(--wsj-black);
            margin-bottom: 20px;
        }

        /* Signal card */
        .signal-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .signal-card {
            background: var(--wsj-white);
            border: 1px solid var(--wsj-border);
            padding: 16px;
            text-align: center;
        }
        .signal-card-label {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--wsj-light-gray);
            margin-bottom: 6px;
        }
        .signal-card-value {
            font-family: 'Playfair Display', serif;
            font-size: 28px;
            font-weight: 700;
        }
        .signal-card-sub {
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            color: var(--wsj-gray);
            margin-top: 4px;
        }

        /* Sentiment gauge */
        .sentiment-gauge {
            background: var(--wsj-white);
            border: 1px solid var(--wsj-border);
            padding: 24px;
            margin-bottom: 30px;
            text-align: center;
        }
        .sentiment-label {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--wsj-light-gray);
        }
        .sentiment-value {
            font-family: 'Playfair Display', serif;
            font-size: 48px;
            font-weight: 900;
            margin: 8px 0;
        }
        .sentiment-EXTREME_BEAR, .sentiment-BEAR { color: var(--wsj-red); }
        .sentiment-NEUTRAL { color: var(--wsj-gray); }
        .sentiment-BULL, .sentiment-EXTREME_BULL { color: var(--wsj-green); }
        .sentiment-bar {
            height: 8px;
            background: linear-gradient(to right, var(--wsj-red), #eee, var(--wsj-green));
            border-radius: 4px;
            position: relative;
            margin: 12px auto;
            max-width: 400px;
        }
        .sentiment-marker {
            width: 16px; height: 16px;
            background: var(--wsj-black);
            border-radius: 50%;
            position: absolute;
            top: -4px;
            transform: translateX(-50%);
        }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            font-family: 'Inter', sans-serif;
            font-size: 14px;
        }
        th {
            text-align: left;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--wsj-light-gray);
            padding: 8px 12px;
            border-bottom: 2px solid var(--wsj-black);
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }
        tr:hover td { background: #f5f5f0; }
        .num { text-align: right; font-variant-numeric: tabular-nums; }
        .positive { color: var(--wsj-green); }
        .negative { color: var(--wsj-red); }

        /* Position box */
        .position-box {
            background: var(--wsj-white);
            border: 2px solid var(--wsj-black);
            padding: 24px;
            margin-bottom: 30px;
        }
        .position-header {
            font-family: 'Playfair Display', serif;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 16px;
        }
        .position-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
        }
        .position-stat-label {
            font-family: 'Inter', sans-serif;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--wsj-light-gray);
        }
        .position-stat-value {
            font-size: 18px;
            font-weight: 600;
            font-family: 'Inter', sans-serif;
        }

        /* Insights timeline */
        .timeline { margin-bottom: 30px; }
        .timeline-item {
            border-left: 3px solid var(--wsj-border);
            padding: 0 0 24px 20px;
            position: relative;
        }
        .timeline-item:last-child { border-left-color: transparent; }
        .timeline-item::before {
            content: '';
            width: 11px; height: 11px;
            background: var(--wsj-black);
            border-radius: 50%;
            position: absolute;
            left: -7px; top: 4px;
        }
        .timeline-time {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            color: var(--wsj-light-gray);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .timeline-action {
            font-family: 'Inter', sans-serif;
            font-size: 14px;
            font-weight: 600;
            margin: 4px 0;
        }
        .timeline-analysis {
            font-size: 15px;
            color: var(--wsj-dark);
            line-height: 1.6;
        }

        /* Footer */
        .footer {
            text-align: center;
            padding: 30px 20px;
            border-top: 3px double var(--wsj-black);
            margin-top: 40px;
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            color: var(--wsj-light-gray);
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        /* Risk warning */
        .risk-warning {
            background: #fff5f5;
            border: 1px solid #fecaca;
            padding: 16px;
            margin: 20px 0;
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            color: var(--wsj-red);
            text-align: center;
        }
    </style>
</head>
<body>

    <header class="masthead">
        <div class="masthead-title">The Bear Report</div>
        <div class="masthead-subtitle">Inverse MicroStrategy — AI-Powered BTC Short Desk</div>
        <div class="masthead-date">{{ report_date }} &bull; {{ report_time }} UTC &bull; {{ mode }}</div>
    </header>

    <!-- Ticker bar -->
    <div class="ticker-bar">
        {% if snapshot.btc_price %}
        <div class="ticker-item">
            <span class="ticker-label">BTC</span>
            <span class="ticker-value">${{ "{:,.0f}".format(snapshot.btc_price) }}</span>
            {% if snapshot.btc_24h_change %}
            <span class="{{ 'ticker-up' if snapshot.btc_24h_change > 0 else 'ticker-down' }}">
                {{ "{:+.1f}".format(snapshot.btc_24h_change) }}%
            </span>
            {% endif %}
        </div>
        {% endif %}
        {% if snapshot.eth_price %}
        <div class="ticker-item">
            <span class="ticker-label">ETH</span>
            <span class="ticker-value">${{ "{:,.0f}".format(snapshot.eth_price) }}</span>
        </div>
        {% endif %}
        {% if snapshot.gold_price %}
        <div class="ticker-item">
            <span class="ticker-label">GOLD</span>
            <span class="ticker-value">${{ "{:,.0f}".format(snapshot.gold_price) }}</span>
        </div>
        {% endif %}
        {% if snapshot.fear_greed_index %}
        <div class="ticker-item">
            <span class="ticker-label">F&G</span>
            <span class="ticker-value {{ 'ticker-down' if snapshot.fear_greed_index < 40 else 'ticker-up' if snapshot.fear_greed_index > 60 else '' }}">
                {{ snapshot.fear_greed_index }}
            </span>
        </div>
        {% endif %}
        {% if snapshot.funding_rate is not none %}
        <div class="ticker-item">
            <span class="ticker-label">FUNDING</span>
            <span class="ticker-value">{{ snapshot.funding_rate }}</span>
        </div>
        {% endif %}
    </div>

    <div class="container">

        <!-- Lead Story: Latest Insight -->
        {% if latest_insight %}
        <article class="lead-story">
            <h1 class="lead-headline">
                {% if latest_insight.recommended_action == 'SHORT' %}Agent Opens Short Position as Bear Signals Intensify
                {% elif latest_insight.recommended_action == 'INCREASE_SHORT' %}Agent Increases Bearish Exposure on Deteriorating Outlook
                {% elif latest_insight.recommended_action == 'CLOSE' %}Agent Closes Position, Locks In {{ 'Gains' if latest_insight.sentiment in ['BEAR', 'EXTREME_BEAR'] else 'Losses' }}
                {% elif latest_insight.recommended_action == 'REDUCE' %}Agent Reduces Position Size Amid Mixed Signals
                {% else %}Agent Holds Steady, Awaits Clearer Entry Point
                {% endif %}
            </h1>
            <p class="lead-deck">{{ latest_insight.analysis }}</p>
            <div class="lead-body">
                <p>{{ latest_insight.reasoning }}</p>
                <p>The agent's conviction level stands at {{ "{:.0%}".format(latest_insight.confidence or 0) }},
                   with an overall market sentiment reading of <strong>{{ latest_insight.sentiment }}</strong>.
                   {% if latest_insight.position_size_pct and latest_insight.position_size_pct > 0 %}
                   The recommended position allocation is {{ latest_insight.position_size_pct }}% of available margin.
                   {% endif %}
                </p>
                {% if latest_insight.signals_used %}
                <p>Key signals driving this decision: {{ latest_insight.signals_used }}.</p>
                {% endif %}
            </div>
        </article>
        {% endif %}

        <!-- Signal Dashboard -->
        <div class="section-header">Market Signals</div>
        <div class="signal-grid">
            {% if snapshot.btc_price %}
            <div class="signal-card">
                <div class="signal-card-label">Bitcoin</div>
                <div class="signal-card-value">${{ "{:,.0f}".format(snapshot.btc_price) }}</div>
                <div class="signal-card-sub {{ 'positive' if (snapshot.btc_24h_change or 0) > 0 else 'negative' }}">
                    {{ "{:+.2f}".format(snapshot.btc_24h_change or 0) }}% 24h
                </div>
            </div>
            {% endif %}
            {% if snapshot.rsi_14 %}
            <div class="signal-card">
                <div class="signal-card-label">RSI (14)</div>
                <div class="signal-card-value {{ 'negative' if snapshot.rsi_14 > 70 else 'positive' if snapshot.rsi_14 < 30 else '' }}">
                    {{ "{:.1f}".format(snapshot.rsi_14) }}
                </div>
                <div class="signal-card-sub">
                    {{ 'Overbought' if snapshot.rsi_14 > 70 else 'Oversold' if snapshot.rsi_14 < 30 else 'Neutral' }}
                </div>
            </div>
            {% endif %}
            {% if snapshot.fear_greed_index %}
            <div class="signal-card">
                <div class="signal-card-label">Fear & Greed</div>
                <div class="signal-card-value {{ 'positive' if snapshot.fear_greed_index < 30 else 'negative' if snapshot.fear_greed_index > 70 else '' }}">
                    {{ snapshot.fear_greed_index }}
                </div>
                <div class="signal-card-sub">{{ snapshot.fear_greed_label }}</div>
            </div>
            {% endif %}
            {% if snapshot.deribit_volatility %}
            <div class="signal-card">
                <div class="signal-card-label">BTC Volatility</div>
                <div class="signal-card-value">{{ "{:.1f}".format(snapshot.deribit_volatility) }}%</div>
                <div class="signal-card-sub">Historical</div>
            </div>
            {% endif %}
        </div>

        <!-- Agent Sentiment -->
        {% if latest_insight %}
        <div class="sentiment-gauge">
            <div class="sentiment-label">Agent Sentiment</div>
            <div class="sentiment-value sentiment-{{ latest_insight.sentiment }}">
                {{ latest_insight.sentiment | replace('_', ' ') }}
            </div>
            <div class="sentiment-bar">
                {% set positions = {'EXTREME_BEAR': 5, 'BEAR': 25, 'NEUTRAL': 50, 'BULL': 75, 'EXTREME_BULL': 95} %}
                <div class="sentiment-marker" style="left: {{ positions.get(latest_insight.sentiment, 50) }}%;"></div>
            </div>
            <div class="signal-card-sub">
                Confidence: {{ "{:.0%}".format(latest_insight.confidence or 0) }} &bull;
                Action: {{ latest_insight.recommended_action }}
            </div>
        </div>
        {% endif %}

        <!-- Current Position -->
        {% if position and position.size and position.size != 0 %}
        <div class="section-header">Open Position</div>
        <div class="position-box">
            <div class="position-header">{{ position.instrument }} — {{ position.direction | upper }}</div>
            <div class="position-grid">
                <div>
                    <div class="position-stat-label">Size</div>
                    <div class="position-stat-value">{{ "{:,.0f}".format(position.size) }} USD</div>
                </div>
                <div>
                    <div class="position-stat-label">Entry Price</div>
                    <div class="position-stat-value">${{ "{:,.2f}".format(position.avg_entry_price or 0) }}</div>
                </div>
                <div>
                    <div class="position-stat-label">Mark Price</div>
                    <div class="position-stat-value">${{ "{:,.2f}".format(position.mark_price or 0) }}</div>
                </div>
                <div>
                    <div class="position-stat-label">Unrealized P&L</div>
                    <div class="position-stat-value {{ 'positive' if (position.unrealized_pnl or 0) > 0 else 'negative' }}">
                        {{ "{:+.6f}".format(position.unrealized_pnl or 0) }} BTC
                    </div>
                </div>
                <div>
                    <div class="position-stat-label">Liquidation</div>
                    <div class="position-stat-value">${{ "{:,.0f}".format(position.liquidation_price or 0) }}</div>
                </div>
            </div>
        </div>
        {% endif %}

        <!-- Account Summary -->
        {% if account and account.equity %}
        <div class="section-header">Account Summary</div>
        <div class="signal-grid">
            <div class="signal-card">
                <div class="signal-card-label">Equity</div>
                <div class="signal-card-value">{{ "{:.6f}".format(account.equity) }}</div>
                <div class="signal-card-sub">BTC</div>
            </div>
            <div class="signal-card">
                <div class="signal-card-label">Balance</div>
                <div class="signal-card-value">{{ "{:.6f}".format(account.balance or 0) }}</div>
                <div class="signal-card-sub">BTC</div>
            </div>
            <div class="signal-card">
                <div class="signal-card-label">Available Margin</div>
                <div class="signal-card-value">{{ "{:.6f}".format(account.available_margin or 0) }}</div>
                <div class="signal-card-sub">BTC</div>
            </div>
            <div class="signal-card">
                <div class="signal-card-label">Total P&L</div>
                <div class="signal-card-value {{ 'positive' if (account.total_pnl or 0) > 0 else 'negative' }}">
                    {{ "{:+.6f}".format(account.total_pnl or 0) }}
                </div>
                <div class="signal-card-sub">BTC</div>
            </div>
        </div>
        {% endif %}

        <!-- Recent Agent Decisions -->
        {% if insights %}
        <div class="section-header">Agent Decision Log</div>
        <div class="timeline">
            {% for ins in insights[:8] %}
            <div class="timeline-item">
                <div class="timeline-time">{{ ins.ts }}</div>
                <div class="timeline-action">
                    {{ ins.recommended_action }}
                    <span style="color: var(--wsj-light-gray); font-weight: 400;">
                        — {{ ins.sentiment }} ({{ "{:.0%}".format(ins.confidence or 0) }})
                    </span>
                </div>
                <div class="timeline-analysis">{{ ins.analysis }}</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <!-- Trade History -->
        {% if trades %}
        <div class="section-header">Trade History</div>
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Instrument</th>
                    <th>Side</th>
                    <th class="num">Amount</th>
                    <th>Status</th>
                    <th>Notes</th>
                </tr>
            </thead>
            <tbody>
                {% for t in trades[:15] %}
                <tr>
                    <td>{{ t.ts }}</td>
                    <td>{{ t.instrument }}</td>
                    <td class="{{ 'negative' if t.direction == 'sell' else 'positive' }}">
                        {{ t.direction | upper }}
                    </td>
                    <td class="num">{{ "{:,.0f}".format(t.amount) }} USD</td>
                    <td>{{ t.status }}</td>
                    <td style="max-width: 200px; font-size: 12px;">{{ (t.notes or '')[:60] }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}

        <!-- Macro Indicators -->
        {% if snapshot.gold_price or snapshot.treasury_10y or snapshot.dxy_value %}
        <div class="section-header">Macro Environment</div>
        <div class="signal-grid">
            {% if snapshot.gold_price %}
            <div class="signal-card">
                <div class="signal-card-label">Gold (XAU)</div>
                <div class="signal-card-value" style="color: var(--wsj-gold);">${{ "{:,.0f}".format(snapshot.gold_price) }}</div>
            </div>
            {% endif %}
            {% if snapshot.treasury_10y %}
            <div class="signal-card">
                <div class="signal-card-label">10Y Treasury</div>
                <div class="signal-card-value">{{ "{:.2f}".format(snapshot.treasury_10y) }}%</div>
            </div>
            {% endif %}
            {% if snapshot.dxy_value %}
            <div class="signal-card">
                <div class="signal-card-label">Dollar Index</div>
                <div class="signal-card-value">{{ "{:.2f}".format(snapshot.dxy_value) }}</div>
            </div>
            {% endif %}
            {% if snapshot.fed_rate %}
            <div class="signal-card">
                <div class="signal-card-label">Fed Funds Rate</div>
                <div class="signal-card-value">{{ "{:.2f}".format(snapshot.fed_rate) }}%</div>
            </div>
            {% endif %}
            {% if snapshot.vix %}
            <div class="signal-card">
                <div class="signal-card-label">VIX</div>
                <div class="signal-card-value">{{ "{:.1f}".format(snapshot.vix) }}</div>
            </div>
            {% endif %}
        </div>
        {% endif %}

        <div class="risk-warning">
            This report is generated by an AI trading agent for informational purposes only.
            It reflects a deliberately bearish bias on Bitcoin. This is NOT financial advice.
            Trading derivatives involves substantial risk of loss. Past performance does not guarantee future results.
        </div>

    </div>

    <footer class="footer">
        The Bear Report &bull; Powered by Claude &bull; Deribit {{ mode }} &bull; Generated {{ report_time }} UTC
    </footer>

</body>
</html>"""


def generate_report(cycle_result: Optional[dict] = None) -> str:
    """Generate an HTML report and return the file path."""
    conn = get_db()
    now = datetime.now(timezone.utc)

    # Gather data
    insights = get_recent_insights(conn, limit=10)
    trades = get_recent_trades(conn, limit=15)
    snapshots = get_recent_snapshots(conn, limit=1)
    position = get_latest_position(conn)
    account = get_latest_account(conn)

    # Use cycle result if available, else latest from DB
    if cycle_result:
        snapshot = cycle_result.get("snapshot", {})
        latest_insight = cycle_result.get("insight", {})
        if cycle_result.get("position"):
            position = cycle_result["position"]
        if cycle_result.get("account"):
            account = cycle_result["account"]
    else:
        snapshot = snapshots[0] if snapshots else {}
        # Parse raw_data if available
        if snapshot.get("raw_data"):
            try:
                snapshot = json.loads(snapshot["raw_data"])
            except (json.JSONDecodeError, TypeError):
                pass
        latest_insight = insights[0] if insights else {}

    # Parse signals_used from JSON string if needed
    if latest_insight.get("signals_used") and isinstance(latest_insight["signals_used"], str):
        try:
            latest_insight["signals_used"] = ", ".join(json.loads(latest_insight["signals_used"]))
        except (json.JSONDecodeError, TypeError):
            pass

    template = Template(WSJ_TEMPLATE)
    html = template.render(
        report_date=now.strftime("%B %d, %Y"),
        report_time=now.strftime("%H:%M"),
        mode="LIVE" if Config.DERIBIT_LIVE else "TESTNET",
        snapshot=snapshot,
        latest_insight=latest_insight,
        insights=insights,
        trades=trades,
        position=position,
        account=account,
    )

    os.makedirs(Config.REPORTS_DIR, exist_ok=True)
    filename = f"bear-report-{now.strftime('%Y%m%d-%H%M%S')}.html"
    filepath = os.path.join(Config.REPORTS_DIR, filename)

    with open(filepath, "w") as f:
        f.write(html)

    # Also write a "latest" symlink / copy
    latest_path = os.path.join(Config.REPORTS_DIR, "latest.html")
    with open(latest_path, "w") as f:
        f.write(html)

    return filepath
