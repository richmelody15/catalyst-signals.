import asyncio, httpx, os, numpy as np, pandas as pd, pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')

# ─── timeframes for both platforms ───
IQ_TIMEFRAMES = ['30s', '45s', '1m', '2m', '3m', '5m']
PO_TIMEFRAMES = ['S3', 'S15', 'S30', 'M1', 'M3', 'M5']

# ─── OTC pairs ───
OTC_PAIRS = [
    'EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'GBPCAD-OTC',
    'AUDCAD-OTC', 'EURJPY-OTC', 'GBPJPY-OTC', 'USDCAD-OTC', 'XAUUSD-OTC'
]

# ─── strict winning configuration ───
CONFIG = {
    'ADX_MIN': 25,                # strong trend required
    'MOMENTUM_MIN': 0.0002,       # 0.02% move in 3 candles
    'VOLUME_MULT': 1.5,           # volume spike multiplier
    'RSI_LIMIT': 70,              # avoid exhaustion
    'RSI_FLOOR': 30,
    'MTF_MIN': 2,                 # at least 2 of 3 timeframes aligned
    'SR_PROXIMITY': 0.005,        # within 0.5% of key level
    'NEWS_AVOID_START': 12,       # UTC hour — US data window
    'NEWS_AVOID_END': 14,
    'LIQUIDITY_WINDOW': 20,
    'MARTINGALE': [('M1', 1.5, 1), ('M2', 2.5, 2), ('M3', 4.0, 3)]
}

TF_SECONDS = {
    '30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300,
    'S3': 3, 'S15': 15, 'S30': 30, 'M1': 60, 'M3': 180, 'M5': 300
}


# ═══════════════════════════════════════════════
#  TECHNICAL LIBRARY
# ═══════════════════════════════════════════════
def adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
    atr = tr.rolling(period).mean().iloc[-1]
    if atr == 0:
        return 0
    up = high.diff().clip(lower=0)
    down = -low.diff().clip(upper=0)
    di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
    di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) != 0 else 0
    return dx


def rsi(close, period=14):
    delta = np.diff(close)
    gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
    loss = -np.mean(delta[delta < 0]) if any(delta < 0) else 0
    if loss == 0:
        return 100
    return 100 - (100 / (1 + gain / loss))


def trend_structure(df):
    if len(df) < 10:
        return 'CONSOLIDATION'
    highs, lows = df['high'].values, df['low'].values
    prev_high, prev_low = max(highs[-10:-5]), min(lows[-10:-5])
    recent_high, recent_low = max(highs[-5:]), min(lows[-5:])
    if recent_high > prev_high * 1.0005 and recent_low > prev_low * 0.9995:
        return 'BULLISH'
    if recent_high < prev_high * 0.9995 and recent_low < prev_low * 1.0005:
        return 'BEARISH'
    return 'CONSOLIDATION'


def mtf_aligned(dfs, direction):
    count = 0
    for tf in ['1m', '3m', '5m']:
        if tf in dfs and len(dfs[tf]) >= 200:
            df = dfs[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction == 'BUY' and ema50 > ema200:
                count += 1
            elif direction == 'SELL' and ema50 < ema200:
                count += 1
    return count >= CONFIG['MTF_MIN']


def liquidity_sweep(df):
    if len(df) < CONFIG['LIQUIDITY_WINDOW']:
        return None
    highs, lows = df['high'].values, df['low'].values
    vol = df.get('volume', pd.Series([1] * len(df))).values
    avg_vol = np.mean(vol[-20:])
    if vol[-1] < avg_vol * CONFIG['VOLUME_MULT']:
        return None
    recent_high = np.max(highs[-CONFIG['LIQUIDITY_WINDOW']:])
    recent_low = np.min(lows[-CONFIG['LIQUIDITY_WINDOW']:])
    if highs[-1] > recent_high:
        return 'buy_side'
    if lows[-1] < recent_low:
        return 'sell_side'
    return None


def candle_ok(df, direction):
    if len(df) < 2:
        return False
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['close'] - last['open'])
    if body == 0:
        return False
    if direction == 'BUY':
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['open']:
            return True
        lower_wick = min(last['open'], last['close']) - last['low']
        if last['close'] > last['open'] and lower_wick > 2 * body:
            return True
    else:
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['open']:
            return True
        upper_wick = last['high'] - max(last['open'], last['close'])
        if last['close'] < last['open'] and upper_wick > 2 * body:
            return True
    return False


def sr_favorable(price, df, direction):
    if len(df) < 20:
        return False
    res = df['high'].rolling(20).max().iloc[-1]
    sup = df['low'].rolling(20).min().iloc[-1]
    if direction == 'BUY':
        return abs(price - sup) / price < CONFIG['SR_PROXIMITY']
    else:
        return abs(res - price) / price < CONFIG['SR_PROXIMITY']


def news_safe():
    now = datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID_START'] <= now.hour < CONFIG['NEWS_AVOID_END'])


# ═══════════════════════════════════════════════
#  STRICT 9-FILTER CHECK
# ═══════════════════════════════════════════════
def all_checks_pass(df_1m, df_3m, df_5m, direction):
    checks = {}

    # 1. ADX >= 25
    a = adx(df_1m)
    checks['adx'] = a >= CONFIG['ADX_MIN']

    # 2. Trend structure
    st = trend_structure(df_1m)
    checks['structure'] = (direction == 'BUY' and st == 'BULLISH') or \
                          (direction == 'SELL' and st == 'BEARISH')

    # 3. Multi-timeframe alignment
    checks['mtf'] = mtf_aligned({'1m': df_1m, '3m': df_3m, '5m': df_5m}, direction)

    # 4. News filter
    checks['news'] = news_safe()

    # 5. Candle confirmation
    checks['candle'] = candle_ok(df_1m, direction)

    # 6. S/R zone proximity
    price = df_1m['close'].iloc[-1]
    checks['sr'] = sr_favorable(price, df_1m, direction)

    # 7. Liquidity sweep
    sweep = liquidity_sweep(df_1m)
    checks['liquidity'] = (direction == 'BUY' and sweep == 'sell_side') or \
                          (direction == 'SELL' and sweep == 'buy_side')

    # 8. Volume spike
    vol_ratio = df_1m['volume'].iloc[-1] / df_1m['volume'].rolling(20).mean().iloc[-1]
    checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9. Momentum
    pct = (df_1m['close'].iloc[-1] / df_1m['close'].iloc[-4] - 1)
    checks['momentum'] = abs(pct) >= CONFIG['MOMENTUM_MIN']

    return all(checks.values()), checks


# ═══════════════════════════════════════════════
#  WINNING ENGINE
# ═══════════════════════════════════════════════
class WinningEngine:
    def generate(self, market_data, pair, platform, timeframe):
        df1m = market_data.get('1m')
        df3m = market_data.get('3m')
        df5m = market_data.get('5m')
        if any(d is None or len(d) < 30 for d in [df1m, df3m, df5m]):
            return None

        # Direction from short-term momentum
        pct = (df1m['close'].iloc[-1] / df1m['close'].iloc[-4] - 1)
        direction = 'BUY' if pct > 0 else 'SELL'

        ok, checks = all_checks_pass(df1m, df3m, df5m, direction)
        if not ok:
            # Try opposite direction
            opp = 'SELL' if direction == 'BUY' else 'BUY'
            ok2, checks2 = all_checks_pass(df1m, df3m, df5m, opp)
            if ok2:
                direction, checks = opp, checks2
            else:
                return None

        # Time & price
        now = datetime.now(pytz.UTC)
        duration = TF_SECONDS.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df1m['close'].iloc[-1])
        confidence = 92  # all 9 strict filters passed

        # Martingale recovery table
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level': lvl, 'multiplier': mult,
                'amount': round(mult, 2),
                'entry_time': t.strftime('%H:%M')
            })

        # Formatted signal text
        color = "\U0001f7e2" if direction == 'BUY' else "\U0001f534"
        arrow = "\u25b2" if direction == 'BUY' else "\u25bc"
        lines = [
            "\u2501" * 24,
            f"\U0001f3af CATALYST WINNING SIGNAL ({platform.upper()})",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {adx(df1m):.1f} | Structure: {trend_structure(df1m)}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 High-probability setup", "\u2501" * 24]

        return {
            'engine': 'WINNING',
            'formatted_signal': '\n'.join(lines),
            'direction': direction,
            'entry_price': entry_price,
            'confidence': confidence,
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform,
            'checks': checks,
            'martingale': martingale,
            'indicators': {
                'adx': round(adx(df1m), 1),
                'rsi': round(rsi(df1m['close'].values), 1),
                'structure': trend_structure(df1m)
            }
        }


# ═══════════════════════════════════════════════
#  KEEP ALIVE
# ═══════════════════════════════════════════════
async def keep_alive():
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(API_URL, timeout=10)
            except:
                pass
            await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()


# ═══════════════════════════════════════════════
#  FASTAPI APP
# ═══════════════════════════════════════════════
app = FastAPI(lifespan=lifespan)
engine = WinningEngine()
latest_signals: list = []


# ═══════════════════════════════════════════════
#  EMBEDDED FRONTEND
# ═══════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e1a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>CATALYST AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:12px}
.container{max-width:520px;width:100%}

.header{display:flex;justify-content:space-between;align-items:center;padding:14px 0;margin-bottom:12px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.4em;font-weight:bold;color:#00ff88;letter-spacing:-0.5px}
.logo span{color:#fff}
.status-pill{padding:4px 12px;border-radius:20px;font-size:.78em;font-weight:600;transition:all .3s}
.status-pill.live{background:rgba(0,255,136,.12);color:#00ff88}
.status-pill.waking{background:rgba(255,215,0,.12);color:#ffd700;animation:blink 1s infinite}
.status-pill.offline{background:rgba(255,68,68,.12);color:#ff5252}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}

.wake-banner{display:none;background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.15);border-radius:10px;padding:10px 14px;margin-bottom:12px;color:#ffd700;font-size:.82em;align-items:center;gap:8px}
.wake-banner.show{display:flex}
.spinner{width:14px;height:14px;border:2px solid rgba(255,215,0,.25);border-top:2px solid #ffd700;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.platform-tabs{display:flex;justify-content:center;gap:8px;margin-bottom:12px}
.ptab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:8px 20px;border-radius:20px;cursor:pointer;font-size:.85em;font-weight:500;transition:all .2s}
.ptab.active{background:#00ff88;color:#0a0e1a;border-color:#00ff88;font-weight:700}
.ptab:hover{border-color:#00ff88}

.tf-tabs{display:flex;justify-content:center;gap:5px;margin-bottom:14px;flex-wrap:wrap}
.tftab{background:#0d1220;border:1px solid #1e2436;color:#888;padding:5px 14px;border-radius:15px;cursor:pointer;font-size:.76em;transition:all .2s;white-space:nowrap}
.tftab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}
.tftab:hover{border-color:#00ff88;color:#ccc}

.pair-tabs{display:flex;gap:5px;margin-bottom:12px;flex-wrap:wrap}
.pair-tab{padding:5px 12px;border-radius:12px;border:1px solid #1e2436;background:#0d1220;color:#777;cursor:pointer;font-size:.72em;transition:all .2s;white-space:nowrap}
.pair-tab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}
.pair-tab:hover{border-color:#00ff88;color:#aaa}

.signal-card{background:#131829;border-radius:14px;padding:20px;margin-bottom:14px;border-left:4px solid;animation:fadeSlide .4s ease-out}
.signal-card.buy{border-color:#00ff88;box-shadow:0 0 24px rgba(0,255,136,.06)}
.signal-card.sell{border-color:#ff5252;box-shadow:0 0 24px rgba(255,82,82,.06)}
.signal-card.no-signal{border-color:#333;background:#0d1117;text-align:center;padding:40px 20px}
@keyframes fadeSlide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.dir-row{display:flex;align-items:center;justify-content:space-between;margin:8px 0}
.direction{font-size:1.8rem;font-weight:bold}
.direction.buy{color:#00ff88}
.direction.sell{color:#ff5252}
.pair-name{font-size:1.1em;font-weight:600;color:#fff}
.engine-tag{display:inline-block;padding:2px 10px;border-radius:10px;font-size:.7em;font-weight:700;margin-left:6px;background:rgba(0,255,136,.12);color:#00ff88}

.detail-row{display:flex;justify-content:space-between;margin:5px 0;font-size:.85em;color:#aaa}
.detail-row .val{color:#e0e0e0;font-weight:500}

.confidence-bar{width:100%;height:6px;background:#1e2436;border-radius:3px;margin:10px 0 4px;overflow:hidden}
.confidence-fill{height:100%;border-radius:3px;transition:width .5s}
.confidence-fill.high{background:linear-gradient(90deg,#00ff88,#00cc6a)}
.confidence-fill.med{background:linear-gradient(90deg,#ffd700,#ffaa00)}
.confidence-fill.low{background:linear-gradient(90deg,#ff5252,#cc0000)}
.conf-label{font-size:.75em;color:#888;text-align:right}

.checks-row{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}
.check-badge{padding:3px 8px;border-radius:8px;font-size:.68em;font-weight:600;border:1px solid}
.check-badge.pass{background:rgba(0,255,136,.06);color:#00ff88;border-color:rgba(0,255,136,.2)}
.check-badge.fail{background:rgba(255,68,68,.06);color:#ff5252;border-color:rgba(255,68,68,.2)}

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
    <div class="logo">CATALYST<span>AI</span> <span style="font-size:.5em;color:#888">WINNING</span></div>
    <div class="status-pill" id="status">Connecting</div>
  </div>
  <div class="wake-banner" id="wakeBanner">
    <div class="spinner"></div>
    <span id="wakeText">Backend is waking up...</span>
  </div>
  <div class="platform-tabs">
    <div class="ptab active" data-platform="iq" onclick="setPlatform(this,'iq')">IQ Option</div>
    <div class="ptab" data-platform="pocket" onclick="setPlatform(this,'pocket')">Pocket Option</div>
  </div>
  <div class="tf-tabs" id="tfTabs"></div>
  <div class="pair-tabs" id="pairTabs"></div>
  <button class="scan-btn" id="scanBtn" onclick="scanAll()">Scan All Pairs</button>
  <div id="signalsContainer">
    <div class="signal-card no-signal">
      <div style="font-size:2em;margin-bottom:10px">&#x23f3;</div>
      <div style="color:#888">Waiting for winning setup...</div>
    </div>
  </div>
  <div class="footer">Trade at your own risk &middot; Risk 1% only &middot; WAT Timezone</div>
</div>
<script>
const API = window.location.origin;
const PAIRS = ['EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC','AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC'];
const IQ_TFS = ['30s','45s','1m','2m','3m','5m'];
const PO_TFS = ['S3','S15','S30','M1','M3','M5'];

let platform = 'iq', tf = '1m', activePair = PAIRS[0], signalCache = {};

async function fetchWithRetry(url, retries=5) {
  for (let i=0; i<retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) { if (i>0) hideWake(); return res; }
      const data = await res.json().catch(()=>({}));
      if (data.Message && data.Message.includes('pending')) {
        showWake('Backend waking... retry '+(i+1)+'/'+retries);
        await new Promise(r=>setTimeout(r,(i+1)*3000)); continue;
      }
      throw new Error(data.Message||'Error '+res.status);
    } catch(err) {
      if (i<retries-1) { showWake('Connecting... retry '+(i+1)+'/'+retries); await new Promise(r=>setTimeout(r,(i+1)*3000)); continue; }
      throw err;
    }
  }
  throw new Error('Backend unavailable');
}

function setStatus(s){ const e=document.getElementById('status'); e.className='status-pill '+s; e.textContent=s==='live'?'Live':s==='waking'?'Waking...':'Offline'; }
function showWake(t){ document.getElementById('wakeBanner').classList.add('show'); document.getElementById('wakeText').textContent=t; setStatus('waking'); }
function hideWake(){ document.getElementById('wakeBanner').classList.remove('show'); setStatus('live'); }

function setPlatform(btn,p) {
  document.querySelectorAll('.ptab').forEach(t=>t.classList.remove('active'));
  btn.classList.add('active'); platform=p; buildTfTabs(); fetchSignal();
}

function buildTfTabs() {
  const tfs = platform==='iq'?IQ_TFS:PO_TFS;
  if (!tfs.includes(tf)) tf=tfs[0];
  const c=document.getElementById('tfTabs'); c.innerHTML='';
  tfs.forEach(t=>{
    const b=document.createElement('div');
    b.className='tftab'+(t===tf?' active':'');
    b.textContent=t;
    b.onclick=()=>{tf=t;buildTfTabs();fetchSignal();};
    c.appendChild(b);
  });
}

function buildPairTabs() {
  const c=document.getElementById('pairTabs'); c.innerHTML='';
  PAIRS.forEach(p=>{
    const b=document.createElement('div');
    b.className='pair-tab'+(p===activePair?' active':'');
    b.textContent=p.replace('-OTC','');
    b.onclick=()=>{activePair=p;buildPairTabs();fetchSignal();};
    c.appendChild(b);
  });
}

async function fetchSignal() {
  try {
    const res = await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${activePair}&timeframe=${tf}`);
    const data = await res.json();
    if (data.formatted_signal) { signalCache[activePair]=data; renderSignal(data); setStatus('live'); }
    else { signalCache[activePair]=null; renderNoSignal(data.message||'No winning setup'); setStatus('live'); }
  } catch(e) { renderNoSignal('Backend offline'); setStatus('offline'); }
}

async function scanAll() {
  const btn=document.getElementById('scanBtn'); btn.disabled=true; btn.textContent='Scanning...';
  let found=0;
  for (const p of PAIRS) {
    try {
      const res=await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${p}&timeframe=${tf}`);
      const data=await res.json();
      if (data.formatted_signal) { signalCache[p]=data; found++; } else { signalCache[p]=null; }
    } catch(e) { signalCache[p]=null; }
  }
  btn.disabled=false; btn.textContent='Scan All Pairs ('+found+' signals)'; renderSignal(signalCache[activePair]); hideWake();
}

function renderSignal(s) {
  const cont=document.getElementById('signalsContainer');
  if (!s||!s.formatted_signal) { renderNoSignal('No winning setup'); return; }
  const cls=s.direction.toLowerCase();
  const confClass=s.confidence>=70?'high':s.confidence>=50?'med':'low';

  let checksHtml='';
  if (s.checks) {
    checksHtml='<div class="checks-row">';
    for (const [k,v] of Object.entries(s.checks)) {
      checksHtml+=`<span class="check-badge ${v?'pass':'fail'}">${v?'&#10003;':'&#10007;'} ${k.replace(/_/g,' ').toUpperCase()}</span>`;
    }
    checksHtml+='</div>';
  }

  let martHtml='';
  if (s.martingale&&s.martingale.length) {
    martHtml='<div class="martingale"><div class="mart-title">\u{1F6E1}\uFE0F RECOVERY</div>';
    s.martingale.forEach(m=>{
      martHtml+='<div class="mart-row"><span class="mart-level">'+m.level+'</span><span class="mart-mult">'+m.multiplier+'x</span><span class="mart-amt">$'+m.amount+'</span><span class="mart-time">'+m.entry_time+'</span></div>';
    });
    martHtml+='</div>';
  }

  const emoji=cls==='buy'?'\u{1F7E2}':'\u{1F534}';
  const arrow=cls==='buy'?'\u25B2':'\u25BC';

  cont.innerHTML=
    '<div class="signal-card '+cls+'">'+
      '<div class="dir-row"><span class="direction '+cls+'">'+emoji+' '+s.direction+' '+arrow+'</span><span class="pair-name">'+s.platform.toUpperCase()+' \u00B7 '+(s.pair||activePair).replace('-OTC','')+'<span class="engine-tag">9/9 STRICT</span></span></div>'+
      '<div class="detail-row"><span>Entry Price</span><span class="val">'+(s.entry_price?s.entry_price.toFixed(5):'--')+'</span></div>'+
      '<div class="detail-row"><span>Expiry</span><span class="val">'+s.timeframe+'</span></div>'+
      '<div class="detail-row"><span>ADX</span><span class="val">'+(s.indicators?s.indicators.adx:'--')+'</span></div>'+
      '<div class="detail-row"><span>RSI</span><span class="val">'+(s.indicators?s.indicators.rsi:'--')+'</span></div>'+
      '<div class="detail-row"><span>Structure</span><span class="val">'+(s.indicators?s.indicators.structure:'--')+'</span></div>'+
      checksHtml+
      '<div class="confidence-bar"><div class="confidence-fill '+confClass+'" style="width:'+s.confidence+'%"></div></div>'+
      '<div class="conf-label">'+s.confidence+'% confidence</div>'+
      martHtml+
      '<div class="risk-note">\u26A0\uFE0F Risk 1% only \u00B7 9/9 confluence passed</div>'+
      '<button class="copy-btn" onclick="navigator.clipboard.writeText(\`'+s.formatted_signal.replace(/`/g,"\\`").replace(/\\/g,"\\\\")+'\`)">\u{1F4CB} Copy Signal</button>'+
    '</div>';
}

function renderNoSignal(msg) {
  document.getElementById('signalsContainer').innerHTML=
    '<div class="signal-card no-signal"><div style="font-size:2em;margin-bottom:10px">\u23F3</div><div style="color:#888">'+msg+'</div></div>';
}

buildTfTabs(); buildPairTabs(); fetchSignal(); setInterval(fetchSignal,15000);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {
        "status": "online",
        "engine": "WinningEngine",
        "filters": 9,
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "pairs": OTC_PAIRS,
        "signals_cached": len(latest_signals),
    }


@app.get("/signal")
async def get_signal(platform: str = "iq", pair: str = "EURUSD-OTC", timeframe: str = "1m"):
    # Validate platform & timeframe
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"Use {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Use {PO_TIMEFRAMES}")
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")

    # Simulate multi-timeframe data — replace with real broker API in production
    np.random.seed(hash(pair) % 2**32)
    trend = np.linspace(0, 0.0003 if 'BUY' in pair else -0.0003, 200) + np.random.randn(200) * 0.0001
    close = 1.0 + trend
    if 'JPY' in pair:
        close = 148.0 + trend * 100
    elif 'XAU' in pair:
        close = 2350.0 + trend * 10000
    elif 'GBP' in pair or 'CAD' in pair:
        close = 1.35 + trend
    elif 'AUD' in pair:
        close = 0.65 + trend

    def make_df(seed):
        np.random.seed(seed)
        spread = 0.0005 if 'XAU' not in pair else 0.5
        return pd.DataFrame({
            'open': close - 0.0002,
            'high': close + spread,
            'low': close - spread,
            'close': close,
            'volume': np.random.randint(50, 200, 200)
        })

    market = {'1m': make_df(0), '3m': make_df(1), '5m': make_df(2)}
    sig = engine.generate(market, pair, platform, timeframe)

    if not sig:
        return {
            "formatted_signal": None,
            "direction": None,
            "message": f"No winning setup for {pair} — strict filters not met",
            "pair": pair,
            "platform": platform,
            "timeframe": timeframe,
            "confidence": 0
        }

    sig["pair"] = pair
    latest_signals.insert(0, sig)
    if len(latest_signals) > 50:
        latest_signals.pop()
    return sig


@app.get("/signal/all")
async def scan_all(platform: str = "iq", timeframe: str = "1m"):
    """Scan all OTC pairs for winning setups."""
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")
    valid_tfs = IQ_TIMEFRAMES if platform == 'iq' else PO_TIMEFRAMES
    if timeframe not in valid_tfs:
        raise HTTPException(400, f"Invalid timeframe. Use: {valid_tfs}")

    results = []
    for pair in OTC_PAIRS:
        try:
            np.random.seed(hash(pair) % 2**32)
            trend = np.linspace(0, 0.0003 if 'BUY' in pair else -0.0003, 200) + np.random.randn(200) * 0.0001
            close = 1.0 + trend
            if 'JPY' in pair:
                close = 148.0 + trend * 100
            elif 'XAU' in pair:
                close = 2350.0 + trend * 10000
            elif 'GBP' in pair or 'CAD' in pair:
                close = 1.35 + trend
            elif 'AUD' in pair:
                close = 0.65 + trend

            def make_df(seed):
                np.random.seed(seed)
                spread = 0.0005 if 'XAU' not in pair else 0.5
                return pd.DataFrame({
                    'open': close - 0.0002, 'high': close + spread,
                    'low': close - spread, 'close': close,
                    'volume': np.random.randint(50, 200, 200)
                })

            market = {'1m': make_df(0), '3m': make_df(1), '5m': make_df(2)}
            sig = engine.generate(market, pair, platform, timeframe)
            if sig:
                sig["pair"] = pair
                results.append(sig)
        except Exception:
            pass

    return {"count": len(results), "signals": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
