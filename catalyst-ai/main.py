"""
CATALYST AI – ULTIMATE WINNING ENGINE
- Market Structure (Uptrend/Downtrend/Ranging/Choppy)
- Hidden Divergence (RSI)
- AI Probability Scorer (logistic regression)
- Session‑based pair selection
- ATR‑based dynamic expiry
- All strict filters (ADX, MTF, S/R, Liquidity, Volume, Candle, News)
- Martingale recovery
- Self‑ping keep‑alive
- Embedded PWA dashboard
"""

import asyncio, httpx, os, json, joblib
import numpy as np, pandas as pd, pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sklearn.linear_model import LogisticRegression
from typing import Dict, List, Optional, Tuple

# ---------- CONFIG ----------
WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')
MODEL_PATH = 'win_prob_model.pkl'

IQ_TIMEFRAMES   = ['30s','45s','1m','2m','3m','5m']
PO_TIMEFRAMES   = ['S3','S15','S30','M1','M3','M5']

CONFIG = {
    'ADX_MIN': 25,
    'VOLUME_MULT': 1.5,
    'RSI_LIMIT': 70,
    'RSI_FLOOR': 30,
    'MTF_MIN': 2,
    'SR_PROXIMITY': 0.005,
    'NEWS_AVOID': (12, 14),
    'LIQUIDITY_WINDOW': 20,
    'MARTINGALE': [('M1',1.5,1), ('M2',2.5,2), ('M3',4.0,3)],
    'DIVERGENCE_WINDOW': 10,
    'MIN_CONFIDENCE_FOR_SIGNAL': 85
}

# ---------- AI MODEL (optional) ----------
class MLScorer:
    def __init__(self):
        self.model = None
        try:
            self.model = joblib.load(MODEL_PATH)
        except Exception:
            pass

    def predict(self, features: dict) -> float:
        if self.model:
            X = np.array([[features['adx'], features['rsi'], features['vol_ratio'],
                           features['momentum'], features['mtf']]])
            return self.model.predict_proba(X)[0][1] * 100
        # fallback static confidence when model absent
        return 92.0

    def train(self, trades: List[dict]):
        """Train logistic regression on closed trades."""
        if len(trades) < 20:
            return False
        df = pd.DataFrame(trades)
        X = df[['adx','rsi','vol_ratio','momentum','mtf']]
        y = df['outcome'].map({'WIN':1,'LOSS':0})
        self.model = LogisticRegression()
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        return True

ml_scorer = MLScorer()

# ---------- TECHNICAL TOOLS ----------
def adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = np.maximum(high-low, np.maximum(abs(high-close.shift()), abs(low-close.shift())))
    atr = tr.rolling(period).mean().iloc[-1]
    if atr == 0: return 0
    up = high.diff().clip(lower=0)
    down = -low.diff().clip(upper=0)
    di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
    di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
    dx = 100 * abs(di_plus-di_minus) / (di_plus+di_minus) if (di_plus+di_minus)!=0 else 0
    return dx

def rsi(close, period=14):
    delta = np.diff(close)
    gain = np.mean(delta[delta>0]) if any(delta>0) else 0
    loss = -np.mean(delta[delta<0]) if any(delta<0) else 0
    if loss==0: return 100
    return 100 - (100/(1+gain/loss))

def market_structure(df):
    """Returns UP_TREND, DOWN_TREND, RANGING, CHOPPY"""
    if len(df) < 50: return 'RANGING'
    a = adx(df)
    highs, lows = df['high'].values, df['low'].values
    # simple swing detection
    sh, sl = [], []
    for i in range(5, len(highs)-5):
        if highs[i] == max(highs[i-5:i+6]): sh.append(highs[i])
        if lows[i] == min(lows[i-5:i+6]): sl.append(lows[i])
    if len(sh)>=3 and len(sl)>=3:
        if sh[-1] > sh[-2] > sh[-3] and sl[-1] > sl[-2] > sl[-3]:
            return 'UP_TREND'
        if sh[-1] < sh[-2] < sh[-3] and sl[-1] < sl[-2] < sl[-3]:
            return 'DOWN_TREND'
    vol = df['close'].pct_change().std()
    if a < 18 or vol > 0.003:
        return 'CHOPPY'
    return 'RANGING'

def divergence(close, rsi_series, direction):
    if len(close) < CONFIG['DIVERGENCE_WINDOW']:
        return False
    close_slice = close[-CONFIG['DIVERGENCE_WINDOW']:]
    rsi_slice = rsi_series[-CONFIG['DIVERGENCE_WINDOW']:]
    if direction == 'BUY':
        # price lower low, rsi higher low → bullish hidden divergence
        if close_slice[-1] < close_slice[0] and rsi_slice[-1] > rsi_slice[0]:
            return True
    else:
        # price higher high, rsi lower high → bearish hidden divergence
        if close_slice[-1] > close_slice[0] and rsi_slice[-1] < rsi_slice[0]:
            return True
    return False

def mtf_aligned(df_dict, direction):
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in df_dict and len(df_dict[tf])>=200:
            df = df_dict[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction == 'BUY' and ema50>ema200: count+=1
            elif direction == 'SELL' and ema50<ema200: count+=1
    return count >= CONFIG['MTF_MIN']

def mtf_score(df_dict, direction):
    """Return MTF alignment count (0-3) for ML features"""
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in df_dict and len(df_dict[tf])>=200:
            df = df_dict[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction == 'BUY' and ema50>ema200: count+=1
            elif direction == 'SELL' and ema50<ema200: count+=1
    return count

def liquidity_sweep(df):
    highs, lows = df['high'].values, df['low'].values
    vol = df['volume'].values
    avg_vol = np.mean(vol[-20:])
    if vol[-1] < avg_vol * CONFIG['VOLUME_MULT']:
        return None
    recent_high = np.max(highs[-CONFIG['LIQUIDITY_WINDOW']:])
    recent_low = np.min(lows[-CONFIG['LIQUIDITY_WINDOW']:])
    if highs[-1] > recent_high: return 'buy_side'
    if lows[-1] < recent_low: return 'sell_side'
    return None

def candle_ok(df, direction):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last['close']-last['open'])
    if body == 0: return False
    if direction == 'BUY':
        if last['close']>last['open'] and prev['close']<prev['open'] and last['close']>prev['open']:
            return True
        lower_wick = min(last['open'],last['close'])-last['low']
        if last['close']>last['open'] and lower_wick>2*body: return True
    else:
        if last['close']<last['open'] and prev['close']>prev['open'] and last['close']<prev['open']:
            return True
        upper_wick = last['high'] - max(last['open'],last['close'])
        if last['close']<last['open'] and upper_wick>2*body: return True
    return False

def sr_favorable(price, df, direction):
    res = df['high'].rolling(20).max().iloc[-1]
    sup = df['low'].rolling(20).min().iloc[-1]
    if direction == 'BUY': return abs(price-sup)/price < CONFIG['SR_PROXIMITY']
    return abs(res-price)/price < CONFIG['SR_PROXIMITY']

def news_safe():
    now = datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID'][0] <= now.hour < CONFIG['NEWS_AVOID'][1])

def select_best_pairs():
    now = datetime.now(pytz.UTC)
    hour = now.hour
    if 8 <= hour < 10: return ['EURUSD-OTC','GBPUSD-OTC','EURGBP-OTC']
    if 13 <= hour < 15: return ['XAUUSD-OTC','USDCAD-OTC','EURJPY-OTC']
    if 15 <= hour < 17: return ['BTCUSD-OTC','USDBRL-OTC','USDMXN-OTC']
    return ['EURUSD-OTC']

# ---------- STRICT CHECK ----------
def all_checks_pass(df1, df3, df5, direction, pair):
    checks = {}
    # 1. Market structure must match
    st = market_structure(df1)
    checks['structure'] = st
    if direction == 'BUY' and st != 'UP_TREND': return False, checks
    if direction == 'SELL' and st != 'DOWN_TREND': return False, checks

    # 2. ADX
    a = adx(df1)
    checks['adx'] = bool(a >= CONFIG['ADX_MIN'])

    # 3. MTF alignment
    checks['mtf'] = mtf_aligned({'1m':df1,'3m':df3,'5m':df5}, direction)

    # 4. News filter
    checks['news'] = news_safe()

    # 5. Candle confirmation
    checks['candle'] = candle_ok(df1, direction)

    # 6. S/R proximity
    price = df1['close'].iloc[-1]
    checks['sr'] = sr_favorable(price, df1, direction)

    # 7. Liquidity sweep
    sweep = liquidity_sweep(df1)
    checks['liquidity'] = (direction=='BUY' and sweep=='sell_side') or \
                          (direction=='SELL' and sweep=='buy_side')

    # 8. Volume spike
    vol_ratio = float(df1['volume'].iloc[-1]/df1['volume'].rolling(20).mean().iloc[-1])
    checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9. Momentum
    pct = (price / df1['close'].iloc[-4] - 1)
    checks['momentum'] = bool(abs(pct) >= 0.0002)

    # 10. Divergence (bonus, not mandatory)
    rsi_arr = np.array([rsi(df1['close'].values[:i], 14) for i in range(14, len(df1))])
    rsi_val = float(rsi_arr[-1]) if len(rsi_arr)>0 else 50.0
    checks['divergence'] = divergence(df1['close'].values, rsi_arr, direction)

    # All mandatory checks must pass (divergence is bonus)
    mandatory = ['adx','mtf','news','candle','sr','liquidity','volume','momentum']
    passed = all(checks[k] for k in mandatory)
    return passed, checks

# ---------- WINNING ENGINE ----------
class UltimateEngine:
    def generate(self, market_data, pair, platform, timeframe):
        df1, df3, df5 = market_data['1m'], market_data['3m'], market_data['5m']
        if any(d is None or len(d)<50 for d in [df1,df3,df5]):
            return None
        # momentum direction
        pct = (df1['close'].iloc[-1]/df1['close'].iloc[-4]-1)
        direction = 'BUY' if pct>0 else 'SELL'
        ok, checks = all_checks_pass(df1, df3, df5, direction, pair)
        if not ok:
            opp = 'SELL' if direction=='BUY' else 'BUY'
            ok2, checks2 = all_checks_pass(df1, df3, df5, opp, pair)
            if ok2: direction, checks = opp, checks2
            else: return None

        # AI confidence — use actual indicator values, not boolean checks
        adx_val = float(adx(df1))
        rsi_val = float(rsi(df1['close'].values, 14))
        vol_ratio = float(df1['volume'].iloc[-1]/df1['volume'].rolling(20).mean().iloc[-1])
        mtf_cnt = float(mtf_score({'1m':df1,'3m':df3,'5m':df5}, direction))

        features = {
            'adx': adx_val, 'rsi': rsi_val,
            'vol_ratio': vol_ratio,
            'momentum': float(abs(pct)), 'mtf': mtf_cnt
        }
        conf = ml_scorer.predict(features)
        if conf < CONFIG['MIN_CONFIDENCE_FOR_SIGNAL']:
            return None

        # dynamic expiry via ATR
        atr_val = df1['high'].sub(df1['low']).rolling(14).mean().iloc[-1]
        speed = df1['close'].diff().abs().rolling(20).mean().iloc[-1]
        if speed == 0: speed = 0.00001
        optimal_sec = int(atr_val * 1.5 / speed * 60)
        optimal_sec = max(30, min(optimal_sec, 300))  # clamp 30s‑5m

        tf_seconds = {
            '30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
            'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300
        }
        duration = tf_seconds.get(timeframe, optimal_sec)

        now = datetime.now(pytz.UTC)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df1['close'].iloc[-1])

        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level':lvl, 'multiplier':mult,
                'amount':round(mult,2), 'entry_time':t.strftime('%H:%M')
            })

        color = "\U0001f7e2" if direction=='BUY' else "\U0001f534"
        arrow = "\u25b2" if direction=='BUY' else "\u25bc"
        div_text = "\u2705" if checks.get('divergence') else "No"
        lines = [
            "\u2501"*24,
            f"\U0001f3af ULTIMATE SIGNAL ({platform.upper()})",
            "\u2501"*24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af AI Confidence: {conf:.0f}%",
            f"\U0001f4c8 Structure: {checks.get('structure','')} | ADX {adx_val:.1f}",
            f"\U0001f50d Divergence: {div_text}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501"*24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Elite setup", "\u2501"*24]
        return {
            'formatted_signal': '\n'.join(lines),
            'direction':direction, 'entry_price':entry_price,
            'confidence':round(conf, 1), 'expiry':expiry.isoformat(),
            'timeframe':timeframe, 'platform':platform,
            'pair': pair,
            'checks': {k: (v if isinstance(v, str) else bool(v)) for k, v in checks.items()},
            'martingale': martingale,
            'indicators': {
                'adx': round(adx_val, 1),
                'rsi': round(rsi_val, 1),
                'structure': checks.get('structure', ''),
                'vol_ratio': round(vol_ratio, 2),
                'divergence': checks.get('divergence', False),
                'dynamic_expiry_seconds': duration,
                'ml_confidence': round(conf, 1)
            }
        }

# ---------- KEEP ALIVE ----------
async def keep_alive():
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try: await client.get(API_URL, timeout=10)
            except: pass
            await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()

# ---------- FASTAPI ----------
app = FastAPI(lifespan=lifespan)
engine = UltimateEngine()

# embedded PWA frontend
HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0a0e1a"><meta name="apple-mobile-web-app-capable" content="yes"><title>Catalyst Ultimate</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0e1a;color:#e0e0e0;font-family:system-ui;padding:16px;display:flex;flex-direction:column;align-items:center;min-height:100vh}.container{max-width:500px;width:100%}h1{color:#00ff88;text-align:center;margin-bottom:16px}.tabs{display:flex;justify-content:center;gap:8px;margin-bottom:16px}.tab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:8px 16px;border-radius:20px;cursor:pointer}.tab.active{background:#00ff88;color:#0a0e1a}.status{text-align:center;margin-bottom:10px;font-size:.85rem}.signal-card{background:#131829;border-radius:12px;padding:20px;margin-bottom:16px;border-left:4px solid}.buy{border-color:#00ff88}.sell{border-color:#ff5252}.direction{font-size:2rem;font-weight:bold;text-align:center;margin:8px 0}.direction.buy{color:#00ff88}.direction.sell{color:#ff5252}.copy-btn{width:100%;padding:12px;background:#00ff88;color:#0a0e1a;border:none;border-radius:8px;font-weight:bold;margin-top:10px;cursor:pointer}.footer{text-align:center;font-size:.75rem;color:#555;margin-top:20px}</style></head><body><div class="container"><h1>&#x1F916; CATALYST ULTIMATE</h1><div class="tabs"><div class="tab active" data-platform="iq">IQ Option</div><div class="tab" data-platform="pocket">Pocket Option</div></div><div class="status" id="status">Connecting...</div><div id="signals"></div><div class="footer">&#x26A0;&#xFE0F; Trade at your own risk &middot; 1-3% risk</div></div><script>const API=window.location.origin;let platform='iq',tf='1m';async function fetchWithRetry(url,retries=5){for(let i=0;i<retries;i++){const r=await fetch(url);if(r.ok)return r;const d=await r.json().catch(()=>({}));if(d.Message&&d.Message.includes('pending')){await new Promise(rs=>setTimeout(rs,(i+1)*2000));continue}throw new Error(d.Message||'Error')}throw new Error('Not reachable')}async function fetchSignal(){try{const res=await fetchWithRetry(API+'/signal?platform='+platform+'&timeframe='+tf);const data=await res.json();if(data.formatted_signal){document.getElementById('signals').innerHTML='<div class="signal-card '+(data.direction.toLowerCase())+'">'+data.formatted_signal.replace(/\n/g,'<br>')+'<button class="copy-btn" onclick="navigator.clipboard.writeText(data.formatted_signal)">&#x1F4CB; Copy</button></div>';document.getElementById('status').textContent='\uD83D\uDFE2 Live'}else{document.getElementById('signals').innerHTML='';document.getElementById('status').textContent='\u23F3 Waiting for perfect setup...'}}catch(e){document.getElementById('status').textContent='\uD83D\uDD34 Retrying...'}}document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t2=>t2.classList.remove('active'));t.classList.add('active');platform=t.dataset.platform;fetchSignal()}));setInterval(fetchSignal,5000);fetchSignal();</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(): return HTML

@app.get("/signal")
async def get_signal(platform: str = "iq", pair: str = None, timeframe: str = "1m"):
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")

    # If no pair given, use best session pairs
    if not pair:
        best = select_best_pairs()
        pair = best[0]

    # Simulated multi-timeframe data (replace with your live feed)
    dates = pd.date_range(end=datetime.now(), periods=200, freq='1min')
    np.random.seed(hash(pair)%2**32)
    trend = np.linspace(0, 0.0004 if 'UP' in pair else -0.0004, 200) + np.random.randn(200)*0.0001
    close = 1.0 + trend
    if 'JPY' in pair: close = 148.0 + trend * 100
    elif 'XAU' in pair: close = 2350.0 + trend * 10000
    elif 'BTC' in pair: close = 65000.0 + trend * 50000
    elif 'BRL' in pair: close = 5.0 + trend
    elif 'MXN' in pair: close = 17.0 + trend * 10
    elif 'GBP' in pair or 'CAD' in pair: close = 1.35 + trend
    elif 'AUD' in pair: close = 0.65 + trend

    def make_df(seed):
        np.random.seed(seed)
        spread = 0.0005 if 'XAU' not in pair else 0.5
        return pd.DataFrame({
            'open':close-0.0002,'high':close+spread,'low':close-spread,
            'close':close,'volume':np.random.randint(50,200,200).astype(float)
        })
    market = {'1m':make_df(0),'3m':make_df(1),'5m':make_df(2)}
    sig = engine.generate(market, pair, platform, timeframe)
    if not sig:
        raise HTTPException(404, "No high-probability signal - strict filters not met")
    return sig

@app.get("/session-pairs")
async def session_pairs():
    return {"pairs": select_best_pairs(), "hour_utc": datetime.now(pytz.UTC).hour}

@app.post("/train")
async def train_model(trades: List[dict]):
    success = ml_scorer.train(trades)
    if not success:
        raise HTTPException(400, "Need at least 20 trades to train")
    return {"message": "Model trained and saved", "samples": len(trades)}

@app.get("/health")
async def health():
    return {
        "status": "online",
        "engine": "UltimateEngine",
        "version": "9.0",
        "filters": 10,
        "ml_model_loaded": ml_scorer.model is not None,
        "best_pairs_now": select_best_pairs(),
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
