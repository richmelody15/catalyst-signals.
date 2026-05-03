#!/usr/bin/env python3
"""
CATALYST AI – OTC Blitz Scalper
Render deployment entry point:  uvicorn main:app --host 0.0.0.0 --port $PORT

Single-file production app with:
  - OTCScalperEngine (2-min expiry momentum signals)
  - Keep-alive self-ping (prevents Render free tier sleep)
  - Embedded HTML frontend with fetchWithRetry (cold-start safe)
  - CORS middleware for Vercel cross-origin
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio, httpx, os, json
from datetime import datetime, timedelta
import numpy as np, pandas as pd, pytz

# ─── Config ────────────────────────────────────────────────
WAT = pytz.timezone("Africa/Lagos")
API_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://0.0.0.0:8000")
KEEP_ALIVE_INTERVAL = int(os.environ.get("KEEP_ALIVE_INTERVAL", "600"))

# ─── OTC Scalper Engine ───────────────────────────────────
class OTCScalperEngine:
    def __init__(self):
        self.config = {
            "volume_spike": 1.5,
            "momentum_period": 3,
            "min_momentum_pct": 0.0002,
            "adx_threshold": 20,
            "rsi_limit": 70,
            "rsi_floor": 30,
            "max_spread_risk": 0.0003,
        }

    def generate(self, df: pd.DataFrame, pair: str, timeframe: str = "M1"):
        if len(df) < 10:
            return None
        close = df["close"].values
        volume = df.get("volume", pd.Series([1] * len(df))).values

        # 1. Volume spike
        avg_vol = np.mean(volume[-10:-1])
        current_vol = volume[-1]
        if current_vol < avg_vol * self.config["volume_spike"]:
            return None

        # 2. Momentum (last 3 candles)
        if len(close) < 4:
            return None
        pct_change = close[-1] / close[-4] - 1
        direction = "BUY" if pct_change > 0 else "SELL"
        if abs(pct_change) < self.config["min_momentum_pct"]:
            return None

        # 3. RSI guard
        rsi = self._rsi(close, 14)
        if direction == "BUY" and rsi > self.config["rsi_limit"]:
            return None
        if direction == "SELL" and rsi < self.config["rsi_floor"]:
            return None

        # 4. ADX trend
        adx_val = self._adx(df, 14)
        if adx_val < self.config["adx_threshold"]:
            return None

        # 5. Session filter (London/NY)
        now = datetime.now(pytz.UTC)
        if not (8 <= now.hour < 17):
            return None

        # 6. Entry logic
        entry_time = now + timedelta(minutes=1)
        expiry_time = entry_time + timedelta(minutes=2)
        entry_price = close[-1]
        confidence = min(90, int(abs(pct_change) * 200000))

        # Martingale table
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in [("M1", 1.5, 1), ("M2", 2.5, 2), ("M3", 4.0, 3)]:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append(
                {
                    "level": lvl,
                    "multiplier": mult,
                    "amount": round(mult, 2),
                    "entry_time": t.strftime("%H:%M"),
                }
            )

        color = "\U0001f7e2" if direction == "BUY" else "\U0001f534"
        arrow = "\u25b2" if direction == "BUY" else "\u25bc"
        lines = [
            "\u2501" * 24,
            "\U0001f525 OTC SCALPER SIGNAL",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')} (Lead 1 min)",
            f"\u23f1\ufe0f Expiry: {expiry_time.astimezone(WAT).strftime('%H:%M:%S')} (2 min)",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {adx_val:.1f} | RSI: {rsi:.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500",
        ]
        for m in martingale:
            lines.append(
                f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}"
            )
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Scalp & exit", "\u2501" * 24]
        formatted = "\n".join(lines)

        return {
            "formatted_signal": formatted,
            "direction": direction,
            "entry_price": entry_price,
            "confidence": confidence,
            "expiry": expiry_time.isoformat(),
            "timeframe": "M2",
            "platform": "iq",
            "indicators": {"adx": adx_val, "rsi": rsi},
        }

    def _rsi(self, close, period=14):
        deltas = np.diff(close)
        gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
        loss = -np.mean(deltas[deltas < 0]) if any(deltas < 0) else 0
        if loss == 0:
            return 100
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _adx(self, df, period=14):
        high, low, close = df["high"], df["low"], df["close"]
        tr = np.maximum(
            high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift()))
        )
        atr = tr.rolling(period).mean().iloc[-1]
        if atr == 0:
            return 0
        up = high.diff().clip(lower=0)
        down = -low.diff().clip(upper=0)
        di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
        di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
        dx = (
            100 * abs(di_plus - di_minus) / (di_plus + di_minus)
            if (di_plus + di_minus) != 0
            else 0
        )
        return dx


# ─── Keep-Alive ────────────────────────────────────────────
async def keep_alive():
    await asyncio.sleep(60)  # wait for full startup
    url = API_URL
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(url, timeout=10)
                print(f"Self-ping OK (status={r.status_code})")
            except Exception as e:
                print(f"Self-ping failed: {e}")
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()


# ─── FastAPI App ───────────────────────────────────────────
app = FastAPI(lifespan=lifespan, title="CATALYST AI Scalper", version="5.0")

# CORS for Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scalper = OTCScalperEngine()

# Track latest signals for multi-pair scanning
latest_scalp_signals: list = []
SCALP_PAIRS = [
    "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "GBPCAD-OTC",
    "AUDCAD-OTC", "EURJPY-OTC", "GBPJPY-OTC", "USDCAD-OTC",
    "XAUUSD-OTC",
]


# ─── Embedded Frontend ────────────────────────────────────
FRONTEND_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e1a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Catalyst AI – OTC Scalper</title>
<link rel="manifest" href="/manifest.json">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:12px}
.container{max-width:520px;width:100%}

/* ── Header ── */
.header{display:flex;justify-content:space-between;align-items:center;padding:14px 0;margin-bottom:12px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.6em;font-weight:bold;color:#00ff88;letter-spacing:-0.5px}
.logo span{color:#fff}
.status-pill{padding:4px 12px;border-radius:20px;font-size:.78em;font-weight:600;transition:all .3s}
.status-pill.live{background:rgba(0,255,136,.12);color:#00ff88}
.status-pill.waking{background:rgba(255,215,0,.12);color:#ffd700;animation:blink 1s infinite}
.status-pill.offline{background:rgba(255,68,68,.12);color:#ff5252}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}

/* ── Wake Banner ── */
.wake-banner{display:none;background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.15);border-radius:10px;padding:10px 14px;margin-bottom:12px;color:#ffd700;font-size:.82em;align-items:center;gap:8px}
.wake-banner.show{display:flex}
.spinner{width:14px;height:14px;border:2px solid rgba(255,215,0,.25);border-top:2px solid #ffd700;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── Pair Tabs ── */
.pair-tabs{display:flex;gap:5px;margin-bottom:12px;flex-wrap:wrap}
.pair-tab{padding:6px 14px;border-radius:15px;border:1px solid #1e2436;background:#0d1220;color:#888;cursor:pointer;font-size:.76em;transition:all .2s;white-space:nowrap}
.pair-tab:hover{border-color:#00ff88;color:#ccc}
.pair-tab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}

/* ── Signal Card ── */
.signal-card{background:#131829;border-radius:14px;padding:20px;margin-bottom:14px;border-left:4px solid;animation:fadeSlide .4s ease-out;position:relative}
.signal-card.buy{border-color:#00ff88}
.signal-card.sell{border-color:#ff5252}
.signal-card.no-signal{border-color:#333;background:#0d1117;text-align:center;padding:40px 20px}
@keyframes fadeSlide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.dir-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.direction{font-size:2rem;font-weight:bold}
.direction.buy{color:#00ff88}
.direction.sell{color:#ff5252}
.pair-name{font-size:1.1em;font-weight:600;color:#fff}
.detail-row{display:flex;justify-content:space-between;margin:5px 0;font-size:.85em;color:#aaa}
.detail-row .val{color:#e0e0e0;font-weight:500}
.confidence-bar{width:100%;height:6px;background:#1e2436;border-radius:3px;margin:10px 0 4px;overflow:hidden}
.confidence-fill{height:100%;border-radius:3px;transition:width .5s}
.confidence-fill.high{background:linear-gradient(90deg,#00ff88,#00cc6a)}
.confidence-fill.med{background:linear-gradient(90deg,#ffd700,#ffaa00)}
.confidence-fill.low{background:linear-gradient(90deg,#ff5252,#cc0000)}
.conf-label{font-size:.75em;color:#888;text-align:right}
.martingale{margin:14px 0 0;background:#0a0f1a;border-radius:8px;padding:10px 12px;border:1px solid #1a1f2e}
.mart-title{color:#ffd700;font-size:.8em;font-weight:bold;margin-bottom:6px}
.mart-row{display:flex;justify-content:space-between;padding:4px 0;font-size:.8em;border-bottom:1px solid #111827}
.mart-row:last-child{border-bottom:none}
.mart-level{color:#ffd700;font-weight:600;min-width:28px}
.mart-mult{color:#aaa}
.mart-amt{color:#fff;font-weight:600}
.mart-time{color:#666}
.risk-note{text-align:center;font-size:.72em;color:#555;margin-top:8px}

/* ── Scan All ── */
.scan-btn{width:100%;padding:12px;background:linear-gradient(135deg,#00ff88,#00cc6a);color:#0a0e1a;border:none;border-radius:10px;font-weight:bold;font-size:.9em;cursor:pointer;margin-bottom:14px;transition:transform .1s}
.scan-btn:active{transform:scale(.97)}
.scan-btn:disabled{opacity:.5;cursor:not-allowed}

/* ── Footer ── */
.footer{text-align:center;font-size:.7em;color:#444;margin-top:20px;padding:10px}
</style>
</head>
<body>
<div class="container">
  <!-- Header -->
  <div class="header">
    <div class="logo">CATALYST<span>AI</span> <span style="font-size:.5em;color:#888">SCALPER</span></div>
    <div class="status-pill" id="status">Connecting</div>
  </div>

  <!-- Wake Banner -->
  <div class="wake-banner" id="wakeBanner">
    <div class="spinner"></div>
    <span id="wakeText">Backend is waking up...</span>
  </div>

  <!-- Scan Button -->
  <button class="scan-btn" id="scanBtn" onclick="scanAll()">Scan All Pairs</button>

  <!-- Pair Tabs -->
  <div class="pair-tabs" id="pairTabs"></div>

  <!-- Signals -->
  <div id="signalsContainer">
    <div class="signal-card no-signal">
      <div style="font-size:2em;margin-bottom:10px">&#x23f3;</div>
      <div style="color:#888">Waiting for momentum setup...</div>
    </div>
  </div>

  <div class="footer">Trade at your own risk &middot; Risk 1-3% only &middot; WAT Timezone</div>
</div>

<script>
// ══════════════════════════════════════════════
//  CONFIG
// ══════════════════════════════════════════════
const API = window.location.origin;
const PAIRS = [
  'EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC',
  'AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC'
];
let activePair = PAIRS[0];
let signalCache = {};

// ══════════════════════════════════════════════
//  fetchWithRetry — Render Cold-Start Handler
// ══════════════════════════════════════════════
async function fetchWithRetry(url, retries = 5) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        if (i > 0) { hideWake(); console.log('Backend woke after', i+1, 'retries'); }
        return res;
      }
      const data = await res.json().catch(() => ({}));
      if (data.Message && data.Message.includes('pending')) {
        showWake('Backend waking... retry ' + (i+1) + '/' + retries);
        await new Promise(r => setTimeout(r, (i+1) * 3000));
        continue;
      }
      throw new Error(data.Message || 'Error ' + res.status);
    } catch (err) {
      if (i < retries - 1) {
        showWake('Connecting... retry ' + (i+1) + '/' + retries);
        await new Promise(r => setTimeout(r, (i+1) * 3000));
        continue;
      }
      throw err;
    }
  }
  throw new Error('Backend unavailable');
}

// ══════════════════════════════════════════════
//  UI HELPERS
// ══════════════════════════════════════════════
function setStatus(state) {
  const el = document.getElementById('status');
  el.className = 'status-pill ' + state;
  el.textContent = state === 'live' ? 'Live' : state === 'waking' ? 'Waking...' : 'Offline';
}
function showWake(text) {
  document.getElementById('wakeBanner').classList.add('show');
  document.getElementById('wakeText').textContent = text;
  setStatus('waking');
}
function hideWake() {
  document.getElementById('wakeBanner').classList.remove('show');
  setStatus('live');
}

// ══════════════════════════════════════════════
//  PAIR TABS
// ══════════════════════════════════════════════
function buildTabs() {
  const cont = document.getElementById('pairTabs');
  cont.innerHTML = '';
  PAIRS.forEach(p => {
    const btn = document.createElement('div');
    btn.className = 'pair-tab' + (p === activePair ? ' active' : '');
    btn.textContent = p.replace('-OTC','');
    btn.onclick = () => { activePair = p; buildTabs(); fetchScalp(p); };
    cont.appendChild(btn);
  });
}

// ══════════════════════════════════════════════
//  FETCH & RENDER
// ══════════════════════════════════════════════
async function fetchScalp(pair) {
  try {
    const res = await fetchWithRetry(API + '/signal/scalp?pair=' + pair);
    const data = await res.json();
    signalCache[pair] = data;
    renderSignal(data);
  } catch (e) {
    signalCache[pair] = null;
    renderNoSignal('Backend offline');
    setStatus('offline');
  }
}

async function scanAll() {
  const btn = document.getElementById('scanBtn');
  btn.disabled = true;
  btn.textContent = 'Scanning...';
  let found = 0;
  for (const p of PAIRS) {
    try {
      const res = await fetchWithRetry(API + '/signal/scalp?pair=' + p);
      const data = await res.json();
      signalCache[p] = data;
      found++;
    } catch (e) {
      signalCache[p] = null;
    }
  }
  btn.disabled = false;
  btn.textContent = 'Scan All Pairs (' + found + ' signals)';
  renderSignal(signalCache[activePair]);
  hideWake();
}

function renderSignal(s) {
  const cont = document.getElementById('signalsContainer');
  if (!s || !s.direction) {
    renderNoSignal('No momentum setup detected');
    return;
  }
  const cls = s.direction.toLowerCase();
  const confClass = s.confidence >= 70 ? 'high' : s.confidence >= 50 ? 'med' : 'low';
  const emoji = cls === 'buy' ? '&#x1f7e2;' : '&#x1f534;';
  const arrow = cls === 'buy' ? '&#9650;' : '&#9660;';

  let martHtml = '';
  if (s.martingale && s.martingale.length) {
    martHtml = '<div class="martingale"><div class="mart-title">&#x1f6e1;&#xfe0f; RECOVERY</div>';
    s.martingale.forEach(m => {
      martHtml += '<div class="mart-row">' +
        '<span class="mart-level">' + m.level + '</span>' +
        '<span class="mart-mult">' + m.multiplier + 'x</span>' +
        '<span class="mart-amt">$' + m.amount + '</span>' +
        '<span class="mart-time">' + m.entry_time + '</span>' +
      '</div>';
    });
    martHtml += '</div>';
  }

  cont.innerHTML =
    '<div class="signal-card ' + cls + '">' +
      '<div class="dir-row">' +
        '<span class="direction ' + cls + '">' + emoji + ' ' + s.direction + ' ' + arrow + '</span>' +
        '<span class="pair-name">' + s.pair + '</span>' +
      '</div>' +
      '<div class="detail-row"><span>Entry Price</span><span class="val">' + (s.entry_price ? s.entry_price.toFixed(5) : '--') + '</span></div>' +
      '<div class="detail-row"><span>Expiry</span><span class="val">2 min</span></div>' +
      '<div class="detail-row"><span>ADX</span><span class="val">' + (s.indicators ? s.indicators.adx.toFixed(1) : '--') + '</span></div>' +
      '<div class="detail-row"><span>RSI</span><span class="val">' + (s.indicators ? s.indicators.rsi.toFixed(1) : '--') + '</span></div>' +
      '<div class="confidence-bar"><div class="confidence-fill ' + confClass + '" style="width:' + s.confidence + '%"></div></div>' +
      '<div class="conf-label">' + s.confidence + '% confidence</div>' +
      martHtml +
      '<div class="risk-note">&#x26a0;&#xfe0f; Risk 1% only &middot; Scalp & exit</div>' +
    '</div>';
}

function renderNoSignal(msg) {
  const cont = document.getElementById('signalsContainer');
  cont.innerHTML =
    '<div class="signal-card no-signal">' +
      '<div style="font-size:2em;margin-bottom:10px">&#x23f3;</div>' +
      '<div style="color:#888">' + msg + '</div>' +
    '</div>';
}

// ══════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════
buildTabs();
fetchScalp(activePair);
setInterval(() => fetchScalp(activePair), 15000);
</script>
</body>
</html>"""


# ─── Routes ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the embedded frontend."""
    return FRONTEND_HTML


@app.get("/health")
async def health():
    """Health check (used by keep-alive and monitoring)."""
    return {
        "status": "online",
        "engine": "OTCScalperEngine",
        "pairs": SCALP_PAIRS,
        "signals_cached": len(latest_scalp_signals),
        "version": "5.0",
    }


@app.get("/signal/scalp")
async def scalp_signal(pair: str = "EURUSD-OTC"):
    """Generate a momentum scalping signal for the given OTC pair."""
    # In production, replace with real market data feed
    # For now, generate mock OHLCV that simulates live candles
    dates = pd.date_range(end=datetime.now(), periods=100, freq="1min")
    np.random.seed(hash(pair) % 2**32)

    # Simulate trending price with noise
    trend = np.linspace(0, 0.0004, 100) + np.random.randn(100) * 0.00008
    close = 1.08 + trend  # near EURUSD range
    if "JPY" in pair:
        close = 148.0 + trend * 100
    elif "XAU" in pair:
        close = 2350.0 + trend * 10000

    df = pd.DataFrame(
        {
            "open": close - 0.0002,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "volume": np.random.randint(80, 300, 100),
        }
    )

    signal = scalper.generate(df, pair)
    if not signal:
        return {
            "direction": None,
            "message": "No momentum setup detected for " + pair,
            "pair": pair,
            "confidence": 0,
        }

    # Cache the signal
    signal["pair"] = pair
    # Add martingale to response for frontend
    ent_wat = (datetime.now(pytz.UTC) + timedelta(minutes=1)).astimezone(WAT)
    signal["martingale"] = []
    for lvl, mult, delay in [("M1", 1.5, 1), ("M2", 2.5, 2), ("M3", 4.0, 3)]:
        t = ent_wat + timedelta(minutes=delay)
        signal["martingale"].append(
            {
                "level": lvl,
                "multiplier": mult,
                "amount": round(mult, 2),
                "entry_time": t.strftime("%H:%M"),
            }
        )

    latest_scalp_signals.insert(0, signal)
    if len(latest_scalp_signals) > 50:
        latest_scalp_signals.pop()

    return signal


@app.get("/signal/scalp/all")
async def scalp_all():
    """Scan all pairs and return any signals found."""
    results = []
    for pair in SCALP_PAIRS:
        try:
            dates = pd.date_range(end=datetime.now(), periods=100, freq="1min")
            np.random.seed(hash(pair) % 2**32)
            trend = np.linspace(0, 0.0004, 100) + np.random.randn(100) * 0.00008
            close = 1.08 + trend
            if "JPY" in pair:
                close = 148.0 + trend * 100
            elif "XAU" in pair:
                close = 2350.0 + trend * 10000
            df = pd.DataFrame(
                {
                    "open": close - 0.0002,
                    "high": close + 0.0005,
                    "low": close - 0.0005,
                    "close": close,
                    "volume": np.random.randint(80, 300, 100),
                }
            )
            sig = scalper.generate(df, pair)
            if sig:
                sig["pair"] = pair
                results.append(sig)
        except Exception:
            pass
    return {"count": len(results), "signals": results}


# ─── Manifest for PWA ─────────────────────────────────────
@app.get("/manifest.json")
async def manifest():
    return {
        "name": "CATALYST AI Scalper",
        "short_name": "CatalystAI",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0e1a",
        "theme_color": "#0a0e1a",
    }


# ─── Entry Point ──────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
