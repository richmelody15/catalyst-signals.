# CATALYST FINAL v3.3 - Self-Improving OTC Signal Engine

> 10 Confluences + Accuracy Level (0-100%) | 80-95% Win Rate Target | 24/7
> IQ Option & Pocket Option | Memory-Based Confidence | Auto-Tuning | Telegram Alerts

---

## Quick Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/catalyst-signals)

### 1. One-Click Deploy

1. Fork or clone this repo
2. Go to [Railway](https://railway.app) and create a new project
3. Select "Deploy from GitHub repo" → choose this repo
4. Add environment variables (see below)
5. Railway will auto-detect the Python app and deploy

### 2. Environment Variables

Set these in Railway → your service → Variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `IQ_EMAIL` | No | IQ Option email |
| `IQ_PASSWORD` | No | IQ Option password |
| `PO_EMAIL` | No | Pocket Option email |
| `PO_PASSWORD` | No | Pocket Option password |
| `TELEGRAM_TOKEN` | No | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | No | Telegram channel/chat ID |
| `USE_IQ_OPTION` | No | Enable IQ Option (default: True) |
| `USE_POCKET_OPTION` | No | Enable Pocket Option (default: True) |
| `NEWS_FILTER_ENABLED` | No | Block signals near high-impact news (default: True) |
| `ENTRY_CONFIRM_ENABLED` | No | Wait for entry-time price confirmation (default: True) |

### 3. Access Your Dashboard

After deployment, your dashboard will be live at:
```
https://your-app-name.up.railway.app
```

---

## Features

### v3.3 (Latest)
- **📋 Copy Signal** — Full enhanced signal format with all v3.2+ fields
- **📱 Telegram Enhanced** — Full CATALYST AI SIGNAL format with Market Regime, BOS/CHoCH, FVG, Liquidity, Volume, Zone, Stochastic, BB Width, R:R, GLM Smart Money, Strategy Guide, Support/Resistance

### v3.2
- **Market Regime Detection** — BREAKOUT, RANGING, TRENDING with description
- **Stochastic Oscillator** — Overbought/Oversold/Bullish Crossover/Bearish Crossover
- **Liquidity Sweep Detection** — Buy/Sell side sweep identification
- **Enhanced Zone Analysis** — Supply/Demand + Order Block labeling
- **BOS/CHoCH Confirmation** — Active/Not Confirmed display
- **R:R Ratio** — Risk-to-Reward display (1:X.X)
- **GLM Smart Money** — Structure, Liquidity, Breakout, Signal validity
- **Strategy Guide** — Context-sensitive rules based on signal type
- **Support/Resistance** — Key levels in signal output

### v3.1
- **Entry-time confirmation** — Wait for entry time and verify price
- **Telegram Bot alerts** — Real-time signal notifications
- **News filter** — Block signals near high-impact economic events
- **Chart.js dashboard** — Daily win-rate graph + live stats
- **Weekly optimization** — APScheduler auto-tunes every Sunday
- **Dual broker** — IQ Option + Pocket Option
- **10-point ALL-AND confluence** — MTF + Accuracy scoring

---

## Signal Format

```
🔔 CATALYST AI SIGNAL!

🎫 Trade: GBPJPY
⏳ Timer: 3m (OTC)
➡️ Entry: 00:02 WAT
📈 Direction: BUY 🟢
🎯 GLM Probability: 94.3% WIN RATE
📊 Market: High Volatility

🔮 Market Regime: STRONG TREND
   Market is in a strong directional move...

🧠 Trend: Bullish
📉 BOS: Confirmed
🔄 CHoCH: Confirmed
📦 FVG: Active
💧 Liquidity: Buy Side Sweep
📦 Volume: High
🏗️ Zone: Demand + Order Block
📉 RSI: 43
📊 Stochastic: Bullish Crossover
📊 BB Width: Contracting
⚖️ RR: 1:2.5

↪️ ── 🛡️ MARTINGALE RECOVERY (Risk Level) ──
  M1 │ 2.5x │ $2.5 │ Entry: 00:05 WAT
  M2 │ 5.5x │ $5.5 │ Entry: 00:08 WAT
  M3 │ 12x │ $12 │ Entry: 00:11 WAT

🧪 GLM SMART MONEY:
  Structure: Break of Structure ↑
  Liquidity: Buy Side Sweep
  Breakout: Confirmed Breakout
  Signal: Valid Buy Signal

📋 STRATEGY GUIDE:
  ✅ Enter on pullback to demand/supply zone
  ✅ Confirm with BOS retest
  🚪 Take profit at 1:2.5 R:R
  🛡️ Risk 1-2% per trade

📐 SUPPORT/RESISTANCE:
  Support: 191.250
  Resistance: 191.890

Note: Trade 1% - 3% of your capability and capital
🎯 SIGNAL STATUS: HIGH PROBABILITY ONLY
🎯 GLM PROBABILITY: 94.3% WIN RATE
   HIGH PROBABILITY ONLY
```

---

## Local Development

```bash
pip install -r requirements.txt
python catalyst_final.py
# Open http://localhost:8000
```

---

## Tech Stack

- **Backend**: Python FastAPI + WebSocket
- **Broker APIs**: IQ Option + Pocket Option
- **Telegram**: python-telegram-bot
- **Dashboard**: Chart.js + WebSocket real-time
- **Scheduler**: APScheduler (weekly optimization)
- **Database**: SQLite (trade memory + auto-tuning)

---

## Files

| File | Description |
|------|-------------|
| `catalyst_final.py` | Main server — all-in-one FastAPI app |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway/Heroku start command |
| `railway.toml` | Railway deployment config |
| `railway.json` | Railway schema config |
| `.gitignore` | Excludes .env, *.db, __pycache__ |
| `.env.example` | Environment variable template |

---

## ⚠️ Disclaimer

This is an AI-powered analysis tool. Trading involves significant risk. Past performance does not guarantee future results. Trade responsibly and never risk more than you can afford to lose.
