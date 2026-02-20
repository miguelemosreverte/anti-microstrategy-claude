"""Generate WSJ-styled HTML backtest report with dark/light mode, inline SVG charts, and rich analytics."""

import math
import os
from datetime import datetime, timezone

from jinja2 import Template

# ---------------------------------------------------------------------------
# Additional metric computation
# ---------------------------------------------------------------------------

def _max_drawdown_from_curve(equity_curve: list) -> float:
    """Compute max peak-to-trough drawdown (%) from an equity curve list."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].get("equity", 1.0)
    max_dd = 0.0
    for pt in equity_curve:
        eq = pt.get("equity", peak)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100 if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def _compute_extra_metrics(results: dict) -> dict:
    """Compute additional aggregate and per-fold metrics. Returns enriched copy."""
    folds = results.get("folds", [])
    agg = results.get("aggregate", {})
    meta = results.get("metadata", {})
    test_days = meta.get("test_days", 5)

    # --- Per-fold computed drawdown ---
    for fold in folds:
        curve = fold.get("pnl", {}).get("equity_curve", [])
        fold["computed_max_drawdown"] = _max_drawdown_from_curve(curve)

    # --- Aggregate max drawdown (worst across folds) ---
    fold_dds = [f["computed_max_drawdown"] for f in folds]
    agg["max_drawdown_pct"] = round(max(fold_dds), 4) if fold_dds else 0.0

    # --- Sharpe ratio (annualised from fold returns) ---
    agent_returns = [f["pnl"]["agent_return_pct"] for f in folds if f.get("pnl")]
    if len(agent_returns) >= 2:
        mean_r = sum(agent_returns) / len(agent_returns)
        var_r = sum((r - mean_r) ** 2 for r in agent_returns) / (len(agent_returns) - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0
        ann_factor = math.sqrt(365 / test_days) if test_days > 0 else 1.0
        agg["sharpe_ratio"] = round((mean_r / std_r) * ann_factor, 2) if std_r else 0.0
    else:
        agg["sharpe_ratio"] = 0.0

    # --- Profit factor ---
    wins_sum = sum(r for r in agent_returns if r > 0)
    losses_sum = sum(r for r in agent_returns if r < 0)
    if losses_sum != 0:
        agg["profit_factor"] = round(wins_sum / abs(losses_sum), 2)
    else:
        agg["profit_factor"] = "inf" if wins_sum > 0 else 0.0

    # --- Avg win / avg loss returns ---
    winning = [r for r in agent_returns if r > 0]
    losing = [r for r in agent_returns if r < 0]
    agg["avg_win_return"] = round(sum(winning) / len(winning), 4) if winning else 0.0
    agg["avg_loss_return"] = round(sum(losing) / len(losing), 4) if losing else 0.0

    # --- Best / worst single trade PnL ---
    all_trades_pnl = []
    for f in folds:
        for t in f.get("pnl", {}).get("trades", []):
            pnl_val = t.get("pnl_btc")
            if pnl_val is not None:
                all_trades_pnl.append(pnl_val)
    agg["best_trade_pnl"] = round(max(all_trades_pnl), 6) if all_trades_pnl else 0.0
    agg["worst_trade_pnl"] = round(min(all_trades_pnl), 6) if all_trades_pnl else 0.0

    # --- Letter grade ---
    avg_alpha = agg.get("avg_alpha_pct", 0)
    win_rate = agg.get("win_rate_pct", 0)
    if avg_alpha > 5 and win_rate > 80:
        agg["grade"] = "A+"
    elif avg_alpha > 3:
        agg["grade"] = "A"
    elif avg_alpha > 1:
        agg["grade"] = "B"
    elif avg_alpha > 0:
        agg["grade"] = "C"
    elif avg_alpha > -2:
        agg["grade"] = "D"
    else:
        agg["grade"] = "F"

    results["aggregate"] = agg
    return results


# ---------------------------------------------------------------------------
# Jinja2 HTML Template
# ---------------------------------------------------------------------------

BACKTEST_REPORT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Report — {{ report_date }}</title>
<style>
/* ===== Google Fonts ===== */
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600;700&display=swap');

/* ===== Custom Properties: Light (default) ===== */
:root {
    --bg: #faf9f6;
    --bg-card: #ffffff;
    --text: #111111;
    --text-secondary: #555555;
    --text-muted: #999999;
    --border: #d4d4d4;
    --border-light: #e8e8e8;
    --green: #15803d;
    --red: #b91c1c;
    --blue: #1e40af;
    --gold: #b8860b;
    --hero-bg: #ffffff;
    --table-stripe: rgba(0,0,0,0.02);
    --table-hover: rgba(0,0,0,0.04);
    --shadow: none;
    --masthead-bg: #ffffff;
    --masthead-border: #111111;
    --risk-bg: #fff5f5;
    --risk-border: #fecaca;
    --methodology-bg: #f8f7f4;
    --toggle-bg: transparent;
    --bar-agent: #15803d;
    --bar-btc: #3b82f6;
    --curve-stroke: #1e40af;
    --marker-short: #b91c1c;
    --marker-close: #15803d;
    --position-flat: #d4d4d4;
    --position-short: #ef4444;
    --position-heavy: #7f1d1d;
    --grade-a-plus: #15803d;
    --grade-a: #16a34a;
    --grade-b: #ca8a04;
    --grade-c: #d97706;
    --grade-d: #dc2626;
    --grade-f: #991b1b;
}

/* ===== Custom Properties: Dark ===== */
[data-theme="dark"] {
    --bg: #1a1a2e;
    --bg-card: #16213e;
    --text: #e0e0e0;
    --text-secondary: #b0b0b0;
    --text-muted: #777777;
    --border: #2a2a4a;
    --border-light: #222244;
    --green: #4ade80;
    --red: #f87171;
    --blue: #60a5fa;
    --gold: #fbbf24;
    --hero-bg: #16213e;
    --table-stripe: rgba(255,255,255,0.02);
    --table-hover: rgba(255,255,255,0.05);
    --shadow: 0 2px 8px rgba(0,0,0,0.3);
    --masthead-bg: #16213e;
    --masthead-border: #e0e0e0;
    --risk-bg: rgba(185,28,28,0.1);
    --risk-border: rgba(248,113,113,0.3);
    --methodology-bg: #16213e;
    --toggle-bg: transparent;
    --bar-agent: #4ade80;
    --bar-btc: #60a5fa;
    --curve-stroke: #60a5fa;
    --marker-short: #f87171;
    --marker-close: #4ade80;
    --position-flat: #333355;
    --position-short: #f87171;
    --position-heavy: #dc2626;
    --grade-a-plus: #4ade80;
    --grade-a: #4ade80;
    --grade-b: #fbbf24;
    --grade-c: #fb923c;
    --grade-d: #f87171;
    --grade-f: #ef4444;
}

/* ===== Reset ===== */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

/* ===== Base ===== */
body {
    font-family: 'Source Serif 4', Georgia, serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    transition: background 0.3s ease, color 0.3s ease;
}

/* ===== Typography ===== */
.font-headline { font-family: 'Playfair Display', Georgia, serif; }
.font-ui { font-family: 'Inter', -apple-system, sans-serif; }
.font-body { font-family: 'Source Serif 4', Georgia, serif; }
.tabnum { font-variant-numeric: tabular-nums; }

/* ===== Layout ===== */
.container { max-width: 980px; margin: 0 auto; padding: 0 24px; }

.section-header {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 2.5px;
    color: var(--text-muted);
    padding: 32px 0 10px;
    border-bottom: 2px solid var(--text);
    margin-bottom: 24px;
}

.positive { color: var(--green); }
.negative { color: var(--red); }

/* ===== Masthead ===== */
.masthead {
    position: relative;
    text-align: center;
    padding: 36px 24px 24px;
    border-bottom: 3px double var(--masthead-border);
    background: var(--masthead-bg);
    transition: background 0.3s ease;
}
.masthead-title {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 42px;
    letter-spacing: -0.5px;
    color: var(--text);
}
.masthead-subtitle {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 4px;
    color: var(--text-muted);
    margin-top: 6px;
}
.masthead-date {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: inline-block;
}

/* ===== Theme Toggle ===== */
.theme-toggle {
    position: absolute;
    top: 16px;
    right: 20px;
    width: 38px;
    height: 38px;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: var(--toggle-bg);
    color: var(--text);
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color 0.2s, transform 0.2s;
    z-index: 100;
    line-height: 1;
}
.theme-toggle:hover { transform: scale(1.1); }

/* ===== Hero Grade ===== */
.hero {
    text-align: center;
    padding: 48px 0 40px;
    border-bottom: 1px solid var(--border);
}
.hero-grade {
    font-family: 'Playfair Display', serif;
    font-size: 120px;
    font-weight: 900;
    line-height: 1;
    margin-bottom: 8px;
}
.hero-grade.grade-a-plus { color: var(--grade-a-plus); }
.hero-grade.grade-a { color: var(--grade-a); }
.hero-grade.grade-b { color: var(--grade-b); }
.hero-grade.grade-c { color: var(--grade-c); }
.hero-grade.grade-d { color: var(--grade-d); }
.hero-grade.grade-f { color: var(--grade-f); }
.hero-alpha {
    font-family: 'Playfair Display', serif;
    font-size: 36px;
    font-weight: 700;
    margin-top: 4px;
}
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--text-secondary);
    margin-top: 12px;
}
.hero-label {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 2.5px;
    color: var(--text-muted);
    margin-bottom: 4px;
}

/* ===== Metric Cards ===== */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
}
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 18px 14px;
    text-align: center;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    box-shadow: var(--shadow);
}
.metric-card:hover {
    transform: translateY(-2px);
    border-color: var(--text-muted);
}
.metric-label {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-muted);
    margin-bottom: 8px;
}
.metric-value {
    font-family: 'Playfair Display', serif;
    font-size: 28px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
}
.metric-sub {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 6px;
}

/* ===== SVG Charts ===== */
.chart-wrapper {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 40px;
    box-shadow: var(--shadow);
    overflow-x: auto;
}
.chart-wrapper svg text { font-family: 'Inter', sans-serif; }

/* ===== Sparkline Grid ===== */
.sparkline-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
}
.sparkline-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px;
    box-shadow: var(--shadow);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.sparkline-card:hover { transform: translateY(-1px); }
.sparkline-title {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin-bottom: 8px;
}
.sparkline-return {
    font-family: 'Playfair Display', serif;
    font-size: 16px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    margin-bottom: 6px;
}

/* ===== Tables ===== */
.data-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 40px;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
}
.data-table th {
    text-align: left;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-muted);
    padding: 10px 12px;
    border-bottom: 2px solid var(--text);
    white-space: nowrap;
}
.data-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-light);
    font-variant-numeric: tabular-nums;
    transition: background 0.1s;
}
.data-table tbody tr:nth-child(even) td { background: var(--table-stripe); }
.data-table tbody tr:hover td { background: var(--table-hover); }
.data-table .num { text-align: right; }
.data-table .result-icon { font-size: 14px; }

/* ===== Fold Detail Cards ===== */
.fold-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: var(--shadow);
    transition: border-color 0.15s ease;
}
.fold-card:hover { border-color: var(--text-muted); }
.fold-card-header {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 6px;
}
.fold-card-meta {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 14px;
    line-height: 1.5;
}
.fold-card-meta span { white-space: nowrap; }
.trades-list {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
}
.trade-row {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-light);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
}
.trade-row:last-child { border-bottom: none; }
.trade-action {
    font-weight: 600;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
    padding: 2px 6px;
    border-radius: 3px;
    background: var(--table-stripe);
}
.trade-price { color: var(--text-secondary); }
.trade-pnl { font-weight: 600; font-variant-numeric: tabular-nums; }
.trade-size { color: var(--text-muted); font-size: 12px; }
.no-trades {
    color: var(--text-muted);
    font-style: italic;
    font-size: 13px;
    padding: 8px 0;
}

/* ===== Position Timeline ===== */
.timeline-section { margin-bottom: 40px; }
.timeline-row {
    display: flex;
    align-items: center;
    margin-bottom: 6px;
    font-family: 'Inter', sans-serif;
    font-size: 12px;
}
.timeline-label {
    width: 70px;
    flex-shrink: 0;
    color: var(--text-muted);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}
.timeline-bar-wrap {
    flex: 1;
    height: 14px;
    background: var(--position-flat);
    border-radius: 3px;
    overflow: hidden;
    display: flex;
}
.timeline-seg {
    height: 100%;
    transition: opacity 0.15s;
}
.timeline-seg.flat { background: var(--position-flat); }
.timeline-seg.short { background: var(--position-short); }
.timeline-seg.heavy { background: var(--position-heavy); }
.timeline-return {
    width: 80px;
    flex-shrink: 0;
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    margin-left: 8px;
}

/* ===== Methodology ===== */
.methodology {
    background: var(--methodology-bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px 24px;
    margin-bottom: 24px;
    font-size: 14px;
    line-height: 1.7;
    color: var(--text-secondary);
}
.methodology p { margin-bottom: 6px; }

/* ===== Risk Warning ===== */
.risk-warning {
    background: var(--risk-bg);
    border: 1px solid var(--risk-border);
    border-radius: 4px;
    padding: 18px 24px;
    margin: 24px 0 0;
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    color: var(--red);
    text-align: center;
    line-height: 1.6;
}

/* ===== Footer ===== */
.footer {
    text-align: center;
    padding: 32px 24px;
    border-top: 3px double var(--masthead-border);
    margin-top: 48px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 2.5px;
}

/* ===== Legend for charts ===== */
.chart-legend {
    display: flex;
    gap: 20px;
    justify-content: center;
    margin-top: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--text-secondary);
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-swatch {
    width: 14px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
}

/* ===== Print ===== */
@media print {
    .theme-toggle { display: none !important; }
    html, html[data-theme="dark"] {
        --bg: #ffffff; --bg-card: #ffffff; --text: #000000;
        --text-secondary: #333333; --text-muted: #666666;
        --border: #cccccc; --border-light: #eeeeee;
        --green: #15803d; --red: #b91c1c; --blue: #1e40af;
        --shadow: none; --masthead-bg: #ffffff; --masthead-border: #000000;
        --table-stripe: rgba(0,0,0,0.03); --table-hover: transparent;
        --hero-bg: #ffffff; --risk-bg: #fff5f5; --risk-border: #fecaca;
        --methodology-bg: #f8f8f8;
        --bar-agent: #15803d; --bar-btc: #3b82f6;
        --curve-stroke: #1e40af;
        --marker-short: #b91c1c; --marker-close: #15803d;
        --position-flat: #d4d4d4; --position-short: #ef4444; --position-heavy: #7f1d1d;
    }
    body { background: #ffffff !important; color: #000000 !important; }
    .fold-card, .sparkline-card, .chart-wrapper { break-inside: avoid; page-break-inside: avoid; }
    .metric-card { box-shadow: none !important; }
}

/* ===== Responsive ===== */
@media (max-width: 600px) {
    .masthead-title { font-size: 28px; }
    .hero-grade { font-size: 80px; }
    .hero-alpha { font-size: 24px; }
    .metric-value { font-size: 22px; }
    .data-table { font-size: 11px; }
    .data-table th, .data-table td { padding: 6px 6px; }
    .sparkline-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- ================= MASTHEAD ================= -->
<header class="masthead">
    <button class="theme-toggle" id="themeToggle" title="Toggle dark/light mode" aria-label="Toggle theme">&#9788;</button>
    <div class="masthead-title">Backtest Report</div>
    <div class="masthead-subtitle">Anti-MicroStrategy</div>
    <div class="masthead-date">
        {{ report_date }} &bull;
        {{ agg.total_folds|default(0) }} folds &bull;
        {{ meta.train_days|default(25) }}d train / {{ meta.test_days|default(5) }}d test &bull;
        {{ meta.stride_hours|default(48) }}h stride
    </div>
</header>

<div class="container">

<!-- ================= HERO ================= -->
<div class="hero">
    <div class="hero-label">Strategy Grade</div>
    {% set g = agg.grade|default('C') %}
    {% if g == 'A+' %}
    <div class="hero-grade grade-a-plus">A+</div>
    {% elif g == 'A' %}
    <div class="hero-grade grade-a">A</div>
    {% elif g == 'B' %}
    <div class="hero-grade grade-b">B</div>
    {% elif g == 'C' %}
    <div class="hero-grade grade-c">C</div>
    {% elif g == 'D' %}
    <div class="hero-grade grade-d">D</div>
    {% else %}
    <div class="hero-grade grade-f">F</div>
    {% endif %}
    <div class="hero-alpha {{ 'positive' if agg.avg_alpha_pct|default(0) > 0 else 'negative' }}">
        {{ "{:+.2f}".format(agg.avg_alpha_pct|default(0)) }}% Alpha
    </div>
    <div class="hero-sub">
        Agent avg {{ "{:+.2f}".format(agg.avg_agent_return_pct|default(0)) }}% &middot;
        BTC avg {{ "{:+.2f}".format(agg.avg_btc_return_pct|default(0)) }}%
    </div>
</div>

<!-- ================= METRIC CARDS ================= -->
<div class="section-header">Performance Summary</div>
<div class="metric-grid">
    <div class="metric-card">
        <div class="metric-label">Avg Alpha</div>
        <div class="metric-value {{ 'positive' if agg.avg_alpha_pct|default(0) > 0 else 'negative' }}">
            {{ "{:+.2f}".format(agg.avg_alpha_pct|default(0)) }}%
        </div>
        <div class="metric-sub">vs buy-and-hold</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Win Rate</div>
        <div class="metric-value {{ 'positive' if agg.win_rate_pct|default(0) >= 50 else 'negative' }}">
            {{ agg.win_rate_pct|default(0) }}%
        </div>
        <div class="metric-sub">{{ agg.winning_folds|default(0) }}/{{ agg.total_folds|default(0) }} folds</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Alpha+ Rate</div>
        <div class="metric-value {{ 'positive' if agg.alpha_positive_rate_pct|default(0) >= 50 else 'negative' }}">
            {{ agg.alpha_positive_rate_pct|default(0) }}%
        </div>
        <div class="metric-sub">{{ agg.alpha_positive_folds|default(0) }}/{{ agg.total_folds|default(0) }} beat BTC</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Sharpe Ratio</div>
        <div class="metric-value {{ 'positive' if agg.sharpe_ratio|default(0) > 0 else 'negative' }}">
            {{ agg.sharpe_ratio|default(0) }}
        </div>
        <div class="metric-sub">annualised</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Max Drawdown</div>
        <div class="metric-value negative">
            {{ "{:.2f}".format(agg.max_drawdown_pct|default(0)) }}%
        </div>
        <div class="metric-sub">worst peak-to-trough</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Profit Factor</div>
        {% if agg.profit_factor == 'inf' %}
        <div class="metric-value positive">&infin;</div>
        {% else %}
        <div class="metric-value {{ 'positive' if agg.profit_factor|default(0)|float > 1 else 'negative' }}">
            {{ agg.profit_factor|default(0) }}
        </div>
        {% endif %}
        <div class="metric-sub">wins / losses</div>
    </div>
</div>

<!-- ================= BAR CHART: Agent vs BTC ================= -->
<div class="section-header">Agent vs BTC Returns by Fold</div>
<div class="chart-wrapper">
{% set ns = namespace(max_val=1, min_val=-1) %}
{% for fold in folds %}
    {% if fold.pnl.agent_return_pct|default(0) > ns.max_val %}{% set ns.max_val = fold.pnl.agent_return_pct %}{% endif %}
    {% if fold.pnl.btc_return_pct|default(0) > ns.max_val %}{% set ns.max_val = fold.pnl.btc_return_pct %}{% endif %}
    {% if fold.pnl.agent_return_pct|default(0) < ns.min_val %}{% set ns.min_val = fold.pnl.agent_return_pct %}{% endif %}
    {% if fold.pnl.btc_return_pct|default(0) < ns.min_val %}{% set ns.min_val = fold.pnl.btc_return_pct %}{% endif %}
{% endfor %}
{% set chart_w = 820 %}
{% set chart_h = 260 %}
{% set pad_l = 60 %}
{% set pad_r = 20 %}
{% set pad_t = 20 %}
{% set pad_b = 40 %}
{% set plot_w = chart_w - pad_l - pad_r %}
{% set plot_h = chart_h - pad_t - pad_b %}
{% set abs_max = [ns.max_val|abs, ns.min_val|abs, 0.5]|max %}
{% set y_range = abs_max * 1.15 %}
{% set n_folds = folds|length %}
{% if n_folds > 0 %}
{% set group_w = (plot_w / n_folds)|int %}
{% set bar_w = ((group_w * 0.35)|int, 30)|min %}
{% set gap = 3 %}
<svg viewBox="0 0 {{ chart_w }} {{ chart_h }}" width="100%" style="max-width:{{ chart_w }}px;display:block;margin:0 auto;">
    <!-- Y-axis grid -->
    {% set n_ticks = 5 %}
    {% for i in range(n_ticks + 1) %}
        {% set tick_val = -y_range + (2 * y_range * i / n_ticks) %}
        {% set tick_y = pad_t + plot_h - (plot_h * (tick_val + y_range) / (2 * y_range)) %}
        <line x1="{{ pad_l }}" y1="{{ tick_y|int }}" x2="{{ pad_l + plot_w }}" y2="{{ tick_y|int }}" stroke="var(--border-light)" stroke-width="1"/>
        <text x="{{ pad_l - 8 }}" y="{{ tick_y|int + 4 }}" text-anchor="end" fill="var(--text-muted)" font-size="10">{{ "{:.1f}".format(tick_val) }}%</text>
    {% endfor %}
    <!-- Zero line -->
    {% set zero_y = pad_t + plot_h - (plot_h * (0 + y_range) / (2 * y_range)) %}
    <line x1="{{ pad_l }}" y1="{{ zero_y|int }}" x2="{{ pad_l + plot_w }}" y2="{{ zero_y|int }}" stroke="var(--text-muted)" stroke-width="1.5" stroke-dasharray="4,3"/>
    <!-- Bars -->
    {% for fold in folds %}
        {% set cx = pad_l + (loop.index0 * group_w) + (group_w / 2) %}
        {% set agent_r = fold.pnl.agent_return_pct|default(0) %}
        {% set btc_r = fold.pnl.btc_return_pct|default(0) %}
        {% set agent_h = (plot_h * agent_r|abs / (2 * y_range)) %}
        {% set btc_h = (plot_h * btc_r|abs / (2 * y_range)) %}
        <!-- Agent bar -->
        {% if agent_r >= 0 %}
        <rect x="{{ (cx - bar_w - gap/2)|int }}" y="{{ (zero_y - agent_h)|int }}" width="{{ bar_w }}" height="{{ agent_h|int|abs }}" fill="var(--bar-agent)" rx="2" opacity="0.85">
            <title>Fold {{ fold.fold_id + 1 }} Agent: {{ "{:+.2f}".format(agent_r) }}%</title>
        </rect>
        {% else %}
        <rect x="{{ (cx - bar_w - gap/2)|int }}" y="{{ zero_y|int }}" width="{{ bar_w }}" height="{{ agent_h|int|abs }}" fill="var(--bar-agent)" rx="2" opacity="0.85">
            <title>Fold {{ fold.fold_id + 1 }} Agent: {{ "{:+.2f}".format(agent_r) }}%</title>
        </rect>
        {% endif %}
        <!-- BTC bar -->
        {% if btc_r >= 0 %}
        <rect x="{{ (cx + gap/2)|int }}" y="{{ (zero_y - btc_h)|int }}" width="{{ bar_w }}" height="{{ btc_h|int|abs }}" fill="var(--bar-btc)" rx="2" opacity="0.85">
            <title>Fold {{ fold.fold_id + 1 }} BTC: {{ "{:+.2f}".format(btc_r) }}%</title>
        </rect>
        {% else %}
        <rect x="{{ (cx + gap/2)|int }}" y="{{ zero_y|int }}" width="{{ bar_w }}" height="{{ btc_h|int|abs }}" fill="var(--bar-btc)" rx="2" opacity="0.85">
            <title>Fold {{ fold.fold_id + 1 }} BTC: {{ "{:+.2f}".format(btc_r) }}%</title>
        </rect>
        {% endif %}
        <!-- Fold label -->
        <text x="{{ cx|int }}" y="{{ (chart_h - 10)|int }}" text-anchor="middle" fill="var(--text-muted)" font-size="10">F{{ fold.fold_id + 1 }}</text>
    {% endfor %}
</svg>
{% else %}
<p style="text-align:center;color:var(--text-muted);padding:40px;">No fold data available.</p>
{% endif %}
<div class="chart-legend">
    <div class="legend-item"><span class="legend-swatch" style="background:var(--bar-agent);"></span> Agent Return</div>
    <div class="legend-item"><span class="legend-swatch" style="background:var(--bar-btc);"></span> BTC Return</div>
</div>
</div>

<!-- ================= EQUITY CURVE SPARKLINES ================= -->
<div class="section-header">Equity Curves</div>
<div class="sparkline-grid">
{% for fold in folds %}
    {% set curve = fold.pnl.equity_curve|default([]) %}
    {% if curve|length > 1 %}
    <div class="sparkline-card">
        <div class="sparkline-title">Fold {{ fold.fold_id + 1 }} &mdash; {{ fold.test_period.start[:10]|default('') }} to {{ fold.test_period.end[:10]|default('') }}</div>
        <div class="sparkline-return {{ 'positive' if fold.pnl.agent_return_pct|default(0) > 0 else 'negative' }}">
            {{ "{:+.3f}".format(fold.pnl.agent_return_pct|default(0)) }}%
            {% if fold.pnl.agent_return_pct|default(0) > 0 %}&#x2713;{% else %}&#x2717;{% endif %}
        </div>
        {% set sp_w = 280 %}
        {% set sp_h = 90 %}
        {% set sp_pad = 8 %}
        {% set ns2 = namespace(eq_min=999999, eq_max=-999999) %}
        {% for pt in curve %}
            {% if pt.equity < ns2.eq_min %}{% set ns2.eq_min = pt.equity %}{% endif %}
            {% if pt.equity > ns2.eq_max %}{% set ns2.eq_max = pt.equity %}{% endif %}
        {% endfor %}
        {% set eq_range = ns2.eq_max - ns2.eq_min %}
        {% if eq_range == 0 %}{% set eq_range = 0.001 %}{% endif %}
        <svg viewBox="0 0 {{ sp_w }} {{ sp_h }}" width="100%" style="max-width:{{ sp_w }}px;display:block;">
            <!-- 1.0 baseline -->
            {% set base_y = sp_pad + (sp_h - 2*sp_pad) * (1 - (1.0 - ns2.eq_min) / eq_range) %}
            <line x1="{{ sp_pad }}" y1="{{ base_y|int }}" x2="{{ sp_w - sp_pad }}" y2="{{ base_y|int }}" stroke="var(--border)" stroke-width="0.5" stroke-dasharray="3,3"/>
            <!-- Equity line -->
            <polyline fill="none" stroke="var(--curve-stroke)" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="
            {%- for pt in curve -%}
                {%- set px = sp_pad + (sp_w - 2*sp_pad) * loop.index0 / (curve|length - 1) -%}
                {%- set py = sp_pad + (sp_h - 2*sp_pad) * (1 - (pt.equity - ns2.eq_min) / eq_range) -%}
                {{ px|int }},{{ py|int }}{{ " " }}
            {%- endfor -%}
            "/>
            <!-- Trade markers -->
            {% for pt in curve %}
                {% set px = sp_pad + (sp_w - 2*sp_pad) * loop.index0 / (curve|length - 1) %}
                {% set py = sp_pad + (sp_h - 2*sp_pad) * (1 - (pt.equity - ns2.eq_min) / eq_range) %}
                {% if pt.action|default('HOLD') == 'SHORT' or pt.action|default('HOLD') == 'INCREASE_SHORT' %}
                <!-- Down triangle for SHORT -->
                <polygon points="{{ (px - 4)|int }},{{ (py - 3)|int }} {{ (px + 4)|int }},{{ (py - 3)|int }} {{ px|int }},{{ (py + 5)|int }}" fill="var(--marker-short)" opacity="0.9">
                    <title>SHORT @ candle {{ pt.candle_idx|default('?') }}</title>
                </polygon>
                {% elif pt.action|default('HOLD') == 'CLOSE' or pt.action|default('HOLD') == 'FINAL_CLOSE' or pt.action|default('HOLD') == 'REDUCE' %}
                <!-- Circle for CLOSE/REDUCE -->
                <circle cx="{{ px|int }}" cy="{{ py|int }}" r="3.5" fill="var(--marker-close)" opacity="0.9">
                    <title>{{ pt.action }} @ candle {{ pt.candle_idx|default('?') }}</title>
                </circle>
                {% endif %}
            {% endfor %}
        </svg>
    </div>
    {% endif %}
{% endfor %}
</div>
<div class="chart-legend" style="margin-top:-24px;margin-bottom:40px;">
    <div class="legend-item">
        <svg width="14" height="12"><polygon points="3,2 11,2 7,10" fill="var(--marker-short)"/></svg>
        Short Entry
    </div>
    <div class="legend-item">
        <svg width="14" height="12"><circle cx="7" cy="6" r="4" fill="var(--marker-close)"/></svg>
        Close / Reduce
    </div>
</div>

<!-- ================= FOLD TABLE ================= -->
<div class="section-header">Fold-by-Fold Results</div>
<div style="overflow-x:auto;">
<table class="data-table">
    <thead>
        <tr>
            <th>Fold</th>
            <th>Test Period</th>
            <th class="num">Agent</th>
            <th class="num">BTC</th>
            <th class="num">Alpha</th>
            <th class="num">Drawdown</th>
            <th class="num">Trades</th>
            <th>Result</th>
        </tr>
    </thead>
    <tbody>
    {% for fold in folds %}
        <tr>
            <td>{{ fold.fold_id + 1 }}</td>
            <td style="font-size:12px;white-space:nowrap;">{{ fold.test_period.start[:10]|default('') }} &rarr; {{ fold.test_period.end[:10]|default('') }}</td>
            <td class="num {{ 'positive' if fold.pnl.agent_return_pct|default(0) > 0 else 'negative' }}">
                {{ "{:+.3f}".format(fold.pnl.agent_return_pct|default(0)) }}%
            </td>
            <td class="num {{ 'positive' if fold.pnl.btc_return_pct|default(0) > 0 else 'negative' }}">
                {{ "{:+.3f}".format(fold.pnl.btc_return_pct|default(0)) }}%
            </td>
            <td class="num {{ 'positive' if fold.pnl.alpha_pct|default(0) > 0 else 'negative' }}">
                {{ "{:+.3f}".format(fold.pnl.alpha_pct|default(0)) }}%
            </td>
            <td class="num negative">{{ "{:.2f}".format(fold.computed_max_drawdown|default(0)) }}%</td>
            <td class="num">{{ fold.pnl.num_trades|default(0) }}</td>
            <td class="result-icon">
                {% if fold.pnl.agent_return_pct|default(0) > 0 %}
                <span class="positive" title="Profitable">&#x2713; Win</span>
                {% else %}
                <span class="negative" title="Loss">&#x2717; Loss</span>
                {% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
</div>

<!-- ================= TRADE DETAIL CARDS ================= -->
<div class="section-header">Trade Details by Fold</div>
{% for fold in folds %}
<div class="fold-card">
    <div class="fold-card-header">
        Fold {{ fold.fold_id + 1 }}:
        <span class="{{ 'positive' if fold.pnl.agent_return_pct|default(0) > 0 else 'negative' }}">
            {{ "{:+.3f}".format(fold.pnl.agent_return_pct|default(0)) }}%
        </span>
        {% if fold.pnl.agent_return_pct|default(0) > 0 %}
        <span class="positive" style="font-size:14px;">&#x2713;</span>
        {% else %}
        <span class="negative" style="font-size:14px;">&#x2717;</span>
        {% endif %}
    </div>
    <div class="fold-card-meta">
        <span>Test: {{ fold.test_period.start[:16]|default('') }} &rarr; {{ fold.test_period.end[:16]|default('') }}</span> &bull;
        <span>BTC: ${{ "{:,.0f}".format(fold.pnl.price.start|default(0)) }} &rarr; ${{ "{:,.0f}".format(fold.pnl.price.end|default(0)) }}
        ({{ "{:+.2f}".format(fold.pnl.btc_return_pct|default(0)) }}%)</span> &bull;
        <span>Max DD: {{ "{:.2f}".format(fold.computed_max_drawdown|default(0)) }}%</span>
    </div>
    <div class="trades-list">
        {% if fold.pnl.trades %}
        {% for trade in fold.pnl.trades %}
        <div class="trade-row">
            <span class="trade-action">{{ trade.action|default('?') }}</span>
            <span class="trade-price">@ ${{ "{:,.0f}".format(trade.price|default(0)) }}</span>
            {% if trade.pnl_btc is defined and trade.pnl_btc is not none %}
            <span class="trade-pnl {{ 'positive' if trade.pnl_btc > 0 else 'negative' }}">
                {% if trade.pnl_btc > 0 %}&#x25B2;{% else %}&#x25BC;{% endif %}
                {{ "{:+.6f}".format(trade.pnl_btc) }} BTC
            </span>
            {% endif %}
            {% if trade.size_usd is defined and trade.size_usd is not none %}
            <span class="trade-size">Size: ${{ "{:,.0f}".format(trade.size_usd) }}</span>
            {% endif %}
            {% if trade.timestamp is defined and trade.timestamp is not none %}
            <span class="trade-size" style="margin-left:auto;">{{ trade.timestamp[:16]|default('') }}</span>
            {% endif %}
        </div>
        {% endfor %}
        {% else %}
        <div class="no-trades">No trades executed (HOLD throughout)</div>
        {% endif %}
    </div>
</div>
{% endfor %}

<!-- ================= POSITION TIMELINE ================= -->
<div class="section-header">Position Timeline</div>
<div class="timeline-section">
{% for fold in folds %}
    {% set curve = fold.pnl.equity_curve|default([]) %}
    <div class="timeline-row">
        <div class="timeline-label">F{{ fold.fold_id + 1 }}</div>
        <div class="timeline-bar-wrap">
            {% if curve|length > 1 %}
                {#- Build segments: we check action to determine state -#}
                {% set total_pts = curve|length %}
                {% set ns3 = namespace(in_position=false, heavy=false) %}
                {% for pt in curve %}
                    {% set w_pct = 100.0 / total_pts %}
                    {% set act = pt.action|default('HOLD') %}
                    {% if act == 'SHORT' or act == 'INCREASE_SHORT' %}
                        {% set ns3.in_position = true %}
                        {% if act == 'INCREASE_SHORT' %}{% set ns3.heavy = true %}{% endif %}
                    {% elif act == 'CLOSE' or act == 'FINAL_CLOSE' %}
                        {% set ns3.in_position = false %}
                        {% set ns3.heavy = false %}
                    {% endif %}
                    {% if ns3.heavy %}
                    <div class="timeline-seg heavy" style="width:{{ "{:.4f}".format(w_pct) }}%;" title="Heavy short"></div>
                    {% elif ns3.in_position %}
                    <div class="timeline-seg short" style="width:{{ "{:.4f}".format(w_pct) }}%;" title="Short"></div>
                    {% else %}
                    <div class="timeline-seg flat" style="width:{{ "{:.4f}".format(w_pct) }}%;" title="Flat"></div>
                    {% endif %}
                {% endfor %}
            {% endif %}
        </div>
        <div class="timeline-return {{ 'positive' if fold.pnl.agent_return_pct|default(0) > 0 else 'negative' }}">
            {{ "{:+.2f}".format(fold.pnl.agent_return_pct|default(0)) }}%
        </div>
    </div>
{% endfor %}
<div class="chart-legend" style="margin-top:12px;">
    <div class="legend-item"><span class="legend-swatch" style="background:var(--position-flat);"></span> Flat</div>
    <div class="legend-item"><span class="legend-swatch" style="background:var(--position-short);"></span> Short</div>
    <div class="legend-item"><span class="legend-swatch" style="background:var(--position-heavy);"></span> Heavy Short</div>
</div>
</div>

<!-- ================= METHODOLOGY ================= -->
<div class="section-header">Methodology</div>
<div class="methodology">
    <p><strong>Sliding-window cross-validation</strong> is used to evaluate this strategy without look-ahead bias.
    A {{ meta.train_days|default(25) }}-day training window provides historical context to the agent, which then
    makes trading decisions over a {{ meta.test_days|default(5) }}-day test window.</p>
    <p>The window advances by {{ meta.stride_hours|default(48) }} hours between folds, producing {{ agg.total_folds|default(0) }}
    overlapping evaluation periods. Each fold starts flat (no position) and is scored independently.</p>
    <p>Alpha is measured as the difference between the agent's return and a simple BTC buy-and-hold over the same test period.</p>
</div>

<!-- ================= RISK WARNING ================= -->
<div class="risk-warning">
    <strong>Risk Disclosure:</strong> Backtested results do not guarantee future performance. This system has a deliberate bearish bias.
    Slippage, fees, and market impact are not fully modeled. Past alpha may not persist.
    This is not financial advice.
</div>

</div><!-- /.container -->

<!-- ================= FOOTER ================= -->
<footer class="footer">
    Backtest Report &bull; Anti-MicroStrategy &bull; Generated {{ report_time|default('') }} UTC
</footer>

<!-- ================= THEME TOGGLE SCRIPT ================= -->
<script>
(function() {
    var html = document.documentElement;
    var btn = document.getElementById('themeToggle');
    var STORAGE_KEY = 'backtest-theme';

    function getSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }

    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
        btn.innerHTML = theme === 'dark' ? '&#9788;' : '&#9790;';
        btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    }

    // Init: localStorage > system preference
    var saved = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch(e) {}
    var initial = saved || getSystemTheme();
    applyTheme(initial);

    btn.addEventListener('click', function() {
        var current = html.getAttribute('data-theme') || 'light';
        var next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try { localStorage.setItem(STORAGE_KEY, next); } catch(e) {}
    });

    // Listen for system theme changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            var s = null;
            try { s = localStorage.getItem(STORAGE_KEY); } catch(ex) {}
            if (!s) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
})();
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_backtest_report(results: dict) -> str:
    """Compute additional metrics and generate WSJ-styled HTML backtest report."""
    now = datetime.now(timezone.utc)

    # Enrich with computed metrics
    results = _compute_extra_metrics(results)

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
