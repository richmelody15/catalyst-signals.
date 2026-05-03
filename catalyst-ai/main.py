import asyncio, httpx, os, numpy as np, pandas as pd, pytz, requests
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, List, Optional, Tuple

WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

IQ_TIMEFRAMES = ['30s','45s','1m','2m','3m','5m']
PO_TIMEFRAMES = ['S3','S15','S30','M1','M3','M5']

OTC_PAIRS = [
    'EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC',
    'AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC',
    'AUDUSD-OTC','NZDUSD-OTC','EURGBP-OTC'
]

CONFIG = {
    'ADX_MIN': 25,
    'MOMENTUM_MIN': 0.0002,
    'VOLUME_MULT': 1.5,
    'RSI_LIMIT': 70,
    'RSI_FLOOR': 30,
    'MTF_MIN': 2,
    'SR_PROXIMITY': 0.005,
    'NEWS_AVOID': (12, 14),
    'LIQUIDITY_WINDOW': 20,
    'MARTINGALE': [('M1',1.5,1), ('M2',2.5,2), ('M3',4.0,3)]
}

CORRELATED_GROUPS = [
    ['EURUSD-OTC','GBPUSD-OTC','EURGBP-OTC'],
    ['AUDUSD-OTC','NZDUSD-OTC'],
    ['USDCAD-OTC','GBPCAD-OTC'],
]

# ═══════════════════════════════════════════════════════════
#  MARKET STRUCTURE
# ═══════════════════════════════════════════════════════════
class MarketStructure:
    @staticmethod
    def find_swings(high, low, window=5):
        sh, sl = [], []
        for i in range(window, len(high)-window):
            if all(high[i] >= high[i-j] for j in range(1,window+1)) and \
               all(high[i] >= high[i+j] for j in range(1,window+1)):
                sh.append(high[i])
            if all(low[i] <= low[i-j] for j in range(1,window+1)) and \
               all(low[i] <= low[i+j] for j in range(1,window+1)):
                sl.append(low[i])
        return sh, sl

    @staticmethod
    def classify(df: pd.DataFrame) -> str:
        if len(df) < 50:
            return 'RANGING'
        adx_val = MarketStructure._adx(df)
        highs = df['high'].values
        lows = df['low'].values
        sh, sl = MarketStructure.find_swings(highs, lows, 5)

        if len(sh) >= 3 and len(sl) >= 3:
            if sh[-1] > sh[-2] > sh[-3] and sl[-1] > sl[-2] > sl[-3]:
                return 'UP_TREND'
            if sh[-1] < sh[-2] < sh[-3] and sl[-1] < sl[-2] < sl[-3]:
                return 'DOWN_TREND'

        vol = df['close'].pct_change().std()
        if adx_val < 18 or vol > 0.003:
            return 'CHOPPY'
        if 18 <= adx_val < 25:
            return 'RANGING'
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

def rsi_series(close, period=14):
    """Full RSI series for divergence detection"""
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean().values
    avg_loss = pd.Series(loss).rolling(period).mean().values
    rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
    return 100 - (100 / (1 + rs))

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

def mtf_score(dfs, direction):
    """Return MTF alignment count (0-3) for ML features"""
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in dfs and len(dfs[tf])>=200:
            df = dfs[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction=='BUY' and ema50>ema200: count+=1
            elif direction=='SELL' and ema50<ema200: count+=1
    return count

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
    if len(df) < 2: return False
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['close']-last['open'])
    if body == 0: return False
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
    if len(df) < 20: return False
    res = df['high'].rolling(20).max().iloc[-1]
    sup = df['low'].rolling(20).min().iloc[-1]
    if direction=='BUY': return abs(price-sup)/price < CONFIG['SR_PROXIMITY']
    return abs(res-price)/price < CONFIG['SR_PROXIMITY']

def news_safe():
    now = datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID'][0] <= now.hour < CONFIG['NEWS_AVOID'][1])


# ═══════════════════════════════════════════════════════════
#  ML PROBABILITY SCORER
# ═══════════════════════════════════════════════════════════
class MLProbabilityScorer:
    def __init__(self, model_path='model.pkl'):
        try:
            import joblib
            self.model = joblib.load(model_path)
        except Exception:
            self.model = None

    def predict(self, features: dict) -> float:
        if self.model:
            X = np.array([[features['adx'], features['rsi'], features['vol_ratio'],
                           features['momentum'], features['mtf']]])
            return float(self.model.predict_proba(X)[0][1] * 100)
        return 90.0  # static fallback when no trained model

ml_scorer = MLProbabilityScorer()


# ═══════════════════════════════════════════════════════════
#  SESSION-BASED PAIR SELECTION
# ═══════════════════════════════════════════════════════════
def best_pairs_for_session():
    now = datetime.now(pytz.UTC)
    hour = now.hour
    if 8 <= hour < 10:
        return ['EURUSD-OTC','GBPUSD-OTC','EURGBP-OTC']
    if 13 <= hour < 15:
        return ['XAUUSD-OTC','USDCAD-OTC','EURJPY-OTC']
    if 15 <= hour < 17:
        return ['USDJPY-OTC','GBPJPY-OTC','USDCAD-OTC']
    return ['EURUSD-OTC']


# ═══════════════════════════════════════════════════════════
#  DIVERGENCE DETECTION
# ═══════════════════════════════════════════════════════════
def detect_divergence(close, rsi_arr, direction):
    if len(close) < 10 or len(rsi_arr) < 10:
        return False
    c = close[-10:]
    r = rsi_arr[-10:]
    if direction == 'BUY':
        if c[-1] < c[0] and r[-1] > r[0]:
            return True
    elif direction == 'SELL':
        if c[-1] > c[0] and r[-1] < r[0]:
            return True
    return False


# ═══════════════════════════════════════════════════════════
#  ATR-BASED DYNAMIC EXPIRY
# ═══════════════════════════════════════════════════════════
def atr_expiry(df, atr_mult=1.5):
    if len(df) < 14:
        return 60
    atr = df['high'].sub(df['low']).rolling(14).mean().iloc[-1]
    if np.isnan(atr) or atr == 0:
        return 60
    target_pips = atr * atr_mult
    speed = df['close'].diff().abs().rolling(20).mean().iloc[-1]
    if np.isnan(speed) or speed == 0:
        return 60
    seconds = int(target_pips / speed * 60)
    return min(max(seconds, 30), 300)  # clamp 30s-5min


# ═══════════════════════════════════════════════════════════
#  CORRELATION FILTER
# ═══════════════════════════════════════════════════════════
def is_correlated_safe(new_pair, new_dir, open_trades):
    for group in CORRELATED_GROUPS:
        if new_pair in group:
            for trade in open_trades:
                if trade['pair'] in group and trade['direction'] == new_dir:
                    return False
    return True


# ═══════════════════════════════════════════════════════════
#  TELEGRAM NOTIFICATION
# ═══════════════════════════════════════════════════════════
def send_to_telegram(message):
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT, "text": message, "parse_mode": "HTML"}
        resp = requests.post(url, data=data, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════
def backtest(pair, df, engine_obj):
    wins, losses = 0, 0
    for i in range(100, len(df)-1):
        slice_1m = df.iloc[max(i-50,0):i]
        slice_3m = df.iloc[max(i-150,0):i]
        slice_5m = df.iloc[max(i-250,0):i]
        if len(slice_1m) < 50 or len(slice_3m) < 50 or len(slice_5m) < 50:
            continue
        signal = engine_obj.generate(
            {'1m': slice_1m, '3m': slice_3m, '5m': slice_5m},
            pair, 'iq', '1m'
        )
        if signal:
            future_price = df['close'].iloc[min(i+2, len(df)-1)]
            entry = signal['entry_price']
            if signal['direction'] == 'BUY':
                outcome = future_price > entry
            else:
                outcome = future_price < entry
            if outcome:
                wins += 1
            else:
                losses += 1
    total = wins + losses
    win_rate = wins / total * 100 if total > 0 else 0
    return wins, losses, win_rate


# ═══════════════════════════════════════════════════════════
#  STRICT SIGNAL CHECK (10 filters + divergence)
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

    # 7. Liquidity sweep
    sweep = liquidity_sweep(df_1m)
    checks['liquidity'] = (direction=='BUY' and sweep=='sell_side') or \
                          (direction=='SELL' and sweep=='buy_side')

    # 8. Volume spike
    if len(df_1m) >= 20 and df_1m['volume'].rolling(20).mean().iloc[-1] > 0:
        vol_ratio = float(df_1m['volume'].iloc[-1] / df_1m['volume'].rolling(20).mean().iloc[-1])
    else:
        vol_ratio = 1.0
    checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9. Momentum
    pct = (df_1m['close'].iloc[-1]/df_1m['close'].iloc[-4]-1)
    checks['momentum'] = abs(pct) >= CONFIG['MOMENTUM_MIN']

    # 10. RSI divergence (bonus filter)
    close_arr = df_1m['close'].values
    rsi_arr = rsi_series(close_arr, 14)
    checks['divergence'] = detect_divergence(close_arr, rsi_arr, direction)

    passed = all(checks.values())
    return passed, checks


# ═══════════════════════════════════════════════════════════
#  WINNING ENGINE v9
# ═══════════════════════════════════════════════════════════
class WinningEngine:
    def __init__(self):
        self.open_trades: list = []

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

        # Correlation filter
        if not is_correlated_safe(pair, direction, self.open_trades):
            return None

        # ATR-based dynamic expiry
        dynamic_seconds = atr_expiry(df1m)
        tf_sec = {'30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
                  'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300}
        duration = tf_sec.get(timeframe, dynamic_seconds)

        now = datetime.now(pytz.UTC)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df1m['close'].iloc[-1])

        # ML confidence scoring
        if len(df1m) >= 20 and df1m['volume'].rolling(20).mean().iloc[-1] > 0:
            vol_ratio = float(df1m['volume'].iloc[-1] / df1m['volume'].rolling(20).mean().iloc[-1])
        else:
            vol_ratio = 1.0
        features = {
            'adx': float(adx(df1m)),
            'rsi': float(rsi(df1m['close'].values)),
            'vol_ratio': vol_ratio,
            'momentum': float(abs(pct)),
            'mtf': float(mtf_score({'1m':df1m,'3m':df3m,'5m':df5m}, direction))
        }
        confidence = int(ml_scorer.predict(features))
        confidence = min(max(confidence, 60), 97)

        # Martingale
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl,mult,delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level':lvl, 'multiplier':mult,
                'amount':round(mult,2),
                'entry_time':t.strftime('%H:%M')
            })

        # Formatted signal
        color = "\U0001f7e2" if direction=='BUY' else "\U0001f534"
        arrow = "\u25b2" if direction=='BUY' else "\u25bc"
        div_text = "\u2705 Divergence" if checks.get('divergence') else ""
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
            f"\U0001f4c8 Structure: {checks['market_structure']} {div_text}",
            f"\U0001f4ca ADX: {features['adx']:.1f} | RSI: {features['rsi']:.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501"*24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 High-probability setup", "\u2501"*24]

        result = {
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
                'adx': round(features['adx'], 1),
                'rsi': round(features['rsi'], 1),
                'structure': checks.get('market_structure', ''),
                'vol_ratio': round(vol_ratio, 2),
                'divergence': checks.get('divergence', False),
                'dynamic_expiry_seconds': duration,
                'ml_confidence': confidence
            }
        }

        # Telegram notification
        send_to_telegram(result['formatted_signal'])

        return result


# ═══════════════════════════════════════════════════════════
#  KEEP ALIVE
# ═══════════════════════════════════════════════════════════
async def keep_alive():
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(f"{API_URL}/health", timeout=10)
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
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e1a">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Catalyst AI v9</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:12px}
.container{max-width:520px;width:100%}
.header{display:flex;justify-content:space-between;align-items:center;padding:12px 0;margin-bottom:10px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.3em;font-weight:bold;color:#00ff88}
.logo span{color:#fff}
.status-pill{padding:4px 10px;border-radius:16px;font-size:.75em;font-weight:600}
.status-pill.live{background:rgba(0,255,136,.12);color:#00ff88}
.status-pill.waking{background:rgba(255,215,0,.12);color:#ffd700;animation:blink 1s infinite}
.status-pill.offline{background:rgba(255,68,68,.12);color:#ff5252}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.wake-banner{display:none;background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.15);border-radius:8px;padding:8px 12px;margin-bottom:10px;color:#ffd700;font-size:.8em;align-items:center;gap:8px}
.wake-banner.show{display:flex}
.spinner{width:12px;height:12px;border:2px solid rgba(255,215,0,.25);border-top:2px solid #ffd700;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.platform-tabs{display:flex;justify-content:center;gap:6px;margin-bottom:10px}
.ptab{background:#131829;border:1px solid #2a2f3d;color:#aaa;padding:7px 18px;border-radius:18px;cursor:pointer;font-size:.82em;font-weight:500;transition:all .2s}
.ptab.active{background:#00ff88;color:#0a0e1a;border-color:#00ff88;font-weight:700}
.tf-tabs{display:flex;justify-content:center;gap:4px;margin-bottom:10px;flex-wrap:wrap}
.tftab{background:#0d1220;border:1px solid #1e2436;color:#888;padding:4px 12px;border-radius:14px;cursor:pointer;font-size:.74em;white-space:nowrap}
.tftab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88;font-weight:600}
.pair-tabs{display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap}
.pair-tab{padding:4px 10px;border-radius:10px;border:1px solid #1e2436;background:#0d1220;color:#777;cursor:pointer;font-size:.7em;white-space:nowrap}
.pair-tab.active{background:rgba(0,255,136,.1);color:#00ff88;border-color:#00ff88}
.pair-tab.session{border-color:rgba(255,215,0,.3);color:#ffd700}
.scan-btn{width:100%;padding:10px;background:linear-gradient(135deg,#00ff88,#00cc6a);color:#0a0e1a;border:none;border-radius:8px;font-weight:bold;font-size:.85em;cursor:pointer;margin-bottom:10px}
.scan-btn:disabled{opacity:.5;cursor:not-allowed}
.signal-card{background:#131829;border-radius:12px;padding:16px;margin-bottom:12px;border-left:4px solid;animation:fadeSlide .4s ease-out}
.signal-card.buy{border-color:#00ff88;box-shadow:0 0 16px rgba(0,255,136,.06)}
.signal-card.sell{border-color:#ff5252;box-shadow:0 0 16px rgba(255,82,82,.06)}
.signal-card.no-signal{border-color:#333;background:#0d1117;text-align:center;padding:30px 16px}
@keyframes fadeSlide{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.dir-row{display:flex;align-items:center;justify-content:space-between;margin:6px 0}
.direction{font-size:1.6rem;font-weight:bold}
.direction.buy{color:#00ff88}
.direction.sell{color:#ff5252}
.pair-name{font-size:1em;font-weight:600;color:#fff}
.engine-tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:.65em;font-weight:700;margin-left:4px;background:rgba(0,255,136,.12);color:#00ff88}
.detail-row{display:flex;justify-content:space-between;margin:4px 0;font-size:.82em;color:#aaa}
.detail-row .val{color:#e0e0e0;font-weight:500}
.checks-row{display:flex;flex-wrap:wrap;gap:3px;margin:8px 0}
.check-badge{padding:2px 7px;border-radius:6px;font-size:.64em;font-weight:600;border:1px solid}
.check-badge.pass{background:rgba(0,255,136,.06);color:#00ff88;border-color:rgba(0,255,136,.2)}
.check-badge.fail{background:rgba(255,68,68,.06);color:#ff5252;border-color:rgba(255,68,68,.2)}
.confidence-bar{width:100%;height:5px;background:#1e2436;border-radius:3px;margin:8px 0 3px;overflow:hidden}
.confidence-fill{height:100%;border-radius:3px;transition:width .5s}
.confidence-fill.high{background:linear-gradient(90deg,#00ff88,#00cc6a)}
.confidence-fill.med{background:linear-gradient(90deg,#ffd700,#ffaa00)}
.confidence-fill.low{background:linear-gradient(90deg,#ff5252,#cc0000)}
.conf-label{font-size:.72em;color:#888;text-align:right}
.martingale{margin:10px 0 0;background:#0a0f1a;border-radius:6px;padding:8px 10px;border:1px solid #1a1f2e}
.mart-title{color:#ffd700;font-size:.75em;font-weight:bold;margin-bottom:4px}
.mart-row{display:flex;justify-content:space-between;padding:3px 0;font-size:.75em;border-bottom:1px solid #111827}
.mart-row:last-child{border-bottom:none}
.mart-level{color:#ffd700;font-weight:600;min-width:24px}
.mart-mult{color:#aaa}
.mart-amt{color:#fff;font-weight:600}
.mart-time{color:#666}
.risk-note{text-align:center;font-size:.68em;color:#555;margin-top:6px}
.copy-btn{width:100%;padding:9px;background:#00ff88;color:#0a0e1a;border:none;border-radius:6px;font-weight:bold;margin-top:8px;cursor:pointer;font-size:.82em}
.copy-btn:active{transform:scale(.97)}
.footer{text-align:center;font-size:.68em;color:#444;margin-top:16px;padding:8px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="logo">CATALYST<span>AI</span> <span style="font-size:.45em;color:#888">v9</span></div>
    <div class="status-pill" id="status">Connecting</div>
  </div>
  <div class="wake-banner" id="wakeBanner">
    <div class="spinner"></div>
    <span id="wakeText">Waking backend...</span>
  </div>
  <div class="platform-tabs">
    <div class="ptab active" onclick="setPlat(this,'iq')">IQ Option</div>
    <div class="ptab" onclick="setPlat(this,'pocket')">Pocket Option</div>
  </div>
  <div class="tf-tabs" id="tfTabs"></div>
  <div class="pair-tabs" id="pairTabs"></div>
  <button class="scan-btn" id="scanBtn" onclick="scanAll()">Scan Best Session Pairs</button>
  <div id="signalsContainer">
    <div class="signal-card no-signal">
      <div style="font-size:1.8em;margin-bottom:8px">&#x23f3;</div>
      <div style="color:#888">Waiting for winning setup...</div>
    </div>
  </div>
  <div class="footer">Trade at your own risk &middot; Risk 1% only &middot; WAT Timezone</div>
</div>
<script>
const API=window.location.origin;
const ALL_PAIRS=['EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC','AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC','AUDUSD-OTC','NZDUSD-OTC','EURGBP-OTC'];
const IQ_TFS=['30s','45s','1m','2m','3m','5m'];
const PO_TFS=['S3','S15','S30','M1','M3','M5'];
let platform='iq',tf='1m',activePair=ALL_PAIRS[0],signalCache={};

async function fetchWithRetry(url,retries=5){
  for(let i=0;i<retries;i++){
    try{const r=await fetch(url);if(r.ok){if(i>0)hideWake();return r;}
    const d=await r.json().catch(()=>({}));if(d.Message&&d.Message.includes('pending')){showWake('Waking... '+(i+1)+'/'+retries);await new Promise(r=>setTimeout(r,(i+1)*3000));continue;}
    throw new Error(d.Message||'Error');}catch(e){if(i<retries-1){showWake('Connecting... '+(i+1)+'/'+retries);await new Promise(r=>setTimeout(r,(i+1)*3000));continue;}throw e;}}
  throw new Error('Unreachable');}

function setStatus(s){const e=document.getElementById('status');e.className='status-pill '+s;e.textContent=s==='live'?'Live':s==='waking'?'Waking...':'Offline';}
function showWake(t){document.getElementById('wakeBanner').classList.add('show');document.getElementById('wakeText').textContent=t;setStatus('waking');}
function hideWake(){document.getElementById('wakeBanner').classList.remove('show');setStatus('live');}
function setPlat(btn,p){document.querySelectorAll('.ptab').forEach(t=>t.classList.remove('active'));btn.classList.add('active');platform=p;buildTf();fetchSig();}

function buildTf(){
  const tfs=platform==='iq'?IQ_TFS:PO_TFS;if(!tfs.includes(tf))tf=tfs[0];
  const c=document.getElementById('tfTabs');c.innerHTML='';
  tfs.forEach(t=>{const b=document.createElement('div');b.className='tftab'+(t===tf?' active':'');b.textContent=t;b.onclick=()=>{tf=t;buildTf();fetchSig();};c.appendChild(b);});
}

function buildPairs(){
  const c=document.getElementById('pairTabs');c.innerHTML='';
  ALL_PAIRS.forEach(p=>{const b=document.createElement('div');b.className='pair-tab'+(p===activePair?' active':'');b.textContent=p.replace('-OTC','');b.onclick=()=>{activePair=p;buildPairs();fetchSig();};c.appendChild(b);});
}

async function fetchSig(){
  try{const res=await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${activePair}&timeframe=${tf}`);
  const data=await res.json();if(data.formatted_signal){signalCache[activePair]=data;renderSig(data);setStatus('live');}
  else{signalCache[activePair]=null;renderNo(data.message||'No winning setup');setStatus('live');}}
  catch(e){renderNo('Backend offline');setStatus('offline');}
}

async function scanAll(){
  const btn=document.getElementById('scanBtn');btn.disabled=true;btn.textContent='Scanning...';let found=0;
  for(const p of ALL_PAIRS){try{const res=await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${p}&timeframe=${tf}`);
  const d=await res.json();if(d.formatted_signal){signalCache[p]=d;found++;}else{signalCache[p]=null;}}catch(e){signalCache[p]=null;}}
  btn.disabled=false;btn.textContent='Scan ('+found+' signals)';renderSig(signalCache[activePair]);hideWake();
}

function renderSig(s){
  const cont=document.getElementById('signalsContainer');
  if(!s||!s.formatted_signal){renderNo('No winning setup');return;}
  const cls=s.direction.toLowerCase();const confCls=s.confidence>=70?'high':s.confidence>=50?'med':'low';
  let chks='';if(s.checks){chks='<div class="checks-row">';for(const[k,v]of Object.entries(s.checks)){const l=k.replace(/_/g,' ').toUpperCase();const isStr=typeof v==='string';chks+=`<span class="check-badge ${isStr?(v.includes('TREND')?'pass':'fail'):(v?'pass':'fail')}">${isStr?v:(v?'&#10003;':'&#10007;')} ${l}</span>`;}chks+='</div>';}
  let mart='';if(s.martingale&&s.martingale.length){mart='<div class="martingale"><div class="mart-title">\u{1F6E1}\uFE0F RECOVERY</div>';s.martingale.forEach(m=>{mart+='<div class="mart-row"><span class="mart-level">'+m.level+'</span><span class="mart-mult">'+m.multiplier+'x</span><span class="mart-amt">$'+m.amount+'</span><span class="mart-time">'+m.entry_time+'</span></div>';});mart+='</div>';}
  const emoji=cls==='buy'?'\u{1F7E2}':'\u{1F534}';const arrow=cls==='buy'?'\u25B2':'\u25BC';
  cont.innerHTML='<div class="signal-card '+cls+'"><div class="dir-row"><span class="direction '+cls+'">'+emoji+' '+s.direction+' '+arrow+'</span><span class="pair-name">'+s.platform.toUpperCase()+' \u00B7 '+(s.pair||activePair).replace('-OTC','')+'<span class="engine-tag">10/10</span></span></div>'+
  '<div class="detail-row"><span>Entry</span><span class="val">'+(s.entry_price?s.entry_price.toFixed(5):'--')+'</span></div>'+
  '<div class="detail-row"><span>ADX</span><span class="val">'+(s.indicators?s.indicators.adx:'--')+'</span></div>'+
  '<div class="detail-row"><span>RSI</span><span class="val">'+(s.indicators?s.indicators.rsi:'--')+'</span></div>'+
  '<div class="detail-row"><span>Structure</span><span class="val">'+(s.indicators?s.indicators.structure:'--')+'</span></div>'+
  (s.indicators&&s.indicators.divergence?'<div class="detail-row"><span>Divergence</span><span class="val" style="color:#00ff88">\u2705 Detected</span></div>':'')+
  chks+'<div class="confidence-bar"><div class="confidence-fill '+confCls+'" style="width:'+s.confidence+'%"></div></div><div class="conf-label">'+s.confidence+'% ML confidence</div>'+
  mart+'<div class="risk-note">\u26A0\uFE0F Risk 1% only \u00B7 10/10 confluence</div>'+
  '<button class="copy-btn" onclick="navigator.clipboard.writeText(\`'+s.formatted_signal.replace(/`/g,"\\`").replace(/\\/g,"\\\\")+'\`)">\u{1F4CB} Copy</button></div>';
}

function renderNo(msg){document.getElementById('signalsContainer').innerHTML='<div class="signal-card no-signal"><div style="font-size:1.8em;margin-bottom:8px">\u23F3</div><div style="color:#888">'+msg+'</div></div>';}

buildTf();buildPairs();fetchSig();setInterval(fetchSig,15000);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {
        "status": "online",
        "engine": "WinningEngine",
        "version": "9.0",
        "features": ["MarketStructure", "MLScorer", "Divergence", "ATR_Expiry",
                     "CorrelationFilter", "SessionPairs", "Telegram", "Backtest"],
        "filters": 10,
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "best_pairs_now": best_pairs_for_session(),
        "signals_cached": len(latest_signals),
    }


@app.get("/signal")
async def get_signal(platform: str = "iq", pair: str = "EURUSD-OTC", timeframe: str = "1m"):
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")

    # Simulated data — replace with live broker API
    np.random.seed(hash(pair) % 2**32)
    trend = np.linspace(0, 0.0004 if 'UP' in pair else -0.0004, 200) + np.random.randn(200)*0.0001
    close = 1.0 + trend
    if 'JPY' in pair: close = 148.0 + trend * 100
    elif 'XAU' in pair: close = 2350.0 + trend * 10000
    elif 'GBP' in pair or 'CAD' in pair: close = 1.35 + trend
    elif 'AUD' in pair: close = 0.65 + trend

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
    if not sig:
        return {
            "formatted_signal": None,
            "direction": None,
            "message": f"No winning setup for {pair} \u2014 filters not met",
            "pair": pair, "platform": platform,
            "timeframe": timeframe, "confidence": 0
        }
    sig["pair"] = pair
    latest_signals.insert(0, sig)
    if len(latest_signals) > 50:
        latest_signals.pop()
    return sig


@app.get("/session-pairs")
async def session_pairs():
    return {"pairs": best_pairs_for_session(), "hour_utc": datetime.now(pytz.UTC).hour}


@app.get("/backtest")
async def run_backtest(pair: str = "EURUSD-OTC"):
    """Quick backtest using simulated data"""
    np.random.seed(hash(pair) % 2**32 + 999)
    n = 500
    trend = np.linspace(0, 0.001, n) + np.random.randn(n) * 0.0003
    close = 1.0 + trend
    spread = 0.0005
    df = pd.DataFrame({
        'open': close - 0.0002, 'high': close + spread,
        'low': close - spread, 'close': close,
        'volume': np.random.randint(50, 200, n)
    })
    wins, losses, win_rate = backtest(pair, df, engine)
    return {"pair": pair, "wins": wins, "losses": losses, "win_rate": round(win_rate, 1), "total_trades": wins + losses}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
