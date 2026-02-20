# Anti-MicroStrategy: AI-Powered BTC Short Desk

An autonomous trading agent powered by Claude that shorts Bitcoin on [Deribit](https://www.deribit.com), guided by the thesis that BTC is fundamentally overvalued and headed toward zero. The inverse of MicroStrategy's strategy — instead of accumulating Bitcoin, we bet against it.

> **v1** (`v1-bear-dao/`): Solidity smart contracts for a gold-accumulating DAO (PAXG vault on Ethereum)
>
> **v2** (`v2-trading-agent/`): **Active** — Claude-powered trading agent that shorts BTC on Deribit

---

## How It Works

```
┌──────────────────┐     ┌───────────────────┐     ┌─────────────┐
│  Market Data     │────▶│  Claude Agent      │────▶│  Deribit    │
│  - CoinGecko     │     │  Analyzes signals, │     │  Executes   │
│  - Fear & Greed  │     │  decides to SHORT, │     │  trades on  │
│  - Deribit APIs  │     │  HOLD, CLOSE, or   │     │  BTC-PERP   │
│  - FRED (macro)  │     │  REDUCE positions  │     │             │
│  - Technicals    │     │                    │     │             │
└──────────────────┘     └────────┬───────────┘     └─────────────┘
                                  │
                         ┌────────▼───────────┐
                         │  SQLite Database    │
                         │  Stores insights,   │
                         │  trades, snapshots  │
                         └────────┬───────────┘
                                  │
                         ┌────────▼───────────┐
                         │  HTML Report        │
                         │  WSJ-styled brief   │
                         │  opens in browser   │
                         └────────────────────┘
```

Each cycle the agent:
1. **Collects** market data from 5+ sources (BTC price, technicals, sentiment, macro, Deribit-specific)
2. **Feeds** everything to Claude with a bearish BTC system prompt
3. **Receives** a structured decision: `SHORT`, `HOLD`, `CLOSE`, `REDUCE`, or `INCREASE_SHORT`
4. **Executes** the trade on Deribit (BTC-PERPETUAL futures)
5. **Stores** the analysis and trade in SQLite
6. **Generates** a Wall Street Journal-styled HTML report and opens it in your browser

---

## Quick Start (5 minutes)

### 1. Clone and install

```bash
git clone https://github.com/miguelemosreverte/anti-microstrategy-claude.git
cd anti-microstrategy-claude/v2-trading-agent
pip install -r requirements.txt
```

### 2. Get your API keys (3 accounts to create)

| Credential | Where to get it | Time |
|---|---|---|
| **Anthropic API Key** | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | 1 min |
| **Deribit API Key** (testnet) | [test.deribit.com](https://test.deribit.com) → Account → API → Create Key | 2 min |
| **FRED API Key** (optional) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) | 1 min |

#### Deribit Testnet Setup (step by step)

1. Go to [test.deribit.com](https://test.deribit.com) and register (no KYC needed)
2. You'll get free test BTC automatically
3. Click your username → **API** → **Add new key**
4. Enable these scopes: `account:read`, `trade:read_write`, `wallet:read`
5. Copy the **Client ID** and **Client Secret**

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
DERIBIT_CLIENT_ID=xxxxxxxx
DERIBIT_CLIENT_SECRET=xxxxxxxxxxxxxxxx
DERIBIT_LIVE=false

# Optional but recommended (adds macro data like gold, DXY, yields):
FRED_API_KEY=xxxxxxxxxxxxxxxx
```

### 4. Run

```bash
# Single analysis cycle (recommended first run)
python run.py

# Continuous mode (runs every 15 min)
python run.py --loop

# Just generate a report from existing data
python run.py --report
```

The agent will analyze the market, make a trading decision, execute it on Deribit testnet, and open a WSJ-styled HTML report in your browser.

---

## Architecture

```
v2-trading-agent/
├── agent/
│   ├── config.py           # Environment variables and settings
│   ├── database.py         # SQLite schema + CRUD operations
│   ├── deribit_client.py   # Deribit REST API client (auth, trading, market data)
│   ├── market_data.py      # Aggregates data from CoinGecko, FRED, Deribit, etc.
│   ├── report.py           # WSJ-styled HTML report generator (Jinja2)
│   └── trader.py           # Core AI agent — Claude analyzes + decides + executes
├── reports/                # Generated HTML reports
├── trading.db              # SQLite database (created on first run)
├── run.py                  # Entry point
├── requirements.txt
└── .env.example
```

### Data Sources

| Source | Data | Auth Required |
|---|---|---|
| **Deribit** (public) | BTC index, perpetual ticker, funding rate, volatility, OHLCV | No |
| **CoinGecko** | BTC/ETH price, 24h change, volume, market cap | No (key optional) |
| **Alternative.me** | Fear & Greed Index | No |
| **FRED** | Gold price, DXY, 10Y Treasury, Fed Funds Rate, VIX | Free key |
| **Computed locally** | RSI, MACD, Bollinger Bands, EMA, ATR (via pandas-ta) | No |

### Database Schema

- **market_snapshots** — Full market state at each cycle (price, funding, sentiment, macro, technicals)
- **agent_insights** — Claude's analysis, sentiment, confidence, and recommended action
- **trades** — Executed trades with instrument, direction, amount, status
- **positions** — Position snapshots (size, entry, PnL, liquidation price)
- **account_snapshots** — Account equity, balance, margin over time

---

## Going Live

When you're ready to trade with real money:

1. Create API keys on [deribit.com](https://www.deribit.com) (production, requires KYC)
2. Set `DERIBIT_LIVE=true` in your `.env`
3. Start with very small positions — the agent caps at 20% of margin per trade

**Risk warning:** This agent has a deliberate bearish bias. Bitcoin can rally significantly before any decline. Short positions have theoretically unlimited loss potential. Only trade with money you can afford to lose.

---

## V1: BearDAO Solidity Contracts

The `v1-bear-dao/` directory contains the original smart contract approach — a vault where users deposit USDC/ETH, the vault swaps to PAXG (tokenized gold) via Uniswap V3, and depositors receive $BEAR ERC-20 tokens. See `v1-bear-dao/README.md` for details.

---

## License

MIT
