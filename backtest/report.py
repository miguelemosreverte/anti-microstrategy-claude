"""Generate WSJ-styled HTML backtest report."""

import json
import os
from datetime import datetime, timezone

from jinja2 import Template

BACKTEST_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report — {{ report_date }}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap');
        :root {
            --wsj-black: #111; --wsj-dark: #222; --wsj-gray: #666;
            --wsj-light-gray: #999; --wsj-border: #ccc; --wsj-bg: #faf9f6;
            --wsj-white: #fff; --wsj-red: #b91c1c; --wsj-green: #15803d;
            --wsj-blue: #1e40af; --wsj-gold: #b8860b;
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Source Serif 4',Georgia,serif; background:var(--wsj-bg); color:var(--wsj-black); line-height:1.6; -webkit-font-smoothing:antialiased; }
        .masthead { text-align:center; padding:32px 20px 20px; border-bottom:3px double var(--wsj-black); background:var(--wsj-white); }
        .masthead-title { font-family:'Playfair Display',serif; font-weight:900; font-size:38px; letter-spacing:-0.5px; }
        .masthead-subtitle { font-family:'Inter',sans-serif; font-size:12px; text-transform:uppercase; letter-spacing:3px; color:var(--wsj-light-gray); margin-top:6px; }
        .masthead-date { font-family:'Inter',sans-serif; font-size:13px; color:var(--wsj-gray); margin-top:10px; padding-top:10px; border-top:1px solid var(--wsj-border); display:inline-block; }
        .container { max-width:960px; margin:0 auto; padding:0 20px; }
        .section-header { font-family:'Inter',sans-serif; font-size:11px; text-transform:uppercase; letter-spacing:2px; color:var(--wsj-light-gray); padding:24px 0 8px; border-bottom:2px solid var(--wsj-black); margin-bottom:20px; }

        /* Hero metric */
        .hero { text-align:center; padding:40px 0 30px; border-bottom:1px solid var(--wsj-border); }
        .hero-label { font-family:'Inter',sans-serif; font-size:11px; text-transform:uppercase; letter-spacing:2px; color:var(--wsj-light-gray); }
        .hero-value { font-family:'Playfair Display',serif; font-size:64px; font-weight:900; margin:8px 0; }
        .hero-sub { font-family:'Inter',sans-serif; font-size:15px; color:var(--wsj-gray); }

        .signal-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:30px; }
        .signal-card { background:var(--wsj-white); border:1px solid var(--wsj-border); padding:16px; text-align:center; }
        .signal-card-label { font-family:'Inter',sans-serif; font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--wsj-light-gray); margin-bottom:6px; }
        .signal-card-value { font-family:'Playfair Display',serif; font-size:28px; font-weight:700; }
        .signal-card-sub { font-family:'Inter',sans-serif; font-size:12px; color:var(--wsj-gray); margin-top:4px; }
        .positive { color:var(--wsj-green); }
        .negative { color:var(--wsj-red); }

        /* Fold table */
        table { width:100%; border-collapse:collapse; margin-bottom:30px; font-family:'Inter',sans-serif; font-size:14px; }
        th { text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--wsj-light-gray); padding:8px 12px; border-bottom:2px solid var(--wsj-black); }
        td { padding:10px 12px; border-bottom:1px solid #eee; }
        tr:hover td { background:#f5f5f0; }
        .num { text-align:right; font-variant-numeric:tabular-nums; }

        /* Equity chart (ASCII) */
        .chart-container { background:var(--wsj-white); border:1px solid var(--wsj-border); padding:20px; margin-bottom:30px; font-family:'Inter',monospace; font-size:12px; line-height:1.4; white-space:pre; overflow-x:auto; }

        /* Progress bar */
        .progress-bar { height:24px; background:#eee; border-radius:4px; overflow:hidden; margin:8px 0; }
        .progress-fill { height:100%; border-radius:4px; display:flex; align-items:center; justify-content:center; color:white; font-family:'Inter',sans-serif; font-size:11px; font-weight:600; }

        .footer { text-align:center; padding:30px 20px; border-top:3px double var(--wsj-black); margin-top:40px; font-family:'Inter',sans-serif; font-size:11px; color:var(--wsj-light-gray); text-transform:uppercase; letter-spacing:2px; }
        .risk-warning { background:#fff5f5; border:1px solid #fecaca; padding:16px; margin:20px 0; font-family:'Inter',sans-serif; font-size:12px; color:var(--wsj-red); text-align:center; }

        /* Fold detail */
        .fold-detail { background:var(--wsj-white); border:1px solid var(--wsj-border); padding:20px; margin-bottom:16px; }
        .fold-header { font-family:'Playfair Display',serif; font-size:18px; font-weight:700; margin-bottom:8px; }
        .fold-meta { font-family:'Inter',sans-serif; font-size:12px; color:var(--wsj-gray); margin-bottom:12px; }
        .fold-trades { font-family:'Inter',sans-serif; font-size:13px; }
        .fold-trades .trade { padding:4px 0; border-bottom:1px solid #f0f0f0; }
    </style>
</head>
<body>
<header class="masthead">
    <div class="masthead-title">Backtest Report</div>
    <div class="masthead-subtitle">Anti-MicroStrategy — Sliding Window Cross-Validation</div>
    <div class="masthead-date">{{ report_date }} &bull; {{ agg.total_folds }} folds &bull; {{ meta.train_days }}d train / {{ meta.test_days }}d test</div>
</header>

<div class="container">

    <!-- Hero: Average Alpha -->
    <div class="hero">
        <div class="hero-label">Average Alpha vs Buy-and-Hold</div>
        <div class="hero-value {{ 'positive' if agg.avg_alpha_pct > 0 else 'negative' }}">
            {{ "{:+.2f}".format(agg.avg_alpha_pct) }}%
        </div>
        <div class="hero-sub">
            Agent avg: {{ "{:+.2f}".format(agg.avg_agent_return_pct) }}% &bull;
            BTC avg: {{ "{:+.2f}".format(agg.avg_btc_return_pct) }}%
        </div>
    </div>

    <!-- Key Metrics -->
    <div class="section-header">Performance Summary</div>
    <div class="signal-grid">
        <div class="signal-card">
            <div class="signal-card-label">Win Rate</div>
            <div class="signal-card-value {{ 'positive' if agg.win_rate_pct >= 50 else 'negative' }}">
                {{ agg.win_rate_pct }}%
            </div>
            <div class="signal-card-sub">{{ agg.winning_folds }}/{{ agg.total_folds }} folds profitable</div>
        </div>
        <div class="signal-card">
            <div class="signal-card-label">Alpha+ Rate</div>
            <div class="signal-card-value {{ 'positive' if agg.alpha_positive_rate_pct >= 50 else 'negative' }}">
                {{ agg.alpha_positive_rate_pct }}%
            </div>
            <div class="signal-card-sub">{{ agg.alpha_positive_folds }}/{{ agg.total_folds }} beat BTC</div>
        </div>
        <div class="signal-card">
            <div class="signal-card-label">Best Fold</div>
            <div class="signal-card-value positive">{{ "{:+.2f}".format(agg.max_agent_return_pct) }}%</div>
        </div>
        <div class="signal-card">
            <div class="signal-card-label">Worst Fold</div>
            <div class="signal-card-value negative">{{ "{:+.2f}".format(agg.min_agent_return_pct) }}%</div>
        </div>
        <div class="signal-card">
            <div class="signal-card-label">Total Trades</div>
            <div class="signal-card-value">{{ agg.total_trades }}</div>
            <div class="signal-card-sub">{{ agg.avg_trades_per_fold }} avg/fold</div>
        </div>
    </div>

    <!-- Win Rate Progress Bar -->
    <div style="margin-bottom:30px;">
        <div style="font-family:'Inter',sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--wsj-light-gray);">
            Win Rate Distribution
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width:{{ agg.win_rate_pct }}%;background:{{ 'var(--wsj-green)' if agg.win_rate_pct >= 50 else 'var(--wsj-red)' }};">
                {{ agg.win_rate_pct }}% Wins
            </div>
        </div>
        <div style="font-family:'Inter',sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--wsj-light-gray);margin-top:8px;">
            Alpha Positive Rate
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width:{{ agg.alpha_positive_rate_pct }}%;background:{{ 'var(--wsj-blue)' if agg.alpha_positive_rate_pct >= 50 else 'var(--wsj-red)' }};">
                {{ agg.alpha_positive_rate_pct }}% Beat BTC
            </div>
        </div>
    </div>

    <!-- Fold Results Table -->
    <div class="section-header">Fold-by-Fold Results</div>
    <table>
        <thead>
            <tr>
                <th>Fold</th>
                <th>Test Period</th>
                <th class="num">Agent Return</th>
                <th class="num">BTC Return</th>
                <th class="num">Alpha</th>
                <th class="num">Trades</th>
                <th>Result</th>
            </tr>
        </thead>
        <tbody>
            {% for fold in folds %}
            <tr>
                <td>{{ fold.fold_id + 1 }}</td>
                <td style="font-size:12px;">{{ fold.test_period.start[:10] }} → {{ fold.test_period.end[:10] }}</td>
                <td class="num {{ 'positive' if fold.pnl.agent_return_pct > 0 else 'negative' }}">
                    {{ "{:+.3f}".format(fold.pnl.agent_return_pct) }}%
                </td>
                <td class="num {{ 'positive' if fold.pnl.btc_return_pct > 0 else 'negative' }}">
                    {{ "{:+.3f}".format(fold.pnl.btc_return_pct) }}%
                </td>
                <td class="num {{ 'positive' if fold.pnl.alpha_pct > 0 else 'negative' }}">
                    {{ "{:+.3f}".format(fold.pnl.alpha_pct) }}%
                </td>
                <td class="num">{{ fold.pnl.num_trades }}</td>
                <td>{{ "✓" if fold.pnl.agent_return_pct > 0 else "✗" }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- Fold Details -->
    <div class="section-header">Trade Details by Fold</div>
    {% for fold in folds %}
    <div class="fold-detail">
        <div class="fold-header">
            Fold {{ fold.fold_id + 1 }}:
            <span class="{{ 'positive' if fold.pnl.agent_return_pct > 0 else 'negative' }}">
                {{ "{:+.3f}".format(fold.pnl.agent_return_pct) }}%
            </span>
        </div>
        <div class="fold-meta">
            Test: {{ fold.test_period.start[:16] }} → {{ fold.test_period.end[:16] }}
            &bull; BTC: ${{ "{:,.0f}".format(fold.pnl.price.start) }} → ${{ "{:,.0f}".format(fold.pnl.price.end) }}
            ({{ "{:+.2f}".format(fold.pnl.btc_return_pct) }}%)
        </div>
        <div class="fold-trades">
            {% for trade in fold.pnl.trades %}
            <div class="trade">
                <strong>{{ trade.action }}</strong> @ ${{ "{:,.0f}".format(trade.price) }}
                {% if trade.pnl_btc is defined and trade.pnl_btc is not none %}
                — PnL: <span class="{{ 'positive' if trade.pnl_btc > 0 else 'negative' }}">{{ "{:+.6f}".format(trade.pnl_btc) }} BTC</span>
                {% endif %}
                {% if trade.size_usd is defined %}
                — Size: ${{ "{:,.0f}".format(trade.size_usd) }}
                {% endif %}
            </div>
            {% endfor %}
            {% if not fold.pnl.trades %}
            <div class="trade" style="color:var(--wsj-light-gray);">No trades executed (HOLD throughout)</div>
            {% endif %}
        </div>
    </div>
    {% endfor %}

    <div class="risk-warning">
        Backtested results do not guarantee future performance. This system has a deliberate bearish bias.
        Slippage, fees, and market impact are not fully modeled. Past alpha may not persist.
    </div>
</div>

<footer class="footer">
    Backtest Report &bull; Anti-MicroStrategy &bull; Generated {{ report_time }} UTC
</footer>
</body>
</html>"""


def generate_backtest_report(results: dict) -> str:
    """Generate WSJ-styled HTML backtest report."""
    now = datetime.now(timezone.utc)

    template = Template(BACKTEST_REPORT_TEMPLATE)
    html = template.render(
        report_date=now.strftime("%B %d, %Y"),
        report_time=now.strftime("%H:%M"),
        meta=results.get("metadata", {}),
        agg=results.get("aggregate", {}),
        folds=results.get("folds", []),
    )

    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(reports_dir, exist_ok=True)

    filename = f"backtest-{now.strftime('%Y%m%d-%H%M%S')}.html"
    filepath = os.path.join(reports_dir, filename)
    with open(filepath, "w") as f:
        f.write(html)

    latest = os.path.join(reports_dir, "backtest-latest.html")
    with open(latest, "w") as f:
        f.write(html)

    return filepath
