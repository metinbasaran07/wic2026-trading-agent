# WIC 2026 Trading Agent

AI Agent Trading Workstation for the **World Investment Competition 2026** (AI Agent Division) organized by Japan Students Investment Union (JPSI).

## 🏆 Competition Overview

| Aspect | Details |
|--------|---------|
| **Division** | AI Agent Division (New in 2026) |
| **Organizer** | JPSI (Japan Students Investment Union) |
| **Account** | $1M Interactive Brokers demo account |
| **Data** | 15-minute delayed market data via TWS API |
| **Team** | 1-3 students from same organization |
| **Timeline** | Dev: Dec 7-31, 2026 → Trial: Jan 4-31, 2027 → Live: Feb 1 - Mar 25, 2027 |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Trading Workstation                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  IB Gateway  │──│  Market Data │──│  Strategy    │          │
│  │  (TWS API)   │  │  Pipeline    │  │  Engine      │          │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘          │
│                           │                 │                   │
│                    ┌──────▼───────┐  ┌──────▼───────┐          │
│                    │  Risk Mgmt   │  │  LLM Review  │          │
│                    │  & Sizing    │  │  Scheduler   │          │
│                    └──────┬───────┘  └──────┬───────┘          │
│                           │                 │                   │
│                    ┌──────▼─────────────────▼───────┐          │
│                    │     Operation Logger &         │          │
│                    │     Change Tracker             │          │
│                    └────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 🎯 Key Features

### Strategies
- **Smart Money Concepts (SMC)** - Primary strategy
  - Market Structure (BOS/CHoCH)
  - Order Blocks (Bullish/Bearish)
  - Fair Value Gaps (FVG)
  - Breaker Blocks
  - Liquidity Pools
  - Premium/Discount zones
- **Mean Reversion** - Bollinger Bands + RSI
- **Momentum** - MACD + ADX trend following
- **Combined** - Multi-strategy consensus

### LLM Integration
- **Development**: OpenRouter API (your own key)
- **Competition**: Organizers' Team Key (provided)
- Hourly strategy review with parameter optimization
- Structured JSON output for reliable parsing

### Risk Management
- 1% risk per trade
- Max 10% position size
- 5% daily drawdown limit
- Kelly criterion sizing (quarter Kelly)
- Volatility-adjusted position sizing (ATR-based)

### Compliance (Competition Requirements)
- ✅ Operation logging (trades, signals, LLM usage, errors)
- ✅ Change tracking (parameters, strategy, code)
- ✅ Pre-report / Post-report generation
- ✅ No human intervention during live trading
- ✅ Emergency stop capability

### Dashboard
- Real-time P&L, positions, equity
- Interactive candlestick charts (Plotly)
- SMC analysis visualization
- LLM review history
- System health monitoring
- WebSocket + SSE real-time updates

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Interactive Brokers account (for IB Gateway)
- OpenRouter API key (for development)

### Installation

```bash
# Clone/navigate to project
cd wic2026-trading-agent

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Build and start
./scripts/deploy.sh build
./scripts/deploy.sh up

# Access dashboard
open http://localhost:8080
```

### Development Mode (without Docker)

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure .env
cp .env.example .env
# Edit with your OpenRouter API key

# Run trading agent
python -m src.main run

# Or run dashboard only
python -m src.main dashboard

# Generate pre-report template
python -m src.main generate_pre_report
```

## 📁 Project Structure

```
wic2026-trading-agent/
├── src/
│   ├── config/          # Settings & configuration
│   ├── ib/              # Interactive Brokers integration
│   │   ├── connection.py    # IB connection with auto-reconnect
│   │   └── market_data.py   # 15-min delayed data pipeline
│   ├── strategy/        # Trading strategies
│   │   ├── base.py          # Base strategy classes
│   │   ├── smc.py           # Smart Money Concepts
│   │   ├── mean_reversion.py
│   │   ├── momentum.py
│   │   └── portfolio.py     # Multi-signal combination
│   ├── risk/            # Risk management
│   │   └── manager.py
│   ├── llm/             # LLM integration
│   │   ├── client.py        # Dual provider (OpenRouter/Team Key)
│   │   ├── reviewer.py      # Hourly strategy review
│   │   ├── prompts.py       # Jinja2 prompt templates
│   │   └── parser.py        # Structured output parsing
│   ├── compliance/      # Competition compliance
│   │   ├── logger.py        # Operation logging (JSONL)
│   │   ├── change_tracker.py
│   │   └── report_generator.py
│   ├── dashboard/       # FastAPI + HTMX dashboard
│   │   └── app.py
│   └── main.py          # CLI entry point
├── docker/              # Docker configuration
├── scripts/             # Deployment scripts
├── tests/               # Test suite
├── pyproject.toml
├── .env.example
└── README.md
```

## ⚙️ Configuration

Key settings in `.env`:

```bash
# Mode: dev | trial | live
MODE=dev

# IB Connection
IB_HOST=127.0.0.1
IB_PORT=4002  # 4001=live, 4002=paper

# LLM Provider
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Strategy
STRATEGY_NAME=smc
REVIEW_INTERVAL_MINUTES=60

# Risk
MAX_POSITION_SIZE=0.1
MAX_DRAWDOWN=0.05
RISK_PER_TRADE=0.01
```

## 🔧 CLI Commands

```bash
# Run trading agent
python -m src.main run

# Run dashboard only
python -m src.main dashboard

# Backtest SMC strategy
python -m src.main backtest SPY --days 30

# Generate pre-report
python -m src.main generate_pre_report
```

## 🐳 Docker Deployment

```bash
# Development
./scripts/deploy.sh up

# View logs
./scripts/deploy.sh logs trading-agent

# Health check
./scripts/deploy.sh health

# Production deployment (competition live)
./scripts/deploy.sh prod

# Backup data
./scripts/deploy.sh backup
```

## 📊 Dashboard Features

- **Real-time**: WebSocket + SSE updates every 5 seconds
- **Charts**: Interactive Plotly candlestick charts
- **SMC Panel**: Order Blocks, FVGs, Structure, Liquidity
- **Risk Metrics**: Drawdown, Sharpe, Win Rate, Profit Factor
- **LLM Reviews**: History with confidence scores
- **Emergency Stop**: One-click stop logging

## 📝 Competition Compliance

### Required Reports

1. **Pre-Report** (before live trading):
   - Return hypothesis
   - Decision process description
   - LLM role in decisions
   - Order logic & risk management
   - Change policy

2. **Operation Log** (continuous):
   - All trades with reasoning
   - LLM usage & costs
   - Parameter changes
   - Errors & recoveries

3. **Post-Report** (after competition):
   - Results vs hypothesis
   - Key decisions record
   - Changes made
   - Lessons learned

### Auto-Generated Files
- `logs/operations.jsonl` - All events
- `logs/trades.jsonl` - Trade executions
- `logs/llm_reviews.jsonl` - LLM reviews
- `logs/changes.jsonl` - Parameter/code changes
- `reports/pre_report_*.md` - Pre-report
- `reports/post_report_*.md` - Post-report

## 🧪 Testing

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## 📈 Competition Timeline

| Phase | Dates | Purpose |
|-------|-------|---------|
| **Development** | Dec 7-31, 2026 | Strategy development, backtesting |
| **Trial** | Jan 4-31, 2027 | Paper trading validation |
| **Live** | Feb 1 - Mar 25, 2027 | Competition trading |

## ⚠️ Important Notes

1. **15-minute delay**: All market data is 15-min delayed per competition rules
2. **No human intervention**: During live trading, agent must run autonomously
3. **LLM spending cap**: Competition provides team key with spending limit
4. **Pre-approved changes**: All strategy changes must be declared in pre-report
5. **Emergency stops**: Logged and reported to organizers

## 🤝 Contributing

This is a competition project. For internal team use only.

## 📄 License

Proprietary - World Investment Competition 2026 entry