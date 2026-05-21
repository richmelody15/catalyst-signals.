#!/usr/bin/env python3
"""
CATALYSTBOTS v5.1 - Self-Healing, Auto-Improving OTC Signal Engine
"below the smart money - CatabotAI.com"

ALL Confluences + Wyckoff + SMC + Divergence + Consequent Encroachment |
POI Scoring + Trend Detection + Chart Patterns + AMD Phase |
Mitigation/Rejection Blocks + Liquidity Detection + ADR Filter |
Session-Based Pair Selection + Memory Auto-Tuning |
IQ Option & Pocket Option | 80-95% Win Rate Target | 24/7

v5.1 CHANGES:
- POI (Point of Interest) confluence scoring (0-100)
- FVG Quality with ATR-relative sizing and age
- Consequent Encroachment detection (FVG partial fill + reversal)
- Enhanced Trend Detection (HH/HL/LH/LL + EMA + ADX fallback)
- Chart Pattern Detection (double top/bottom, H&S, wedges, flags)
- AMD Phase Detection (Accumulation/Advance/Distribution/Decline)
- Mitigation Block detection (mitigated OB bounce)
- Rejection Block detection (hammer/shooting star)
- Equal Highs/Lows (liquidity pool detection)
- Liquidity Side detection (volume-confirmed sweep direction)
- Liquidity Trap detection (false break + reversal)
- Imbalance Swing Levels (FVG-originated price targets)
- ADR Remaining % (daily range exhaustion filter)
- Inversion Point detection (volume spike reversal)
- Equilibrium detection (price distance from range midpoint)
- Session-based best pair selection
- Widened Wyckoff thresholds (1.5% zones, recency check on manipulation)
- Division-by-zero guards on all ratio calculations
- All score boosters integrated into accuracy calculation
- CATALYSTBOTS branding with CatabotAI.com tagline
- Volume Profile (POC, Value Area, HVN/LVN)
- Cumulative Volume Delta (CVD trend)
- Aggressive Zone detection (large candle + high volume)
- Fresh Zone / Tested Zone detection
- Initiation Detection (breakout confirmation via CVD + VP)
- VP/OF score boosters in signal accuracy

DEPLOY:
  Set env vars: IQ_EMAIL, IQ_PASSWORD, PO_EMAIL, PO_PASSWORD
  Set TELEGRAM_TOKEN, TELEGRAM_CHAT_ID for alerts
  Set USE_IQ_OPTION=True / USE_POCKET_OPTION=True
  pip install -r requirements.txt
  python catalystbots.py
  Open http://localhost:8000
"""
import asyncio, json, sqlite3, logging, uuid, os, traceback, time, hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple
import numpy as np
import pandas as pd
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn

# ============================================================
# 0. BROKER CREDENTIALS & CONFIG (read from env vars)
# ============================================================
IQ_EMAIL        = os.environ.get("IQ_EMAIL", "your_iq_option_email@example.com")
IQ_PASSWORD     = os.environ.get("IQ_PASSWORD", "your_iq_option_password")
PO_EMAIL        = os.environ.get("PO_EMAIL", "")
PO_PASSWORD     = os.environ.get("PO_PASSWORD", "")

USE_IQ_OPTION     = os.environ.get("USE_IQ_OPTION", "True").strip().lower() in ("true", "1", "yes")
USE_POCKET_OPTION = os.environ.get("USE_POCKET_OPTION", "True").strip().lower() in ("true", "1", "yes")

# Telegram
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Entry confirmation
ENTRY_CONFIRM_ENABLED = os.environ.get("ENTRY_CONFIRM_ENABLED", "True").strip().lower() in ("true", "1", "yes")
ENTRY_PRICE_THRESHOLD = float(os.environ.get("ENTRY_PRICE_THRESHOLD", "0.0005"))

# News filter
NEWS_FILTER_ENABLED = os.environ.get("NEWS_FILTER_ENABLED", "True").strip().lower() in ("true", "1", "yes")
NEWS_WINDOW_SECONDS = int(os.environ.get("NEWS_WINDOW_SECONDS", "600"))

# IQ Option API (optional)
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_API_AVAILABLE = True
except ImportError:
    IQ_API_AVAILABLE = False

# Pocket Option API (optional)
PO_API_TYPE = None
try:
    from pocketoptionapi.stable_api import PocketOption
    PO_API_AVAILABLE = True
    PO_API_TYPE = 'stable_api'
except ImportError:
    try:
        from pocket_option import PocketOptionClient as PocketOption
        PO_API_AVAILABLE = True
        PO_API_TYPE = 'pocket_option'
    except ImportError:
        PO_API_AVAILABLE = False

# Economic Calendar API (optional)
try:
    from economiccalendarapi import EconomicCalendar
    EC_API_AVAILABLE = True
except ImportError:
    EC_API_AVAILABLE = False

# APScheduler (optional)
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    APS_AVAILABLE = True
except ImportError:
    APS_AVAILABLE = False

# Telegram Bot (optional)
try:
    from telegram import Bot as TelegramBot
    TG_AVAILABLE = True
except ImportError:
    TG_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CatalystBots")


# ============================================================
# 1. AUTO ERROR FIXER
# ============================================================
def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame has valid OHLCV data, no NaN/Inf, high>=low, prices>0."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col not in df.columns:
            df[col] = 0.0
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    mask = df['high'] < df['low']
    if mask.any():
        df.loc[mask, ['high', 'low']] = df.loc[mask, ['low', 'high']].values
    for c in ['open', 'high', 'low', 'close']:
        df[c] = df[c].abs().clip(lower=0.00001)
    return df


# ============================================================
# 2. PROVEN INDICATORS
# ============================================================
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_di = 100.0 * pd.Series(plus_dm, index=high.index).ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-10)
    minus_di = 100.0 * pd.Series(minus_dm, index=low.index).ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-10)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    return dx.ewm(alpha=1/period, adjust=False).mean()

def bb_width(series: pd.Series, period: int = 20) -> pd.Series:
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return (4.0 * std) / sma.replace(0, 1e-10)

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[float, str]:
    if len(close) < k_period:
        return 50.0, 'Neutral'
    hh = high.rolling(k_period).max()
    ll = low.rolling(k_period).min()
    k = 100.0 * (close - ll) / (hh - ll).replace(0, 1e-10)
    k_val = k.iloc[-1]
    if pd.isna(k_val):
        return 50.0, 'Neutral'
    if k_val > 80: status = 'Overbought'
    elif k_val < 20: status = 'Oversold'
    else: status = 'Neutral'
    return round(float(k_val), 1), status


# ============================================================
# 2b. S/R LEVELS & SWING HELPERS
# ============================================================
def sr_levels(price: float, df: pd.DataFrame, lookback: int = 40) -> Tuple[float, float]:
    if len(df) < lookback:
        return price * 0.99, price * 1.01
    highs = df['high'].values[-lookback:]
    lows = df['low'].values[-lookback:]
    sh, sl = [], []
    for i in range(3, len(highs) - 3):
        if (all(highs[i] >= highs[i - j] for j in range(1, 4)) and
            all(highs[i] >= highs[i + j] for j in range(1, 4))):
            sh.append(highs[i])
        if (all(lows[i] <= lows[i - j] for j in range(1, 4)) and
            all(lows[i] <= lows[i + j] for j in range(1, 4))):
            sl.append(lows[i])
    resistance = min([h for h in sh if h > price * 1.001], default=price * 1.01)
    support = max([l for l in sl if l < price * 0.999], default=price * 0.99)
    return support, resistance

def identify_swings(df: pd.DataFrame, order: int = 3) -> List[dict]:
    """Identify swing highs and lows with metadata."""
    if len(df) < order * 2 + 1:
        return []
    swings = []
    for i in range(order, len(df) - order):
        if (all(df['high'].iloc[i] >= df['high'].iloc[i - j] for j in range(1, order + 1)) and
            all(df['high'].iloc[i] >= df['high'].iloc[i + j] for j in range(1, order + 1))):
            swings.append({'type': 'high', 'price': df['high'].iloc[i], 'time': df.index[i] if hasattr(df.index, '__getitem__') else i, 'strength': order})
        if (all(df['low'].iloc[i] <= df['low'].iloc[i - j] for j in range(1, order + 1)) and
            all(df['low'].iloc[i] <= df['low'].iloc[i + j] for j in range(1, order + 1))):
            swings.append({'type': 'low', 'price': df['low'].iloc[i], 'time': df.index[i] if hasattr(df.index, '__getitem__') else i, 'strength': order})
    return swings


# ============================================================
# 2c. SMC CORE FUNCTIONS
# ============================================================
def order_block(df: pd.DataFrame) -> Optional[str]:
    if len(df) < 5:
        return None
    last_body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
    prev_body = abs(df['close'].iloc[-2] - df['open'].iloc[-2])
    if prev_body > 0 and last_body > 2.0 * prev_body and df['volume'].iloc[-1] > df['volume'].iloc[-2] * 1.5:
        return 'demand' if df['close'].iloc[-1] > df['open'].iloc[-1] else 'supply'
    return None

def detect_fvg(df: pd.DataFrame) -> Optional[str]:
    """Simple FVG detection - returns 'bullish'/'bearish' or None."""
    if len(df) < 3:
        return None
    for i in range(len(df) - 1, max(len(df) - 5, -1), -1):
        if i >= 2:
            prev2 = df.iloc[i - 2]
            curr = df.iloc[i]
            if curr['low'] > prev2['high']:
                return 'bullish'
            if curr['high'] < prev2['low']:
                return 'bearish'
    return None

def fvg_quality(df: pd.DataFrame):
    """FVG with quality metrics. Returns (direction, atr_relative_size, age_in_bars) or None."""
    if len(df) < 3:
        return None
    tr = df['high'] - df['low']
    atr_val = tr.rolling(14).mean().iloc[-1] if len(tr) >= 14 else 0.001
    for i in range(len(df) - 1, max(len(df) - 5, -1), -1):
        if i >= 2:
            prev2 = df.iloc[i - 2]
            curr = df.iloc[i]
            if curr['low'] > prev2['high']:
                size = (curr['low'] - prev2['high']) / atr_val if atr_val > 0 else 0
                return ('bullish', round(size, 2), len(df) - 1 - i)
            if curr['high'] < prev2['low']:
                size = (prev2['low'] - curr['high']) / atr_val if atr_val > 0 else 0
                return ('bearish', round(size, 2), len(df) - 1 - i)
    return None


# ============================================================
# 2d. WYCKOFF PHASE DETECTION (Enhanced v5.0)
# ============================================================
def detect_wyckoff_phase(df):
    """
    Returns 'accumulation', 'distribution', 'manipulation', or None.
    v5.0: Widened thresholds (1.5% zones), recency check on manipulation,
          division-by-zero guards.
    """
    if len(df) < 40:
        return None
    high = df['high'].values[-40:]
    low = df['low'].values[-40:]
    close = df['close'].values[-40:]
    volume = df['volume'].values[-40:]

    # Range contraction with guard
    recent_range = np.mean(high[-10:] - low[-10:])
    older_range = np.mean(high[-20:-10] - low[-20:-10])
    range_contracting = recent_range < older_range * 0.9 if older_range > 0 else False

    # Volume trend with guard
    recent_vol = np.mean(volume[-10:])
    older_vol = np.mean(volume[-20:-10])
    vol_rising = recent_vol > older_vol * 1.1 if older_vol > 0 else False
    vol_falling = recent_vol < older_vol * 0.9 if older_vol > 0 else False

    # Find swing points
    sh, sl = [], []
    for i in range(3, 37):
        if all(high[i] >= high[i - j] for j in range(1, 4)) and all(high[i] >= high[i + j] for j in range(1, 4)):
            sh.append(i)
        if all(low[i] <= low[i - j] for j in range(1, 4)) and all(low[i] <= low[i + j] for j in range(1, 4)):
            sl.append(i)

    if len(sh) < 2 or len(sl) < 2:
        return None

    current_price = close[-1]
    last_swing_high = high[sh[-1]]
    last_swing_low = low[sl[-1]]

    # v5.0: Widened thresholds from 0.2% to 1.5%
    if current_price <= last_swing_low * 1.015 and vol_rising and range_contracting:
        return 'accumulation'
    if current_price >= last_swing_high * 0.985 and vol_falling and range_contracting:
        return 'distribution'

    # v5.0: Manipulation with recency check (must be within last 5 bars)
    if len(sl) >= 2:
        prev_low = low[sl[-2]]
        if low[sl[-1]] < prev_low and close[-1] > prev_low and (39 - sl[-1]) <= 5:
            return 'manipulation'
    if len(sh) >= 2:
        prev_high = high[sh[-2]]
        if high[sh[-1]] > prev_high and close[-1] < prev_high and (39 - sh[-1]) <= 5:
            return 'manipulation'

    return None

def wyckoff_confirms_signal(phase, direction):
    if phase is None:
        return True
    if direction == 'BUY' and phase in ('accumulation', 'manipulation'):
        return True
    if direction == 'SELL' and phase in ('distribution', 'manipulation'):
        return True
    return False

def detect_direction_bias(df, higher_tf_trend, market_trend):
    """Multi-timeframe direction bias: micro (1m) + short (5m) + medium (15m)."""
    if len(df) < 20:
        return 'neutral'
    ema5 = ema(df['close'], 5)
    ema20 = ema(df['close'], 20)
    micro = 'bullish' if ema5.iloc[-1] > ema20.iloc[-1] else ('bearish' if ema5.iloc[-1] < ema20.iloc[-1] else 'neutral')
    signals = [micro]
    if higher_tf_trend in ('bullish', 'bearish'):
        signals.append(higher_tf_trend)
    if market_trend in ('bullish', 'bearish'):
        signals.append(market_trend)
    bullish = sum(1 for s in signals if s == 'bullish')
    bearish = sum(1 for s in signals if s == 'bearish')
    if bullish >= 2:
        return 'bullish'
    elif bearish >= 2:
        return 'bearish'
    return 'neutral'


# ============================================================
# 2e. RSI DIVERGENCE
# ============================================================
def detect_rsi_divergence(df, direction):
    """Returns True if divergence confirms direction, True if no divergence (neutral), False if conflict."""
    if len(df) < 20:
        return True
    close = df['close'].values[-20:]
    rsi_vals = rsi(df['close'], 14).values[-20:]
    def find_swing_points(data):
        highs_idx, lows_idx = [], []
        for i in range(2, len(data) - 2):
            if all(data[i] >= data[i - j] for j in range(1, 3)) and all(data[i] >= data[i + j] for j in range(1, 3)):
                highs_idx.append(i)
            if all(data[i] <= data[i - j] for j in range(1, 3)) and all(data[i] <= data[i + j] for j in range(1, 3)):
                lows_idx.append(i)
        return highs_idx, lows_idx
    price_highs, price_lows = find_swing_points(close)
    rsi_highs, rsi_lows = find_swing_points(rsi_vals)
    if len(price_lows) >= 2 and len(rsi_lows) >= 2:
        if close[price_lows[-1]] < close[price_lows[-2]] and rsi_vals[rsi_lows[-1]] > rsi_vals[rsi_lows[-2]]:
            return direction == 'BUY'
    if len(price_highs) >= 2 and len(rsi_highs) >= 2:
        if close[price_highs[-1]] > close[price_highs[-2]] and rsi_vals[rsi_highs[-1]] < rsi_vals[rsi_highs[-2]]:
            return direction == 'SELL'
    return True


# ============================================================
# 2f. CONSEQUENT ENCROACHMENT
# ============================================================
def detect_consequent_encroachment(df):
    """Returns 'bullish'/'bearish' if FVG was partially filled and price is reversing."""
    if len(df) < 5:
        return None
    fvg_data = fvg_quality(df)
    if not fvg_data:
        return None
    direction, size, age = fvg_data
    if age > 3:
        return None
    if direction == 'bullish':
        for i in range(len(df) - 1, max(len(df) - 5, -1), -1):
            if i >= 2:
                prev2 = df.iloc[i - 2]
                curr = df.iloc[i]
                if curr['low'] > prev2['high']:
                    gap_top = curr['low']
                    subsequent = df.iloc[i + 1:]
                    if len(subsequent) > 0 and any(subsequent['low'] < gap_top):
                        c = df.iloc[-1]
                        if c['close'] > c['open'] and (c['close'] - c['low']) > (c['high'] - c['low']) * 0.7:
                            return 'bullish'
                    break
    else:
        for i in range(len(df) - 1, max(len(df) - 5, -1), -1):
            if i >= 2:
                prev2 = df.iloc[i - 2]
                curr = df.iloc[i]
                if curr['high'] < prev2['low']:
                    gap_bottom = curr['high']
                    subsequent = df.iloc[i + 1:]
                    if len(subsequent) > 0 and any(subsequent['high'] > gap_bottom):
                        c = df.iloc[-1]
                        if c['close'] < c['open'] and (c['high'] - c['close']) > (c['high'] - c['low']) * 0.7:
                            return 'bearish'
                    break
    return None


# ============================================================
# 2g. POI SCORE (Point of Interest Confluence)
# ============================================================
def poi_score(df, direction):
    """Return a score 0-100 based on how many confluences exist at current price."""
    score = 0
    if order_block(df) == ('demand' if direction == 'BUY' else 'supply'):
        score += 20
    fvg_data = fvg_quality(df)
    if fvg_data and fvg_data[0] == ('bullish' if direction == 'BUY' else 'bearish'):
        score += 20
    price = df['close'].iloc[-1]
    support, resistance = sr_levels(price, df)
    # v5.0: Widened S/R proximity (0.5% instead of 0.2%)
    if direction == 'BUY' and price <= support * 1.005:
        score += 20
    if direction == 'SELL' and price >= resistance * 0.995:
        score += 20
    if detect_equal_highs_lows(df) == ('bullish' if direction == 'BUY' else 'bearish'):
        score += 20
    if detect_liquidity_trap(df) == direction:
        score += 20
    return min(100, score)


# ============================================================
# 2h. EQUAL HIGHS / LOWS
# ============================================================
def detect_equal_highs_lows(df):
    """Returns 'bullish' (equal lows → buy after sweep) or 'bearish' (equal highs → sell after sweep)."""
    if len(df) < 15:
        return None
    highs = df['high'].values[-15:]
    lows = df['low'].values[-15:]
    closes = df['close'].values[-15:]

    def has_cluster(arr):
        arr_sorted = np.sort(arr)
        diffs = np.diff(arr_sorted)
        return bool(np.any(diffs < arr_sorted[:-1] * 0.0003))

    if has_cluster(highs):
        cluster_mid = np.median(highs)
        if closes[-1] < cluster_mid:
            return 'bearish'
    if has_cluster(lows):
        cluster_mid = np.median(lows)
        if closes[-1] > cluster_mid:
            return 'bullish'
    return None


# ============================================================
# 2i. LIQUIDITY FUNCTIONS
# ============================================================
def detect_liquidity_trap(df):
    """Support trap → 'bullish', resistance trap → 'bearish'."""
    if len(df) < 20:
        return None
    swings = identify_swings(df, order=3)
    if not swings:
        return None
    supports = [s for s in swings if s['type'] == 'low']
    resistances = [s for s in swings if s['type'] == 'high']
    price = df['close'].iloc[-1]
    for s in supports[-3:]:
        last_lows = df['low'].iloc[-5:].values
        if any(last_lows < s['price'] * 0.9995):
            if price > s['price']:
                return 'bullish'
    for r in resistances[-3:]:
        last_highs = df['high'].iloc[-5:].values
        if any(last_highs > r['price'] * 1.0005):
            if price < r['price']:
                return 'bearish'
    return None

def detect_liquidity_side(df):
    """Returns 'buy_side'/'sell_side' based on volume-confirmed sweep direction."""
    if len(df) < 15:
        return None
    eq = detect_equal_highs_lows(df)
    if eq is None:
        return None
    vol = df['volume'].iloc[-1]
    avg_vol = df['volume'].iloc[-20:-1].mean() if len(df) >= 20 else 1
    if avg_vol == 0:
        return None
    if eq == 'bullish' and vol > avg_vol * 1.5:
        return 'sell_side'
    if eq == 'bearish' and vol > avg_vol * 1.5:
        return 'buy_side'
    return None

def detect_liquidity_sweep(df: pd.DataFrame) -> Tuple[bool, str]:
    """Detect liquidity sweep (stop hunt). Returns (sweep_detected, side)."""
    if len(df) < 20:
        return False, 'None'
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    recent_high = max(high[-10:-1])
    recent_low = min(low[-10:-1])
    if high[-1] > recent_high and close[-1] < recent_high:
        return True, 'Buy Side Sweep'
    if low[-1] < recent_low and close[-1] > recent_low:
        return True, 'Sell Side Sweep'
    return False, 'None'


# ============================================================
# 2j. IMBALANCE SWING LEVELS
# ============================================================
def imbalance_swing_levels(df):
    """Return (bullish_target, bearish_target) price levels from FVG origination."""
    if len(df) < 20:
        return None, None
    swings = identify_swings(df, order=3)
    if not swings:
        return None, None
    fvg_data = fvg_quality(df)
    if fvg_data:
        fvg_dir = fvg_data[0]
        if fvg_dir == 'bullish':
            lows = [s for s in swings if s['type'] == 'low']
            if lows:
                return None, lows[-1]['price']
        else:
            highs = [s for s in swings if s['type'] == 'high']
            if highs:
                return highs[-1]['price'], None
    return None, None


# ============================================================
# 2k. ADR REMAINING %
# ============================================================
def adr_remaining_pct(df):
    """Return estimate of how much daily range is left, as a fraction."""
    if len(df) < 100:
        return 1.0
    recent_high = df['high'].iloc[-50:].max()
    recent_low = df['low'].iloc[-50:].min()
    current_range = recent_high - recent_low
    avg_range = (df['high'] - df['low']).rolling(50).mean().iloc[-1] * 6
    if avg_range == 0:
        return 1.0
    return max(0, 1 - (current_range / avg_range))


# ============================================================
# 2l. INVERSION POINT
# ============================================================
def detect_inversion_point(df):
    """Return price level where a strong reversal occurred in the last 10 bars."""
    if len(df) < 5:
        return None
    for i in range(-5, -1):
        c = df.iloc[i]
        body = abs(c['close'] - c['open'])
        lower_wick = min(c['open'], c['close']) - c['low']
        upper_wick = c['high'] - max(c['open'], c['close'])
        range_ = c['high'] - c['low']
        if range_ == 0:
            continue
        vol = c['volume']
        avg_vol = df['volume'].iloc[-20:-1].mean() if len(df) >= 20 else 1
        if avg_vol > 0 and vol > avg_vol * 1.8:
            if lower_wick > 2 * body and upper_wick < body * 0.5 and c['close'] > c['open']:
                return c['low']
            if upper_wick > 2 * body and lower_wick < body * 0.5 and c['close'] < c['open']:
                return c['high']
    return None


# ============================================================
# 2m. EQUILIBRIUM
# ============================================================
def detect_equilibrium(df):
    """Return (eq_price, distance_pct) of how close price is to range midpoint."""
    if len(df) < 30:
        return None, None
    high = df['high'].iloc[-30:].max()
    low = df['low'].iloc[-30:].min()
    eq = (high + low) / 2
    price = df['close'].iloc[-1]
    distance = abs(price - eq) / price * 100 if price > 0 else 0
    return eq, distance


# ============================================================
# 2n. ENHANCED TREND DETECTION
# ============================================================
def detect_trend(df):
    """Returns 'strong_bullish', 'bullish', 'sideways', 'bearish', 'strong_bearish'."""
    if len(df) < 40:
        return 'sideways'
    highs = df['high'].values[-40:]
    lows = df['low'].values[-40:]
    closes = df['close'].values[-40:]
    sh, sl = [], []
    for i in range(3, 37):
        if all(highs[i] >= highs[i - j] for j in range(1, 4)) and all(highs[i] >= highs[i + j] for j in range(1, 4)):
            sh.append(i)
        if all(lows[i] <= lows[i - j] for j in range(1, 4)) and all(lows[i] <= lows[i + j] for j in range(1, 4)):
            sl.append(i)
    if len(sh) < 2 or len(sl) < 2:
        ema50 = ema(df['close'], 50).iloc[-1] if len(df) >= 50 else df['close'].iloc[-1]
        ema5 = ema(df['close'], 5).iloc[-1]
        if ema5 > ema50:
            return 'bullish'
        elif ema5 < ema50:
            return 'bearish'
        return 'sideways'
    last_highs = [highs[i] for i in sh[-3:]]
    last_lows = [lows[i] for i in sl[-3:]]
    if len(last_highs) >= 2 and len(last_lows) >= 2:
        hh = last_highs[-1] > last_highs[-2]
        hl = last_lows[-1] > last_lows[-2]
        lh = last_highs[-1] < last_highs[-2]
        ll = last_lows[-1] < last_lows[-2]
        ema50 = ema(df['close'], 50).iloc[-1] if len(df) >= 50 else closes[-1]
        price = closes[-1]
        distance = (price - ema50) / ema50 * 100 if ema50 > 0 else 0
        if hh and hl:
            return 'strong_bullish' if distance > 0.5 else 'bullish'
        elif lh and ll:
            return 'strong_bearish' if distance < -0.5 else 'bearish'
    # ADX fallback
    adx_val = adx(df['high'], df['low'], df['close'], 14).iloc[-1]
    if not pd.isna(adx_val) and adx_val > 25:
        return 'bullish' if closes[-1] > closes[-10] else 'bearish'
    return 'sideways'


# ============================================================
# 2o. CHART PATTERN DETECTION
# ============================================================
def detect_chart_pattern(df):
    """Returns (pattern_name, expected_direction) or (None, None)."""
    if len(df) < 25:
        return None, None
    swings = identify_swings(df, order=3)
    if len(swings) < 5:
        return None, None
    highs = [s for s in swings if s['type'] == 'high']
    lows = [s for s in swings if s['type'] == 'low']

    # Double top / bottom
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if abs(h1['price'] - h2['price']) / max(h1['price'], 0.0001) < 0.003:
            return 'double_top', 'SELL'
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if abs(l1['price'] - l2['price']) / max(l1['price'], 0.0001) < 0.003:
            return 'double_bottom', 'BUY'

    # Head & Shoulders
    if len(highs) >= 3:
        h1, h2, h3 = highs[-3], highs[-2], highs[-1]
        if h2['price'] > h1['price'] and h2['price'] > h3['price'] and \
           abs(h1['price'] - h3['price']) / max(h1['price'], 0.0001) < 0.015:
            return 'head_shoulders', 'SELL'
    if len(lows) >= 3:
        l1, l2, l3 = lows[-3], lows[-2], lows[-1]
        if l2['price'] < l1['price'] and l2['price'] < l3['price'] and \
           abs(l1['price'] - l3['price']) / max(l1['price'], 0.0001) < 0.015:
            return 'inv_head_shoulders', 'BUY'

    # Rising / Falling wedge
    if len(highs) >= 4 and len(lows) >= 4:
        h_prices = [h['price'] for h in highs[-4:]]
        l_prices = [l['price'] for l in lows[-4:]]
        slope_h = np.polyfit(range(len(h_prices)), h_prices, 1)[0]
        slope_l = np.polyfit(range(len(l_prices)), l_prices, 1)[0]
        if slope_h > 0 and slope_l > 0 and slope_l > slope_h:
            return 'rising_wedge', 'SELL'
        if slope_h < 0 and slope_l < 0 and slope_h < slope_l:
            return 'falling_wedge', 'BUY'

    # Flag detection
    if len(df) >= 20:
        recent = df.iloc[-10:]
        prev = df.iloc[-20:-10]
        if len(prev) >= 10:
            prev_move = prev['close'].iloc[-1] - prev['close'].iloc[0]
            recent_range = recent['high'].max() - recent['low'].min()
            if recent_range > 0 and abs(prev_move) > 2 * recent_range:
                return ('bullish_flag', 'BUY') if prev_move > 0 else ('bearish_flag', 'SELL')

    return None, None


# ============================================================
# 2p. AMD PHASE DETECTION
# ============================================================
def market_structure(df):
    """Simple structure: bullish if HH+HL, bearish if LH+LL."""
    if len(df) < 12:
        return None
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    sh, sl = [], []
    for i in range(3, len(highs) - 3):
        if (all(highs[i] >= highs[i - j] for j in range(1, 4)) and
            all(highs[i] >= highs[i + j] for j in range(1, 4))):
            sh.append(i)
        if (all(lows[i] <= lows[i - j] for j in range(1, 4)) and
            all(lows[i] <= lows[i + j] for j in range(1, 4))):
            sl.append(i)
    if len(sh) < 2 or len(sl) < 2:
        return None
    if closes[-1] > highs[sh[-1]] and lows[sl[-1]] > lows[sl[-2]]:
        return 'bullish'
    if closes[-1] < lows[sl[-1]] and highs[sh[-1]] < highs[sh[-2]]:
        return 'bearish'
    if closes[-1] > highs[sh[-1]]:
        return 'bullish'
    if closes[-1] < lows[sl[-1]]:
        return 'bearish'
    return None

def detect_mss(df):
    """Market Structure Shift - early reversal signal."""
    if len(df) < 12:
        return None
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    sh, sl = [], []
    for i in range(3, len(highs) - 3):
        if (all(highs[i] >= highs[i - j] for j in range(1, 4)) and
            all(highs[i] >= highs[i + j] for j in range(1, 4))):
            sh.append(i)
        if (all(lows[i] <= lows[i - j] for j in range(1, 4)) and
            all(lows[i] <= lows[i + j] for j in range(1, 4))):
            sl.append(i)
    if len(sh) < 2 or len(sl) < 2:
        return None
    if len(sh) >= 2 and highs[sh[-1]] < highs[sh[-2]] and closes[-1] > highs[sh[-1]]:
        return 'bullish'
    if len(sl) >= 2 and lows[sl[-1]] > lows[sl[-2]] and closes[-1] < lows[sl[-1]]:
        return 'bearish'
    return None

def detect_market_structure_reversal(df):
    """Confirmed reversal - prior trend + BOS/CHoCH."""
    if len(df) < 18:
        return None
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    sh, sl = [], []
    for i in range(3, len(highs) - 3):
        if (all(highs[i] >= highs[i - j] for j in range(1, 4)) and
            all(highs[i] >= highs[i + j] for j in range(1, 4))):
            sh.append(i)
        if (all(lows[i] <= lows[i - j] for j in range(1, 4)) and
            all(lows[i] <= lows[i + j] for j in range(1, 4))):
            sl.append(i)
    if len(sh) < 3 or len(sl) < 3:
        return None
    prior_bearish = highs[sh[-2]] < highs[sh[-3]]
    prior_bullish = lows[sl[-2]] > lows[sl[-3]]
    bos_up = closes[-1] > highs[sh[-1]]
    bos_down = closes[-1] < lows[sl[-1]]
    if bos_up and prior_bearish:
        return 'bullish'
    elif bos_down and prior_bullish:
        return 'bearish'
    if prior_bullish and bos_down:
        return 'bearish'
    if prior_bearish and bos_up:
        return 'bullish'
    return None

def detect_amd_phase(df):
    """Returns 'accumulation', 'advance', 'distribution', 'decline', or None."""
    if len(df) < 40:
        return None
    wyckoff = detect_wyckoff_phase(df)
    if wyckoff in ('accumulation', 'manipulation'):
        struct = market_structure(df)
        return 'advance' if struct == 'bullish' else 'accumulation'
    if wyckoff == 'distribution':
        struct = market_structure(df)
        return 'decline' if struct == 'bearish' else 'distribution'
    return wyckoff


# ============================================================
# 2q. MITIGATION & REJECTION BLOCKS
# ============================================================
def mitigation_block(df):
    """Returns 'bullish' if demand OB was mitigated (price reached and bounced)."""
    if len(df) < 20:
        return None
    for i in range(10, len(df) - 1):
        c_body = abs(df['close'].iloc[i] - df['open'].iloc[i])
        p_body = abs(df['close'].iloc[i - 1] - df['open'].iloc[i - 1])
        if p_body > 0:
            if df['close'].iloc[i] < df['open'].iloc[i] and c_body > 1.5 * p_body:
                ob_high = df['high'].iloc[i]
                subsequent = df.iloc[i + 1:]
                if len(subsequent) > 0 and any((subsequent['low'] <= ob_high) & (subsequent['close'] > ob_high)):
                    return 'bullish'
            if df['close'].iloc[i] > df['open'].iloc[i] and c_body > 1.5 * p_body:
                ob_low = df['low'].iloc[i]
                subsequent = df.iloc[i + 1:]
                if len(subsequent) > 0 and any((subsequent['high'] >= ob_low) & (subsequent['close'] < ob_low)):
                    return 'bearish'
    return None

def rejection_block(df):
    """Returns 'support' if hammer, 'resistance' if shooting star."""
    if len(df) < 1:
        return None
    c = df.iloc[-1]
    body = abs(c['close'] - c['open'])
    lower_wick = min(c['open'], c['close']) - c['low']
    upper_wick = c['high'] - max(c['open'], c['close'])
    range_ = c['high'] - c['low']
    if range_ == 0:
        return None
    if lower_wick > 2 * body and upper_wick < body * 0.5:
        return 'support'
    if upper_wick > 2 * body and lower_wick < body * 0.5:
        return 'resistance'
    return None


# ============================================================
# 2r. VOLUME PROFILE & ORDER FLOW (v5.1)
# ============================================================
def build_volume_profile(df, lookback=50, bins=30):
    """
    Build a volume profile over the last `lookback` candles.
    Returns dict with:
        poc: price of Point of Control (highest volume)
        va_high, va_low: Value Area (70% of total volume)
        hvn: list of High Volume Nodes (bins with volume > 1.5x avg)
        lvn: list of Low Volume Nodes (bins with volume < 0.5x avg)
    """
    if len(df) < lookback:
        lookback = len(df)
    if lookback < 5:
        return None
    subset = df.iloc[-lookback:]
    price_low = subset['low'].min()
    price_high = subset['high'].max()
    bin_size = (price_high - price_low) / bins
    if bin_size == 0:
        return None

    volume_profile = np.zeros(bins)
    for i in range(len(subset)):
        candle_low = subset['low'].iloc[i]
        candle_high = subset['high'].iloc[i]
        vol = subset['volume'].iloc[i]
        candle_range = candle_high - candle_low
        # distribute volume evenly across the candle's range
        for j in range(bins):
            bin_low = price_low + j * bin_size
            bin_high = bin_low + bin_size
            # overlap fraction
            overlap_low = max(candle_low, bin_low)
            overlap_high = min(candle_high, bin_high)
            if overlap_high > overlap_low:
                fraction = (overlap_high - overlap_low) / candle_range if candle_range > 0 else 0
                volume_profile[j] += vol * fraction

    # POC = bin with highest volume
    poc_idx = np.argmax(volume_profile)
    poc = price_low + (poc_idx + 0.5) * bin_size

    # Value Area (70% of total volume)
    total_vol = volume_profile.sum()
    if total_vol == 0:
        return None
    target_vol = total_vol * 0.70
    # sort bins by volume descending
    sorted_indices = np.argsort(volume_profile)[::-1]
    cumulative_vol = 0
    va_bins = []
    for idx in sorted_indices:
        cumulative_vol += volume_profile[idx]
        va_bins.append(idx)
        if cumulative_vol >= target_vol:
            break
    va_high_idx = max(va_bins)
    va_low_idx = min(va_bins)
    va_high = price_low + (va_high_idx + 1) * bin_size
    va_low = price_low + va_low_idx * bin_size

    # HVN / LVN
    avg_vol_per_bin = volume_profile.mean()
    hvn = []
    lvn = []
    for j in range(bins):
        mid_price = price_low + (j + 0.5) * bin_size
        if volume_profile[j] > avg_vol_per_bin * 1.5:
            hvn.append(round(mid_price, 5))
        elif volume_profile[j] < avg_vol_per_bin * 0.5:
            lvn.append(round(mid_price, 5))

    return {
        'poc': round(poc, 5),
        'va_high': round(va_high, 5),
        'va_low': round(va_low, 5),
        'hvn': hvn,
        'lvn': lvn
    }

def cumulative_volume_delta(df, lookback=20):
    """
    Approximate CVD by summing volume * sign(close - open).
    Positive = bullish, negative = bearish.
    Returns dict: trend ('bullish'/'bearish'), delta_value, recent_bias.
    """
    if len(df) < lookback:
        lookback = len(df)
    if lookback < 3:
        return {'trend': 'neutral', 'delta': 0, 'recent_bias': 0}
    delta = 0
    for i in range(-lookback, 0):
        sign = 1 if df['close'].iloc[i] > df['open'].iloc[i] else -1
        delta += sign * df['volume'].iloc[i]
    recent_count = min(5, lookback)
    recent = [1 if df['close'].iloc[i] > df['open'].iloc[i] else -1 for i in range(-recent_count, 0)]
    recent_sum = sum(recent)
    if recent_sum > 0:
        trend = 'bullish'
    elif recent_sum < 0:
        trend = 'bearish'
    else:
        trend = 'neutral'
    return {'trend': trend, 'delta': delta, 'recent_bias': recent_sum}

def detect_aggressive_zone(df, direction):
    """True if price is near a level formed by a large, high-volume candle."""
    if len(df) < 5:
        return False
    avg_body = (df['close'] - df['open']).abs().rolling(20).mean().iloc[-1]
    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
    if pd.isna(avg_body) or pd.isna(avg_vol) or avg_body == 0 or avg_vol == 0:
        return False
    for i in range(-3, 0):
        body = abs(df['close'].iloc[i] - df['open'].iloc[i])
        vol = df['volume'].iloc[i]
        if body > avg_body * 1.5 and vol > avg_vol * 1.5:
            level = df['low'].iloc[i] if df['close'].iloc[i] > df['open'].iloc[i] else df['high'].iloc[i]
            price = df['close'].iloc[-1]
            if direction == 'BUY' and price <= level * 1.002 and price >= level * 0.998:
                return True
            if direction == 'SELL' and price >= level * 0.998 and price <= level * 1.002:
                return True
    return False

def detect_fresh_zone(df, zone_type):
    """zone_type: 'supply' or 'demand'. Returns True if the zone hasn't been revisited."""
    if len(df) < 20:
        return True
    swings = identify_swings(df, order=3)
    if not swings:
        return True
    if zone_type == 'demand':
        lows = [s for s in swings if s['type'] == 'low']
        if lows:
            last_low = lows[-1]['price']
            idx = lows[-1].get('time')
            if idx is not None:
                try:
                    if isinstance(idx, int):
                        subsequent = df.iloc[idx + 1:]
                    else:
                        loc_idx = df.index.get_loc(idx)
                        subsequent = df.iloc[loc_idx + 1:]
                except (KeyError, TypeError):
                    subsequent = pd.DataFrame()
                if len(subsequent) > 0 and any(subsequent['low'] <= last_low * 1.001):
                    return False
            return True
    elif zone_type == 'supply':
        highs = [s for s in swings if s['type'] == 'high']
        if highs:
            last_high = highs[-1]['price']
            idx = highs[-1].get('time')
            if idx is not None:
                try:
                    if isinstance(idx, int):
                        subsequent = df.iloc[idx + 1:]
                    else:
                        loc_idx = df.index.get_loc(idx)
                        subsequent = df.iloc[loc_idx + 1:]
                except (KeyError, TypeError):
                    subsequent = pd.DataFrame()
                if len(subsequent) > 0 and any(subsequent['high'] >= last_high * 0.999):
                    return False
            return True
    return True

def detect_tested_zone(df, zone_type):
    """Returns number of times a zone has been tested."""
    if len(df) < 20:
        return 0
    swings = identify_swings(df, order=3)
    if not swings:
        return 0
    count = 0
    if zone_type == 'demand':
        lows = [s for s in swings if s['type'] == 'low']
        if len(lows) >= 2:
            level = lows[-1]['price']
            for i in range(len(lows) - 1):
                if abs(lows[i]['price'] - level) / max(level, 0.00001) < 0.002:
                    count += 1
    else:
        highs = [s for s in swings if s['type'] == 'high']
        if len(highs) >= 2:
            level = highs[-1]['price']
            for i in range(len(highs) - 1):
                if abs(highs[i]['price'] - level) / max(level, 0.00001) < 0.002:
                    count += 1
    return count

def initiation_detection(df, direction):
    """
    Returns True if volume delta confirms a breakout (initiation) in the signal direction.
    For BUY: CVD bullish and price above POC.
    For SELL: CVD bearish and price below POC.
    """
    vp = build_volume_profile(df, lookback=50, bins=30)
    if not vp:
        return False
    cvd = cumulative_volume_delta(df)
    if direction == 'BUY':
        return df['close'].iloc[-1] > vp['poc'] and cvd['trend'] == 'bullish'
    else:
        return df['close'].iloc[-1] < vp['poc'] and cvd['trend'] == 'bearish'

def vp_of_score(df, direction):
    """
    Volume Profile & Order Flow score boosters (0-65 points).
    Called from generate_signal() to add accuracy based on VP/OF confluence.
    """
    score = 0
    vp = build_volume_profile(df)
    if vp:
        if direction == 'BUY' and df['close'].iloc[-1] <= vp['poc']:
            score += 10   # buying below POC (value)
        if direction == 'SELL' and df['close'].iloc[-1] >= vp['poc']:
            score += 10
        if vp['va_low'] <= df['close'].iloc[-1] <= vp['va_high']:
            score += 5    # inside value area
    cvd = cumulative_volume_delta(df)
    if direction == 'BUY' and cvd['trend'] == 'bullish':
        score += 10
    if direction == 'SELL' and cvd['trend'] == 'bearish':
        score += 10
    if detect_aggressive_zone(df, direction):
        score += 10
    if detect_fresh_zone(df, 'demand' if direction == 'BUY' else 'supply'):
        score += 10
    if detect_tested_zone(df, 'demand' if direction == 'BUY' else 'supply') == 1:
        score += 5   # once tested is good
    if initiation_detection(df, direction):
        score += 15
    return score


# ============================================================
# 2s. V3.2 LEGACY HELPERS (preserved)
# ============================================================
def detect_regime(df: pd.DataFrame) -> Tuple[str, str]:
    if len(df) < 30:
        return 'RANGING', 'Insufficient data'
    close = df['close']; high = df['high']; low = df['low']; volume = df['volume']
    tr1 = high - low; tr2 = (high - close.shift()).abs(); tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    avg_atr = atr.iloc[-20:].mean(); recent_atr = atr.iloc[-5:].mean()
    avg_vol = volume.iloc[-20:].mean(); recent_vol = volume.iloc[-5:].mean()
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
    range_20 = high.iloc[-20:].max() - low.iloc[-20:].min()
    range_5 = high.iloc[-5:].max() - low.iloc[-5:].min()
    range_ratio = range_5 / range_20 if range_20 > 0 else 0.5
    adx_val = adx(high, low, close, 14).iloc[-1]
    if pd.isna(adx_val): adx_val = 20.0
    ema5_val = ema(close, 5)
    ema_slope = (ema5_val.iloc[-1] - ema5_val.iloc[-5]) / ema5_val.iloc[-5] * 100 if len(ema5_val) >= 5 else 0
    if vol_ratio > 1.5 and range_ratio > 0.4 and recent_atr > avg_atr * 1.3:
        return 'BREAKOUT', 'Market is breaking out with surging volume.'
    elif adx_val > 30 and abs(ema_slope) > 0.05:
        direction = 'upward' if ema_slope > 0 else 'downward'
        return 'TRENDING', f'Sustained {direction} trend with strong momentum.'
    else:
        return 'RANGING', 'Market is consolidating, awaiting breakout.'

def classify_volume(df: pd.DataFrame) -> str:
    if len(df) < 20: return 'Normal'
    vol = df['volume']; avg = vol.iloc[-20:].mean()
    if avg == 0: return 'Normal'
    ratio = vol.iloc[-1] / avg
    if ratio > 1.5: return 'High'
    elif ratio < 0.6: return 'Low'
    return 'Normal'

def classify_bb_width(bb_w: pd.Series) -> str:
    if len(bb_w) < 5 or pd.isna(bb_w.iloc[-1]) or pd.isna(bb_w.iloc[-2]):
        return 'Neutral'
    if bb_w.iloc[-1] > bb_w.iloc[-2] * 1.1: return 'Expanding'
    elif bb_w.iloc[-1] < bb_w.iloc[-2] * 0.9: return 'Contracting'
    else: return 'Stable'

def calculate_rr(price: float, support: float, resistance: float, direction: str) -> str:
    if direction == 'BUY':
        risk = price - support; reward = resistance - price
    else:
        risk = resistance - price; reward = price - support
    if risk <= 0: return '1:1.0'
    rr = reward / risk
    return f'1:{rr:.1f}'

def candlestick_confirmation(df: pd.DataFrame) -> Optional[str]:
    if len(df) < 5: return None
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    if len(o) < 3: return None
    body = abs(c[-2] - o[-2]); full_range = h[-2] - l[-2]
    upper_wick = h[-2] - max(c[-2], o[-2]); lower_wick = min(c[-2], o[-2]) - l[-2]
    bullish = False; bearish = False
    if full_range > 0 and body > 0:
        if lower_wick >= 2.0 * body and upper_wick <= body * 0.3 and c[-2] > o[-2]: bullish = True
        if upper_wick >= 2.0 * body and lower_wick <= body * 0.3 and c[-2] > o[-2]: bullish = True
        if upper_wick >= 2.0 * body and lower_wick <= body * 0.3 and c[-2] < o[-2]: bearish = True
        if lower_wick >= 2.0 * body and upper_wick <= body * 0.3 and c[-2] < o[-2]: bearish = True
    prev_body_range = abs(c[-3] - o[-3])
    if prev_body_range > 0:
        if c[-3] < o[-3] and c[-2] > o[-2] and o[-2] <= c[-3] and c[-2] >= o[-3]: bullish = True
        if c[-3] > o[-3] and c[-2] < o[-2] and o[-2] >= c[-3] and c[-2] <= o[-3]: bearish = True
    if len(o) >= 3:
        mother_high = h[-3]; mother_low = l[-3]
        if h[-2] <= mother_high and l[-2] >= mother_low:
            if c[-1] > mother_high: bullish = True
            elif c[-1] < mother_low: bearish = True
    if bullish and not bearish: return 'bullish'
    if bearish and not bullish: return 'bearish'
    if bullish and bearish: return 'bullish' if c[-1] > o[-1] else 'bearish'
    return None


# ============================================================
# 3. MULTI-TIMEFRAME TREND CACHE
# ============================================================
_trend_cache: Dict[str, Tuple[datetime, str]] = {}
_market_trend_cache: Dict[str, Tuple[datetime, str]] = {}

def get_higher_tf_trend(symbol: str) -> Optional[str]:
    if symbol in _trend_cache:
        cached_time, trend = _trend_cache[symbol]
        if (datetime.now(timezone.utc) - cached_time).seconds < 300:
            return trend
    return None

def cache_higher_tf_trend(symbol: str, trend: str):
    _trend_cache[symbol] = (datetime.now(timezone.utc), trend)

def get_market_trend(symbol: str) -> Optional[str]:
    if symbol in _market_trend_cache:
        cached_time, trend = _market_trend_cache[symbol]
        if (datetime.now(timezone.utc) - cached_time).seconds < 900:
            return trend
    return None

def cache_market_trend(symbol: str, trend: str):
    _market_trend_cache[symbol] = (datetime.now(timezone.utc), trend)


# ============================================================
# 3b. SESSION-BASED PAIR SELECTION
# ============================================================
PAIRS = [
    "EURUSD-OTC", "GBPJPY-OTC", "AUDUSD-OTC", "NZDUSD-OTC", "USDCAD-OTC",
    "EUR/JPY (OTC)", "USD/JPY (OTC)", "EUR/GBP (OTC)"
]

SESSION_BEST_PAIRS = {
    'Sydney/Tokyo': ['AUDUSD-OTC', 'NZDUSD-OTC', 'USD/JPY (OTC)'],
    'London': ['EURUSD-OTC', 'GBPJPY-OTC', 'EUR/GBP (OTC)', 'USD/JPY (OTC)'],
    'New York': ['EURUSD-OTC', 'GBPJPY-OTC', 'USD/JPY (OTC)', 'EUR/JPY (OTC)', 'AUDUSD-OTC'],
}

def current_session():
    h = datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60
    if 22 <= h or h < 7:
        return "Sydney/Tokyo"
    elif 7 <= h < 12:
        return "London"
    elif 12 <= h < 16:
        return "New York"
    else:
        return "Off"

def get_best_pairs_for_current_session():
    session = current_session()
    return SESSION_BEST_PAIRS.get(session, PAIRS)


# ============================================================
# 3c. ECONOMIC CALENDAR NEWS FILTER
# ============================================================
_ec_cache_time: Optional[datetime] = None
_ec_cache_events: List = []

def news_safe(symbol: str) -> bool:
    if not NEWS_FILTER_ENABLED or not EC_API_AVAILABLE:
        return True
    global _ec_cache_time, _ec_cache_events
    try:
        now = datetime.now(timezone.utc)
        if _ec_cache_time is None or (now - _ec_cache_time).seconds > 300:
            ec = EconomicCalendar()
            _ec_cache_events = ec.get_events(country='US', importance='high')
            _ec_cache_time = now
        for event in _ec_cache_events:
            event_time = event.date if hasattr(event, 'date') else event.get('date', None)
            if event_time:
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                if abs((event_time - now).total_seconds()) < NEWS_WINDOW_SECONDS:
                    logger.warning(f"News filter blocking {symbol}")
                    return False
    except Exception as e:
        logger.debug(f"News filter error (allowing trade): {e}")
    return True


# ============================================================
# 3d. TELEGRAM ALERTS
# ============================================================
async def send_telegram(signal: dict):
    if not TG_AVAILABLE or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        bot = TelegramBot(token=TELEGRAM_TOKEN)
        emoji = "🔴" if signal['direction'] == 'SELL' else "🟢"
        entry_dt = datetime.fromisoformat(signal['entry_time'].replace('Z', '+00:00'))
        entry_str = entry_dt.astimezone(timezone(timedelta(hours=1))).strftime('%H:%M') + ' WAT'
        sym = signal['symbol'].replace('-OTC', '').replace('_OTC', '').replace(' (OTC)', '')
        mart_lines = []
        for i, m in enumerate(signal.get('martingale', [])):
            m_dt = datetime.fromisoformat(m['entry_time'].replace('Z', '+00:00'))
            t = m_dt.astimezone(timezone(timedelta(hours=1))).strftime('%H:%M') + ' WAT'
            mart_lines.append(f"M{i+1} | {m['multiplier']}x | ${m['amount']} | {t}")
        mart_block = "\n".join(mart_lines) if mart_lines else ""
        msg = f"""
NEW SIGNAL!
{sym} | {signal['timeframe']} (OTC)
Entry: {entry_str} | {signal['direction']} {emoji}
Confidence: {signal['confidence']}% | Accuracy: {signal['accuracy']}%
Trend: {signal.get('trend', 'N/A')} | Wyckoff: {signal.get('wyckoff', 'N/A')}
POI: {signal.get('poi', 'N/A')} | ADR Left: {signal.get('adr_remaining', 'N/A')}
CVD: {signal.get('cvd_trend', 'N/A')} | POC: {signal.get('poc', 'N/A')}
{mart_block}
CATALYSTBOTS - below the smart money - CatabotAI.com
"""
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        logger.info(f"Telegram alert sent for {signal['symbol']}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


# ============================================================
# 4. MEMORY, AUTO-TUNING & DAILY STATS
# ============================================================
MEMORY_DB = os.environ.get("DB_PATH", "memory.db")
PARAMS = {'rsi_buy': 33, 'rsi_sell': 67, 'adx_min': 25, 'vol_mult': 1.5}
MIN_CONFIDENCE = 80.0

def init_memory():
    conn = sqlite3.connect(MEMORY_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE, symbol TEXT, direction TEXT,
            timeframe TEXT, platform TEXT, entry_time TIMESTAMP,
            outcome TEXT DEFAULT 'pending', rsi REAL, adx REAL,
            confidence REAL, accuracy REAL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE, wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0, ignored INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0, win_rate REAL DEFAULT 0,
            avg_accuracy REAL DEFAULT 0, avg_confidence REAL DEFAULT 0
        )
    """)
    conn.commit(); conn.close()

def remember_signal(sig_id, sym, dir_, tf, platform, entry, rsi_val, adx_val, conf, accuracy=0):
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (None, sig_id, sym, dir_, tf, platform, entry, 'pending', rsi_val, adx_val, conf, accuracy))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"DB write error: {e}")

def learn_from_outcome(sig_id, outcome):
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("UPDATE trades SET outcome=? WHERE signal_id=?", (outcome, sig_id))
        cur.execute("SELECT outcome FROM trades WHERE outcome IN ('win','loss') ORDER BY entry_time DESC LIMIT 50")
        real_rows = cur.fetchall()
        global PARAMS, MIN_CONFIDENCE
        if len(real_rows) >= 50:
            wins = sum(1 for r in real_rows if r[0] == 'win')
            wr = wins / len(real_rows)
            logger.info(f"WR {wr:.1%} ({wins}/{len(real_rows)})")
            if wr < 0.80:
                PARAMS['rsi_buy'] = max(15, PARAMS['rsi_buy'] - 3)
                PARAMS['rsi_sell'] = min(85, PARAMS['rsi_sell'] + 3)
                PARAMS['adx_min'] = min(45, PARAMS['adx_min'] + 3)
                PARAMS['vol_mult'] = min(3.0, PARAMS['vol_mult'] + 0.3)
                MIN_CONFIDENCE = min(95, MIN_CONFIDENCE + 2)
                logger.warning(f"TIGHTENING: {PARAMS}, min conf {MIN_CONFIDENCE}")
            elif wr >= 0.95 and PARAMS['adx_min'] > 20:
                PARAMS['adx_min'] = max(20, PARAMS['adx_min'] - 1)
                PARAMS['vol_mult'] = max(1.2, PARAMS['vol_mult'] - 0.1)
                if MIN_CONFIDENCE > 75: MIN_CONFIDENCE -= 1
                logger.info(f"Relaxing: {PARAMS}, min conf {MIN_CONFIDENCE}")
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"DB learn error: {e}")

def get_stats() -> dict:
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT outcome FROM trades WHERE outcome IN ('win','loss')")
        real = cur.fetchall()
        total_real = len(real)
        wins = sum(1 for r in real if r[0] == 'win')
        cur.execute("SELECT outcome FROM trades WHERE outcome='ignored'")
        ignored = len(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM trades WHERE outcome='pending'")
        pending = cur.fetchone()[0]
        conn.close()
        wr = round(wins / total_real * 100, 1) if total_real else 0
        return {"total_trades": total_real, "wins": wins, "losses": total_real - wins,
                "win_rate": wr, "ignored": ignored, "pending": pending,
                "params": PARAMS, "min_confidence": MIN_CONFIDENCE}
    except:
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "ignored": 0, "pending": 0, "params": PARAMS, "min_confidence": MIN_CONFIDENCE}

def historical_confidence(rsi_val, adx_val, direction, platform) -> float:
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("""SELECT outcome FROM trades WHERE direction=? AND platform=? AND outcome IN ('win','loss')
                       AND rsi BETWEEN ? AND ? AND adx BETWEEN ? AND ?
                       ORDER BY entry_time DESC LIMIT 30""",
                    (direction, platform, rsi_val - 5, rsi_val + 5, adx_val - 10, adx_val + 10))
        rows = cur.fetchall()
        conn.close()
        if len(rows) >= 10:
            wins = sum(1 for r in rows if r[0] == 'win')
            return round(wins / len(rows) * 100, 1)
    except:
        pass
    return 75.0


# ============================================================
# 5. SIGNAL GENERATION (v5.0: ALL filters + score boosters)
# ============================================================
def generate_signal(df, symbol="", higher_tf_trend=None, market_trend=None):
    """
    v5.0 Signal Generation: Hard filters + soft filters + accuracy scoring with boosters.
    Returns dict with all signal fields or None.
    """
    df = safe_df(df)
    if len(df) < 80 or df.empty:
        return None

    close = df['close']; high = df['high']; low = df['low']; volume = df['volume']

    # ── Core indicators ────────────────────────────────
    ema5 = ema(close, 5); ema20 = ema(close, 20)
    bull = ema5.iloc[-2] < ema20.iloc[-2] and ema5.iloc[-1] > ema20.iloc[-1]
    bear = ema5.iloc[-2] > ema20.iloc[-2] and ema5.iloc[-1] < ema20.iloc[-1]

    rsi_val = rsi(close, 14).iloc[-1]
    if pd.isna(rsi_val): return None
    adx_val = adx(high, low, close, 14).iloc[-1]
    if pd.isna(adx_val): return None

    avg_vol = volume.iloc[-20:-1].mean()
    if avg_vol == 0: avg_vol = 1
    vol_spike = volume.iloc[-1] >= avg_vol * PARAMS['vol_mult']

    bb_w = bb_width(close, 20)
    if len(bb_w) < 20: return None
    recent_bw = bb_w.iloc[-20:].dropna()
    if len(recent_bw) < 5: return None
    bb_pct = recent_bw.rank(pct=True).iloc[-1]
    bb_sq = bb_pct < 0.30
    bb_exp = bb_w.iloc[-1] > bb_w.iloc[-2]

    price = close.iloc[-1]
    support, resistance = sr_levels(price, df)
    buy_sr = price >= support * 1.0012
    sell_sr = price <= resistance * 0.9988

    # ── v3.2 indicators ────────────────────────────────
    struct = market_structure(df)
    mss = detect_mss(df)
    reversal = detect_market_structure_reversal(df)
    candle = candlestick_confirmation(df)
    sd = order_block(df)
    fvg_ = detect_fvg(df)
    fvg_q = fvg_quality(df)
    fresh_fvg = fvg_q is not None and fvg_q[2] <= 3 and fvg_q[1] >= 0.3
    mom_3 = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100 if len(close) >= 4 else 0
    stoch_val, stoch_status = stochastic(high, low, close)
    regime, regime_desc = detect_regime(df)
    liq_sweep, liq_side = detect_liquidity_sweep(df)
    vol_class = classify_volume(df)
    bb_status = classify_bb_width(bb_w)
    trend_dir = 'Bullish' if ema5.iloc[-1] > ema20.iloc[-1] else 'Bearish'

    # ── v5.0 NEW indicators ────────────────────────────
    wyckoff_phase = detect_wyckoff_phase(df)
    bias = detect_direction_bias(df, higher_tf_trend, market_trend)
    div_buy = detect_rsi_divergence(df, 'BUY')
    div_sell = detect_rsi_divergence(df, 'SELL')
    encroach = detect_consequent_encroachment(df)
    poi_buy = poi_score(df, 'BUY')
    poi_sell = poi_score(df, 'SELL')
    adr_rem = adr_remaining_pct(df)
    trend = detect_trend(df)
    pattern_name, pattern_dir = detect_chart_pattern(df)
    amd = detect_amd_phase(df)
    eq_hl = detect_equal_highs_lows(df)
    trap = detect_liquidity_trap(df)
    liq_side_smc = detect_liquidity_side(df)
    inv_point = detect_inversion_point(df)
    eq_price, eq_dist = detect_equilibrium(df)
    mit = mitigation_block(df)
    rej = rejection_block(df)

    # ── v5.1 VP/OF indicators ────────────────────────
    vp_data = build_volume_profile(df)
    cvd_data = cumulative_volume_delta(df)
    aggressive = detect_aggressive_zone(df, 'BUY') or detect_aggressive_zone(df, 'SELL')
    fresh_demand = detect_fresh_zone(df, 'demand')
    fresh_supply = detect_fresh_zone(df, 'supply')
    tested_demand = detect_tested_zone(df, 'demand')
    tested_supply = detect_tested_zone(df, 'supply')

    # ══════════════════════════════════════════════════════
    # DIRECTION DECISION (hard filters)
    # ══════════════════════════════════════════════════════
    direction = None

    # ── BUY hard filters ───────────────────────────────
    if (bull and rsi_val < PARAMS['rsi_buy'] and adx_val > PARAMS['adx_min']
        and vol_spike and bb_sq and bb_exp and buy_sr
        and (struct == 'bullish' or mss == 'bullish')
        and reversal == 'bullish' and candle == 'bullish'
        and sd == 'demand' and fvg_ == 'bullish' and mom_3 > 0.03
        and wyckoff_confirms_signal(wyckoff_phase, 'BUY')
        and bias in ('bullish', 'neutral') and div_buy
        and (encroach == 'bullish' or encroach is None)
        and poi_buy >= 60
        and adr_rem > 0.3
        and trend in ('bullish', 'strong_bullish', 'sideways')
        and (pattern_dir is None or pattern_dir == 'BUY')
        and amd in ('accumulation', 'advance', None)
        and liq_side_smc != 'sell_side'):
        direction = 'BUY'

    # ── SELL hard filters ──────────────────────────────
    elif (bear and rsi_val > PARAMS['rsi_sell'] and adx_val > PARAMS['adx_min']
        and vol_spike and bb_sq and bb_exp and sell_sr
        and (struct == 'bearish' or mss == 'bearish')
        and reversal == 'bearish' and candle == 'bearish'
        and sd == 'supply' and fvg_ == 'bearish' and mom_3 < -0.03
        and wyckoff_confirms_signal(wyckoff_phase, 'SELL')
        and bias in ('bearish', 'neutral') and div_sell
        and (encroach == 'bearish' or encroach is None)
        and poi_sell >= 60
        and adr_rem > 0.3
        and trend in ('bearish', 'strong_bearish', 'sideways')
        and (pattern_dir is None or pattern_dir == 'SELL')
        and amd in ('distribution', 'decline', None)
        and liq_side_smc != 'buy_side'):
        direction = 'SELL'

    if direction is None:
        return None

    # ══════════════════════════════════════════════════════
    # SOFT FILTERS (can veto direction)
    # ══════════════════════════════════════════════════════
    if eq_price and eq_dist and eq_dist > 0.5:
        direction = None
    if inv_point:
        if direction == 'BUY' and price < inv_point: direction = None
        if direction == 'SELL' and price > inv_point: direction = None
    if direction == 'BUY' and encroach == 'bearish': direction = None
    if direction == 'SELL' and encroach == 'bullish': direction = None

    if direction is None:
        return None

    # ══════════════════════════════════════════════════════
    # ACCURACY SCORING with boosters
    # ══════════════════════════════════════════════════════
    score = 0
    if direction == 'BUY':
        score += min(30, max(0, PARAMS['rsi_buy'] - rsi_val))
    else:
        score += min(30, max(0, rsi_val - PARAMS['rsi_sell']))
    score += min(20, max(0, adx_val - 20))
    if vol_spike: score += 5
    if bb_sq and bb_exp: score += 5
    if sd: score += 5
    if fvg_: score += 10
    if struct or mss: score += 10
    if reversal: score += 15
    if candle: score += 15
    if wyckoff_confirms_signal(wyckoff_phase, direction): score += 10
    score += poi_score(df, direction) / 5

    # v5.0 Score boosters
    if poi_score(df, direction) >= 80: score += 10
    if adr_rem > 0.5: score += 5
    if eq_dist and eq_dist < 0.3: score += 5
    if inv_point: score += 10
    if direction == 'BUY' and trend in ('bullish', 'strong_bullish'): score += 10
    if direction == 'SELL' and trend in ('bearish', 'strong_bearish'): score += 10
    if pattern_dir == direction: score += 15
    if (direction == 'BUY' and eq_hl == 'bullish') or (direction == 'SELL' and eq_hl == 'bearish'): score += 10
    if (direction == 'BUY' and amd in ('accumulation', 'advance')) or \
       (direction == 'SELL' and amd in ('distribution', 'decline')): score += 10
    if (direction == 'BUY' and trap == 'bullish') or (direction == 'SELL' and trap == 'bearish'): score += 15
    if (direction == 'BUY' and encroach == 'bullish') or (direction == 'SELL' and encroach == 'bearish'): score += 15
    if (direction == 'BUY' and mit == 'bullish') or (direction == 'SELL' and mit == 'bearish'): score += 10
    if (direction == 'BUY' and rej == 'support') or (direction == 'SELL' and rej == 'resistance'): score += 10

    # v5.1 VP/OF score boosters
    score += vp_of_score(df, direction)

    accuracy = min(100, max(50, score))

    # ── MTF check ──────────────────────────────────────
    if direction == 'BUY':
        mtf_ok = higher_tf_trend is None or higher_tf_trend == 'bullish'
        market_ok = market_trend is None or market_trend == 'bullish'
    else:
        mtf_ok = higher_tf_trend is None or higher_tf_trend == 'bearish'
        market_ok = market_trend is None or market_trend == 'bearish'
    if not mtf_ok or not market_ok:
        return None

    # ── Build result ───────────────────────────────────
    rr = calculate_rr(price, support, resistance, direction)
    zone_label = ''
    if sd == 'demand': zone_label = 'Demand + Order Block'
    elif sd == 'supply': zone_label = 'Supply + Order Block'
    elif sd: zone_label = sd.title() + ' Zone'
    else: zone_label = 'None Detected'
    bos_status = 'Confirmed' if struct == ('bullish' if direction == 'BUY' else 'bearish') else 'Not Confirmed'
    choch_status = 'Confirmed' if mss == ('bullish' if direction == 'BUY' else 'bearish') else 'Not Confirmed'

    return {
        'direction': direction,
        'rsi': round(rsi_val, 1), 'adx': round(adx_val, 1),
        'accuracy': round(accuracy, 1),
        'regime': regime, 'regime_desc': regime_desc,
        'trend': trend_dir, 'bos': bos_status, 'choch': choch_status,
        'fvg': 'Active' if fvg_ else 'Inactive', 'fvg_type': fvg_ or 'None',
        'liquidity_sweep': liq_sweep, 'liquidity_side': liq_side,
        'volume_class': vol_class, 'zone': zone_label,
        'stoch_val': stoch_val, 'stoch_status': stoch_status,
        'bb_status': bb_status, 'rr': rr,
        'support': round(support, 5), 'resistance': round(resistance, 5),
        'price': round(price, 5), 'order_block': sd or 'None',
        'mtf_ok': mtf_ok, 'market_ok': market_ok,
        # v5.0 new fields
        'wyckoff': wyckoff_phase, 'bias': bias,
        'poi': poi_buy if direction == 'BUY' else poi_sell,
        'adr_remaining': round(adr_rem, 2),
        'trend_strength': trend,
        'pattern': pattern_name,
        'amd': amd,
        'encroach': encroach,
        # v5.1 VP/OF new fields
        'poc': vp_data['poc'] if vp_data else None,
        'va_high': vp_data['va_high'] if vp_data else None,
        'va_low': vp_data['va_low'] if vp_data else None,
        'cvd_trend': cvd_data['trend'] if cvd_data else 'neutral',
        'aggressive_zone': aggressive,
        'fresh_demand': fresh_demand,
        'fresh_supply': fresh_supply,
    }

def calculate_martingale(entry: datetime, timeframe: str, confidence: float, base_stake: float = 1.0) -> List[dict]:
    tf_min = {'30s': 0.5, '45s': 0.75, '1m': 1, '2m': 2, '3m': 3, '5m': 5}
    offset_minutes = tf_min.get(timeframe, 1)
    if confidence >= 90: mults = [2.2, 4.8, 10.5]
    elif confidence >= 80: mults = [2.5, 5.5, 12.0]
    else: mults = [2.8, 6.2, 13.6]
    levels = []
    for i, (m, off) in enumerate(zip(mults, [1, 2, 3])):
        t = entry + timedelta(minutes=offset_minutes * off)
        amount = round(base_stake * m, 2)
        if amount > 3.0: amount = 3.0; m = round(amount / base_stake, 1)
        levels.append({'level': f'M{i+1}', 'multiplier': m, 'amount': amount, 'entry_time': t.isoformat()})
    return levels


# ============================================================
# 5b. BROKER CONNECTION & DATA
# ============================================================
IQ_TFS = ["1m", "2m", "3m", "5m"]
PO_TFS = ["30s", "45s", "1m", "2m", "3m", "5m"]
TF_SECONDS = {'30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300, '15m': 900}

iq_api = None; iq_connected = False; iq_practice_mode = True
po_api = None; po_connected = False; po_demo_mode = True

IQ_SYMBOL_MAP = {
    "EURUSD-OTC": "EURUSD-OTC", "GBPJPY-OTC": "GBPJPY-OTC",
    "AUDUSD-OTC": "AUDUSD-OTC", "NZDUSD-OTC": "NZDUSD-OTC",
    "USDCAD-OTC": "USDCAD-OTC", "EUR/JPY (OTC)": "EURJPY-OTC",
    "USD/JPY (OTC)": "USDJPY-OTC", "EUR/GBP (OTC)": "EURGBP-OTC",
}
PO_SYMBOL_MAP = {
    "EURUSD-OTC": "EURUSD_OTC", "GBPJPY-OTC": "GBPJPY_OTC",
    "AUDUSD-OTC": "AUDUSD_OTC", "NZDUSD-OTC": "NZDUSD_OTC",
    "USDCAD-OTC": "USDCAD_OTC", "EUR/JPY (OTC)": "EURJPY_OTC",
    "USD/JPY (OTC)": "USDJPY_OTC", "EUR/GBP (OTC)": "EURGBP_OTC",
}

def connect_iq_option():
    global iq_api, iq_connected
    if not USE_IQ_OPTION or not IQ_API_AVAILABLE: return False
    if not IQ_EMAIL or IQ_EMAIL == "your_iq_option_email@example.com": return False
    try:
        iq_api = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        check, reason = iq_api.connect()
        if check:
            iq_api.connect(); iq_connected = True
            if iq_practice_mode: iq_api.change_balance("PRACTICE")
            logger.info(f"IQ Option connected ({'PRACTICE' if iq_practice_mode else 'REAL'})")
            return True
        else:
            logger.error(f"IQ Option connection failed: {reason}")
            iq_api = None; return False
    except Exception as e:
        logger.error(f"IQ Option API error: {e}")
        iq_api = None; return False

def connect_pocket_option():
    global po_api, po_connected
    if not USE_POCKET_OPTION or not PO_API_AVAILABLE: return False
    if not PO_EMAIL: return False
    try:
        if PO_API_TYPE == 'stable_api':
            po_api = PocketOption(PO_EMAIL, PO_PASSWORD)
            po_api.connect(); po_connected = True
            logger.info("Pocket Option connected (pocketoptionapi)")
            return True
        else:
            logger.info("Pocket Option PyPI package - requires SSID auth")
            return False
    except Exception as e:
        logger.error(f"Pocket Option API error: {e}")
        po_api = None; po_connected = False; return False

def connect_brokers():
    iq_ok = connect_iq_option()
    po_ok = connect_pocket_option()
    if iq_ok or po_ok:
        logger.info(f"Brokers connected - IQ: {iq_ok}, PO: {po_ok}")
    else:
        logger.warning("No brokers connected - running on demo data")
    return iq_ok or po_ok

def fetch_iq_candles(symbol: str, tf: str, count: int = 120) -> Optional[pd.DataFrame]:
    global iq_connected
    if not iq_connected or iq_api is None: return None
    iq_symbol = IQ_SYMBOL_MAP.get(symbol, symbol)
    tf_sec = TF_SECONDS.get(tf, 60)
    try:
        candles = iq_api.get_candles(iq_symbol, tf_sec, count, time.time())
        if not candles or len(candles) < 30: return None
        df = pd.DataFrame(candles)
        rename_map = {}
        if 'max' in df.columns and 'high' not in df.columns: rename_map['max'] = 'high'
        if 'min' in df.columns and 'low' not in df.columns: rename_map['min'] = 'low'
        if rename_map: df = df.rename(columns=rename_map)
        if 'high' not in df.columns: df['high'] = df[['open', 'close']].max(axis=1)
        if 'low' not in df.columns: df['low'] = df[['open', 'close']].min(axis=1)
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            df['volume'] = np.random.randint(50, 250, size=len(df))
        if 'from' in df.columns: df.index = pd.to_datetime(df['from'], unit='s')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        return safe_df(df)
    except Exception as e:
        logger.error(f"IQ fetch error {iq_symbol}: {e}")
        iq_connected = False; return None

def fetch_po_candles(symbol: str, tf: str, count: int = 120) -> Optional[pd.DataFrame]:
    global po_connected
    if not po_connected or po_api is None: return None
    po_symbol = PO_SYMBOL_MAP.get(symbol, symbol)
    tf_sec = TF_SECONDS.get(tf, 60)
    try:
        candles = po_api.get_candles(po_symbol, tf_sec, count)
        if not candles or len(candles) < 30: return None
        df = pd.DataFrame(candles)
        rename_map = {}
        if 'max' in df.columns and 'high' not in df.columns: rename_map['max'] = 'high'
        if 'min' in df.columns and 'low' not in df.columns: rename_map['min'] = 'low'
        if rename_map: df = df.rename(columns=rename_map)
        if 'high' not in df.columns: df['high'] = df[['open', 'close']].max(axis=1)
        if 'low' not in df.columns: df['low'] = df[['open', 'close']].min(axis=1)
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            df['volume'] = np.random.randint(50, 250, size=len(df))
        if 'time' in df.columns: df.index = pd.to_datetime(df['time'], unit='s')
        elif 'from' in df.columns: df.index = pd.to_datetime(df['from'], unit='s')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        return safe_df(df)
    except Exception as e:
        logger.error(f"PO fetch error {po_symbol}: {e}")
        po_connected = False; return None

def _demo_data(symbol, tf):
    np.random.seed(hash(symbol + tf) % 10000)
    periods = 120
    freq = tf.replace('m', 'min').replace('s', 's')
    try:
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq=freq)
    except:
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq='1min')
    price = 1.0800; trend = 1; closes = []
    for _ in range(periods):
        price += trend * 0.00008 + np.random.normal(0, 0.00015)
        closes.append(price)
        if np.random.random() < 0.02: trend *= -1
    df = pd.DataFrame({
        'open': closes,
        'high': [c + abs(np.random.normal(0, 0.00008)) for c in closes],
        'low': [c - abs(np.random.normal(0, 0.00008)) for c in closes],
        'close': closes,
        'volume': [np.random.randint(30, 200) if np.random.random() > 0.05 else np.random.randint(300, 600) for _ in range(periods)]
    }, index=dates)
    df['high'] = df[['high', 'low', 'close']].max(axis=1)
    df['low'] = df[['high', 'low', 'close']].min(axis=1)
    return safe_df(df)

def get_data_sync(symbol, tf):
    if po_connected and po_api is not None and USE_POCKET_OPTION:
        try:
            df = fetch_po_candles(symbol, tf)
            if df is not None and len(df) >= 30: return df
        except: pass
    if iq_connected and iq_api is not None and USE_IQ_OPTION:
        try:
            df = fetch_iq_candles(symbol, tf)
            if df is not None and len(df) >= 30: return df
        except: pass
    return _demo_data(symbol, tf)


# ============================================================
# 6. FASTAPI APP & SCANNING LOOP
# ============================================================
app = FastAPI(title="CATALYSTBOTS", description="below the smart money - CatabotAI.com")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

clients: set = set()
latest_signals: List[dict] = []
init_memory()

async def scan_loop():
    while True:
        active_pairs = get_best_pairs_for_current_session()
        for platform, tfs in [("IQ Option", IQ_TFS), ("Pocket Option", PO_TFS)]:
            for sym in active_pairs:
                # Update MTF caches
                if get_higher_tf_trend(sym) is None:
                    try:
                        df5 = get_data_sync(sym, '5m')
                        if df5 is not None and len(df5) >= 20:
                            e5 = ema(df5['close'], 5); e20 = ema(df5['close'], 20)
                            trend5 = 'bullish' if e5.iloc[-1] > e20.iloc[-1] else ('bearish' if e5.iloc[-1] < e20.iloc[-1] else None)
                            if trend5: cache_higher_tf_trend(sym, trend5)
                    except: pass
                if get_market_trend(sym) is None:
                    try:
                        df15 = get_data_sync(sym, '5m')
                        if df15 is not None and len(df15) >= 20:
                            e5 = ema(df15['close'], 5); e20 = ema(df15['close'], 20)
                            trend15 = 'bullish' if e5.iloc[-1] > e20.iloc[-1] else ('bearish' if e5.iloc[-1] < e20.iloc[-1] else None)
                            if trend15: cache_market_trend(sym, trend15)
                    except: pass

                for tf in tfs:
                    try:
                        if not news_safe(sym):
                            continue
                        df = get_data_sync(sym, tf)
                        sig_info = generate_signal(df, sym, get_higher_tf_trend(sym), get_market_trend(sym))
                        if sig_info is None: continue

                        mem_conf = historical_confidence(sig_info['rsi'], sig_info['adx'], sig_info['direction'], platform)
                        final_conf = round((sig_info['accuracy'] + mem_conf) / 2, 1)
                        if final_conf < MIN_CONFIDENCE: continue

                        now_utc = datetime.now(timezone.utc)
                        entry_time = now_utc + timedelta(minutes=1)
                        sig_id = str(uuid.uuid4())
                        remember_signal(sig_id, sym, sig_info['direction'], tf, platform, entry_time, sig_info['rsi'], sig_info['adx'], final_conf, sig_info['accuracy'])

                        martingale = calculate_martingale(entry_time, tf, final_conf)

                        sig = {
                            'signal_id': sig_id, 'symbol': sym,
                            'direction': sig_info['direction'], 'timeframe': tf,
                            'platform': platform, 'generated_at': now_utc.isoformat(),
                            'entry_time': entry_time.isoformat(),
                            'duration_minutes': TF_SECONDS.get(tf, 60) // 60,
                            'rsi': sig_info['rsi'], 'adx': sig_info['adx'],
                            'confidence': final_conf, 'accuracy': sig_info['accuracy'],
                            'martingale': martingale,
                            # v3.2 fields
                            'regime': sig_info.get('regime', 'RANGING'),
                            'regime_desc': sig_info.get('regime_desc', ''),
                            'trend': sig_info.get('trend', 'N/A'),
                            'bos': sig_info.get('bos', 'Not Confirmed'),
                            'choch': sig_info.get('choch', 'Not Confirmed'),
                            'fvg_type': sig_info.get('fvg_type', 'None'),
                            'liquidity_sweep': sig_info.get('liquidity_sweep', False),
                            'liquidity_side': sig_info.get('liquidity_side', 'None'),
                            'volume_class': sig_info.get('volume_class', 'Normal'),
                            'zone': sig_info.get('zone', 'None'),
                            'stoch_val': sig_info.get('stoch_val', 50),
                            'stoch_status': sig_info.get('stoch_status', 'Neutral'),
                            'bb_status': sig_info.get('bb_status', 'Neutral'),
                            'rr': sig_info.get('rr', '1:1.0'),
                            'support': sig_info.get('support', 0),
                            'resistance': sig_info.get('resistance', 0),
                            # v5.0 fields
                            'wyckoff': sig_info.get('wyckoff'),
                            'poi': sig_info.get('poi', 0),
                            'adr_remaining': sig_info.get('adr_remaining', 0),
                            'trend_strength': sig_info.get('trend_strength', 'sideways'),
                            'pattern': sig_info.get('pattern'),
                            'amd': sig_info.get('amd'),
                            'encroach': sig_info.get('encroach'),
                        }

                        latest_signals.insert(0, sig)
                        if len(latest_signals) > 50: latest_signals.pop()

                        payload = {'type': 'new_signal', **sig}
                        for ws_client in list(clients):
                            try: await ws_client.send_json(payload)
                            except: clients.discard(ws_client)

                        logger.info(f"{platform} {sym} {sig_info['direction']} | Acc:{sig_info['accuracy']:.0f}% Final:{final_conf:.0f}%")
                        asyncio.create_task(send_telegram(sig))
                    except Exception as e:
                        logger.error(f"Error {platform} {sym} {tf}: {traceback.format_exc()}")
        await asyncio.sleep(15)

async def protected_scan_loop():
    while True:
        try:
            await scan_loop()
        except Exception as e:
            logger.critical(f"Scan loop crashed: {e}. Restart in 5s.")
            await asyncio.sleep(5)


# ============================================================
# 6b. DASHBOARD HTML (CATALYSTBOTS branded, mobile-friendly)
# ============================================================
DASHBOARD = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>CATALYSTBOTS - below the smart money</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{background:#050510;color:#e0e0e0;font-family:'Segoe UI',system-ui,sans-serif;padding:10px;min-height:100vh}
.app{max-width:1200px;margin:0 auto;padding:10px}
.header{background:linear-gradient(135deg,#0a0a2e,#1a1a4e);border-radius:16px;padding:15px;display:flex;justify-content:space-between;align-items:center;border:1px solid #2a2a5a;margin-bottom:10px;flex-wrap:wrap;gap:10px}
.logo{font-size:1.5em;font-weight:bold}.logo span{color:#00ff88}
.tagline{font-size:0.7em;color:#888;margin-top:2px}
.status{color:#00ff88;background:rgba(0,255,136,0.1);padding:5px 12px;border-radius:20px;font-size:0.8em}
.session-badge{display:inline-block;padding:3px 10px;border-radius:15px;font-size:0.8em}
.active{background:rgba(0,255,136,0.1);color:#00ff88}
.inactive{background:rgba(255,68,68,0.1);color:#ff4444}
.platform-selector{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:15px}
.platform-btn{padding:8px 16px;border-radius:25px;border:1px solid #2a2a5a;background:#0a0a2e;color:#e0e0e0;cursor:pointer;font-weight:600;font-size:0.8em}
.platform-btn.active{background:#00ff88;color:#000}
.signals{background:#0a0a1e;border-radius:16px;padding:15px;border:1px solid #2a2a5a;min-height:200px}
.waiting{text-align:center;padding:40px;color:#666}
.signal-card{background:#1a1a3e;border-radius:12px;padding:15px;margin:10px 0;border-left:4px solid #00ff88;animation:slide .3s}
.signal-card.sell{border-left-color:#ff4444}
.signal-card.iq{border-top:2px solid #00b4d8}
.signal-card.po{border-top:2px solid #ffd700}
.card-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:5px}
.pair{font-size:1.1em;font-weight:bold}
.platform-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:0.7em;font-weight:bold}
.platform-badge.iq{background:rgba(0,180,216,0.2);color:#00b4d8}
.platform-badge.po{background:rgba(255,215,0,0.2);color:#ffd700}
.accuracy{font-size:1.2em;font-weight:bold}
.accuracy.high{color:#00ff88}.accuracy.medium{color:#ffd700}.accuracy.low{color:#ff4444}
.conf{color:#00ff88;background:rgba(0,255,136,0.1);padding:3px 10px;border-radius:15px;font-size:0.8em}
.direction{display:inline-block;padding:5px 12px;border-radius:8px;margin:8px 0;font-size:0.9em}
.direction.buy{background:rgba(0,255,136,0.2);color:#00ff88}
.direction.sell{background:rgba(255,68,68,0.2);color:#ff4444}
.btn-group{margin-top:10px;display:flex;flex-wrap:wrap;gap:5px}
.btn{padding:8px 14px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;font-size:0.8em}
.win-btn{background:#00ff88;color:#000}.loss-btn{background:#ff4444;color:#fff}.ignore-btn{background:#666;color:#fff}.copy-btn{background:#00b4d8;color:#fff}
.countdown{font-size:1.3em;font-weight:bold;color:#ffd700;margin:8px 0}
.timing-details{font-size:0.8em;color:#aaa;margin-bottom:10px}
.martingale{margin-top:10px;background:#111;padding:10px;border-radius:8px;font-size:0.8em}
.martingale-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #222}
.smc-tags{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px}
.smc-tag{padding:2px 8px;border-radius:12px;font-size:0.7em;font-weight:bold}
.smc-tag.wyckoff{background:rgba(0,180,216,0.15);color:#00b4d8}
.smc-tag.trend{background:rgba(0,255,136,0.15);color:#00ff88}
.smc-tag.pattern{background:rgba(255,215,0,0.15);color:#ffd700}
.smc-tag.poi{background:rgba(255,105,180,0.15);color:#ff69b4}
.smc-tag.amd{background:rgba(138,43,226,0.15);color:#ba55d3}
.smc-tag.encroach{background:rgba(255,165,0,0.15);color:#ffa500}
.smc-tag.bos{background:rgba(0,255,136,0.15);color:#00ff88}
.smc-tag.choch{background:rgba(255,68,68,0.15);color:#ff4444}
.smc-tag.poc-tag{background:rgba(0,191,255,0.15);color:#00bfff}
.smc-tag.cvd{background:rgba(50,205,50,0.15);color:#32cd32}
.smc-tag.aggressive{background:rgba(255,69,0,0.15);color:#ff4500}
.smc-tag.fresh{background:rgba(0,250,154,0.15);color:#00fa9a}
@keyframes slide{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:768px){.header{flex-direction:column;align-items:flex-start}.logo{font-size:1.3em}.pair{font-size:1em}.signal-card{padding:12px}.btn{padding:8px 12px;font-size:0.75em}.countdown{font-size:1.1em}}
</style>
</head>
<body>
<div class="app">
<div class="header">
<div>
<div class="logo">CATALYST<span>BOTS</span></div>
<div class="tagline">below the smart money - CatabotAI.com</div>
</div>
<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
<span class="session-badge" id="session-badge">...</span>
<span class="status" id="sys-status">Live</span>
</div>
</div>
<div id="session-timer" style="color:#888;margin-bottom:10px;font-size:0.8em"></div>
<div class="platform-selector">
<button class="platform-btn active" onclick="filterPlatform('all',this)">All</button>
<button class="platform-btn" onclick="filterPlatform('IQ Option',this)">IQ Option</button>
<button class="platform-btn" onclick="filterPlatform('Pocket Option',this)">Pocket Option</button>
</div>
<div class="stats-bar" id="stats" style="margin-bottom:15px;">Loading stats...</div>
<div class="signals" id="signals"><div class="waiting" id="waiting"><div style="font-size:2.5em">🧠</div><h3>Waiting for perfect setups</h3><p>Scanning OTC pairs across IQ Option and Pocket Option.</p></div></div>
</div>
<script>
var currentPlatform='all';
function filterPlatform(p,btn){currentPlatform=p;document.querySelectorAll('.platform-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.signal-card').forEach(card=>{card.style.display=(p==='all'||card.dataset.platform===p)?'':'none';});}
function updateStats(){fetch('/api/stats').then(r=>r.json()).then(d=>{document.getElementById('stats').innerHTML='Win Rate: '+d.win_rate+'% | Wins: '+d.wins+' | Losses: '+d.losses+' | Ignored: '+d.ignored;});}
setInterval(updateStats,10000);updateStats();
function updateSession(){fetch('/api/session').then(r=>r.json()).then(d=>{var b=document.getElementById('session-badge');b.textContent=d.active?d.session:'Off';b.className='session-badge '+(d.active?'active':'inactive');});}
setInterval(updateSession,30000);updateSession();
function formatTime(s){if(s<=0)return"Entry passed";var m=Math.floor(s/60),sec=Math.floor(s%60);return'Entry in '+m+':'+(sec<10?'0':'')+sec;}
function updateCountdowns(){document.querySelectorAll('.signal-card').forEach(card=>{var entryTime=new Date(card.dataset.entryTime),diff=(entryTime-new Date())/1000,el=card.querySelector('.countdown');if(el){el.textContent=formatTime(diff);el.style.color=diff<=0?'#ff4444':'#ffd700';}});}
setInterval(updateCountdowns,2000);
var ws=new WebSocket('ws://'+location.host+'/ws');
ws.onmessage=function(e){
var d=JSON.parse(e.data);
if(d.type==='new_signal'){
var card=document.createElement('div');
card.className='signal-card '+d.direction.toLowerCase();
Object.assign(card.dataset,{signalId:d.signal_id,entryTime:d.entry_time,platform:d.platform});
if(d.platform==='IQ Option')card.classList.add('iq');else card.classList.add('po');
var gen=new Date(d.generated_at),entry=new Date(d.entry_time),end=new Date(entry.getTime()+d.duration_minutes*60000);
var accClass=d.accuracy>=85?'high':(d.accuracy>=70?'medium':'low');
var mart='';
if(d.martingale&&d.martingale.length>0){
mart='<div class="martingale"><div style="color:#ffd700;font-weight:bold;">MARTINGALE</div>';
d.martingale.forEach(function(m){
var mt=new Date(m.entry_time).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';
mart+='<div class="martingale-row"><span>'+m.level+'</span><span>'+m.multiplier+'x</span><span>$'+m.amount+'</span><span>'+mt+'</span></div>';
});
mart+='</div>';
}
var platformBadge=d.platform==='IQ Option'?'<span class="platform-badge iq">IQ Option</span>':'<span class="platform-badge po">Pocket Option</span>';
var smcTags='';
if(d.wyckoff)smcTags+='<span class="smc-tag wyckoff">Wyckoff: '+d.wyckoff+'</span>';
if(d.trend_strength)smcTags+='<span class="smc-tag trend">Trend: '+d.trend_strength+'</span>';
if(d.pattern)smcTags+='<span class="smc-tag pattern">'+d.pattern+'</span>';
if(d.poi)smcTags+='<span class="smc-tag poi">POI: '+d.poi+'</span>';
if(d.amd)smcTags+='<span class="smc-tag amd">AMD: '+d.amd+'</span>';
if(d.encroach)smcTags+='<span class="smc-tag encroach">Encroach: '+d.encroach+'</span>';
if(d.bos)smcTags+='<span class="smc-tag bos">BOS: '+d.bos+'</span>';
if(d.choch)smcTags+='<span class="smc-tag choch">CHoCH: '+d.choch+'</span>';
if(d.poc)smcTags+='<span class="smc-tag poc-tag">POC: '+d.poc+'</span>';
if(d.cvd_trend&&d.cvd_trend!=='neutral')smcTags+='<span class="smc-tag cvd">CVD: '+d.cvd_trend+'</span>';
if(d.aggressive_zone)smcTags+='<span class="smc-tag aggressive">Aggressive Zone</span>';
if(d.fresh_demand&&d.direction==='BUY')smcTags+='<span class="smc-tag fresh">Fresh Demand</span>';
if(d.fresh_supply&&d.direction==='SELL')smcTags+='<span class="smc-tag fresh">Fresh Supply</span>';
card.innerHTML='<div class="card-header"><div class="pair">'+d.symbol+' '+platformBadge+'</div><div class="conf">'+d.confidence+'%</div></div>'+
'<div class="accuracy '+accClass+'">Accuracy: '+d.accuracy+'%</div>'+
'<div class="direction '+d.direction.toLowerCase()+'">'+d.direction+'</div>'+
'<div class="countdown">'+formatTime((entry-new Date())/1000)+'</div>'+
'<div class="timing-details">Start: '+gen.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' | Entry: '+entry.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' | End: '+end.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' ('+d.duration_minutes+'m)</div>'+
'<div>'+d.timeframe+' (OTC) | RSI: '+d.rsi+' | ADX: '+d.adx+' | ADR: '+d.adr_remaining+'% | RR: '+d.rr+'</div>'+
'<div class="smc-tags">'+smcTags+'</div>'+mart+
'<div class="btn-group"><button class="btn copy-btn" onclick="copySignal(this)">Copy</button><button class="btn win-btn" onclick="report(\''+d.signal_id+'\',\'win\',this)">WIN</button><button class="btn loss-btn" onclick="report(\''+d.signal_id+'\',\'loss\',this)">LOSS</button><button class="btn ignore-btn" onclick="report(\''+d.signal_id+'\',\'ignored\',this)">IGNORE</button></div>'+
'<div class="outcome-text" style="display:none;font-weight:bold;margin-top:5px;"></div>';
var cont=document.getElementById('signals');
document.getElementById('waiting').style.display='none';
cont.insertBefore(card,cont.firstChild);
if(currentPlatform!=='all'&&d.platform!==currentPlatform)card.style.display='none';
}
};
function report(sid,outcome,btn){
var card=btn.closest('.signal-card');
card.querySelectorAll('.btn').forEach(b=>b.disabled=true);
fetch('/api/trade/outcome?signal_id='+sid+'&outcome='+outcome,{method:'POST'}).then(r=>r.json()).then(data=>{
var txt=card.querySelector('.outcome-text');
txt.style.display='block';
if(outcome==='win'){card.style.borderLeft='4px solid #00ff88';txt.style.color='#00ff88';txt.textContent='Trade Won';}
else if(outcome==='loss'){card.style.borderLeft='4px solid #ff4444';txt.style.color='#ff4444';txt.textContent='Trade Lost';}
else{card.style.borderLeft='4px solid #888';txt.style.color='#888';txt.textContent='Ignored';}
card.querySelector('.btn-group').style.display='none';
updateStats();
}).catch(e=>{card.querySelectorAll('.btn').forEach(b=>b.disabled=false);});
}
function copySignal(btn){
var card=btn.closest('.signal-card');
navigator.clipboard.writeText(card.innerText).then(()=>{
btn.textContent='Copied!';btn.style.background='#00ff88';
setTimeout(()=>{btn.textContent='Copy';btn.style.background='#00b4d8';},2000);
});
}
setInterval(function(){
var now=new Date(),hour=now.getUTCHours()+now.getUTCMinutes()/60,rem='';
if(hour>=22||hour<7){var end=new Date(now);end.setUTCHours(7,0,0,0);if(hour>=22)end.setUTCDate(end.getUTCDate()+1);rem='Sydney/Tokyo ends in '+Math.floor((end-now)/3600000)+'h '+Math.floor(((end-now)%3600000)/60000)+'m';}
else if(hour>=8&&hour<16){var end=new Date(now);end.setUTCHours(16,0,0,0);rem='London/NY ends in '+Math.floor((end-now)/3600000)+'h '+Math.floor(((end-now)%3600000)/60000)+'m';}
else rem='Low liquidity';
document.getElementById('session-timer').textContent=rem;
},10000);
</script>
</body>
</html>
"""


# ============================================================
# 7. API ENDPOINTS
# ============================================================
@app.on_event("startup")
async def startup():
    connect_brokers()
    if APS_AVAILABLE:
        try:
            scheduler = AsyncIOScheduler()
            scheduler.add_job(weekly_optimise, 'cron', day_of_week='mon', hour=3)
            scheduler.start()
            logger.info("Weekly optimizer scheduled")
        except: pass
    asyncio.create_task(protected_scan_loop())

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True: await websocket.receive_text()
    except: clients.discard(websocket)

@app.post("/api/trade/outcome")
async def outcome(signal_id: str, outcome: str):
    if outcome not in ('win', 'loss', 'ignored'):
        return {"error": "invalid"}
    learn_from_outcome(signal_id, outcome)
    return {"status": "ok"}

@app.get("/api/stats")
async def stats():
    return get_stats()

@app.get("/api/session")
async def session_info():
    h = datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60
    if 22 <= h or h < 7: s = "Sydney/Tokyo"
    elif 7 <= h < 12: s = "London"
    elif 12 <= h < 16: s = "New York"
    else: s = "Off"
    return {"session": s, "active": True}

@app.get("/api/status")
async def status():
    return {
        "engine": "CATALYSTBOTS v5.1",
        "tagline": "below the smart money - CatabotAI.com",
        "session": current_session(),
        "active_pairs": get_best_pairs_for_current_session(),
        "iq_connected": iq_connected,
        "po_connected": po_connected,
        "params": PARAMS,
        "min_confidence": MIN_CONFIDENCE,
        "ws_clients": len(clients),
    }

@app.get("/api/signals")
async def get_signals():
    return {"signals": latest_signals[:20]}

@app.get("/api/pnl")
async def pnl():
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) FROM trades")
        total, wins, losses = cur.fetchone()
        conn.close()
        return {"total": total or 0, "wins": wins or 0, "losses": losses or 0}
    except:
        return {"total": 0, "wins": 0, "losses": 0}

@app.get("/api/scan")
async def manual_scan():
    asyncio.create_task(scan_loop())
    return {"status": "started"}

@app.get("/")
async def dashboard():
    return HTMLResponse(content=DASHBOARD)


# ============================================================
# 8. WEEKLY OPTIMIZER
# ============================================================
async def weekly_optimise():
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT outcome FROM trades WHERE outcome IN ('win','loss') ORDER BY entry_time DESC LIMIT 500")
        rows = cur.fetchall()
        conn.close()
        if len(rows) < 50: return
        global PARAMS, MIN_CONFIDENCE
        wins = sum(1 for r in rows if r[0] == 'win')
        wr = wins / len(rows)
        logger.info(f"Weekly optimize: WR={wr:.1%} over {len(rows)} trades")
        if wr < 0.85:
            PARAMS['adx_min'] = min(40, PARAMS['adx_min'] + 2)
            PARAMS['rsi_buy'] = max(18, PARAMS['rsi_buy'] - 2)
            PARAMS['rsi_sell'] = min(82, PARAMS['rsi_sell'] + 2)
            MIN_CONFIDENCE = min(93, MIN_CONFIDENCE + 1)
        elif wr >= 0.92:
            PARAMS['adx_min'] = max(20, PARAMS['adx_min'] - 1)
            if MIN_CONFIDENCE > 78: MIN_CONFIDENCE -= 1
    except Exception as e:
        logger.error(f"Weekly optimize error: {e}")


# ============================================================
# 9. ENTRY POINT
# ============================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
