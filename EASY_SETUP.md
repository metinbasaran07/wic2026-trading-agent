# 🚀 Easy Setup - No Terminal Required!

## Option 1: Double-Click Launcher (Easiest)

**Just double-click:** `launch_setup.command`

This opens a menu where you can choose:
- **GUI Wizard** - Native macOS window with forms
- **Web Wizard** - Opens in your browser at http://localhost:8081

---

## Option 2: Direct Double-Click

| File | What it does |
|------|--------------|
| `run_setup.command` | Opens the GUI wizard directly |
| `launch_setup.command` | Menu to choose GUI or Web |

---

## What the Wizards Do

### 📝 Configuration Form
Fill in your details once:
- **OpenRouter API Key** (get from https://openrouter.ai/keys)
- **IB Username/Password** (your Interactive Brokers credentials)
- **Trading Symbols** (comma-separated, e.g., SPY,QQQ,AAPL)
- **Risk Settings** (sliders for position size, drawdown, etc.)

### 💾 One-Click Save
Creates `.env` file automatically - no manual editing!

### 🚀 One-Click Start
- **Start Trading Agent** - Runs the full system
- **Open Dashboard** - Opens http://localhost:8080 in browser
- **Run Backtest** - Test strategies on historical data
- **Generate Pre-Report** - Creates competition report template

### 🐳 Docker Support (if installed)
- Build Docker images
- Start with Docker Compose
- View logs

---

## First Time Setup Checklist

1. **Get OpenRouter API Key** (free tier works)
   - Go to https://openrouter.ai/keys
   - Create key → Copy → Paste in wizard

2. **Set up Interactive Brokers**
   - Paper trading account at IBKR
   - Enable API in IB Gateway/TWS
   - Port 4002 for paper, 4001 for live

3. **Run the wizard**
   - Double-click `launch_setup.command`
   - Fill form → Save → Start

---

## After Starting

The **Dashboard** opens at http://localhost:8080 with:
- 📈 Real-time P&L and positions
- 🕯️ Interactive candlestick charts
- 🎯 SMC analysis (Order Blocks, FVGs, Structure)
- ⚖️ Risk metrics (Drawdown, Sharpe, Win Rate)
- 🤖 LLM review history
- 🛑 Emergency stop button

---

## Competition Mode Switch

When competition starts (Feb 1, 2027):
1. Open wizard again
2. Change **Mode** to "Live"
3. Change **LLM Provider** to "Team Key" (organizers provide)
4. Save → Restart agent

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Command not found" | Make sure you're in the project folder |
| "Permission denied" | Run: `chmod +x *.command` in terminal once |
| IB connection failed | Check IB Gateway is running on correct port |
| Dashboard not loading | Wait 10 seconds after starting agent |

---

## Files Created by Setup

```
.env                 # Your configuration (auto-generated)
logs/                # Operation logs (auto-created)
reports/             # Competition reports (auto-created)
```

**That's it!** No terminal commands needed after initial setup. 🎉