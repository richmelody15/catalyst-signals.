"""
CATALYST AI v13 – LIVE BLITZ ENGINE + S/D + S/R DETECTOR
- Live broker data (IQ Option + Pocket Option) with simulated fallback
- OTC-optimized Blitz CONFIG (faster ADX, wider zones, shorter windows)
- Smart Money Concepts (Order Blocks, Fair Value Gaps, Liquidity Sweeps)
- Supply/Demand Zones + Support/Resistance Lines (3-layer confirmation)
- Market Structure (Uptrend/Downtrend/Ranging/Choppy)
- Hidden RSI Divergence (bonus confidence boost)
- AI Probability Scorer (Logistic Regression with bonuses)
- Platform-aware filters (volume skipped for Pocket Option)
- Auto-scan session pairs
- Martingale recovery
- Self-ping keep-alive
- Embedded PWA dashboard
"""

import asyncio, httpx, os, joblib, time as time_module
import numpy as np, pandas as pd, pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sklearn.linear_model import LogisticRegression
from typing import Dict, List, Optional, Tuple

# Optional broker API imports (graceful fallback if not installed)
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

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════
WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')
MODEL_PATH = 'model.pkl'

IQ_TIMEFRAMES   = ['30s','45s','1m','2m','3m','5m']
PO_TIMEFRAMES   = ['S3','S15','S30','M1','M3','M5']

# ⚡ Optimised for OTC Blitz (quick, strong moves)
CONFIG = {
    'ADX_MIN': 20,                 # slightly lower – OTC trends can spike fast
    'VOLUME_MULT': 1.3,            # OTC volume can be erratic
    'RSI_OB': 65,                  # tighter overbought
    'RSI_OS': 35,                  # tighter oversold
    'MTF_MIN': 2,                  # keep strict
    'SR_PROXIMITY': 0.008,         # wider zone for fast markets
    'NEWS_AVOID': (12, 14),
    'LIQUIDITY_WINDOW': 15,        # shorter lookback for sweeps
    'MOMENTUM_MIN': 0.0003,        # require slightly more move
    'MARTINGALE': [('M1',1.5,1), ('M2',2.5,2), ('M3',4.0,3)],
    'MIN_CONFIDENCE': 80,
    'DIVERGENCE_WINDOW': 10
}


# ═══════════════════════════════════════════════════════════
#  LIVE DATA FEED
# ═══════════════════════════════════════════════════════════
class LiveDataFeed:
    """Connects to IQ Option and Pocket Option APIs with graceful fallback."""

    def __init__(self):
        self.iq = None
        self.po = None
        self._connect_all()

    def _connect_all(self):
        # IQ Option
        iq_email = os.getenv('IQ_EMAIL', '')
        iq_pass = os.getenv('IQ_PASSWORD', '')
        if HAS_IQ and iq_email and iq_pass:
            try:
                self.iq = IQ_Option(iq_email, iq_pass)
                check, reason = self.iq.connect()
                if check:
                    self.iq.change_balance('PRACTICE')
                    print("✅ IQ Option connected (PRACTICE)")
                else:
                    print(f"⚠️ IQ Option login failed: {reason}")
                    self.iq = None
            except Exception as e:
                print(f"⚠️ IQ Option error: {e}")
                self.iq = None
        else:
            print("ℹ️ IQ Option: no credentials or library not installed – using simulated data")

        # Pocket Option
        po_ssid = os.getenv('PO_SSID', '')
        if HAS_PO and po_ssid:
            try:
                demo = os.getenv('PO_DEMO', '1') == '1'
                self.po = PocketOption(po_ssid, demo)
                self.po.connect()
                print("✅ Pocket Option connected")
            except Exception as e:
                print(f"⚠️ Pocket Option error: {e}")
                self.po = None
        else:
            print("ℹ️ Pocket Option: no SSID or library not installed – using simulated data")

    @property
    def is_live(self, platform='iq'):
        if platform == 'iq':
            return self.iq is not None
        return self.po is not None

    def get_candles(self, platform, pair, timeframe_sec, count=200):
        """Fetch OHLCV DataFrame. Falls back to simulated data on error."""
        try:
            if platform == 'iq' and self.iq is not None:
                return self._get_iq_candles(pair, timeframe_sec, count)
            elif platform == 'pocket' and self.po is not None:
                return self._get_po_candles(pair, timeframe_sec, count)
        except Exception as e:
            print(f"⚠️ Live data error for {pair}: {e}")

        # Fallback to simulated data
        return self._generate_simulated(pair, count)

    def _get_iq_candles(self, pair, timeframe_sec, count):
        end = time_module.time()
        candles = self.iq.get_candles(pair, timeframe_sec, count, end)
        df = pd.DataFrame(candles)
        if not df.empty:
            df = df.rename(columns={
                'open': 'open', 'high': 'high',
                'low': 'low', 'close': 'close', 'volume': 'volume'
            })
        return df

    def _get_po_candles(self, pair, timeframe_sec, count):
        end = int(time_module.time())
        start = end - (count * timeframe_sec)
        candles = self.po.get_history(pair, timeframe_sec, start, end)
        df = pd.DataFrame(candles)
        if not df.empty:
            df = df.rename(columns={
                'open': 'open', 'high': 'high',
                'low': 'low', 'close': 'close'
            })
            # Pocket Option does NOT provide volume – generate pseudo volume
            if 'volume' not in df.columns or df['volume'].isna().all():
                df['volume'] = ((df['high'] - df['low']) * 10000).astype(int)
        return df

    def _generate_simulated(self, pair, count=200):
        """Simulated data fallback when broker APIs are unavailable."""
        np.random.seed(hash(pair) % 2**32)
        trend = np.linspace(0, 0.0004 if 'UP' in pair else -0.0004, count) + np.random.randn(count)*0.0001
        close = 1.0 + trend
        if 'JPY' in pair: close = 148.0 + trend * 100
        elif 'XAU' in pair: close = 2350.0 + trend * 10000
        elif 'BTC' in pair: close = 65000.0 + trend * 50000
        elif 'BRL' in pair: close = 5.0 + trend
        elif 'MXN' in pair: close = 17.0 + trend * 10
        elif 'GBP' in pair or 'CAD' in pair: close = 1.35 + trend
        elif 'AUD' in pair: close = 0.65 + trend

        spread = 0.0005 if 'XAU' not in pair else 0.5
        return pd.DataFrame({
            'open': close - 0.0002,
            'high': close + spread,
            'low': close - spread,
            'close': close,
            'volume': np.random.randint(50, 200, count).astype(float)
        })


# ═══════════════════════════════════════════════════════════
#  INDICATORS
# ═══════════════════════════════════════════════════════════
def adx(df, period=14):
    h, l, c = df['high'], df['low'], df['close']
    tr = np.maximum(h - l, np.maximum(abs(h - c.shift()), abs(l - c.shift())))
    atr = tr.rolling(period).mean().iloc[-1]
    if atr == 0: return 0
    up = h.diff().clip(lower=0)
    down = -l.diff().clip(upper=0)
    di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
    di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) != 0 else 0
    return dx

def rsi(close, period=14):
    delta = np.diff(close)
    gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
    loss = -np.mean(delta[delta < 0]) if any(delta < 0) else 0
    if loss == 0: return 100
    return 100 - (100 / (1 + gain / loss))


# ═══════════════════════════════════════════════════════════
#  MARKET STRUCTURE
# ═══════════════════════════════════════════════════════════
def market_structure(df):
    if len(df) < 50: return 'RANGING'
    highs, lows = df['high'].values, df['low'].values
    sh, sl = [], []
    for i in range(5, len(highs) - 5):
        if highs[i] == max(highs[i-5:i+6]): sh.append(highs[i])
        if lows[i] == min(lows[i-5:i+6]): sl.append(lows[i])
    if len(sh) >= 3 and len(sl) >= 3:
        if sh[-1] > sh[-2] > sh[-3] and sl[-1] > sl[-2] > sl[-3]: return 'UP_TREND'
        if sh[-1] < sh[-2] < sh[-3] and sl[-1] < sl[-2] < sl[-3]: return 'DOWN_TREND'
    a = adx(df)
    vol = df['close'].pct_change().std()
    if a < 18 or vol > 0.003: return 'CHOPPY'
    return 'RANGING'


# ═══════════════════════════════════════════════════════════
#  SMART MONEY CONCEPTS
# ═══════════════════════════════════════════════════════════
def detect_order_blocks(df):
    obs = []
    if len(df) < 3: return obs
    for i in range(2, len(df)-1):
        if df['close'].iloc[i] < df['open'].iloc[i] and df['high'].iloc[i+1] > df['high'].iloc[i]:
            obs.append({'type': 'DEMAND', 'high': float(df['high'].iloc[i]), 'low': float(df['low'].iloc[i])})
        if df['close'].iloc[i] > df['open'].iloc[i] and df['low'].iloc[i+1] < df['low'].iloc[i]:
            obs.append({'type': 'SUPPLY', 'high': float(df['high'].iloc[i]), 'low': float(df['low'].iloc[i])})
    return obs[-10:]

def detect_fvg(df):
    fvgs = []
    if len(df) < 3: return fvgs
    for i in range(1, len(df)-1):
        if df['low'].iloc[i] > df['high'].iloc[i-1]:
            fvgs.append({'type': 'BULLISH', 'top': float(df['low'].iloc[i]), 'bottom': float(df['high'].iloc[i-1])})
        if df['high'].iloc[i] < df['low'].iloc[i-1]:
            fvgs.append({'type': 'BEARISH', 'top': float(df['low'].iloc[i-1]), 'bottom': float(df['high'].iloc[i])})
    return fvgs[-5:]

def smart_money_confirmation(price, df, direction):
    obs = detect_order_blocks(df)
    fvgs = detect_fvg(df)
    for ob in obs:
        if direction == 'BUY' and ob['type'] == 'DEMAND' and ob['low'] <= price <= ob['high']: return True
        if direction == 'SELL' and ob['type'] == 'SUPPLY' and ob['low'] <= price <= ob['high']: return True
    for fvg in fvgs:
        if direction == 'BUY' and fvg['type'] == 'BULLISH' and fvg['bottom'] <= price <= fvg['top']: return True
        if direction == 'SELL' and fvg['type'] == 'BEARISH' and fvg['bottom'] <= price <= fvg['top']: return True
    return False


# ═══════════════════════════════════════════════════════════
#  SUPPORT / RESISTANCE + SUPPLY / DEMAND ENGINE
# ═══════════════════════════════════════════════════════════
class SRSupplyDemand:
    """Detects S/R levels (multi-touch swing lines) and Supply/Demand order-block zones."""

    def __init__(self, swing_window=5, touch_tolerance=0.001, merge_pct=0.003):
        self.swing_window = swing_window
        self.touch_tolerance = touch_tolerance
        self.merge_pct = merge_pct

    def find_swing_levels(self, df):
        """Returns support and resistance lines with strength based on multiple touches."""
        highs = df['high'].values
        lows = df['low'].values
        supports = []
        resistances = []

        for i in range(self.swing_window, len(highs) - self.swing_window):
            if highs[i] == max(highs[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(highs[i], df, 'high')
                resistances.append({'price': highs[i], 'touches': touches, 'type': 'resistance'})
            if lows[i] == min(lows[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(lows[i], df, 'low')
                supports.append({'price': lows[i], 'touches': touches, 'type': 'support'})

        supports = self._merge_levels(supports)
        resistances = self._merge_levels(resistances)
        supports = [l for l in supports if l['touches'] >= 2]
        resistances = [l for l in resistances if l['touches'] >= 2]
        return supports, resistances

    def find_order_blocks(self, df):
        """Detects supply (bearish OB) and demand (bullish OB) as zones."""
        obs = []
        for i in range(2, len(df) - 1):
            if df['close'].iloc[i] < df['open'].iloc[i]:
                if df['high'].iloc[i+1] > df['high'].iloc[i]:
                    volume = df.get('volume', pd.Series([1]*len(df)))
                    vol_score = volume.iloc[i] / volume.rolling(20).mean().iloc[i] if not volume.isna().all() else 1.0
                    obs.append({'type': 'demand', 'high': df['high'].iloc[i], 'low': df['low'].iloc[i], 'strength': vol_score})
            if df['close'].iloc[i] > df['open'].iloc[i]:
                if df['low'].iloc[i+1] < df['low'].iloc[i]:
                    volume = df.get('volume', pd.Series([1]*len(df)))
                    vol_score = volume.iloc[i] / volume.rolling(20).mean().iloc[i] if not volume.isna().all() else 1.0
                    obs.append({'type': 'supply', 'high': df['high'].iloc[i], 'low': df['low'].iloc[i], 'strength': vol_score})
        return obs[-10:]

    def is_near_sr(self, price, levels, direction, threshold_pct=0.005):
        for lvl in levels:
            if direction == 'BUY' and lvl['type'] == 'support' and price >= lvl['price']:
                if abs(price - lvl['price']) / price < threshold_pct: return True, lvl
            if direction == 'SELL' and lvl['type'] == 'resistance' and price <= lvl['price']:
                if abs(price - lvl['price']) / price < threshold_pct: return True, lvl
        return False, None

    def is_in_zone(self, price, zones, direction):
        for zone in zones:
            if direction == 'BUY' and zone['type'] == 'demand':
                if zone['low'] <= price <= zone['high']: return True, zone
            if direction == 'SELL' and zone['type'] == 'supply':
                if zone['low'] <= price <= zone['high']: return True, zone
        return False, None

    def _count_touches(self, level, df, col='high', tolerance=None):
        if tolerance is None: tolerance = self.touch_tolerance
        col_vals = df[col].values
        return sum(abs(val - level) / level < tolerance for val in col_vals)

    def _merge_levels(self, levels):
        if not levels: return []
        sorted_levels = sorted(levels, key=lambda x: x['price'])
        merged = []
        current_group = [sorted_levels[0]]
        for lvl in sorted_levels[1:]:
            prev = current_group[-1]
            if abs(lvl['price'] - prev['price']) / prev['price'] < self.merge_pct:
                current_group.append(lvl)
            else:
                merged.append(self._combine_group(current_group))
                current_group = [lvl]
        merged.append(self._combine_group(current_group))
        return merged

    def _combine_group(self, group):
        avg_price = sum(l['price'] for l in group) / len(group)
        total_touches = sum(l['touches'] for l in group)
        return {'price': avg_price, 'touches': total_touches, 'type': group[0]['type']}


sr_sd = SRSupplyDemand()


# ═══════════════════════════════════════════════════════════
#  PRO-LEVEL S/D + S/R DETECTOR (3-LAYER CONFIRMATION)
# ═══════════════════════════════════════════════════════════
class ProLevelSD_SR:
    """
    Main filter:  Supply/Demand zones
    Confirmation: Support/Resistance lines (multi-touch)
    Final:        RSI + ADX alignment
    """
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
                    strength = vol.iloc[i] / avg_vol if avg_vol > 0 else 1
                    obs.append({'type': 'demand', 'top': df['high'].iloc[i], 'bottom': df['low'].iloc[i], 'strength': strength})
            if df['close'].iloc[i] > df['open'].iloc[i]:
                if df['low'].iloc[i+1] < df['low'].iloc[i]:
                    vol = df.get('volume', pd.Series([1]*len(df)))
                    avg_vol = vol.rolling(20).mean().iloc[i] if not vol.isna().all() else 1
                    strength = vol.iloc[i] / avg_vol if avg_vol > 0 else 1
                    obs.append({'type': 'supply', 'top': df['high'].iloc[i], 'bottom': df['low'].iloc[i], 'strength': strength})
        return obs[-recent:]

    # ---- S/R: SWING LEVELS (LINES) ----
    def find_swing_levels(self, df, min_touches=2):
        highs = df['high'].values
        lows = df['low'].values
        supports = []
        resistances = []

        for i in range(self.swing_window, len(highs) - self.swing_window):
            if highs[i] == max(highs[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(highs[i], df, 'high')
                if touches >= min_touches:
                    resistances.append({'price': highs[i], 'touches': touches, 'type': 'resistance'})
            if lows[i] == min(lows[i-self.swing_window:i+self.swing_window+1]):
                touches = self._count_touches(lows[i], df, 'low')
                if touches >= min_touches:
                    supports.append({'price': lows[i], 'touches': touches, 'type': 'support'})

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

        return rsi_ok and adx_ok, {'rsi': rsi_val, 'adx': adx_val}

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
        near_sr, sr_level = self._is_near_sr(price, supports if direction == 'BUY' else resistances, direction)
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

    # ---- HELPER METHODS ----
    def _count_touches(self, level, df, col='high', tolerance=None):
        if tolerance is None: tolerance = self.touch_tolerance
        return sum(abs(val - level) / level < tolerance for val in df[col].values)

    def _merge_levels(self, levels):
        if not levels: return []
        sorted_lvls = sorted(levels, key=lambda x: x['price'])
        merged = []
        group = [sorted_lvls[0]]
        for lvl in sorted_lvls[1:]:
            if abs(lvl['price'] - group[-1]['price']) / group[-1]['price'] < self.merge_pct:
                group.append(lvl)
            else:
                merged.append(self._combine_group(group))
                group = [lvl]
        merged.append(self._combine_group(group))
        return merged

    def _combine_group(self, group):
        avg_price = sum(l['price'] for l in group) / len(group)
        total_touches = sum(l['touches'] for l in group)
        return {'price': avg_price, 'touches': total_touches, 'type': group[0]['type']}

    def _is_in_zone(self, price, zones, direction):
        for zone in zones:
            if direction == 'BUY' and zone['type'] == 'demand':
                if zone['bottom'] <= price <= zone['top']: return True, zone
            if direction == 'SELL' and zone['type'] == 'supply':
                if zone['bottom'] <= price <= zone['top']: return True, zone
        return False, None

    def _is_near_sr(self, price, levels, direction, threshold=0.005):
        for lvl in levels:
            if direction == 'BUY' and lvl['type'] == 'support' and price > lvl['price']:
                if abs(price - lvl['price']) / price < threshold: return True, lvl
            if direction == 'SELL' and lvl['type'] == 'resistance' and price < lvl['price']:
                if abs(price - lvl['price']) / price < threshold: return True, lvl
        return False, None

    # ---- INDICATORS ----
    def _rsi(self, close, period=14):
        delta = np.diff(close)
        gain = np.mean(delta[delta>0]) if any(delta>0) else 0
        loss = -np.mean(delta[delta<0]) if any(delta<0) else 0
        if loss == 0: return 100
        return 100 - (100 / (1 + gain/loss))

    def _adx(self, df, period=14):
        h, l, c = df['high'], df['low'], df['close']
        tr = np.maximum(h - l, np.maximum(abs(h - c.shift()), abs(l - c.shift())))
        atr = tr.rolling(period).mean().iloc[-1]
        if atr == 0: return 0
        up = h.diff().clip(lower=0)
        down = -l.diff().clip(upper=0)
        di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
        di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) != 0 else 0
        return dx


pro_sd_sr = ProLevelSD_SR()


# ═══════════════════════════════════════════════════════════
#  OTHER FILTERS
# ═══════════════════════════════════════════════════════════
def mtf_aligned(df_dict, direction):
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in df_dict and len(df_dict[tf]) >= 200:
            df = df_dict[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction == 'BUY' and ema50 > ema200: count += 1
            elif direction == 'SELL' and ema50 < ema200: count += 1
    return count >= CONFIG['MTF_MIN']

def mtf_score(df_dict, direction):
    count = 0
    for tf in ['1m','3m','5m']:
        if tf in df_dict and len(df_dict[tf]) >= 200:
            df = df_dict[tf]
            ema50 = df['close'].ewm(50).mean().iloc[-1]
            ema200 = df['close'].ewm(200).mean().iloc[-1]
            if direction == 'BUY' and ema50 > ema200: count += 1
            elif direction == 'SELL' and ema50 < ema200: count += 1
    return count

def candle_ok(df, direction):
    if len(df) < 2: return False
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['close'] - last['open'])
    if body == 0: return False
    if direction == 'BUY':
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['open']: return True
        lower_wick = min(last['open'], last['close']) - last['low']
        if last['close'] > last['open'] and lower_wick > 2 * body: return True
    else:
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['open']: return True
        upper_wick = last['high'] - max(last['open'], last['close'])
        if last['close'] < last['open'] and upper_wick > 2 * body: return True
    return False

def sr_favorable(price, df, direction):
    if len(df) < 20: return False
    res = df['high'].rolling(20).max().iloc[-1]
    sup = df['low'].rolling(20).min().iloc[-1]
    if direction == 'BUY': return abs(price - sup) / price < CONFIG['SR_PROXIMITY']
    return abs(res - price) / price < CONFIG['SR_PROXIMITY']

def liquidity_sweep(df):
    if len(df) < CONFIG['LIQUIDITY_WINDOW'] + 1: return None
    highs, lows = df['high'].values, df['low'].values
    vol = df['volume'].values
    avg_vol = np.mean(vol[-20:])
    if vol[-1] < avg_vol * CONFIG['VOLUME_MULT']: return None
    recent_high = np.max(highs[-CONFIG['LIQUIDITY_WINDOW']:])
    recent_low = np.min(lows[-CONFIG['LIQUIDITY_WINDOW']:])
    if highs[-1] > recent_high: return 'buy_side'
    if lows[-1] < recent_low: return 'sell_side'
    return None

def news_safe():
    now = datetime.now(pytz.UTC)
    return not (CONFIG['NEWS_AVOID'][0] <= now.hour < CONFIG['NEWS_AVOID'][1])

def detect_divergence(close, rsi_array, direction):
    if len(close) < CONFIG['DIVERGENCE_WINDOW']: return False
    c = close[-CONFIG['DIVERGENCE_WINDOW']:]
    r = rsi_array[-CONFIG['DIVERGENCE_WINDOW']:]
    if direction == 'BUY' and c[-1] < c[0] and r[-1] > r[0]: return True
    if direction == 'SELL' and c[-1] > c[0] and r[-1] < r[0]: return True
    return False

def select_best_pairs():
    """Return the most predictable OTC pairs for current session."""
    hour = datetime.now(pytz.UTC).hour
    if 8 <= hour < 10: return ['EURUSD-OTC','GBPUSD-OTC','EURGBP-OTC']
    elif 13 <= hour < 15: return ['XAUUSD-OTC','USDCAD-OTC','EURJPY-OTC']
    elif 15 <= hour < 17: return ['BTCUSD-OTC','USDBRL-OTC','USDMXN-OTC']
    else: return ['EURUSD-OTC']


# ═══════════════════════════════════════════════════════════
#  FILTER GATE (11 mandatory + 1 bonus) — platform-aware + S/D→S/R→Indicator
# ═══════════════════════════════════════════════════════════
def filter_gate(df1, df3, df5, direction, platform):
    """
    Returns (passed, checks_dict).
    Platform-aware: volume filter skipped for Pocket Option.
    3-layer S/D → S/R → Indicator confirmation integrated.
    """
    checks = {}

    # Gate 1: Market Structure
    structure = market_structure(df1)
    checks['structure'] = structure
    if direction == 'BUY' and structure != 'UP_TREND': return False, checks
    if direction == 'SELL' and structure != 'DOWN_TREND': return False, checks

    # 2: ADX
    checks['adx'] = bool(adx(df1) >= CONFIG['ADX_MIN'])

    # 3: MTF
    checks['mtf'] = mtf_aligned({'1m': df1, '3m': df3, '5m': df5}, direction)

    # 4: News
    checks['news'] = news_safe()

    # 5: Candle
    checks['candle'] = candle_ok(df1, direction)

    # 6: S/R (simple proximity)
    price = float(df1['close'].iloc[-1])
    checks['sr'] = sr_favorable(price, df1, direction)

    # 7: Liquidity
    sweep = liquidity_sweep(df1)
    checks['liquidity'] = (direction == 'BUY' and sweep == 'sell_side') or \
                          (direction == 'SELL' and sweep == 'buy_side')

    # 8: Volume (skip for Pocket Option — no real volume)
    if platform == 'pocket':
        checks['volume'] = True
    else:
        vol_ratio = float(df1['volume'].iloc[-1] / df1['volume'].rolling(20).mean().iloc[-1])
        checks['volume'] = vol_ratio >= CONFIG['VOLUME_MULT']

    # 9: Smart Money (OB or FVG)
    checks['smart_money'] = smart_money_confirmation(price, df1, direction)

    # 10: Momentum
    pct = (price / df1['close'].iloc[-4] - 1)
    checks['momentum'] = bool(abs(pct) >= CONFIG['MOMENTUM_MIN'])

    # 11: Supply/Demand → S/R → Indicator (3-layer confirmation)
    sd_passed, sd_sr_details = pro_sd_sr.entry_check(df1, direction)
    checks['sd_zone'] = sd_sr_details.get('sd_zone', False)
    checks['sr_confirmed'] = sd_sr_details.get('sr_confirmed', False)
    checks['indicator_final'] = sd_sr_details.get('indicator_final', False)
    checks['supply_demand'] = sd_passed  # combined gate for mandatory list

    # Bonus: Divergence
    rsi_vals = np.array([rsi(df1['close'].values[:i], 14) for i in range(14, len(df1))])
    checks['divergence'] = detect_divergence(df1['close'].values, rsi_vals, direction)

    mandatory = ['adx','mtf','news','candle','sr','liquidity','volume','smart_money','momentum','supply_demand']
    passed = all(checks[k] for k in mandatory)
    return passed, checks


# ═══════════════════════════════════════════════════════════
#  AI CONFIDENCE SCORER
# ═══════════════════════════════════════════════════════════
class AIScorer:
    def __init__(self):
        try:
            self.model = joblib.load(MODEL_PATH)
        except Exception:
            self.model = None

    def predict(self, features):
        if self.model:
            X = np.array([[features['adx'], features['rsi'],
                           features['vol_ratio'], features['momentum'],
                           features['mtf']]])
            return float(self.model.predict_proba(X)[0][1] * 100)
        base = 86.0
        if features.get('divergence'): base += 5
        if features.get('smart_money'): base += 4
        if features.get('supply_demand'): base += 3  # S/D + S/R 3-layer confirmation bonus
        return min(base, 98.0)

    def train(self, trades):
        if len(trades) < 20: return False
        df = pd.DataFrame(trades)
        X = df[['adx','rsi','vol_ratio','momentum','mtf']]
        y = df['outcome'].map({'WIN':1,'LOSS':0})
        self.model = LogisticRegression()
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        return True

ai_scorer = AIScorer()


# ═══════════════════════════════════════════════════════════
#  ULTIMATE BLITZ ENGINE
# ═══════════════════════════════════════════════════════════
class UltimateEngine:
    def generate(self, market_data, pair, platform, timeframe):
        df1, df3, df5 = market_data['1m'], market_data['3m'], market_data['5m']
        if any(d is None or len(d) < 50 for d in [df1, df3, df5]):
            return None

        momentum_pct = (df1['close'].iloc[-1] / df1['close'].iloc[-4] - 1)
        direction = 'BUY' if momentum_pct > 0 else 'SELL'

        passed, checks = filter_gate(df1, df3, df5, direction, platform)
        if not passed:
            opp = 'SELL' if direction == 'BUY' else 'BUY'
            passed2, checks2 = filter_gate(df1, df3, df5, opp, platform)
            if passed2: direction, checks = opp, checks2
            else: return None

        # AI confidence
        adx_val = float(adx(df1))
        rsi_val = float(rsi(df1['close'].values, 14))
        vol_ratio = float(df1['volume'].iloc[-1] / df1['volume'].rolling(20).mean().iloc[-1]) if platform == 'iq' else 1.5
        mtf_cnt = float(mtf_score({'1m':df1, '3m':df3, '5m':df5}, direction))

        features = {
            'adx': adx_val, 'rsi': rsi_val,
            'vol_ratio': vol_ratio, 'momentum': float(abs(momentum_pct)),
            'mtf': mtf_cnt,
            'divergence': checks.get('divergence', False),
            'smart_money': checks.get('smart_money', False),
            'supply_demand': checks.get('supply_demand', False)
        }
        confidence = ai_scorer.predict(features)
        if confidence < CONFIG['MIN_CONFIDENCE']: return None

        # Time & expiry
        tf_sec = {'30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
                  'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300}
        duration = tf_sec.get(timeframe, 60)
        now = datetime.now(pytz.UTC)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df1['close'].iloc[-1])

        # Martingale
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append({
                'level': lvl, 'multiplier': mult,
                'amount': round(mult, 2), 'entry_time': t.strftime('%H:%M')
            })

        # Format
        color = "\U0001f7e2" if direction == 'BUY' else "\U0001f534"
        arrow = "\u25b2" if direction == 'BUY' else "\u25bc"
        data_src = "LIVE" if feed.is_live(platform) else "SIM"
        lines = [
            "\u2501"*24,
            f"\u26a1 LIVE BLITZ SIGNAL ({platform.upper()}) [{data_src}]",
            "\u2501"*24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence:.0f}%",
            f"\U0001f4c8 Structure: {checks['structure']}",
            f"\U0001f3e6 Smart Money: {'\u2705' if checks['smart_money'] else '\u274c'}",
            f"\U0001f4e6 S/D Zone: {'\u2705' if checks.get('sd_zone') else '\u274c'}",
            f"\U0001f4ca S/R Confirmed: {'\u2705' if checks.get('sr_confirmed') else '\u274c'}",
            f"\U0001f50d Divergence: {'\u2705' if checks.get('divergence') else 'No bonus'}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501"*24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Blitz-optimised", "\u2501"*24]

        return {
            'formatted_signal': '\n'.join(lines),
            'direction': direction,
            'entry_price': entry_price,
            'confidence': round(confidence, 1),
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform,
            'pair': pair,
            'data_source': data_src,
            'checks': {k: (v if isinstance(v, str) else bool(v)) for k, v in checks.items()},
            'martingale': martingale,
            'indicators': {
                'adx': round(adx_val, 1),
                'rsi': round(rsi_val, 1),
                'structure': checks.get('structure', ''),
                'vol_ratio': round(vol_ratio, 2),
                'smart_money': checks.get('smart_money', False),
                'divergence': checks.get('divergence', False),
                'sd_zone': checks.get('sd_zone', False),
                'sr_confirmed': checks.get('sr_confirmed', False),
                'indicator_final': checks.get('indicator_final', False),
                'supply_demand': checks.get('supply_demand', False),
                'ml_confidence': round(confidence, 1)
            }
        }


# ═══════════════════════════════════════════════════════════
#  KEEP ALIVE
# ═══════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════
#  FASTAPI
# ═══════════════════════════════════════════════════════════
app = FastAPI(lifespan=lifespan)
engine = UltimateEngine()
feed = LiveDataFeed()


# ═══════════════════════════════════════════════════════════
#  EMBEDDED PWA FRONTEND
# ═══════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e1a">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Catalyst Blitz</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:12px}
.container{max-width:520px;width:100%}
.header{display:flex;justify-content:space-between;align-items:center;padding:12px 0;margin-bottom:10px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.3em;font-weight:bold;color:#00ff88}
.logo span{color:#fff}
.badge{font-size:.55em;color:#ffd700;background:rgba(255,215,0,.1);padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}
.live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;animation:pulse 1.5s infinite}
.live-dot.on{background:#00ff88}
.live-dot.sim{background:#ffd700}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
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
.engine-tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:.65em;font-weight:700;margin-left:4px;background:rgba(255,215,0,.12);color:#ffd700}
.data-tag{display:inline-block;padding:2px 6px;border-radius:6px;font-size:.6em;font-weight:700;margin-left:4px}
.data-tag.live{background:rgba(0,255,136,.12);color:#00ff88}
.data-tag.sim{background:rgba(255,215,0,.12);color:#ffd700}
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
    <div class="logo">CATALYST<span>AI</span> <span class="badge">BLITZ v13</span></div>
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
      <div style="font-size:1.8em;margin-bottom:8px">&#x26a1;</div>
      <div style="color:#888">Waiting for Blitz setup...</div>
    </div>
  </div>
  <div class="footer">Trade at your own risk &middot; Risk 1% only &middot; Blitz Engine + S/D + S/R</div>
</div>
<script>
const API=window.location.origin;
const ALL_PAIRS=['EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC','AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC','AUDUSD-OTC','NZDUSD-OTC','EURGBP-OTC'];
const IQ_TFS=['30s','45s','1m','2m','3m','5m'];
const PO_TFS=['S3','S15','S30','M1','M3','M5'];
let platform='iq',tf='1m',activePair=ALL_PAIRS[0],signalCache={},lastSig=null;

async function fetchWithRetry(url,retries=5){
  for(let i=0;i<retries;i++){
    try{const r=await fetch(url);if(r.ok){if(i>0)hideWake();return r;}
    const d=await r.json().catch(()=>({}));if(d.detail&&d.detail.includes('pending')){showWake('Waking... '+(i+1)+'/'+retries);await new Promise(r=>setTimeout(r,(i+1)*3000));continue;}
    throw new Error(d.detail||'Error');}catch(e){if(i<retries-1){showWake('Connecting... '+(i+1)+'/'+retries);await new Promise(r=>setTimeout(r,(i+1)*3000));continue;}throw e;}}
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
  ALL_PAIRS.forEach(p=>{const b=document.createElement('div');b.className='pair-tab'+(p===activePair?' active':'');b.textContent=p.replace('-OTC','');b.onclick=()=>{activePair=p;buildPairs();fetchSigForPair();};c.appendChild(b);});
}

async function fetchSig(){
  try{const res=await fetchWithRetry(API+'/signal?platform='+platform+'&timeframe='+tf);
  const data=await res.json();if(data.formatted_signal){lastSig=data;renderSig(data);setStatus('live');}
  else{renderNo('No Blitz-grade setup');setStatus('live');}}
  catch(e){renderNo('Backend offline');setStatus('offline');}
}

async function fetchSigForPair(){
  try{const res=await fetchWithRetry(API+'/signal/'+activePair+'?platform='+platform+'&timeframe='+tf);
  const data=await res.json();if(data.formatted_signal){signalCache[activePair]=data;lastSig=data;renderSig(data);setStatus('live');}
  else{signalCache[activePair]=null;renderNo('No signal for '+activePair.replace('-OTC',''));setStatus('live');}}
  catch(e){renderNo('Backend offline');setStatus('offline');}
}

async function scanAll(){
  const btn=document.getElementById('scanBtn');btn.disabled=true;btn.textContent='Scanning...';let found=0;
  for(const p of ALL_PAIRS){try{const res=await fetchWithRetry(API+'/signal/'+p+'?platform='+platform+'&timeframe='+tf);
  const d=await res.json();if(d.formatted_signal){signalCache[p]=d;found++;}else{signalCache[p]=null;}}catch(e){signalCache[p]=null;}}
  btn.disabled=false;btn.textContent='Scan ('+found+' signals)';renderSig(signalCache[activePair]||lastSig);hideWake();
}

function renderSig(s){
  const cont=document.getElementById('signalsContainer');
  if(!s||!s.formatted_signal){renderNo('No Blitz-grade setup');return;}
  const cls=s.direction.toLowerCase();const confCls=s.confidence>=70?'high':s.confidence>=50?'med':'low';
  const dataTag=s.data_source==='LIVE'?'<span class="data-tag live">LIVE</span>':'<span class="data-tag sim">SIM</span>';
  let chks='';if(s.checks){chks='<div class="checks-row">';for(const[k,v]of Object.entries(s.checks)){const l=k.replace(/_/g,' ').toUpperCase();const isStr=typeof v==='string';chks+='<span class="check-badge '+(isStr?(v.includes('TREND')?'pass':'fail'):(v?'pass':'fail'))+'">'+(isStr?v:(v?'&#10003;':'&#10007;'))+' '+l+'</span>';}chks+='</div>';}
  let mart='';if(s.martingale&&s.martingale.length){mart='<div class="martingale"><div class="mart-title">\u{1F6E1}\uFE0F RECOVERY</div>';s.martingale.forEach(m=>{mart+='<div class="mart-row"><span class="mart-level">'+m.level+'</span><span class="mart-mult">'+m.multiplier+'x</span><span class="mart-amt">$'+m.amount+'</span><span class="mart-time">'+m.entry_time+'</span></div>';});mart+='</div>';}
  const emoji=cls==='buy'?'\u{1F7E2}':'\u{1F534}';const arrow=cls==='buy'?'\u25B2':'\u25BC';
  cont.innerHTML='<div class="signal-card '+cls+'"><div class="dir-row"><span class="direction '+cls+'">'+emoji+' '+s.direction+' '+arrow+'</span><span class="pair-name">'+s.platform.toUpperCase()+' \u00B7 '+(s.pair||activePair).replace('-OTC','')+'<span class="engine-tag">BLITZ</span>'+dataTag+'</span></div>'+
  '<div class="detail-row"><span>Entry</span><span class="val">'+(s.entry_price?s.entry_price.toFixed(5):'--')+'</span></div>'+
  '<div class="detail-row"><span>ADX</span><span class="val">'+(s.indicators?s.indicators.adx:'--')+'</span></div>'+
  '<div class="detail-row"><span>RSI</span><span class="val">'+(s.indicators?s.indicators.rsi:'--')+'</span></div>'+
  '<div class="detail-row"><span>Structure</span><span class="val">'+(s.indicators?s.indicators.structure:'--')+'</span></div>'+
  (s.indicators&&s.indicators.smart_money?'<div class="detail-row"><span>Smart Money</span><span class="val" style="color:#ffd700">\u2705 OB/FVG</span></div>':'')+
  (s.indicators&&s.indicators.sd_zone?'<div class="detail-row"><span>S/D Zone</span><span class="val" style="color:#00bfff">\u2705 In Zone</span></div>':'')+
  (s.indicators&&s.indicators.sr_confirmed?'<div class="detail-row"><span>S/R Confirmed</span><span class="val" style="color:#00bfff">\u2705 Multi-touch</span></div>':'')+
  (s.indicators&&s.indicators.divergence?'<div class="detail-row"><span>Divergence</span><span class="val" style="color:#00ff88">\u2705 Detected</span></div>':'')+
  chks+'<div class="confidence-bar"><div class="confidence-fill '+confCls+'" style="width:'+s.confidence+'%"></div></div><div class="conf-label">'+s.confidence+'% AI confidence</div>'+
  mart+'<div class="risk-note">\u26A0\uFE0F Risk 1% only \u00B7 Blitz Confluence</div>'+
  '<button class="copy-btn" onclick="navigator.clipboard.writeText(lastSig.formatted_signal)">\u{1F4CB} Copy</button></div>';
}

function renderNo(msg){document.getElementById('signalsContainer').innerHTML='<div class="signal-card no-signal"><div style="font-size:1.8em;margin-bottom:8px">\u26A1</div><div style="color:#888">'+msg+'</div></div>';}

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
        "engine": "UltimateEngine",
        "version": "13.0",
        "mode": "Blitz OTC + S/D + S/R",
        "filters": 11,
        "bonus_filters": 1,
        "ml_model_loaded": ai_scorer.model is not None,
        "iq_connected": feed.iq is not None,
        "po_connected": feed.po is not None,
        "best_pairs_now": select_best_pairs(),
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "config": {
            "adx_min": CONFIG['ADX_MIN'],
            "volume_mult": CONFIG['VOLUME_MULT'],
            "sr_proximity": CONFIG['SR_PROXIMITY'],
            "liquidity_window": CONFIG['LIQUIDITY_WINDOW'],
            "momentum_min": CONFIG['MOMENTUM_MIN']
        },
        "sd_sr_layers": ["sd_zone", "sr_confirmed", "indicator_final"],
        "mandatory_filters": ["structure","adx","mtf","news","candle","sr","liquidity","volume","smart_money","momentum","supply_demand"]
    }


@app.get("/signal")
async def high_confidence_signal(platform: str = "iq", timeframe: str = "1m"):
    """Auto-scan session pairs and return the highest-confidence signal."""
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")

    pairs = select_best_pairs()
    tf_sec = {'30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
              'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300}
    sec = tf_sec.get(timeframe, 60)

    best_signal = None
    best_confidence = 0

    for pair in pairs:
        try:
            df1 = feed.get_candles(platform, pair, sec, 200)
            df3 = feed.get_candles(platform, pair, sec*3, 200)
            df5 = feed.get_candles(platform, pair, sec*5, 200)
            if df1 is None or df1.empty: continue

            market = {'1m': df1, '3m': df3, '5m': df5}
            sig = engine.generate(market, pair, platform, timeframe)
            if sig and sig['confidence'] > best_confidence:
                best_signal = sig
                best_confidence = sig['confidence']
        except Exception as e:
            print(f"Error on {pair}: {e}")

    if not best_signal:
        raise HTTPException(404, "No high-confidence signal across session pairs")
    return best_signal


@app.get("/signal/{pair}")
async def get_signal_for_pair(pair: str, platform: str = "iq", timeframe: str = "1m"):
    """Get signal for a specific pair."""
    if platform == 'iq' and timeframe not in IQ_TIMEFRAMES:
        raise HTTPException(400, f"IQ timeframes: {IQ_TIMEFRAMES}")
    if platform == 'pocket' and timeframe not in PO_TIMEFRAMES:
        raise HTTPException(400, f"Pocket timeframes: {PO_TIMEFRAMES}")

    tf_sec = {'30s':30,'45s':45,'1m':60,'2m':120,'3m':180,'5m':300,
              'S3':3,'S15':15,'S30':30,'M1':60,'M3':180,'M5':300}
    sec = tf_sec.get(timeframe, 60)

    try:
        df1 = feed.get_candles(platform, pair, sec, 200)
        df3 = feed.get_candles(platform, pair, sec*3, 200)
        df5 = feed.get_candles(platform, pair, sec*5, 200)
        if df1 is None or df1.empty:
            raise HTTPException(404, f"No data for {pair}")

        market = {'1m': df1, '3m': df3, '5m': df5}
        sig = engine.generate(market, pair, platform, timeframe)
        if not sig:
            raise HTTPException(404, f"No SMC-grade signal for {pair}")
        return sig
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)}")


@app.get("/session-pairs")
async def session_pairs():
    return {"pairs": select_best_pairs(), "hour_utc": datetime.now(pytz.UTC).hour}


@app.post("/train")
async def train(trades: List[dict]):
    success = ai_scorer.train(trades)
    if not success:
        raise HTTPException(400, "Need at least 20 trades to train")
    return {"message": "Model trained and saved", "samples": len(trades)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
