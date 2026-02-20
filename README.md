# Anti-MicroStrategy: AI-Powered BTC Short Desk

An autonomous trading agent powered by Claude that shorts Bitcoin on [Deribit](https://www.deribit.com), guided by the thesis that BTC is fundamentally overvalued. The inverse of MicroStrategy's strategy.

**Live Dashboard:** [GitHub Pages](https://miguelemosreverte.github.io/anti-microstrategy-claude/)

---

## How It Works

```
┌──────────────────┐     ┌───────────────────┐     ┌─────────────┐
│  Market Data     │────>│  Claude Agent      │────>│  Deribit    │
│  - CoinGecko     │     │  Analyzes signals, │     │  Executes   │
│  - Fear & Greed  │     │  decides to SHORT, │     │  trades on  │
│  - Deribit APIs  │     │  HOLD, CLOSE, or   │     │  BTC-PERP   │
│  - FRED (macro)  │     │  REDUCE positions  │     │             │
│  - Technicals    │     │                    │     │             │
└──────────────────┘     └────────┬───────────┘     └─────────────┘
                                  │
                         ┌────────v───────────┐
                         │  SQLite Database    │
                         │  Stores insights,   │
                         │  trades, snapshots  │
                         └────────┬───────────┘
                                  │
                         ┌────────v───────────┐
                         │  HTML Report        │
                         │  WSJ-styled brief   │
                         │  opens in browser   │
                         └────────────────────┘
```

Each cycle the agent:
1. **Collects** market data from 5+ sources
2. **Feeds** everything to Claude via `claude -p` with bearish BTC system prompt
3. **Receives** a structured decision: `SHORT`, `HOLD`, `CLOSE`, `REDUCE`, or `INCREASE_SHORT`
4. **Executes** the trade on Deribit (BTC-PERPETUAL futures)
5. **Stores** the analysis and trade in SQLite
6. **Generates** a WSJ-styled HTML report

---

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/miguelemosreverte/anti-microstrategy-claude.git
cd anti-microstrategy-claude
pip install -r requirements.txt

# Install git hooks (runs backtest on commit, updates GitHub Pages)
./setup.sh
```

### 2. Get your credentials

| Credential | Where to get it | Required |
|---|---|---|
| **Claude Code CLI** | `npm install -g @anthropic-ai/claude-code` | Yes |
| **Deribit API Key** (testnet) | [test.deribit.com](https://test.deribit.com) > Account > API > Create Key | For live trading |
| **FRED API Key** | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) | Optional |

> The backtest engine uses `claude -p` (Claude Code CLI) directly. No separate Anthropic API key needed.

### 3. Configure (for live trading)

```bash
cp .env.example .env
# Edit .env with your Deribit credentials
```

### 4. Run

```bash
# Run a backtest (downloads data + evaluates agent across 3 folds)
python -m backtest.run_backtest

# Single live trading cycle
python run.py

# Continuous mode (runs every 15 min)
python run.py --loop
```

---

## Backtesting

The backtest engine uses **sliding-window cross-validation** (like ML time-series CV):

```
Dataset: 30 days of hourly BTC-PERPETUAL candles from Deribit

Fold 1: [===== 25d train =====][== 5d test ==]
Fold 2:   [===== 25d train =====][== 5d test ==]
Fold 3:     [===== 25d train =====][== 5d test ==]
```

Each fold:
1. Agent sees 25 days of historical data (OHLCV, RSI, MACD, BB, funding, sentiment)
2. Agent makes trading decisions for the 5-day test window
3. PnL is simulated against actual price movements
4. Alpha vs buy-and-hold is calculated

```bash
# Default: 3 folds, 48h stride
python -m backtest.run_backtest

# More folds, tighter stride
python -m backtest.run_backtest --folds 5 --stride 24

# Re-fetch fresh data
python -m backtest.run_backtest --fetch

# All possible folds
python -m backtest.run_backtest --all
```

Reports are generated as WSJ-styled HTML and auto-open in your browser.

---

## Git Hooks & Calibration

The repo uses git hooks to enforce a **regression guard** on backtest performance:

```bash
# Install hooks (done by setup.sh)
./setup.sh

# What happens on each commit:
# 1. Backtest runs automatically (post-commit hook)
# 2. Results are saved with the commit hash
# 3. GitHub Pages are updated with latest calibration data
# 4. If performance regresses, you'll see a warning
```

Calibration results are **event-sourced via git** — each commit records its backtest performance, creating an audit trail of how the agent improves over time.

---

## Project Structure

```
.
├── agent/                  # Live trading agent
│   ├── config.py           # Environment variables
│   ├── database.py         # SQLite schema + CRUD
│   ├── deribit_client.py   # Deribit REST API client
│   ├── market_data.py      # Market data aggregator
│   ├── report.py           # WSJ-styled HTML report
│   └── trader.py           # Core AI agent (Claude)
├── backtest/               # Backtesting framework
│   ├── engine.py           # Sliding-window CV engine
│   ├── fetch_dataset.py    # Historical data downloader
│   ├── report.py           # Backtest report generator
│   └── run_backtest.py     # CLI entry point
├── docs/                   # GitHub Pages site
│   ├── index.html          # Dashboard homepage
│   └── calibration.json    # Historical calibration data
├── hooks/                  # Git hooks (installed by setup.sh)
│   └── post-commit         # Runs backtest on commit
├── setup.sh                # Installs git hooks
├── run.py                  # Live trading entry point
├── requirements.txt
└── .env.example
```

---

## Going Live

1. Create API keys on [deribit.com](https://www.deribit.com) (requires KYC)
2. Set `DERIBIT_LIVE=true` in `.env`
3. Start with small positions

**Risk warning:** This agent has a deliberate bearish bias. Short positions have theoretically unlimited loss. Only trade with money you can afford to lose.

---

## License

MIT
