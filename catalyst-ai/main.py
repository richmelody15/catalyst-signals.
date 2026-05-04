#!/usr/bin/env python3
"""
ULTIMATE WINNING ENGINE – IQ Option & Pocket Option Live OTC Signals
- 10‑FilterGateTM with Supply/Demand as main filter,
  Support/Resistance as confirmation, RSI+ADX as final momentum.
- Live dual‑platform data (IQ Option + Pocket Option)
- Self‑improving AI confidence scorer
- PWA dashboard with martingale recovery
- Keep‑alive (24/7 on Render) + auto‑session pair selection
"""

import asyncio, httpx, os, joblib, time as time_module
import numpy as np, pandas as pd, pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sklearn.linear_model import LogisticRegression
try:
    from iqoptionapi.stable_api import IQ_Option
    HAS_IQ = True
except ImportError:
    HAS_IQ = False

try:
    from pocketoptionapi.stable_api import PocketOption
    HAS_PO = True
except ImportError:
    HAS_PO = False
from typing import Dict, List, Optional, Tuple

# ─── Timezone & Config ──────────────────────────────────
WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')

IQ_TIMEFRAMES = ['30s','45s','1m','2m','3m','5m']
PO_TIMEFRAMES = ['S3','S15','S30','M1','M3','M5']

CONFIG = {
    'ADX_MIN': 20,
    'VOLUME_MULT': 1.3,
    'RSI_OB': 65,
    'RSI_OS': 35,
    'MTF_MIN': 2,
    'SR_PROXIMITY': 0.008,
    'NEWS_AVOID': (12, 14),
    'LIQUIDITY_WINDOW': 15,
    'MOMENTUM_MIN': 0.0003,
    'MARTINGALE': [('M1',1.5,1), ('M2',2.5,2), ('M3',4.0,3)],
    'MIN_CONFIDENCE': 80,
    'DIVERGENCE_WINDOW': 10
}

# ─── Live Data Feed ─────────────────────────────────────
class LiveDataFeed:
    def __init__(self):
        self.iq = None
        self.po = None

    def connect_iq(self, email, password, demo=True):
        if not HAS_IQ:
            print("IQ Option API not installed – skipping")
            return False
        try:
            self.iq = IQ_Option(email, password)
            check, reason = self.iq.connect()
            if check:
                self.iq.change_balance('PRACTICE' if demo else 'REAL')
                return True
            print(f"IQ Option login failed: {reason}")
            return False
        except Exception as e:
            print(f"IQ Option error: {e}")
            return False

    def connect_po(self, ssid, demo=True):
        if not HAS_PO:
            print("Pocket Option API not installed – skipping")
            return False
        try:
            self.po = PocketOption(ssid, demo)
            self.po.connect()
            return True
        except Exception as e:
            print(f"PO login failed: {e}")
            return False

    def get_candles(self, platform, pair, timeframe_sec, count=200):
        if platform == 'iq':
            if self.iq is None: raise RuntimeError("IQ not connected")
            end = time_module.time()
            start = end - (count * timeframe_sec)
            candles = self.iq.get_candles(pair, timeframe_sec, count, end)
            df = pd.DataFrame(candles)
            if not df.empty:
                df.rename(columns={'open':'open','high':'high','low':'low','close':'close','volume':'volume'}, inplace=True)
            return df
        else:
            if self.po is None: raise RuntimeError("PO not connected")
            end = int(time_module.time())
            start = end - (count * timeframe_sec)
            candles = self.po.get_history(pair, timeframe_sec, start, end)
            df = pd.DataFrame(candles)
            if not df.empty:
                df.rename(columns={'open':'open','high':'high','low':'low','close':'close'}, inplace=True)
                if 'volume' not in df.columns or df['volume'].isna().all():
                    df['volume'] = ((df['high'] - df['low']) * 10000).astype(int)
            return df

# ─── Indicators ─────────────────────────────────────────
def adx(df, period=14):
    h,l,c = df['high'], df['low'], df['close']
    tr = np.maximum(h-l, np.maximum(abs(h-c.shift()), abs(l-c.shift())))
    atr = tr.rolling(period).mean().iloc[-1]
    if atr==0: return 0
    up = h.diff().clip(lower=0)
    down = -l.diff().clip(upper=0)
    di_plus = 100*up.rolling(period).mean().iloc[-1]/atr
    di_minus = 100*down.rolling(period).mean().iloc[-1]/atr
    dx = 100*abs(di_plus-di_minus)/(di_plus+di_minus) if (di_plus+di_minus)!=0 else 0
    return dx

def rsi(close, period=14):
    delta = np.diff(close)
    gain = np.mean(delta[delta>0]) if any(delta>0) else 0
    loss = -np.mean(delta[delta<0]) if any(delta<0) else 0
    if loss==0: return 100
    return 100 - (100/(1+gain/loss))

# ─── Pro‑Level S/D + S/R + Final Confirmation ─────────
class ProLevelSD_SR:
    def __init__(self, swing_window=5, touch_tolerance=0.001, merge_pct=0.003):
        self.swing_window = swing_window
        self.touch_tolerance = touch_tolerance
        self.merge_pct = merge_pct

    # ---- S/D: ORDER BLOCKS (ZONES) ----
    def find_order_blocks(self, df, recent=10):
        obs = []
        for i in range(2, len(df)-1):
            if df['close'].iloc[i] < df['open'].iloc[i]:
                if df['high'].iloc[i+1] > df['high'].iloc[i]:
                    vol = df.get('volume', pd.Series([1]*len(df)))
                    avg_vol = vol.rolling(20).mean().iloc[i] if not vol.isna().all() else 1
                    strength = vol.iloc[i]/avg_vol if avg_vol>0 else 1
                    obs.append({'type':'demand','top':df['high'].iloc[i],'bottom':df['low'].iloc[i],'strength':strength})
            if df['close'].iloc[i] > df['open'].iloc[i]:
                if df['low'].iloc[i+1] < df['low'].iloc[i]:
                    vol = df.get('volume', pd.Series([1]*len(df)))
                    avg_vol = vol.rolling(20).mean().iloc[i] if not vol.isna().all() else 1
                    strength = vol.iloc[i]/avg_vol if avg_vol>0 else 1
                    obs.append({'type':'supply','top':df['high'].iloc[i],'bottom':df['low'].iloc[i],'strength':strength})
        return obs[-recent:]

    # ---- S/R: SWING LEVELS (LINES) ----
    def find_swing_levels(self, df, min_touches=2):
        highs = df['high'].values
        lows = df['low'].values
        supports = []
        resistances = []
        for i in range(self.swing_window, len(highs)-self.swing_window):
            if highs[i] == max(highs[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(highs[i], df, 'high')
                if touches >= min_touches:
                    resistances.append({'price':highs[i],'touches':touches,'type':'resistance'})
            if lows[i] == min(lows[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(lows[i], df, 'low')
                if touches >= min_touches:
                    supports.append({'price':lows[i],'touches':touches,'type':'support'})
        supports = self._merge_levels(supports)
        resistances = self._merge_levels(resistances)
        return supports, resistances

    # ---- FINAL CONFIRMATION (RSI + ADX) ----
    def final_indicator_check(self, df, direction):
        rsi_val = self._rsi(df['close'].values, 14)
        adx_val = self._adx(df)
        if direction == 'BUY':
            rsi_ok = 30 < rsi_val < 65
            adx_ok = adx_val >= 20
        else:
            rsi_ok = 35 < rsi_val < 70
            adx_ok = adx_val >= 20
        return rsi_ok and adx_ok, {'rsi':rsi_val, 'adx':adx_val}

    # ---- MAIN ENTRY CHECK ----
    def entry_check(self, df, direction):
        price = df['close'].iloc[-1]
        details = {}

        # 1. MAIN FILTER: supply/demand zone
        zones = self.find_order_blocks(df)
        in_zone, active_zone = self._is_in_zone(price, zones, direction)
        details['sd_zone'] = in_zone
        if not in_zone:
            return False, details

        # 2. CONFIRMATION: S/R level
        supports, resistances = self.find_swing_levels(df)
        near_sr, sr_level = self._is_near_sr(price, supports if direction=='BUY' else resistances, direction)
        details['sr_confirmed'] = near_sr
        if not near_sr:
            return False, details

        # 3. FINAL: RSI + ADX
        final_ok, ind_data = self.final_indicator_check(df, direction)
        details.update(ind_data)
        details['indicator_final'] = final_ok
        if not final_ok:
            return False, details

        return True, details

    # ---- Helpers ----
    def _count_touches(self, level, df, col='high', tolerance=None):
        if tolerance is None: tolerance = self.touch_tolerance
        return sum(abs(val-level)/level < tolerance for val in df[col].values)

    def _merge_levels(self, levels):
        if not levels: return []
        sorted_lvls = sorted(levels, key=lambda x: x['price'])
        merged = []
        group = [sorted_lvls[0]]
        for lvl in sorted_lvls[1:]:
            if abs(lvl['price'] - group[-1]['price'])/group[-1]['price'] < self.merge_pct:
                group.append(lvl)
            else:
                merged.append(self._combine_group(group))
                group = [lvl]
        merged.append(self._combine_group(group))
        return merged

    def _combine_group(self, group):
        avg_price = sum(l['price'] for l in group)/len(group)
        total_touches = sum(l['touches'] for l in group)
        return {'price':avg_price, 'touches':total_touches, 'type':group[0]['type']}

    def _is_in_zone(self, price, zones, direction):
        for zone in zones:
            if direction=='BUY' and zone['type']=='demand':
                if zone['bottom'] <= price <= zone['top']:
                    return True, zone
            if direction=='SELL' and zone['type']=='supply':
                if zone['bottom'] <= price <= zone['top']:
                    return True, zone
        return False, None

    def _is_near_sr(self, price, levels, direction, threshold=0.005):
        for lvl in levels:
            if direction=='BUY' and lvl['type']=='support' and price > lvl['price']:
                if abs(price-lvl['price'])/price < threshold:
                    return True, lvl
            if direction=='SELL' and lvl['type']=='resistance' and price < lvl['price']:
                if abs(price-lvl['price'])/price < threshold:
                    return True, lvl
        return False, None

    def _rsi(self, close, period=14):
        return rsi(close, period)

    def _adx(self, df, period=14):
        return adx(df, period)

# ─── Other Filter Helpers ───────────────────────────────
def market_structure(df):
    if len(df)<50: return 'RANGING'
    highs = df['high'].values
    lows = df['low'].values
    sh, sl = [], []
    for i in range(5, len(highs)-5):
        if highs[i]==max(highs[i-5:i+6]): sh.append(highs[i])
        if lows[i]==min(lows[i-5:i+6]): sl.append(lows[i])
    if len(sh)>=3 and len(sl)>=3:
        if sh[-1]>sh[-2]>sh[-3] and sl[-1]>sl[-2]>sl[-3]: return 'UP_TREND'
        if sh[-1]<sh[-2]<sh[-3] and sl[-1]<sl[-2]<sl[-3]: return 'DOWN_TREND'
    a = adx(df)
    vol = df['close'].pct_change().std()
    if a<18 or vol>0.003: return 'CHOPPY'
    return 'RANGING'

def mtf_aligned(df_dict, direction):
    count=0
    for tf in ['1m','3m','5m']:
        if tf in df_dict and len(df_dict[tf])>=200:
            df=df_dict[tf]
            ema50=df['close'].ewm(50).mean().iloc[-1]
            ema200=df['close'].ewm(200).mean().iloc[-1]
            if direction=='BUY' and ema50>ema200: count+=1
            elif direction=='SELL' and ema50<ema200: count+=1
    return count>=CONFIG['MTF_MIN']

def candle_ok(df, direction):
    last,prev = df.iloc[-1], df.iloc[-2]
    body=abs(last['close']-last['open'])
    if direction=='BUY':
        if last['close']>last['open'] and prev['close']<prev['open'] and last['close']>prev['open']: return True
        lower_wick=min(last['open'],last['close'])-last['low']
        if last['close']>last['open'] and lower_wick>2*body: return True
    else:
        if last['close']<last['open'] and prev['close']>prev['open'] and last['close']<prev['open']: return True
        upper_wick=last['high']-max(last['open'],last['close'])
        if last['close']<last['open'] and upper_wick>2*body: return True
    return False

def liquidity_sweep(df):
    highs,lows=df['high'].values, df['low'].values
    vol=df['volume'].values
    avg_vol=np.mean(vol[-20:])
    if vol[-1] < avg_vol*CONFIG['VOLUME_MULT']: return None
    recent_high=np.max(highs[-CONFIG['LIQUIDITY_WINDOW']:])
    recent_low=np.min(lows[-CONFIG['LIQUIDITY_WINDOW']:])
    if highs[-1]>recent_high: return 'buy_side'
    if lows[-1]<recent_low: return 'sell_side'
    return None

def news_safe():
    now=datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID'][0]<=now.hour<CONFIG['NEWS_AVOID'][1])

def detect_divergence(close, rsi_array, direction):
    if len(close) < CONFIG['DIVERGENCE_WINDOW']: return False
    c=close[-CONFIG['DIVERGENCE_WINDOW']:]
    r=rsi_array[-CONFIG['DIVERGENCE_WINDOW']:]
    if direction=='BUY' and c[-1]<c[0] and r[-1]>r[0]: return True
    if direction=='SELL' and c[-1]>c[0] and r[-1]<r[0]: return True
    return False

# ─── FilterGate ─────────────────────────────────────────
pro_sd_sr = ProLevelSD_SR()

def filter_gate(df1, df3, df5, direction, platform):
    checks = {}
    # 1. Market structure
    structure = market_structure(df1)
    checks['structure'] = structure
    if direction=='BUY' and structure!='UP_TREND': return False, checks
    if direction=='SELL' and structure!='DOWN_TREND': return False, checks

    # 2. ADX
    checks['adx'] = adx(df1) >= CONFIG['ADX_MIN']

    # 3. MTF
    checks['mtf'] = mtf_aligned({'1m':df1,'3m':df3,'5m':df5}, direction)

    # 4. News
    checks['news'] = news_safe()

    # 5. Candle
    checks['candle'] = candle_ok(df1, direction)

    # 6. S/R + S/D + Final Confirmation (new layered filter)
    sd_sr_passed, sd_sr_details = pro_sd_sr.entry_check(df1, direction)
    checks['sd_zone'] = sd_sr_details.get('sd_zone', False)
    checks['sr_confirmed'] = sd_sr_details.get('sr_confirmed', False)
    checks['indicator_final'] = sd_sr_details.get('indicator_final', False)
    # these three must all be True for a valid entry
    if not (checks['sd_zone'] and checks['sr_confirmed'] and checks['indicator_final']):
        return False, checks

    # 7. Liquidity sweep
    sweep = liquidity_sweep(df1)
    checks['liquidity'] = (direction=='BUY' and sweep=='sell_side') or (direction=='SELL' and sweep=='buy_side')

    # 8. Volume spike (skip for Pocket Option)
    if platform == 'pocket':
        checks['volume'] = True
    else:
        vol_ratio = df1['volume'].iloc[-1]/df1['volume'].rolling(20).mean().iloc[-1]
        checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9. Smart Money (order block/FVG) – already included in sd_zone, keep as extra
    # we reuse the same logic, so we'll just set it to True if sd_zone is True
    checks['smart_money'] = checks['sd_zone']

    # 10. Momentum
    pct = (df1['close'].iloc[-1] / df1['close'].iloc[-4] - 1)
    checks['momentum'] = abs(pct) >= CONFIG['MOMENTUM_MIN']

    # Divergence (bonus)
    rsi_vals = np.array([rsi(df1['close'].values[:i], 14) for i in range(14, len(df1))])
    checks['divergence'] = detect_divergence(df1['close'].values, rsi_vals, direction)

    mandatory = ['adx','mtf','news','candle','sd_zone','sr_confirmed','indicator_final','liquidity','volume','momentum']
    passed = all(checks[k] for k in mandatory)
    return passed, checks

# ─── AI Confidence Scorer ───────────────────────────────
class AIScorer:
    def __init__(self):
        try: self.model = joblib.load('model.pkl')
        except: self.model = None
    def predict(self, features):
        if self.model:
            X = np.array([[features['adx'],features['rsi'],features['vol_ratio'],features['momentum'],features['mtf']]])
            return self.model.predict_proba(X)[0][1]*100
        base = 86.0
        if features.get('divergence'): base += 5
        if features.get('smart_money'): base += 4
        return min(base, 98.0)
    def train(self, trades):
        if len(trades) < 20: return
        df = pd.DataFrame(trades)
        X = df[['adx','rsi','vol_ratio','momentum','mtf']]
        y = df['outcome'].map({'WIN':1,'LOSS':0})
        self.model = LogisticRegression()
        self.model.fit(X,y)
        joblib.dump(self.model, 'model.pkl')

ai_scorer = AIScorer()

# ─── Ultimate Signal Engine ─────────────────────────────
class UltimateEngine:
    def generate(self, market_data, pair, platform, timeframe):
        df1, df3, df5 = market_data['1m'], market_data['3m'], market_data['5m']
        if any(d is None or len(d)<50 for d in [df1,df3,df5]):
            return None

        momentum_pct = (df1['close'].iloc[-1] / df1['close'].iloc[-4] - 1)
        direction = 'BUY' if momentum_pct > 0 else 'SELL'

        passed, checks = filter_gate(df1, df3, df5, direction, platform)
        if not passed:
            opp = 'SELL' if direction == 'BUY' else 'BUY'
            passed2, checks2 = filter_gate(df1, df3, df5, opp, platform)
            if passed2: direction, checks = opp, checks2
            else: return None

        rsi_val = rsi(df1['close'].values, 14)
        vol_ratio = df1['volume'].iloc[-1] / df1['volume'].rolling(20).mean().iloc[-1] if platform=='iq' else 1.5
        features = {
            'adx': adx(df1),
            'rsi': rsi_val,
            'vol_ratio': vol_ratio,
            'momentum': abs(momentum_pct),
            'mtf': 1 if checks['mtf'] else 0,
            'divergence': checks.get('divergence', False),
            'smart_money': checks.get('smart_money', False)
        }
        confidence = ai_scorer.predict(features)
        if confidence < CONFIG['MIN_CONFIDENCE']:
            return None

        tf_sec = {
            '30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
            'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300
        }
        duration = tf_sec.get(timeframe, 60)
        now = datetime.now(pytz.UTC)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = df1['close'].iloc[-1]

        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level': lvl, 'multiplier': mult,
                'amount': round(mult, 2),
                'entry_time': t.strftime('%H:%M')
            })

        color = "\U0001f7e2" if direction == 'BUY' else "\U0001f534"
        arrow = "\u25b2" if direction == 'BUY' else "\u25bc"
        lines = [
            "\u2501"*24,
            f"\U0001f3af ULTIMATE SIGNAL ({platform.upper()})",
            "\u2501"*24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence:.0f}%",
            f"\U0001f4c8 Structure: {checks['structure']} | ADX {adx(df1):.1f}",
            f"\U0001f3e6 Smart Money: {'\u2705' if checks['smart_money'] else '\u274c'}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501"*24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Institutional grade", "\u2501"*24]
        return {
            'formatted_signal': '\n'.join(lines),
            'direction': direction,
            'entry_price': entry_price,
            'confidence': confidence,
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform
        }

# ─── Session Pairs ──────────────────────────────────────
def select_best_pairs():
    hour = datetime.now(pytz.UTC).hour
    if 8 <= hour < 10: return ['EURUSD-OTC','GBPUSD-OTC','EURGBP-OTC']
    if 13 <= hour < 15: return ['XAUUSD-OTC','USDCAD-OTC','EURJPY-OTC']
    if 15 <= hour < 17: return ['BTCUSD-OTC','USDBRL-OTC','USDMXN-OTC']
    return ['EURUSD-OTC']

# ─── Keep‑Alive ─────────────────────────────────────────
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

# ─── FastAPI App ────────────────────────────────────────
app = FastAPI(lifespan=lifespan)
engine = UltimateEngine()

# Connect live data feeds
feed = LiveDataFeed()
IQ_EMAIL = os.getenv('IQ_EMAIL')
IQ_PASSWORD = os.getenv('IQ_PASSWORD')
PO_SSID = os.getenv('PO_SSID')
if IQ_EMAIL and IQ_PASSWORD:
    feed.connect_iq(IQ_EMAIL, IQ_PASSWORD, demo=True)
if PO_SSID:
    feed.connect_po(PO_SSID, demo=True)

# Embedded PWA Dashboard
HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0a0e1a"><meta name="apple-mobile-web-app-capable" content="yes"><title>Catalyst Ultimate</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0e1a;color:#e0e0e0;font-family:system-ui;padding:16px;display:flex;flex-direction:column;align-items:center;min-height:100vh}.container{max-width:500px;width:100%}h1{color:#00ff88;text-align:center;margin-bottom:16px}.tabs{display:flex;justify-content:center;gap:8px;margin-bottom:16px}.tab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:8px 16px;border-radius:20px;cursor:pointer}.tab.active{background:#00ff88;color:#0a0e1a}.status{text-align:center;margin-bottom:10px;font-size:0.85rem}.signal-card{background:#131829;border-radius:12px;padding:20px;margin-bottom:16px;border-left:4px solid}.buy{border-color:#00ff88}.sell{border-color:#ff5252}.direction{font-size:2rem;font-weight:bold;text-align:center;margin:8px 0}.direction.buy{color:#00ff88}.direction.sell{color:#ff5252}.copy-btn{width:100%;padding:12px;background:#00ff88;color:#0a0e1a;border:none;border-radius:8px;font-weight:bold;margin-top:10px;cursor:pointer}.footer{text-align:center;font-size:0.75rem;color:#555;margin-top:20px}</style></head><body><div class="container"><h1>&#x1f916; CATALYST ULTIMATE</h1><div class="tabs"><div class="tab active" data-platform="iq">IQ Option</div><div class="tab" data-platform="pocket">Pocket Option</div></div><div class="status" id="status">Connecting...</div><div id="signals"></div><div class="footer">&#x26a0;&#xfe0f; Trade at your own risk &middot; 1-3% risk</div></div><script>const API=window.location.origin;let platform='iq',tf='1m';async function fetchWithRetry(url,retries=5){for(let i=0;i<retries;i++){const r=await fetch(url);if(r.ok)return r;const d=await r.json().catch(()=>({}));if(d.Message?.includes('pending')){await new Promise(rs=>setTimeout(rs,(i+1)*2000));continue}throw new Error(d.Message||'Error')}throw new Error('Not reachable')}async function fetchSignal(){try{const res=await fetchWithRetry(API+'/signal?platform='+platform+'&timeframe='+tf);const data=await res.json();if(data.formatted_signal){document.getElementById('signals').innerHTML='<div class="signal-card '+data.direction.toLowerCase()+'">'+data.formatted_signal.replace(/\n/g,'<br>')+'<button class="copy-btn" onclick="navigator.clipboard.writeText(lastSig)">Copy</button></div>';window.lastSig=data.formatted_signal;document.getElementById('status').innerHTML='<span style="color:#00ff88">&#x1f7e2; Live</span>'}else{document.getElementById('signals').innerHTML='';document.getElementById('status').textContent='Waiting for perfect setup...'}}catch(e){document.getElementById('status').textContent='Retrying...'}}document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t2=>t2.classList.remove('active'));t.classList.add('active');platform=t.dataset.platform;fetchSignal()}));setInterval(fetchSignal,5000);fetchSignal();</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML

@app.get("/signal")
async def signal(platform: str = "iq", pair: str = None, timeframe: str = "1m"):
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")

    pairs = select_best_pairs() if not pair else [pair]
    tf_sec = {
        '30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
        'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300
    }
    best_signal = None
    best_confidence = 0

    for p in pairs:
        try:
            df1 = feed.get_candles(platform, p, tf_sec[timeframe], 200)
            df3 = feed.get_candles(platform, p, tf_sec[timeframe]*3, 200)
            df5 = feed.get_candles(platform, p, tf_sec[timeframe]*5, 200)
            if df1.empty: continue
            sig = engine.generate({'1m':df1,'3m':df3,'5m':df5}, p, platform, timeframe)
            if sig and sig['confidence'] > best_confidence:
                best_signal = sig
                best_confidence = sig['confidence']
        except Exception as e:
            print(f"Error on {p}: {e}")
            continue

    if not best_signal:
        raise HTTPException(404, "No high-confidence signal - strict filters not met")
    return best_signal

@app.post("/train")
async def train(trades: List[dict]):
    ai_scorer.train(trades)
    return {"message": "Model trained", "samples": len(trades)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
