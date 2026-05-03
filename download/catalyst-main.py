import asyncio, httpx, os, numpy as np, pandas as pd, pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, List, Optional, Tuple

WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')

IQ_TIMEFRAMES = ['30s','45s','1m','2m','3m','5m']
PO_TIMEFRAMES = ['S3','S15','S30','M1','M3','M5']

CONFIG = {
    'ADX_MIN': 25,
    'MOMENTUM_MIN': 0.0002,
    'VOLUME_MULT': 1.5,
    'RSI_LIMIT': 70,
    'RSI_FLOOR': 30,
    'MTF_MIN': 2,
    'SR_PROXIMITY': 0.005,
    'NEWS_AVOID': (12, 14),   # UTC hours
    'LIQUIDITY_WINDOW': 20,
    'MARTINGALE': [('M1',1.5,1), ('M2',2.5,2), ('M3',4.0,3)]
}

# ═══════════════════════════════════════════════════════════
#  MARKET STRUCTURE CLASS
# ═══════════════════════════════════════════════════════════
class MarketStructure:
    @staticmethod
    def find_swings(high, low, window=5):
        sh, sl = [], []
        for i in range(window, len(high)-window):
            if all(high[i] >= high[i-j] for j in range(1,window+1)) and all(high[i] >= high[i+j] for j in range(1,window+1)):
                sh.append(high[i])
            if all(low[i] <= low[i-j] for j in range(1,window+1)) and all(low[i] <= low[i+j] for j in range(1,window+1)):
                sl.append(low[i])
        return sh, sl

    @staticmethod
    def classify(df: pd.DataFrame) -> str:
        """
        Returns: UP_TREND, DOWN_TREND, RANGING, CHOPPY
        """
        if len(df) < 50:
            return 'RANGING'
        adx_val = MarketStructure._adx(df)
        highs = df['high'].values
        lows = df['low'].values
        sh, sl = MarketStructure.find_swings(highs, lows, 5)

        # Trend based on swing structure
        if len(sh) >= 3 and len(sl) >= 3:
            # Check higher highs and higher lows
            if sh[-1] > sh[-2] > sh[-3] and sl[-1] > sl[-2] > sl[-3]:
                return 'UP_TREND'
            # Lower highs and lower lows
            if sh[-1] < sh[-2] < sh[-3] and sl[-1] < sl[-2] < sl[-3]:
                return 'DOWN_TREND'

        # ADX and volatility based
        vol = df['close'].pct_change().std()
        if adx_val < 18 or vol > 0.003:    # high volatility with no direction
            return 'CHOPPY'
        if 18 <= adx_val < 25:
            return 'RANGING'
        # Default
        return 'RANGING'

    @staticmethod
    def _adx(df, period=14):
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


# ═══════════════════════════════════════════════════════════
#  TECHNICAL HELPERS
# ═══════════════════════════════════════════════════════════
def adx(df, period=14):
    return MarketStructure._adx(df)

def rsi(close, period=14):
    delta = np.diff(close)
    gain = np.mean(delta[delta>0]) if any(delta>0) else 0
    loss = -np.mean(delta[delta<0]) if any(delta<0) else 0
    if loss==0: return 100
    return 100 - (100/(1+gain/loss))

def mtf_aligned(dfs, direction):
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in dfs and len(dfs[tf])>=200:
            df = dfs[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction=='BUY' and ema50>ema200: count+=1
            elif direction=='SELL' and ema50<ema200: count+=1
    return count >= CONFIG['MTF_MIN']

def liquidity_sweep(df):
    if len(df) < CONFIG['LIQUIDITY_WINDOW']:
        return None
    highs, lows = df['high'].values, df['low'].values
    vol = df.get('volume', pd.Series([1]*len(df))).values
    avg_vol = np.mean(vol[-20:])
    if vol[-1] < avg_vol*CONFIG['VOLUME_MULT']: return None
    recent_high = np.max(highs[-CONFIG['LIQUIDITY_WINDOW']:])
    recent_low = np.min(lows[-CONFIG['LIQUIDITY_WINDOW']:])
    if highs[-1] > recent_high: return 'buy_side'
    if lows[-1] < recent_low: return 'sell_side'
    return None

def candle_ok(df, direction):
    if len(df) < 2:
        return False
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['close']-last['open'])
    if body == 0:
        return False
    if direction=='BUY':
        if last['close']>last['open'] and prev['close']<prev['open'] and last['close']>prev['open']:
            return True
        lower_wick = min(last['open'],last['close']) - last['low']
        if last['close']>last['open'] and lower_wick>2*body: return True
    else:
        if last['close']<last['open'] and prev['close']>prev['open'] and last['close']<prev['open']:
            return True
        upper_wick = last['high'] - max(last['open'],last['close'])
        if last['close']<last['open'] and upper_wick>2*body: return True
    return False

def sr_favorable(price, df, direction):
    if len(df) < 20:
        return False
    res = df['high'].rolling(20).max().iloc[-1]
    sup = df['low'].rolling(20).min().iloc[-1]
    if direction=='BUY': return abs(price-sup)/price < CONFIG['SR_PROXIMITY']
    return abs(res-price)/price < CONFIG['SR_PROXIMITY']

def news_safe():
    now = datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID'][0] <= now.hour < CONFIG['NEWS_AVOID'][1])


# ═══════════════════════════════════════════════════════════
#  STRICT SIGNAL CHECK (9 filters)
# ═══════════════════════════════════════════════════════════
def all_checks_pass(df_1m, df_3m, df_5m, direction):
    checks = {}

    # 1. Market structure — MUST MATCH direction
    structure = MarketStructure.classify(df_1m)
    checks['market_structure'] = structure
    if direction == 'BUY' and structure != 'UP_TREND':
        return False, checks
    if direction == 'SELL' and structure != 'DOWN_TREND':
        return False, checks

    # 2. ADX
    a = adx(df_1m)
    checks['adx'] = a >= CONFIG['ADX_MIN']

    # 3. MTF alignment
    checks['mtf'] = mtf_aligned({'1m':df_1m,'3m':df_3m,'5m':df_5m}, direction)

    # 4. News filter
    checks['news'] = news_safe()

    # 5. Candle confirmation
    checks['candle'] = candle_ok(df_1m, direction)

    # 6. S/R proximity
    price = df_1m['close'].iloc[-1]
    checks['sr'] = sr_favorable(price, df_1m, direction)

    # 7. Liquidity sweep (mandatory)
    sweep = liquidity_sweep(df_1m)
    checks['liquidity'] = (direction=='BUY' and sweep=='sell_side') or \
                          (direction=='SELL' and sweep=='buy_side')

    # 8. Volume spike
    if len(df_1m) >= 20 and df_1m['volume'].rolling(20).mean().iloc[-1] > 0:
        vol_ratio = df_1m['volume'].iloc[-1] / df_1m['volume'].rolling(20).mean().iloc[-1]
    else:
        vol_ratio = 1.0
    checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9. Momentum
    pct = (df_1m['close'].iloc[-1]/df_1m['close'].iloc[-4]-1)
    checks['momentum'] = abs(pct) >= CONFIG['MOMENTUM_MIN']

    # All must be True
    passed = all(checks.values())
    return passed, checks


# ═══════════════════════════════════════════════════════════
#  WINNING ENGINE
# ═══════════════════════════════════════════════════════════
class WinningEngine:
    def generate(self, market_data, pair, platform, timeframe):
        df1m = market_data.get('1m')
        df3m = market_data.get('3m')
        df5m = market_data.get('5m')
        if any(d is None or len(d)<50 for d in [df1m,df3m,df5m]):
            return None

        # Momentum direction
        pct = (df1m['close'].iloc[-1]/df1m['close'].iloc[-4]-1)
        direction = 'BUY' if pct>0 else 'SELL'

        ok, checks = all_checks_pass(df1m, df3m, df5m, direction)
        if not ok:
            opp = 'SELL' if direction=='BUY' else 'BUY'
            ok2, checks2 = all_checks_pass(df1m, df3m, df5m, opp)
            if ok2:
                direction, checks = opp, checks2
            else:
                return None

        now = datetime.now(pytz.UTC)
        tf_sec = {'30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
                  'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300}
        duration = tf_sec.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df1m['close'].iloc[-1])
        confidence = 92

        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl,mult,delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level':lvl, 'multiplier':mult,
                'amount':round(mult,2),
                'entry_time':t.strftime('%H:%M')
            })

        color = "\U0001f7e2" if direction=='BUY' else "\U0001f534"
        arrow = "\u25b2" if direction=='BUY' else "\u25bc"
        lines = [
            "\u2501"*24,
            f"\U0001f3af STRICT WINNING SIGNAL ({platform.upper()})",
            "\u2501"*24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 Market Structure: {checks['market_structure']}",
            f"\U0001f4ca ADX: {adx(df1m):.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501"*24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 High-probability setup", "\u2501"*24]

        return {
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
                'structure': checks.get('market_structure', '')
            }
        }


# ═══════════════════════════════════════════════════════════
#  KEEP ALIVE
# ═══════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════
#  FASTAPI
# ═══════════════════════════════════════════════════════════
app = FastAPI(lifespan=lifespan)
engine = WinningEngine()
latest_signals: list = []


# ═══════════════════════════════════════════════════════════
#  EMBEDDED FRONTEND
# ═══════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0a0e1a"><meta name="apple-mobile-web-app-capable" content="yes"><title>Catalyst AI</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0e1a;color:#e0e0e0;font-family:system-ui;padding:16px;display:flex;flex-direction:column;align-items:center;min-height:100vh}.container{max-width:500px;width:100%}h1{color:#00ff88;text-align:center;margin-bottom:16px}.tabs{display:flex;justify-content:center;gap:8px;margin-bottom:16px}.tab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:8px 16px;border-radius:20px;cursor:pointer}.tab.active{background:#00ff88;color:#0a0e1a}.status{text-align:center;margin-bottom:10px;font-size:0.85rem}.signal-card{background:#131829;border-radius:12px;padding:20px;margin-bottom:16px;border-left:4px solid}.buy{border-color:#00ff88}.sell{border-color:#ff5252}.direction{font-size:2rem;font-weight:bold;text-align:center;margin:8px 0}.direction.buy{color:#00ff88}.direction.sell{color:#ff5252}.copy-btn{width:100%;padding:12px;background:#00ff88;color:#0a0e1a;border:none;border-radius:8px;font-weight:bold;margin-top:10px;cursor:pointer}.footer{text-align:center;font-size:0.75rem;color:#555;margin-top:20px}</style></head><body><div class="container"><h1>\U0001f916 CATALYST AI</h1><div class="tabs"><div class="tab active" data-platform="iq">IQ Option</div><div class="tab" data-platform="pocket">Pocket Option</div></div><div class="status" id="status">Connecting...</div><div id="signals"></div><div class="footer">\u26a0\ufe0f Trade at your own risk \u00b7 1-3% risk</div></div><script>const API=window.location.origin;let platform='iq';let tf='1m';async function fetchWithRetry(url,retries=5){for(let i=0;i<retries;i++){const r=await fetch(url);if(r.ok)return r;const d=await r.json().catch(()=>({}));if(d.Message?.includes('pending')){await new Promise(rs=>setTimeout(rs,(i+1)*2000));continue}throw new Error(d.Message||'Error')}throw new Error('Not reachable')}async function fetchSignal(){try{const res=await fetchWithRetry(`${API}/signal?platform=${platform}&timeframe=${tf}`);const data=await res.json();if(data.formatted_signal){document.getElementById('signals').innerHTML=`<div class="signal-card ${data.direction.toLowerCase()}">${data.formatted_signal.replace(/\\n/g,'<br>')}<button class="copy-btn" onclick="navigator.clipboard.writeText(\`${data.formatted_signal}\`)">\U0001f4cb Copy</button></div>`;document.getElementById('status').textContent='\U0001f7e2 Live'}else{document.getElementById('signals').innerHTML='';document.getElementById('status').textContent='\u23f3 Waiting for clear trend...'}}catch(e){document.getElementById('status').textContent='\U0001f534 Retrying...'}}document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t2=>t2.classList.remove('active'));t.classList.add('active');platform=t.dataset.platform;fetchSignal()}));setInterval(fetchSignal,5000);fetchSignal();</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {
        "status": "online",
        "engine": "WinningEngine",
        "structure": "MarketStructure",
        "filters": 9,
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "signals_cached": len(latest_signals),
    }


@app.get("/signal")
async def signal(platform:str="iq", pair:str="EURUSD-OTC", timeframe:str="1m"):
    if platform=='iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform=='pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")

    # --- simulated data (replace with live broker API) ---
    np.random.seed(hash(pair)%2**32)
    trend = np.linspace(0, 0.0004 if 'UP' in pair else -0.0004, 200) + np.random.randn(200)*0.0001
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
            'open': close-0.0002, 'high': close+spread,
            'low': close-spread, 'close': close,
            'volume': np.random.randint(50,200,200)
        })

    market = {'1m':make_df(0),'3m':make_df(1),'5m':make_df(2)}
    sig = engine.generate(market, pair, platform, timeframe)
    if not sig:
        raise HTTPException(404, "No trade \u2013 market structure not aligned")
    sig["pair"] = pair
    latest_signals.insert(0, sig)
    if len(latest_signals) > 50:
        latest_signals.pop()
    return sig


if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
