import asyncio, httpx, os, json
from datetime import datetime, timedelta
import numpy as np, pandas as pd, pytz
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

# ---------- CONFIG ----------
WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')

# Scalper settings (winning configuration)
SCALPER_CONFIG = {
    'volume_spike': 1.5,         # volume > 1.5x average
    'momentum_period': 3,        # last 3 candles
    'min_momentum_pct': 0.0002,  # 0.02% move
    'adx_threshold': 20,         # weak trend is acceptable
    'rsi_limit': 70,             # avoid top
    'rsi_floor': 30,             # avoid bottom
    'trade_sessions': [(8, 17)]  # London/NY only (UTC hours)
}

# Pocket Option valid timeframes
PO_TIMEFRAMES = ['S3', 'S15', 'S30', 'M1', 'M3', 'M5']
# IQ Option valid timeframes
IQ_TIMEFRAMES = ['30s', '45s', '1m', '2m', '3m', '5m']

# OTC pairs
OTC_PAIRS = [
    'EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'GBPCAD-OTC',
    'AUDCAD-OTC', 'EURJPY-OTC', 'GBPJPY-OTC', 'USDCAD-OTC', 'XAUUSD-OTC'
]


# ---------- SCALPER ENGINE ----------
class OTCScalper:
    def generate_signal(self, df: pd.DataFrame, pair: str, timeframe: str, platform: str) -> dict | None:
        if len(df) < 10:
            return None
        close = df['close'].values
        volume = df.get('volume', pd.Series([1] * len(df))).values
        avg_vol = np.mean(volume[-10:-1])
        if volume[-1] < avg_vol * SCALPER_CONFIG['volume_spike']:
            return None

        # Momentum
        if len(close) < 4:
            return None
        pct = (close[-1] / close[-4] - 1)
        if abs(pct) < SCALPER_CONFIG['min_momentum_pct']:
            return None
        direction = 'BUY' if pct > 0 else 'SELL'

        # RSI filter
        rsi = self._rsi(close, 14)
        if direction == 'BUY' and rsi > SCALPER_CONFIG['rsi_limit']:
            return None
        if direction == 'SELL' and rsi < SCALPER_CONFIG['rsi_floor']:
            return None

        # ADX
        adx = self._adx(df, 14)
        if adx < SCALPER_CONFIG['adx_threshold']:
            return None

        # Session
        now = datetime.now(pytz.UTC)
        if not any(start <= now.hour < end for (start, end) in SCALPER_CONFIG['trade_sessions']):
            return None

        # Time calculation
        tf_seconds = {
            '30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300,
            'S3': 3, 'S15': 15, 'S30': 30, 'M1': 60, 'M3': 180, 'M5': 300
        }
        duration = tf_seconds.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)

        entry_price = close[-1]
        confidence = min(90, int(abs(pct) * 200000))

        # Martingale
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in [('M1', 1.5, 1), ('M2', 2.5, 2), ('M3', 4.0, 3)]:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level': lvl, 'multiplier': mult,
                'amount': round(mult, 2),
                'entry_time': t.strftime('%H:%M')
            })

        color = "\U0001f7e2" if direction == 'BUY' else "\U0001f534"
        arrow = "\u25b2" if direction == 'BUY' else "\u25bc"
        lines = [
            "\u2501" * 24,
            f"\U0001f525 OTC SCALPER ({platform.upper()})",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {adx:.1f} | RSI: {rsi:.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Scalp & exit", "\u2501" * 24]
        return {
            'formatted_signal': '\n'.join(lines),
            'direction': direction,
            'entry_price': entry_price,
            'confidence': confidence,
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform,
            'martingale': martingale,
            'indicators': {'adx': adx, 'rsi': rsi}
        }

    def _rsi(self, close, period=14):
        delta = np.diff(close)
        gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
        loss = -np.mean(delta[delta < 0]) if any(delta < 0) else 0
        if loss == 0: return 100
        return 100 - (100 / (1 + gain / loss))

    def _adx(self, df, period=14):
        high, low, close = df['high'], df['low'], df['close']
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
        atr = tr.rolling(period).mean().iloc[-1]
        if atr == 0: return 0
        up = high.diff().clip(lower=0)
        down = -low.diff().clip(upper=0)
        di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
        di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) != 0 else 0
        return dx


# ---------- KEEP ALIVE ----------
async def keep_alive():
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(API_URL, timeout=10)
                print("\u2705 Self-ping OK")
            except Exception as e:
                print(f"\u274c Self-ping failed: {e}")
            await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()


# ---------- FASTAPI ----------
app = FastAPI(lifespan=lifespan, title="CATALYST AI Scalper", version="5.1")
scalper = OTCScalper()
latest_signals: list = []

# ---------- FRONTEND HTML (embedded) ----------
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e1a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Catalyst AI Scalper</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:12px}
.container{max-width:520px;width:100%}

/* Header */
.header{display:flex;justify-content:space-between;align-items:center;padding:14px 0;margin-bottom:12px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.5em;font-weight:bold;color:#00ff88;letter-spacing:-0.5px}
.logo span{color:#fff}
.status-pill{padding:4px 12px;border-radius:20px;font-size:.78em;font-weight:600;transition:all .3s}
.status-pill.live{background:rgba(0,255,136,.12);color:#00ff88}
.status-pill.waking{background:rgba(255,215,0,.12);color:#ffd700;animation:blink 1s infinite}
.status-pill.offline{background:rgba(255,68,68,.12);color:#ff5252}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}

/* Wake Banner */
.wake-banner{display:none;background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.15);border-radius:10px;padding:10px 14px;margin-bottom:12px;color:#ffd700;font-size:.82em;align-items:center;gap:8px}
.wake-banner.show{display:flex}
.spinner{width:14px;height:14px;border:2px solid rgba(255,215,0,.25);border-top:2px solid #ffd700;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Platform Tabs */
.platform-tabs{display:flex;justify-content:center;gap:8px;margin-bottom:12px}
.ptab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:8px 20px;border-radius:20px;cursor:pointer;font-size:.85em;font-weight:500;transition:all .2s}
.ptab.active{background:#00ff88;color:#0a0e1a;border-color:#00ff88;font-weight:700}
.ptab:hover{border-color:#00ff88}

/* Timeframe Tabs */
.tf-tabs{display:flex;justify-content:center;gap:5px;margin-bottom:14px;flex-wrap:wrap}
.tftab{background:#0d1220;border:1px solid #1e2436;color:#888;padding:5px 14px;border-radius:15px;cursor:pointer;font-size:.76em;transition:all .2s;white-space:nowrap}
.tftab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}
.tftab:hover{border-color:#00ff88;color:#ccc}

/* Pair Tabs */
.pair-tabs{display:flex;gap:5px;margin-bottom:12px;flex-wrap:wrap}
.pair-tab{padding:5px 12px;border-radius:12px;border:1px solid #1e2436;background:#0d1220;color:#777;cursor:pointer;font-size:.72em;transition:all .2s;white-space:nowrap}
.pair-tab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}
.pair-tab:hover{border-color:#00ff88;color:#aaa}

/* Signal Card */
.signal-card{background:#131829;border-radius:14px;padding:20px;margin-bottom:14px;border-left:4px solid;animation:fadeSlide .4s ease-out}
.signal-card.buy{border-color:#00ff88}
.signal-card.sell{border-color:#ff5252}
.signal-card.no-signal{border-color:#333;background:#0d1117;text-align:center;padding:40px 20px}
@keyframes fadeSlide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.dir-row{display:flex;align-items:center;justify-content:space-between;margin:8px 0}
.direction{font-size:1.8rem;font-weight:bold}
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
.copy-btn{width:100%;padding:10px;background:#00ff88;color:#0a0e1a;border:none;border-radius:8px;font-weight:bold;margin-top:10px;cursor:pointer;font-size:.85em;transition:transform .1s}
.copy-btn:active{transform:scale(.97)}
.scan-btn{width:100%;padding:12px;background:linear-gradient(135deg,#00ff88,#00cc6a);color:#0a0e1a;border:none;border-radius:10px;font-weight:bold;font-size:.9em;cursor:pointer;margin-bottom:14px;transition:transform .1s}
.scan-btn:active{transform:scale(.97)}
.scan-btn:disabled{opacity:.5;cursor:not-allowed}
.footer{text-align:center;font-size:.7em;color:#444;margin-top:20px;padding:10px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="logo">CATALYST<span>AI</span> <span style="font-size:.5em;color:#888">SCALPER</span></div>
    <div class="status-pill" id="status">Connecting</div>
  </div>

  <div class="wake-banner" id="wakeBanner">
    <div class="spinner"></div>
    <span id="wakeText">Backend is waking up...</span>
  </div>

  <!-- Platform Tabs -->
  <div class="platform-tabs">
    <div class="ptab active" data-platform="iq" onclick="setPlatform(this,'iq')">IQ Option</div>
    <div class="ptab" data-platform="pocket" onclick="setPlatform(this,'pocket')">Pocket Option</div>
  </div>

  <!-- Timeframe Tabs (changes per platform) -->
  <div class="tf-tabs" id="tfTabs"></div>

  <!-- Pair Tabs -->
  <div class="pair-tabs" id="pairTabs"></div>

  <!-- Scan Button -->
  <button class="scan-btn" id="scanBtn" onclick="scanAll()">Scan All Pairs</button>

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
// ═══════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════
const API = window.location.origin;
const PAIRS = ['EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC','AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC'];
const IQ_TFS = ['30s','45s','1m','2m','3m','5m'];
const PO_TFS = ['S3','S15','S30','M1','M3','M5'];

let platform = 'iq';
let tf = '1m';
let activePair = PAIRS[0];
let signalCache = {};

// ═══════════════════════════════════════
//  fetchWithRetry — Render Cold Start
// ═══════════════════════════════════════
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

// ═══════════════════════════════════════
//  UI HELPERS
// ═══════════════════════════════════════
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
function setPlatform(btn, p) {
  document.querySelectorAll('.ptab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  platform = p;
  buildTfTabs();
  fetchSignal();
}

// ═══════════════════════════════════════
//  TIMEFRAME TABS (per platform)
// ═══════════════════════════════════════
function buildTfTabs() {
  const tfs = platform === 'iq' ? IQ_TFS : PO_TFS;
  if (!tfs.includes(tf)) tf = tfs[0];
  const cont = document.getElementById('tfTabs');
  cont.innerHTML = '';
  tfs.forEach(t => {
    const btn = document.createElement('div');
    btn.className = 'tftab' + (t === tf ? ' active' : '');
    btn.textContent = t;
    btn.onclick = () => { tf = t; buildTfTabs(); fetchSignal(); };
    cont.appendChild(btn);
  });
}

// ═══════════════════════════════════════
//  PAIR TABS
// ═══════════════════════════════════════
function buildPairTabs() {
  const cont = document.getElementById('pairTabs');
  cont.innerHTML = '';
  PAIRS.forEach(p => {
    const btn = document.createElement('div');
    btn.className = 'pair-tab' + (p === activePair ? ' active' : '');
    btn.textContent = p.replace('-OTC','');
    btn.onclick = () => { activePair = p; buildPairTabs(); fetchSignal(); };
    cont.appendChild(btn);
  });
}

// ═══════════════════════════════════════
//  FETCH & RENDER
// ═══════════════════════════════════════
async function fetchSignal() {
  try {
    const res = await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${activePair}&timeframe=${tf}`);
    const data = await res.json();
    if (data.formatted_signal) {
      signalCache[activePair] = data;
      renderSignal(data);
      setStatus('live');
    } else {
      signalCache[activePair] = null;
      renderNoSignal(data.message || 'No momentum setup');
      setStatus('live');
    }
  } catch (e) {
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
      const res = await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${p}&timeframe=${tf}`);
      const data = await res.json();
      if (data.formatted_signal) {
        signalCache[p] = data;
        found++;
      } else {
        signalCache[p] = null;
      }
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
  if (!s || !s.formatted_signal) { renderNoSignal('No momentum setup'); return; }
  const cls = s.direction.toLowerCase();
  const confClass = s.confidence >= 70 ? 'high' : s.confidence >= 50 ? 'med' : 'low';

  let martHtml = '';
  if (s.martingale && s.martingale.length) {
    martHtml = '<div class="martingale"><div class="mart-title">\U0001f6e1\ufe0f RECOVERY</div>';
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

  const emoji = cls === 'buy' ? '\U0001f7e2' : '\U0001f534';
  const arrow = cls === 'buy' ? '\u25b2' : '\u25bc';

  cont.innerHTML =
    '<div class="signal-card ' + cls + '">' +
      '<div class="dir-row">' +
        '<span class="direction ' + cls + '">' + emoji + ' ' + s.direction + ' ' + arrow + '</span>' +
        '<span class="pair-name">' + s.platform.toUpperCase() + ' · ' + (s.pair || activePair) + '</span>' +
      '</div>' +
      '<div class="detail-row"><span>Entry Price</span><span class="val">' + (s.entry_price ? s.entry_price.toFixed(5) : '--') + '</span></div>' +
      '<div class="detail-row"><span>Expiry</span><span class="val">' + s.timeframe + '</span></div>' +
      '<div class="detail-row"><span>ADX</span><span class="val">' + (s.indicators ? s.indicators.adx.toFixed(1) : '--') + '</span></div>' +
      '<div class="detail-row"><span>RSI</span><span class="val">' + (s.indicators ? s.indicators.rsi.toFixed(1) : '--') + '</span></div>' +
      '<div class="confidence-bar"><div class="confidence-fill ' + confClass + '" style="width:' + s.confidence + '%"></div></div>' +
      '<div class="conf-label">' + s.confidence + '% confidence</div>' +
      martHtml +
      '<div class="risk-note">\u26a0\ufe0f Risk 1% only \u00b7 Scalp & exit</div>' +
      '<button class="copy-btn" onclick="navigator.clipboard.writeText(\`' + s.formatted_signal.replace(/`/g,"\\`").replace(/\\/g,"\\\\") + '\`)">\U0001f4cb Copy Signal</button>' +
    '</div>';
}

function renderNoSignal(msg) {
  document.getElementById('signalsContainer').innerHTML =
    '<div class="signal-card no-signal">' +
      '<div style="font-size:2em;margin-bottom:10px">\u23f3</div>' +
      '<div style="color:#888">' + msg + '</div>' +
    '</div>';
}

// ═══════════════════════════════════════
//  INIT
// ═══════════════════════════════════════
buildTfTabs();
buildPairTabs();
fetchSignal();
setInterval(fetchSignal, 15000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {
        "status": "online",
        "engine": "OTCScalper",
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "pairs": OTC_PAIRS,
        "signals_cached": len(latest_signals),
        "version": "5.1",
    }


@app.get("/signal")
async def get_signal(platform: str = "iq", pair: str = "EURUSD-OTC", timeframe: str = "1m"):
    """Generate a momentum scalping signal for the given pair/timeframe/platform."""
    # Validate platform/timeframe
    if platform == 'iq':
        if timeframe not in IQ_TIMEFRAMES:
            raise HTTPException(400, f"Invalid timeframe for IQ Option. Use one of: {IQ_TIMEFRAMES}")
    elif platform == 'pocket':
        if timeframe not in PO_TIMEFRAMES:
            raise HTTPException(400, f"Invalid timeframe for Pocket Option. Use one of: {PO_TIMEFRAMES}")
    else:
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")

    # Simulate data (replace with real feed in production)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='1min')
    np.random.seed(hash(pair) % 2**32)
    trend = np.linspace(0, 0.0003, 100) + np.random.randn(100) * 0.0001
    close = 1.0 + trend
    if "JPY" in pair:
        close = 148.0 + trend * 100
    elif "XAU" in pair:
        close = 2350.0 + trend * 10000
    elif "GBP" in pair or "CAD" in pair:
        close = 1.35 + trend
    elif "AUD" in pair:
        close = 0.65 + trend

    df = pd.DataFrame({
        'open': close - 0.0002,
        'high': close + 0.0005,
        'low': close - 0.0005,
        'close': close,
        'volume': np.random.randint(50, 200, 100)
    })
    signal = scalper.generate_signal(df, pair, timeframe, platform)
    if not signal:
        return {
            "formatted_signal": None,
            "direction": None,
            "message": "No momentum setup detected for " + pair,
            "pair": pair,
            "platform": platform,
            "timeframe": timeframe,
            "confidence": 0,
        }

    signal["pair"] = pair
    latest_signals.insert(0, signal)
    if len(latest_signals) > 50:
        latest_signals.pop()

    return signal


@app.get("/signal/all")
async def scan_all(platform: str = "iq", timeframe: str = "1m"):
    """Scan all OTC pairs for momentum setups."""
    results = []
    for pair in OTC_PAIRS:
        try:
            dates = pd.date_range(end=datetime.now(), periods=100, freq='1min')
            np.random.seed(hash(pair) % 2**32)
            trend = np.linspace(0, 0.0003, 100) + np.random.randn(100) * 0.0001
            close = 1.0 + trend
            if "JPY" in pair: close = 148.0 + trend * 100
            elif "XAU" in pair: close = 2350.0 + trend * 10000
            elif "GBP" in pair or "CAD" in pair: close = 1.35 + trend
            elif "AUD" in pair: close = 0.65 + trend
            df = pd.DataFrame({
                'open': close - 0.0002,
                'high': close + 0.0005,
                'low': close - 0.0005,
                'close': close,
                'volume': np.random.randint(50, 200, 100)
            })
            sig = scalper.generate_signal(df, pair, timeframe, platform)
            if sig:
                sig["pair"] = pair
                results.append(sig)
        except Exception:
            pass
    return {"count": len(results), "signals": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
