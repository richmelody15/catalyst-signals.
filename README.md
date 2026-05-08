# ⚡ CATALYST FINAL v3.0 — Self-Improving OTC Signal Engine

**AI-powered OTC binary option signal generator** targeting 80-95%+ win rate using Smart Money Concepts (SMC) filters.

## 🧠 Core Features

- **Dual Broker Support**: IQ Option + Pocket Option with OTC asset routing
- **5-Layer SMC Filter Stack** (ALL-AND mode):
  - Order Block detection
  - Fair Value Gap (FVG) scanner
  - Break of Structure / Change of Character (BOS/CHoCH)
  - Market Structure Shift (MSS)
  - Market Structure Reversal pattern
- **Wait-and-Confirm Entry**: Sleeps until entry time, verifies price moved in predicted direction
- **Telegram Bot Integration**: Broadcasts confirmed signals in real-time
- **Economic Calendar / News Filter**: Blocks signals within 10min of high-impact US events
- **Real-time Win-Rate Dashboard**: Chart.js visualization + daily stats table
- **Weekly Auto-Optimization**: APScheduler Sunday 03:00 UTC cron for self-improvement

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run the server
python catalyst_final.py
```

## ⚙️ Environment Variables

| Variable | Description |
|----------|-------------|
| `IQ_EMAIL` | IQ Option login email |
| `IQ_PASSWORD` | IQ Option password |
| `PO_EMAIL` | Pocket Option email |
| `PO_PASSWORD` | Pocket Option password |
| `USE_IQ_OPTION` | Enable IQ Option broker (True/False) |
| `USE_POCKET_OPTION` | Enable Pocket Option broker (True/False) |
| `TELEGRAM_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram channel/group ID |
| `ENTRY_CONFIRM_ENABLED` | Enable wait-and-confirm logic (True/False) |
| `NEWS_FILTER_ENABLED` | Enable news filter (True/False) |

## 📁 Project Files

| File | Description |
|------|-------------|
| `catalyst_final.py` | Main server (v3.0) — all features integrated |
| `catalyst_ai.py` | Previous version with SMC + dual-broker |
| `catalyst-main.py` | Legacy main entry point |
| `otc_scalper.py` | OTC scalping module |
| `requirements.txt` | Python dependencies |
| `Procfile` | Deployment config (Railway/Render) |

## 📊 Dashboard

Access the real-time dashboard at `http://localhost:8000/dashboard` after starting the server.

## 🔧 Deployment

Compatible with Railway, Render, or any Docker/cloud platform that supports Python.

## 📜 License

Private project — all rights reserved.
