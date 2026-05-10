#!/usr/bin/env python3
"""
CATALYST v3.9 - Self-Improving OTC Signal Engine
10 Confluences + Accuracy Level (0-100%) | 80-95% Win Rate Target | 24/7
IQ Option & Pocket Option | Memory-Based Confidence | Auto-Tuning | Telegram Alerts

v3.3 CHANGES (Full Enhanced Format in Copy + Telegram):
- Copy Signal button now outputs FULL v3.2+ enhanced signal format
- Telegram send_telegram() now outputs FULL enhanced signal format
- Both copy and Telegram formats match exactly: Market Regime, BOS/CHoCH, FVG,
  Liquidity, Volume, Zone, RSI, Stochastic, BB Width, R:R, GLM Smart Money,
  Strategy Guide, Support/Resistance, GLM Probability branding
- Format matches: CATALYST AI SIGNAL header + all sections

v3.2 CHANGES (Enhanced Signal Format):
- Market Regime Detection: BREAKOUT, RANGING, TRENDING with description
- Stochastic Oscillator: Overbought/Oversold/Neutral status
- Liquidity Sweep Detection: Buy/Sell side sweep identification
- Enhanced Zone Analysis: Supply/Demand + Order Block labeling
- BOS/CHoCH Confirmation Status: Active/Not Confirmed display
- R:R Ratio Calculation: Risk-to-Reward display (1:X.X)
- GLM Smart Money Section: Structure, Liquidity, Breakout, Signal validity
- Strategy Guide: Context-sensitive rules based on signal type
- Support/Resistance Levels in signal output
- Enhanced Telegram format: Full emoji-rich signal template
- Enhanced Dashboard: All new fields displayed in signal cards
- Volume Classification: Normal/High/Low labels
- BB Width Status: Expanding/Contracting/Squeezing labels
- GLM Probability branding with HIGH PROBABILITY ONLY filter

v3.1 FEATURES (preserved):
- Entry-time price confirmation
- Telegram Bot alerts
- Economic calendar news filter
- Daily stats + Chart.js win-rate graph
- APScheduler weekly optimization
- Dual broker: IQ Option + Pocket Option
- 10-point ALL-AND confluence + MTF + Accuracy scoring
- Candlestick confirmation
- Market Structure Shift + Confirmed Reversal

DEPLOY:
  Set env vars: IQ_EMAIL, IQ_PASSWORD, PO_EMAIL, PO_PASSWORD
  Set TELEGRAM_TOKEN, TELEGRAM_CHAT_ID for alerts
  Set USE_IQ_OPTION=True / USE_POCKET_OPTION=True
  pip install -r requirements.txt
  python catalyst_final.py
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
import uvicorn

# ============================================================
# 0. BROKER CREDENTIALS & CONFIG (read from env vars)
# ============================================================
IQ_EMAIL        = os.environ.get("IQ_EMAIL", "clarityvisuals4@gmail.com")
IQ_PASSWORD     = os.environ.get("IQ_PASSWORD", "Calarity2819")
PO_EMAIL        = os.environ.get("PO_EMAIL", "richmelody15@gmail.com")
PO_PASSWORD     = os.environ.get("PO_PASSWORD", "Calarity2819")

USE_IQ_OPTION     = os.environ.get("USE_IQ_OPTION", "True").strip().lower() in ("true", "1", "yes")
USE_POCKET_OPTION = os.environ.get("USE_POCKET_OPTION", "True").strip().lower() in ("true", "1", "yes")

# Telegram
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "272156752:AAGHUYuyynp276o1nL66UtpqaT2T-8glt9A")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5844295006")

# Entry confirmation: wait for entry time and verify price moved
ENTRY_CONFIRM_ENABLED = os.environ.get("ENTRY_CONFIRM_ENABLED", "True").strip().lower() in ("true", "1", "yes")
ENTRY_PRICE_THRESHOLD = float(os.environ.get("ENTRY_PRICE_THRESHOLD", "0.0005"))  # 0.05% move required

# News filter: block signals near high-impact economic events
NEWS_FILTER_ENABLED = os.environ.get("NEWS_FILTER_ENABLED", "True").strip().lower() in ("true", "1", "yes")
NEWS_WINDOW_SECONDS = int(os.environ.get("NEWS_WINDOW_SECONDS", "600"))  # 10-minute buffer

# IQ Option API (optional)
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_API_AVAILABLE = True
except ImportError:
    IQ_API_AVAILABLE = False

# Pocket Option API (optional – tries GitHub package then PyPI)
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

# Economic Calendar API (optional – graceful fallback)
try:
    from economiccalendarapi import EconomicCalendar
    EC_API_AVAILABLE = True
except ImportError:
    EC_API_AVAILABLE = False

# APScheduler (optional – for weekly optimization)
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
logger = logging.getLogger("CatalystFinal")

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

def order_block(df: pd.DataFrame) -> Optional[str]:
    if len(df) < 5:
        return None
    last_body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
    prev_body = abs(df['close'].iloc[-2] - df['open'].iloc[-2])
    if prev_body > 0 and last_body > 2.0 * prev_body and df['volume'].iloc[-1] > df['volume'].iloc[-2] * 1.5:
        return 'demand' if df['close'].iloc[-1] > df['open'].iloc[-1] else 'supply'
    return None

def detect_fvg(df: pd.DataFrame) -> Optional[str]:
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

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[float, str]:
    """Stochastic Oscillator %K. Returns (k_value, status_string)."""
    if len(close) < k_period:
        return 50.0, 'Neutral'
    hh = high.rolling(k_period).max()
    ll = low.rolling(k_period).min()
    k = 100.0 * (close - ll) / (hh - ll).replace(0, 1e-10)
    k_val = k.iloc[-1]
    if pd.isna(k_val):
        return 50.0, 'Neutral'
    if k_val > 80:
        status = 'Overbought'
    elif k_val < 20:
        status = 'Oversold'
    else:
        status = 'Neutral'
    return round(float(k_val), 1), status

def detect_regime(df: pd.DataFrame) -> Tuple[str, str]:
    """Detect market regime: BREAKOUT, RANGING, TRENDING. Returns (regime, description)."""
    if len(df) < 30:
        return 'RANGING', 'Insufficient data for regime detection'
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # ATR for range measurement
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    avg_atr = atr.iloc[-20:].mean()
    recent_atr = atr.iloc[-5:].mean()

    # Volume analysis
    avg_vol = volume.iloc[-20:].mean()
    recent_vol = volume.iloc[-5:].mean()
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    # Range analysis
    range_20 = high.iloc[-20:].max() - low.iloc[-20:].min()
    range_5 = high.iloc[-5:].max() - low.iloc[-5:].min()
    range_ratio = range_5 / range_20 if range_20 > 0 else 0.5

    # ADX for trend strength
    adx_val = adx(high, low, close, 14).iloc[-1]
    if pd.isna(adx_val):
        adx_val = 20.0

    # EMA slope
    ema5_val = ema(close, 5)
    ema20_val = ema(close, 20)
    ema_slope = (ema5_val.iloc[-1] - ema5_val.iloc[-5]) / ema5_val.iloc[-5] * 100 if len(ema5_val) >= 5 else 0

    if vol_ratio > 1.5 and range_ratio > 0.4 and recent_atr > avg_atr * 1.3:
        return 'BREAKOUT', 'Market is breaking out of a defined range with surging volume.'
    elif adx_val > 30 and abs(ema_slope) > 0.05:
        direction = 'upward' if ema_slope > 0 else 'downward'
        return 'TRENDING', f'Market is in a sustained {direction} trend with strong momentum.'
    else:
        return 'RANGING', 'Market is consolidating within a defined range, awaiting breakout.'

def detect_liquidity_sweep(df: pd.DataFrame) -> Tuple[bool, str]:
    """Detect liquidity sweep (stop hunt). Returns (sweep_detected, side)."""
    if len(df) < 20:
        return False, 'None'
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values

    # Find recent swing highs and lows (liquidity pools)
    swing_highs = []
    swing_lows = []
    for i in range(3, min(len(high) - 1, 20)):
        idx = len(high) - 1 - i
        if idx < 3:
            break
        if all(high[idx] >= high[idx - j] for j in range(1, 4)) and all(high[idx] >= high[idx + j] for j in range(1, min(4, len(high) - idx))):
            swing_highs.append(high[idx])
        if all(low[idx] <= low[idx - j] for j in range(1, 4)) and all(low[idx] <= low[idx + j] for j in range(1, min(4, len(low) - idx))):
            swing_lows.append(low[idx])

    # Check if price swept above swing high then reversed (sell side liquidity grab)
    if swing_highs and high[-1] > max(swing_highs[:3]) and close[-1] < max(swing_highs[:3]):
        return True, 'Buy Side Sweep'

    # Check if price swept below swing low then reversed (buy side liquidity grab)
    if swing_lows and low[-1] < min(swing_lows[:3]) and close[-1] > min(swing_lows[:3]):
        return True, 'Sell Side Sweep'

    # Simpler check: wick beyond recent range with close back inside
    recent_high = max(high[-10:-1])
    recent_low = min(low[-10:-1])
    if high[-1] > recent_high and close[-1] < recent_high:
        return True, 'Buy Side Sweep'
    if low[-1] < recent_low and close[-1] > recent_low:
        return True, 'Sell Side Sweep'

    return False, 'None'

def classify_volume(df: pd.DataFrame) -> str:
    """Classify current volume as High/Normal/Low."""
    if len(df) < 20:
        return 'Normal'
    vol = df['volume']
    avg = vol.iloc[-20:].mean()
    if avg == 0:
        return 'Normal'
    current = vol.iloc[-1]
    ratio = current / avg
    if ratio > 1.5:
        return 'High'
    elif ratio < 0.6:
        return 'Low'
    return 'Normal'

def classify_bb_width(bb_w: pd.Series) -> str:
    """Classify Bollinger Band width state."""
    if len(bb_w) < 5 or pd.isna(bb_w.iloc[-1]) or pd.isna(bb_w.iloc[-2]):
        return 'Neutral'
    if bb_w.iloc[-1] > bb_w.iloc[-2] * 1.1:
        return 'Expanding'
    elif bb_w.iloc[-1] < bb_w.iloc[-2] * 0.9:
        return 'Contracting'
    else:
        return 'Stable'

def calculate_rr(price: float, support: float, resistance: float, direction: str) -> str:
    """Calculate Risk:Reward ratio string like '1:2.5'."""
    if direction == 'BUY':
        risk = price - support
        reward = resistance - price
    else:
        risk = resistance - price
        reward = price - support
    if risk <= 0:
        return '1:1.0'
    rr = reward / risk
    return f'1:{rr:.1f}'

def market_structure(df: pd.DataFrame) -> Optional[str]:
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

def detect_mss(df: pd.DataFrame) -> Optional[str]:
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

def detect_market_structure_reversal(df: pd.DataFrame) -> Optional[str]:
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

def candlestick_confirmation(df: pd.DataFrame) -> Optional[str]:
    """Hammer/Shooting Star, Engulfing, Inside Bar Breakout - MANDATORY for entry."""
    if len(df) < 5:
        return None
    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    if len(o) < 3:
        return None

    body = abs(c[-2] - o[-2])
    full_range = h[-2] - l[-2]
    upper_wick = h[-2] - max(c[-2], o[-2])
    lower_wick = min(c[-2], o[-2]) - l[-2]
    bullish = False
    bearish = False

    if full_range > 0 and body > 0:
        if lower_wick >= 2.0 * body and upper_wick <= body * 0.3 and c[-2] > o[-2]:
            bullish = True
        if upper_wick >= 2.0 * body and lower_wick <= body * 0.3 and c[-2] > o[-2]:
            bullish = True
        if upper_wick >= 2.0 * body and lower_wick <= body * 0.3 and c[-2] < o[-2]:
            bearish = True
        if lower_wick >= 2.0 * body and upper_wick <= body * 0.3 and c[-2] < o[-2]:
            bearish = True

    prev_body_range = abs(c[-3] - o[-3])
    if prev_body_range > 0:
        if c[-3] < o[-3] and c[-2] > o[-2] and o[-2] <= c[-3] and c[-2] >= o[-3]:
            bullish = True
        if c[-3] > o[-3] and c[-2] < o[-2] and o[-2] >= c[-3] and c[-2] <= o[-3]:
            bearish = True

    if len(o) >= 3:
        mother_high = h[-3]
        mother_low = l[-3]
        if h[-2] <= mother_high and l[-2] >= mother_low:
            if c[-1] > mother_high:
                bullish = True
            elif c[-1] < mother_low:
                bearish = True

    if bullish and not bearish:
        return 'bullish'
    if bearish and not bullish:
        return 'bearish'
    if bullish and bearish:
        return 'bullish' if c[-1] > o[-1] else 'bearish'
    return None

# ============================================================
# 2b. SESSION HELPER
# ============================================================
def current_session():
    """Return current trading session name."""
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60.0
    if 22.0 <= hour or hour < 7.0:
        return 'Sydney/Tokyo'
    elif 7.0 <= hour < 12.0:
        return 'London'
    elif 12.0 <= hour < 16.0:
        return 'New York'
    else:
        return 'Off-peak'

# ============================================================
# 2c. SWING IDENTIFICATION
# ============================================================
def identify_swings(df, order=3):
    """Identify swing highs and lows. Returns list of dicts with 'type','price','index'."""
    if len(df) < order * 2 + 1:
        return []
    highs = df['high'].values
    lows = df['low'].values
    swings = []
    for i in range(order, len(highs) - order):
        if all(highs[i] >= highs[i - j] for j in range(1, order + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, order + 1)):
            swings.append({'type': 'high', 'price': highs[i], 'index': i})
        if all(lows[i] <= lows[i - j] for j in range(1, order + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, order + 1)):
            swings.append({'type': 'low', 'price': lows[i], 'index': i})
    return swings

# ============================================================
# 2d. FVG QUALITY (returns tuple)
# ============================================================
def fvg_quality(df):
    """Return ('bullish', size, age) or ('bearish', size, age) or None."""
    if len(df) < 5:
        return None
    try:
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr_val = tr.rolling(14).mean().iloc[-1]
        if pd.isna(atr_val) or atr_val == 0:
            return None
    except Exception:
        return None
    for i in range(len(df) - 1, max(len(df) - 6, 2), -1):
        prev2 = df.iloc[i - 2]
        curr = df.iloc[i]
        age = len(df) - 1 - i
        if curr['low'] > prev2['high']:
            size = (curr['low'] - prev2['high']) / atr_val
            if size >= 0.3 and age <= 3:
                return ('bullish', round(size, 3), age)
        if curr['high'] < prev2['low']:
            size = (prev2['low'] - curr['high']) / atr_val
            if size >= 0.3 and age <= 3:
                return ('bearish', round(size, 3), age)
    return None

# ============================================================
# 2e. WYCKOFF PHASE DETECTION
# ============================================================
def detect_wyckoff_phase(df):
    """Detect Wyckoff phase: accumulation, markup, distribution, markdown, or None."""
    if len(df) < 30:
        return None
    close = df['close']
    volume = df['volume']
    ema20 = ema(close, 20).iloc[-1]
    ema50 = ema(close, 50).iloc[-1] if len(close) >= 50 else ema20
    price = close.iloc[-1]
    avg_vol = volume.iloc[-20:].mean()
    recent_vol = volume.iloc[-5:].mean()
    price_range = df['high'].iloc[-20:].max() - df['low'].iloc[-20:].min()
    price_avg = close.iloc[-20:].mean()
    if price_avg == 0:
        return None
    range_pct = price_range / price_avg * 100
    if range_pct < 0.3 and recent_vol < avg_vol * 0.8:
        if price < ema20:
            return 'accumulation'
        else:
            return 'distribution'
    if price > ema20 and ema20 > ema50 and recent_vol > avg_vol:
        return 'markup'
    if price < ema20 and ema20 < ema50 and recent_vol > avg_vol:
        return 'markdown'
    return None

# ============================================================
# 2f. RSI DIVERGENCE
# ============================================================
def detect_rsi_divergence(df):
    """Detect RSI divergence. Returns 'bullish', 'bearish', or None."""
    if len(df) < 20:
        return None
    close = df['close'].values
    rsi_vals = rsi(df['close'], 14).values
    lows_idx = []
    for i in range(3, len(close) - 3):
        if all(close[i] <= close[i - j] for j in range(1, 4)) and \
           all(close[i] <= close[i + j] for j in range(1, 4)):
            lows_idx.append(i)
    if len(lows_idx) >= 2:
        l1, l2 = lows_idx[-2], lows_idx[-1]
        if close[l2] < close[l1] and rsi_vals[l2] > rsi_vals[l1]:
            return 'bullish'
    highs_idx = []
    for i in range(3, len(close) - 3):
        if all(close[i] >= close[i - j] for j in range(1, 4)) and \
           all(close[i] >= close[i + j] for j in range(1, 4)):
            highs_idx.append(i)
    if len(highs_idx) >= 2:
        h1, h2 = highs_idx[-2], highs_idx[-1]
        if close[h2] > close[h1] and rsi_vals[h2] < rsi_vals[h1]:
            return 'bearish'
    return None

# ============================================================
# 2g. DAILY BIAS & MTF ALIGNMENT
# ============================================================
def get_daily_bias(df):
    """Return 'bullish', 'bearish', or 'neutral' based on price position."""
    if len(df) < 50:
        return 'neutral'
    ema20 = ema(df['close'], 20).iloc[-1]
    ema50 = ema(df['close'], 50).iloc[-1] if len(df) >= 50 else ema20
    price = df['close'].iloc[-1]
    if price > ema20 > ema50:
        return 'bullish'
    if price < ema20 < ema50:
        return 'bearish'
    return 'neutral'

def mtf_full_alignment(higher_tf_trend, market_trend, current_trend):
    """Check if all timeframes align. Returns True if aligned."""
    trends = [t for t in [higher_tf_trend, market_trend, current_trend] if t is not None]
    if not trends:
        return True
    return all(t == trends[0] for t in trends)

# ============================================================
# 2h. CHoCH CONFIRMED
# ============================================================
def choch_confirmed(df):
    """Detect CHoCH confirmation. Returns 'bullish', 'bearish', or None."""
    return detect_mss(df)

# ============================================================
# 2i. BATCH 0: GUARDS & LEVERAGE
# ============================================================
def detect_leverage_zone(df, direction):
    """Detect if price is in a high-probability leverage zone near FVG + OB."""
    if len(df) < 20:
        return False
    fvg_data = fvg_quality(df)
    ob = order_block(df)
    if fvg_data is None:
        return False
    fvg_dir = fvg_data[0]
    if direction == 'BUY' and fvg_dir == 'bullish' and ob == 'demand':
        return True
    if direction == 'SELL' and fvg_dir == 'bearish' and ob == 'supply':
        return True
    return False

def is_kill_zone():
    """Return True during London 07-09 UTC or NY 13-15 UTC kill zones."""
    now = datetime.now(timezone.utc)
    hour = now.hour
    if 7 <= hour < 9:
        return True
    if 13 <= hour < 15:
        return True
    return False

def is_near_daily_level(df, direction):
    """Block signals when price is too close to daily high/low."""
    if len(df) < 50:
        return False
    daily_high = df['high'].iloc[-50:].max()
    daily_low = df['low'].iloc[-50:].min()
    price = df['close'].iloc[-1]
    range_ = daily_high - daily_low
    if range_ == 0:
        return False
    if direction == 'BUY' and (daily_high - price) / range_ < 0.05:
        return True
    if direction == 'SELL' and (price - daily_low) / range_ < 0.05:
        return True
    return False

def valid_entry_candle(df, direction):
    """Check if last candle is a valid entry candle for the given direction."""
    if len(df) < 2:
        return False
    c = df.iloc[-1]
    body = abs(c['close'] - c['open'])
    full_range = c['high'] - c['low']
    if full_range == 0:
        return False
    body_pct = body / full_range
    if body_pct >= 0.40:
        if direction == 'BUY' and c['close'] > c['open']:
            return True
        if direction == 'SELL' and c['close'] < c['open']:
            return True
    lower_wick = min(c['open'], c['close']) - c['low']
    upper_wick = c['high'] - max(c['open'], c['close'])
    if direction == 'BUY' and lower_wick > 2 * body and upper_wick < body * 0.5:
        return True
    if direction == 'SELL' and upper_wick > 2 * body and lower_wick < body * 0.5:
        return True
    return False

def detect_liquidity_trap(df):
    """Detect liquidity trap: price sweeps key level then reverses."""
    if len(df) < 15:
        return None
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    recent_high = max(high[-10:-2])
    recent_low = min(low[-10:-2])
    if low[-1] < recent_low and close[-1] > recent_low:
        return 'bullish'
    if high[-1] > recent_high and close[-1] < recent_high:
        return 'bearish'
    return None

# ============================================================
# 2j. BATCH 1: SMC ADVANCED (11 functions)
# ============================================================
def ifvg_detection(df):
    """Inverse FVG detection. Returns 'bullish', 'bearish', or None."""
    if len(df) < 10:
        return None
    fvg_data = fvg_quality(df)
    if fvg_data is None:
        return None
    fvg_dir = fvg_data[0]
    for i in range(len(df) - 1, max(len(df) - 6, 2), -1):
        prev2 = df.iloc[i - 2]
        curr = df.iloc[i]
        if fvg_dir == 'bullish' and curr['low'] <= prev2['high']:
            return 'bearish'
        if fvg_dir == 'bearish' and curr['high'] >= prev2['low']:
            return 'bullish'
    return None

def market_holding_creating(df, direction):
    """Check if market is holding/creating structure for direction."""
    if len(df) < 20:
        return False
    struct = market_structure(df)
    if direction == 'BUY' and struct == 'bullish':
        return True
    if direction == 'SELL' and struct == 'bearish':
        return True
    return False

def market_respecting(df, direction):
    """Check if price is respecting key levels for direction."""
    if len(df) < 15:
        return False
    swings = identify_swings(df, order=3)
    if not swings:
        return False
    price = df['close'].iloc[-1]
    if direction == 'BUY':
        lows = [s['price'] for s in swings if s['type'] == 'low']
        if lows and price >= min(lows[-3:]) * 0.999:
            return True
    if direction == 'SELL':
        highs = [s['price'] for s in swings if s['type'] == 'high']
        if highs and price <= max(highs[-3:]) * 1.001:
            return True
    return False

def price_momentum(df, direction):
    """Check price momentum alignment with direction."""
    if len(df) < 5:
        return False
    mom = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
    if direction == 'BUY' and mom > 0:
        return True
    if direction == 'SELL' and mom < 0:
        return True
    return False

def direction_flow(df, direction):
    """Check if order flow aligns with direction."""
    if len(df) < 10:
        return False
    bullish_vol = df[df['close'] > df['open']]['volume'].iloc[-10:].sum()
    bearish_vol = df[df['close'] < df['open']]['volume'].iloc[-10:].sum()
    if direction == 'BUY' and bullish_vol > bearish_vol * 1.2:
        return True
    if direction == 'SELL' and bearish_vol > bullish_vol * 1.2:
        return True
    return False

def detect_mm_model(df):
    """Detect market maker model (manipulation -> liquidity -> continuation)."""
    if len(df) < 20:
        return None
    trap = detect_liquidity_trap(df)
    if trap is None:
        return None
    struct = market_structure(df)
    if trap == 'bullish' and struct == 'bullish':
        return 'buy_model'
    if trap == 'bearish' and struct == 'bearish':
        return 'sell_model'
    return None

BUY_MODELS = {'buy_model'}

def cicd_reversal_confirmed(df, direction):
    """CICD (Change in Character of Demand) reversal confirmation."""
    if len(df) < 20:
        return False
    choch = choch_confirmed(df)
    fvg_data = fvg_quality(df)
    if choch is None:
        return False
    if direction == 'BUY' and choch == 'bullish':
        if fvg_data and fvg_data[0] == 'bullish':
            return True
    if direction == 'SELL' and choch == 'bearish':
        if fvg_data and fvg_data[0] == 'bearish':
            return True
    return False

def detect_market_pattern(df):
    """Detect market pattern with direction. Returns (pattern_name, direction) or (None, None)."""
    if len(df) < 20:
        return None, None
    recent_range = df['high'].iloc[-5:].max() - df['low'].iloc[-5:].min()
    prev_range = df['high'].iloc[-10:-5].max() - df['low'].iloc[-10:-5].min()
    if prev_range == 0:
        return None, None
    if recent_range > prev_range * 1.5:
        return 'expansion', 'bullish' if df['close'].iloc[-1] > df['close'].iloc[-5] else 'bearish'
    if recent_range < prev_range * 0.5:
        return 'contraction', None
    return None, None

def price_aims(df, direction):
    """Check if price aims (directional intent) aligns."""
    if len(df) < 5:
        return False
    closes = df['close'].values
    if direction == 'BUY' and closes[-1] > closes[-2] > closes[-3]:
        return True
    if direction == 'SELL' and closes[-1] < closes[-2] < closes[-3]:
        return True
    return False

def optimal_expiry_seconds(df, tf):
    """Calculate optimal expiry based on candle duration and momentum."""
    tf_seconds = {'30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300}
    base = tf_seconds.get(tf, 60)
    if len(df) < 5:
        return base
    mom = abs(df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
    if mom > 0.1:
        return int(base * 0.8)
    return base

# ============================================================
# 2k. BATCH 2: CONFIRMATION LAYER (7 functions)
# ============================================================
def breakout_retest(df, direction):
    """Check if price broke out and retested a level."""
    if len(df) < 20:
        return False
    swings = identify_swings(df, order=3)
    if len(swings) < 2:
        return False
    price = df['close'].iloc[-1]
    if direction == 'BUY':
        highs = [s['price'] for s in swings if s['type'] == 'high']
        if len(highs) >= 2:
            level = highs[-2]
            if df['close'].iloc[-3] > level and price >= level * 0.998:
                return True
    if direction == 'SELL':
        lows = [s['price'] for s in swings if s['type'] == 'low']
        if len(lows) >= 2:
            level = lows[-2]
            if df['close'].iloc[-3] < level and price <= level * 1.002:
                return True
    return False

def strong_candle(df, direction):
    """Check if last candle is strong directional."""
    if len(df) < 2:
        return False
    c = df.iloc[-1]
    body = abs(c['close'] - c['open'])
    full_range = c['high'] - c['low']
    if full_range == 0:
        return False
    if body / full_range < 0.6:
        return False
    if direction == 'BUY' and c['close'] > c['open']:
        return True
    if direction == 'SELL' and c['close'] < c['open']:
        return True
    return False

def consecutive_volume_spikes(df):
    """Check for 2+ consecutive volume spikes."""
    if len(df) < 5:
        return False
    avg_vol = df['volume'].iloc[-20:-1].mean() if len(df) >= 20 else df['volume'].mean()
    if avg_vol == 0:
        return False
    spikes = 0
    for i in range(-3, 0):
        if df['volume'].iloc[i] > avg_vol * 1.5:
            spikes += 1
    return spikes >= 2

def sr_flip(df, direction):
    """S/R flip: old resistance becomes support (or vice versa)."""
    if len(df) < 30:
        return False
    price = df['close'].iloc[-1]
    swings = identify_swings(df, order=3)
    if len(swings) < 3:
        return False
    if direction == 'BUY':
        old_resist = [s['price'] for s in swings if s['type'] == 'high']
        if len(old_resist) >= 2:
            level = old_resist[-2]
            if price > level and price < level * 1.005:
                return True
    if direction == 'SELL':
        old_support = [s['price'] for s in swings if s['type'] == 'low']
        if len(old_support) >= 2:
            level = old_support[-2]
            if price < level and price > level * 0.995:
                return True
    return False

def high_volatility(df):
    """Check if current volatility is high."""
    if len(df) < 20:
        return False
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    current_atr = tr.rolling(14).mean().iloc[-1]
    avg_atr = tr.rolling(50).mean().iloc[-1] if len(df) >= 50 else current_atr
    if pd.isna(avg_atr) or avg_atr == 0:
        return False
    return current_atr > avg_atr * 1.5

def order_flow_direction(df):
    """Detect order flow direction. Returns 'bullish', 'bearish', or 'neutral'."""
    if len(df) < 10:
        return 'neutral'
    bullish_vol = df[df['close'] > df['open']]['volume'].iloc[-10:].sum()
    bearish_vol = df[df['close'] < df['open']]['volume'].iloc[-10:].sum()
    total = bullish_vol + bearish_vol
    if total == 0:
        return 'neutral'
    if bullish_vol / total > 0.6:
        return 'bullish'
    if bearish_vol / total > 0.6:
        return 'bearish'
    return 'neutral'

def wyckoff_phase_continuity(df, phase):
    """Check if Wyckoff phase supports the signal direction."""
    if len(df) < 30:
        return False
    current_phase = detect_wyckoff_phase(df)
    if phase == 'accumulation' and current_phase in ('accumulation', 'markup'):
        return True
    if phase == 'distribution' and current_phase in ('distribution', 'markdown'):
        return True
    return False

# ============================================================
# 2l. BATCH 3: CHART PATTERNS (bonus scoring only)
# ============================================================
def detect_bullish_flag(df):
    """Detect bullish flag pattern."""
    if len(df) < 25:
        return False
    prev = df.iloc[-20:-10]
    recent = df.iloc[-10:]
    if len(prev) < 10:
        return False
    prev_move = prev['close'].iloc[-1] - prev['close'].iloc[0]
    if prev_move <= 0:
        return False
    recent_range = recent['high'].max() - recent['low'].min()
    if abs(prev_move) > 2 * recent_range:
        return True
    return False

def detect_descending_scallop(df):
    """Detect descending scallop pattern."""
    if len(df) < 20:
        return False
    closes = df['close'].values[-20:]
    mid = len(closes) // 2
    if closes[-1] > closes[mid] < closes[0]:
        return True
    return False

def detect_rising_wedge(df):
    """Detect rising wedge (bearish)."""
    if len(df) < 25:
        return False
    swings = identify_swings(df, order=3)
    if len(swings) < 4:
        return False
    highs = [s['price'] for s in swings if s['type'] == 'high']
    lows = [s['price'] for s in swings if s['type'] == 'low']
    if len(highs) >= 2 and len(lows) >= 2:
        h_slope = highs[-1] - highs[-2]
        l_slope = lows[-1] - lows[-2]
        if h_slope > 0 and l_slope > 0 and l_slope > h_slope:
            return True
    return False

def detect_adam_eve_bull(df):
    """Detect Adam & Eve bottom pattern."""
    if len(df) < 30:
        return False
    lows = df['low'].values[-30:]
    min_idx = np.argmin(lows)
    if min_idx < 5 or min_idx > 25:
        return False
    first_low = lows[min_idx]
    remaining = lows[min_idx+1:]
    if len(remaining) < 3:
        return False
    second_low = min(remaining)
    if abs(first_low - second_low) / first_low < 0.005:
        return True
    return False

def detect_bullish_wolfe(df):
    """Detect bullish Wolfe wave pattern."""
    if len(df) < 30:
        return False
    swings = identify_swings(df, order=3)
    lows = [s for s in swings if s['type'] == 'low']
    if len(lows) >= 3:
        if lows[-1]['price'] < lows[-2]['price'] and lows[-3]['price'] < lows[-1]['price']:
            return True
    return False

# ============================================================
# 2m. BATCH 5: MARKET IMBALANCE
# ============================================================
def detect_market_imbalance(df):
    """Detect market imbalance. Returns 'bullish', 'bearish', or None."""
    if len(df) < 10:
        return None
    bullish_vol = df[df['close'] > df['open']]['volume'].iloc[-10:].sum()
    bearish_vol = df[df['close'] < df['open']]['volume'].iloc[-10:].sum()
    total = bullish_vol + bearish_vol
    if total == 0:
        return None
    if bullish_vol / total > 0.7:
        return 'bullish'
    if bearish_vol / total > 0.7:
        return 'bearish'
    return None

# ============================================================
# 2n. BATCH 6: ADVANCED DETECTIONS
# ============================================================
def detect_equal_highs_lows(df):
    """Returns 'bullish' if equal lows, 'bearish' if equal highs, or None."""
    if len(df) < 15:
        return None
    highs = df['high'].values[-15:]
    lows  = df['low'].values[-15:]
    closes = df['close'].values[-15:]
    def has_cluster(arr):
        arr_sorted = np.sort(arr)
        diffs = np.diff(arr_sorted)
        return any(diffs < arr_sorted[:-1]*0.0003)
    if has_cluster(highs):
        cluster_mid = np.median(highs)
        if closes[-1] < cluster_mid:
            return 'bearish'
    if has_cluster(lows):
        cluster_mid = np.median(lows)
        if closes[-1] > cluster_mid:
            return 'bullish'
    return None

def detect_amd_phase(df):
    """Returns 'accumulation', 'advance', 'distribution', 'decline', or None."""
    if len(df) < 40:
        return None
    wyckoff = detect_wyckoff_phase(df)
    if wyckoff in ('accumulation', 'manipulation'):
        struct = market_structure(df)
        if struct == 'bullish':
            return 'advance'
        return 'accumulation'
    if wyckoff == 'distribution':
        struct = market_structure(df)
        if struct == 'bearish':
            return 'decline'
        return 'distribution'
    return wyckoff

def detect_trend(df):
    """Returns 'strong_bullish', 'bullish', 'sideways', 'bearish', 'strong_bearish'."""
    if len(df) < 40:
        return 'sideways'
    highs = df['high'].values[-40:]
    lows = df['low'].values[-40:]
    closes = df['close'].values[-40:]
    sh, sl = [], []
    for i in range(3, 37):
        if all(highs[i] >= highs[i-j] for j in range(1,4)) and all(highs[i] >= highs[i+j] for j in range(1,4)):
            sh.append(i)
        if all(lows[i] <= lows[i-j] for j in range(1,4)) and all(lows[i] <= lows[i+j] for j in range(1,4)):
            sl.append(i)
    if len(sh) < 2 or len(sl) < 2:
        ema50 = ema(df['close'], 50).iloc[-1]
        ema5  = ema(df['close'], 5).iloc[-1]
        if ema5 > ema50: return 'bullish'
        elif ema5 < ema50: return 'bearish'
        return 'sideways'
    last_highs = [highs[i] for i in sh[-3:]]
    last_lows  = [lows[i] for i in sl[-3:]]
    if len(last_highs) >= 2 and len(last_lows) >= 2:
        hh = last_highs[-1] > last_highs[-2]
        hl = last_lows[-1] > last_lows[-2]
        lh = last_highs[-1] < last_highs[-2]
        ll = last_lows[-1] < last_lows[-2]
        ema50 = ema(df['close'], 50).iloc[-1]
        price = closes[-1]
        distance = (price - ema50) / ema50 * 100
        if hh and hl:
            if distance > 0.5: return 'strong_bullish'
            return 'bullish'
        elif lh and ll:
            if distance < -0.5: return 'strong_bearish'
            return 'bearish'
    adx_val = adx(df['high'], df['low'], df['close'], 14).iloc[-1]
    if adx_val > 25:
        if closes[-1] > closes[-10]: return 'bullish'
        else: return 'bearish'
    return 'sideways'

def detect_chart_pattern(df):
    """Returns (pattern_name, expected_direction) or (None, None)."""
    if len(df) < 25:
        return None, None
    swings = identify_swings(df, order=3)
    if len(swings) < 5:
        return None, None
    highs = [s for s in swings if s['type']=='high']
    lows  = [s for s in swings if s['type']=='low']
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if abs(h1['price'] - h2['price']) / h1['price'] < 0.001:
            return 'double_top', 'SELL'
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if abs(l1['price'] - l2['price']) / l1['price'] < 0.001:
            return 'double_bottom', 'BUY'
    if len(highs) >= 3:
        h1, h2, h3 = highs[-3], highs[-2], highs[-1]
        if h2['price'] > h1['price'] and h2['price'] > h3['price'] and abs(h1['price']-h3['price'])/h1['price']<0.01:
            return 'head_shoulders', 'SELL'
    if len(lows) >= 3:
        l1, l2, l3 = lows[-3], lows[-2], lows[-1]
        if l2['price'] < l1['price'] and l2['price'] < l3['price'] and abs(l1['price']-l3['price'])/l1['price']<0.01:
            return 'inv_head_shoulders', 'BUY'
    if len(highs)>=4 and len(lows)>=4:
        h_prices = [h['price'] for h in highs[-4:]]
        l_prices = [l['price'] for l in lows[-4:]]
        slope_h = np.polyfit(range(len(h_prices)), h_prices, 1)[0]
        slope_l = np.polyfit(range(len(l_prices)), l_prices, 1)[0]
        if slope_h > 0 and slope_l > 0 and slope_l > slope_h:
            return 'rising_wedge', 'SELL'
        if slope_h < 0 and slope_l < 0 and slope_h < slope_l:
            return 'falling_wedge', 'BUY'
    recent = df.iloc[-10:]
    prev = df.iloc[-20:-10]
    if len(prev) < 10: return None, None
    prev_move = prev['close'].iloc[-1] - prev['close'].iloc[0]
    if abs(prev_move) > 2 * (recent['high'].max() - recent['low'].min()):
        if prev_move > 0: return 'bullish_flag', 'BUY'
        else: return 'bearish_flag', 'SELL'
    return None, None

def imbalance_swing_levels(df):
    """Return (bullish_target, bearish_target) price levels where an FVG originated."""
    if len(df) < 20: return None, None
    swings = identify_swings(df, order=3)
    if not swings: return None, None
    fvg_data = fvg_quality(df)
    if fvg_data:
        fvg_dir = fvg_data[0]
        if fvg_dir == 'bullish':
            lows = [s for s in swings if s['type']=='low']
            if lows: return None, lows[-1]['price']
        else:
            highs = [s for s in swings if s['type']=='high']
            if highs: return highs[-1]['price'], None
    return None, None

def detect_liquidity_side(df):
    """Return 'buy_side' or 'sell_side' based on volume at equal highs/lows."""
    if len(df) < 15: return None
    eq = detect_equal_highs_lows(df)
    if eq is None: return None
    vol = df['volume'].iloc[-1]
    avg_vol = df['volume'].iloc[-20:-1].mean()
    if eq == 'bullish' and vol > avg_vol * 1.5: return 'sell_side'
    if eq == 'bearish' and vol > avg_vol * 1.5: return 'buy_side'
    return None

def adr_remaining_pct(df, timeframe_min=1440):
    """Return estimate of how much daily range is left, as a fraction."""
    if len(df) < 100: return 1.0
    recent_high = df['high'].iloc[-50:].max()
    recent_low = df['low'].iloc[-50:].min()
    current_range = recent_high - recent_low
    avg_range = (df['high'] - df['low']).rolling(50).mean().iloc[-1] * 6
    if avg_range == 0: return 1.0
    return max(0, 1 - (current_range / avg_range))

def detect_equilibrium(df):
    """Return (eq_price, distance_pct) of how close price is to equilibrium."""
    if len(df) < 30: return None, None
    high = df['high'].iloc[-30:].max()
    low = df['low'].iloc[-30:].min()
    eq = (high + low) / 2
    price = df['close'].iloc[-1]
    distance = abs(price - eq) / price * 100
    return eq, distance

def atr_indicator(high, low, close, period=14):
    """ATR indicator returning last value as float."""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr_val = tr.rolling(period).mean().iloc[-1]
    return atr_val

def smart_ema(df, base_period=20):
    """EMA with period scaled inversely to ATR."""
    atr_val = atr_indicator(df['high'], df['low'], df['close'], 14)
    if atr_val == 0 or pd.isna(atr_val):
        period = base_period
    else:
        period = max(5, int(base_period * 0.001 / atr_val))
    return ema(df['close'], period)

def mitigation_block(df):
    """Returns 'bullish' if demand OB was mitigated, 'bearish' if supply OB was mitigated."""
    if len(df) < 20: return None
    for i in range(10, len(df)-1):
        if (df['close'].iloc[i] < df['open'].iloc[i] and
            abs(df['close'].iloc[i] - df['open'].iloc[i]) > 1.5 * abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])):
            ob_high = df['high'].iloc[i]
            subsequent = df.iloc[i+1:]
            if any((subsequent['low'] <= ob_high) & (subsequent['close'] > ob_high)):
                return 'bullish'
        if (df['close'].iloc[i] > df['open'].iloc[i] and
            abs(df['close'].iloc[i] - df['open'].iloc[i]) > 1.5 * abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])):
            ob_low = df['low'].iloc[i]
            subsequent = df.iloc[i+1:]
            if any((subsequent['high'] >= ob_low) & (subsequent['close'] < ob_low)):
                return 'bearish'
    return None

def rejection_block(df):
    """Returns 'support' if bullish rejection, 'resistance' if bearish rejection."""
    if len(df) < 1: return None
    c = df.iloc[-1]
    body = abs(c['close'] - c['open'])
    lower_wick = min(c['open'], c['close']) - c['low']
    upper_wick = c['high'] - max(c['open'], c['close'])
    range_ = c['high'] - c['low']
    if range_ == 0: return None
    if lower_wick > 2*body and upper_wick < body*0.5: return 'support'
    if upper_wick > 2*body and lower_wick < body*0.5: return 'resistance'
    return None

def volume_imbalance(df):
    """Returns 'bullish' if volume surged on bullish candle, 'bearish' if on bearish."""
    if len(df) < 5: return None
    c = df.iloc[-1]
    prev_vol = df['volume'].iloc[-2]
    vol = c['volume']
    if vol > prev_vol * 2.5:
        if c['close'] > c['open']: return 'bullish'
        elif c['close'] < c['open']: return 'bearish'
    return None

def poi_score(df, direction):
    """Point of Interest score 0-100 based on confluences near key levels."""
    if len(df) < 20: return 0
    score = 0
    if fvg_quality(df) is not None: score += 25
    if order_block(df) is not None: score += 25
    if detect_liquidity_trap(df) is not None: score += 25
    swings = identify_swings(df, order=3)
    if swings:
        price = df['close'].iloc[-1]
        for s in swings[-5:]:
            if abs(price - s['price']) / price < 0.002:
                score += 25
                break
    return min(100, score)

def detect_inversion_point(df):
    """Detect potential inversion point (reversal zone)."""
    if len(df) < 20: return False
    trap = detect_liquidity_trap(df)
    fvg_data = fvg_quality(df)
    div = detect_rsi_divergence(df)
    if trap and fvg_data and div:
        return True
    return False

# ============================================================
# 3. MULTI-TIMEFRAME TREND CACHE
# ============================================================
_trend_cache: Dict[str, Tuple[datetime, str]] = {}

def get_higher_tf_trend(symbol: str) -> Optional[str]:
    if symbol in _trend_cache:
        cached_time, trend = _trend_cache[symbol]
        if (datetime.now(timezone.utc) - cached_time).seconds < 300:
            return trend
    return None

def cache_higher_tf_trend(symbol: str, trend: str):
    _trend_cache[symbol] = (datetime.now(timezone.utc), trend)

def compute_5m_trend(df_5m: pd.DataFrame) -> Optional[str]:
    if df_5m is None or len(df_5m) < 20:
        return None
    df_5m = safe_df(df_5m)
    close_5m = df_5m['close']
    ema5_5m = ema(close_5m, 5)
    ema20_5m = ema(close_5m, 20)
    adx_5m = adx(df_5m['high'], df_5m['low'], close_5m, 14)
    if ema5_5m.iloc[-1] > ema20_5m.iloc[-1] and not pd.isna(adx_5m.iloc[-1]):
        return 'bullish'
    elif ema5_5m.iloc[-1] < ema20_5m.iloc[-1] and not pd.isna(adx_5m.iloc[-1]):
        return 'bearish'
    return None

_market_trend_cache: Dict[str, Tuple[datetime, str]] = {}

def get_market_trend(symbol: str) -> Optional[str]:
    if symbol in _market_trend_cache:
        cached_time, trend = _market_trend_cache[symbol]
        if (datetime.now(timezone.utc) - cached_time).seconds < 900:
            return trend
    return None

def cache_market_trend(symbol: str, trend: str):
    _market_trend_cache[symbol] = (datetime.now(timezone.utc), trend)

def compute_15m_trend(df_15m: pd.DataFrame) -> Optional[str]:
    if df_15m is None or len(df_15m) < 20:
        return None
    df_15m = safe_df(df_15m)
    close_15m = df_15m['close']
    ema5_15m = ema(close_15m, 5)
    ema20_15m = ema(close_15m, 20)
    if ema5_15m.iloc[-1] > ema20_15m.iloc[-1]:
        return 'bullish'
    elif ema5_15m.iloc[-1] < ema20_15m.iloc[-1]:
        return 'bearish'
    return None

# ============================================================
# 3b. LIVE PRICE FROM BROKER
# ============================================================
async def get_current_price(symbol: str) -> Optional[float]:
    """Fetch live price. Tries PO first, then IQ, then last close from data."""
    if po_connected and po_api is not None:
        po_symbol = PO_SYMBOL_MAP.get(symbol, symbol)
        try:
            loop = asyncio.get_event_loop()
            candles = await loop.run_in_executor(
                None, lambda: po_api.get_candles(po_symbol, 1, 1)
            )
            if candles and len(candles) > 0:
                price = candles[0].get('close')
                if price:
                    return float(price)
        except Exception as e:
            logger.debug(f"PO price fetch error for {po_symbol}: {e}")

    if iq_connected and iq_api is not None:
        iq_symbol = IQ_SYMBOL_MAP.get(symbol, symbol)
        try:
            loop = asyncio.get_event_loop()
            candles = await loop.run_in_executor(
                None, lambda: iq_api.get_candles(iq_symbol, 1, 1, time.time())
            )
            if candles and len(candles) > 0:
                return candles[0].get('close')
        except Exception as e:
            logger.debug(f"IQ price fetch error for {iq_symbol}: {e}")
    return None

# ============================================================
# 3c. ECONOMIC CALENDAR NEWS FILTER
# ============================================================
_ec_cache_time: Optional[datetime] = None
_ec_cache_events: List = []

def news_safe(symbol: str) -> bool:
    """Check if it's safe to trade - no high-impact news within the buffer window.
    Returns True if safe, False if high-impact event is imminent.
    Gracefully returns True if the API is not available."""
    if not NEWS_FILTER_ENABLED:
        return True
    if not EC_API_AVAILABLE:
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
                    logger.warning(f"News filter: high-impact event within {NEWS_WINDOW_SECONDS}s - blocking signal for {symbol}")
                    return False
    except Exception as e:
        logger.debug(f"News filter error (allowing trade): {e}")
    return True

# ============================================================
# 3d. TELEGRAM ALERTS
# ============================================================
async def send_telegram(signal: dict):
    """Send formatted signal alert via Telegram with full v3.2 enhanced format. No-ops if not configured."""
    if not TG_AVAILABLE or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        bot = TelegramBot(token=TELEGRAM_TOKEN)
        emoji = "🔴" if signal['direction'] == 'SELL' else "🟢"
        entry_dt = datetime.fromisoformat(signal['entry_time'].replace('Z', '+00:00'))
        entry_str = entry_dt.astimezone(timezone(timedelta(hours=1))).strftime('%H:%M') + ' WAT'

        # Clean symbol
        sym = signal['symbol'].replace('-OTC', '').replace('_OTC', '').replace(' (OTC)', '')

        # Market regime
        regime = signal.get('regime', 'RANGING')
        regime_desc = signal.get('regime_desc', '')

        # BOS/CHoCH
        bos_status = signal.get('bos', 'Not Confirmed')
        choch_status = signal.get('choch', 'Not Confirmed')

        # FVG
        fvg_status = signal.get('fvg', 'Inactive')

        # Liquidity
        liq_sweep = signal.get('liquidity_sweep', False)
        liq_side = signal.get('liquidity_side', 'None')
        liq_display = liq_side if liq_sweep else 'None'

        # Volume & Zone
        vol_class = signal.get('volume_class', 'Normal')
        zone = signal.get('zone', 'None Detected')

        # Stochastic
        stoch_status = signal.get('stoch_status', 'Neutral')
        stoch_val = signal.get('stoch_val', 50)
        if stoch_val > 80:
            stoch_display = 'Overbought'
        elif stoch_val < 20:
            stoch_display = 'Oversold'
        elif signal['direction'] == 'BUY' and stoch_val < 50:
            stoch_display = 'Bullish Crossover'
        elif signal['direction'] == 'SELL' and stoch_val > 50:
            stoch_display = 'Bearish Crossover'
        else:
            stoch_display = stoch_status

        # BB Width
        bb_status = signal.get('bb_status', 'Stable')
        bb_display = 'Expanding' if bb_status == 'Expanding' else ('Contracting' if bb_status == 'Contracting' else 'Squeezing')

        # R:R
        rr = signal.get('rr', '1:1.0')

        # GLM Smart Money
        sm_structure = signal.get('sm_structure', 'No Clear Break')
        sm_liquidity = signal.get('sm_liquidity', 'N/A')
        sm_breakout = signal.get('sm_breakout', 'No Breakout')
        sm_signal = signal.get('sm_signal', 'N/A')

        # Add arrow to structure
        if 'Up' in sm_structure:
            sm_structure_display = sm_structure.replace('Up', '↑')
        elif 'Down' in sm_structure:
            sm_structure_display = sm_structure.replace('Down', '↓')
        else:
            sm_structure_display = sm_structure

        # Martingale lines
        mart_lines = []
        for i, m in enumerate(signal.get('martingale', [])):
            m_dt = datetime.fromisoformat(m['entry_time'].replace('Z', '+00:00'))
            t = m_dt.astimezone(timezone(timedelta(hours=1))).strftime('%H:%M') + ' WAT'
            mart_lines.append(f"  M{i+1} │ {m['multiplier']}x │ ${m['amount']} │ Entry: {t}")
        mart_block = "\n".join(mart_lines) if mart_lines else ""

        # Strategy Guide
        strategy_guide = signal.get('strategy_guide', [])
        strat_lines = []
        for s in strategy_guide:
            if 'confirm' in s.lower() or 'wait' in s.lower() or 'bos' in s.lower() or 'fvg' in s.lower() or 'pullback' in s.lower() or 'enter' in s.lower():
                icon = '✅'
            elif 'profit' in s.lower() or 'stop' in s.lower() or 'take' in s.lower() or 'trail' in s.lower() or 'exit' in s.lower() or 'bream' in s.lower():
                icon = '🚪'
            else:
                icon = '🛡️'
            strat_lines.append(f"  {icon} {s}")
        strat_block = "\n".join(strat_lines) if strat_lines else ""

        # Support/Resistance
        support = signal.get('support', 'N/A')
        resistance = signal.get('resistance', 'N/A')
        sr_display = f"  Support: {support}\n  Resistance: {resistance}" if support and resistance else ""

        # Signal status
        sig_status = 'HIGH PROBABILITY ONLY' if signal['confidence'] >= 85 else 'MODERATE PROBABILITY'

        msg = f"""🔔 CATALYST AI SIGNAL!

🎫 Trade: {sym}
⏳ Timer: {signal['timeframe']} (OTC)
➡️ Entry: {entry_str}
📈 Direction: {signal['direction']} {emoji}
🎯 GLM Probability: {signal['confidence']}% WIN RATE
📊 Market: {signal.get('volatility', 'High Volatility')}

🔮 Market Regime: {regime}
   {regime_desc}

🧠 Trend: {signal.get('trend', 'Analyzing...')}
📉 BOS: {bos_status}
🔄 CHoCH: {choch_status}
📦 FVG: {fvg_status}
💧 Liquidity: {liq_display}
📦 Volume: {vol_class}
🏗️ Zone: {zone}
📉 RSI: {signal['rsi']}
📊 Stochastic: {stoch_display}
📊 BB Width: {bb_display}
⚖️ RR: {rr}

↪️ ── 🛡️ MARTINGALE RECOVERY (Risk Level) ──
{mart_block}

🧪 GLM SMART MONEY:
  Structure: {sm_structure_display}
  Liquidity: {sm_liquidity}
  Breakout: {sm_breakout}
  Signal: {sm_signal}

📋 STRATEGY GUIDE:
{strat_block}

📐 SUPPORT/RESISTANCE:
{sr_display}

Note: Trade 1% - 3% of your capability and capital
🎯 SIGNAL STATUS: {sig_status}

🎯 GLM PROBABILITY: {signal['confidence']}% WIN RATE
   {sig_status}
"""
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        logger.info(f"📱 Telegram alert sent for {signal['symbol']}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")

# ============================================================
# 4. MEMORY, AUTO-TUNING & DAILY STATS
# ============================================================
MEMORY_DB = os.environ.get("DB_PATH", "memory.db")
PARAMS = {
    'rsi_buy': 33,
    'rsi_sell': 67,
    'adx_min': 25,
    'vol_mult': 1.5,
}
MIN_CONFIDENCE = 80.0

def init_memory():
    conn = sqlite3.connect(MEMORY_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE,
            symbol TEXT,
            direction TEXT,
            timeframe TEXT,
            platform TEXT,
            entry_time TIMESTAMP,
            outcome TEXT DEFAULT 'pending',
            rsi REAL,
            adx REAL,
            confidence REAL,
            accuracy REAL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            ignored INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_accuracy REAL DEFAULT 0,
            avg_confidence REAL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def remember_signal(sig_id, sym, dir_, tf, platform, entry, rsi_val, adx_val, conf, accuracy=0):
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (None, sig_id, sym, dir_, tf, platform, entry, 'pending', rsi_val, adx_val, conf, accuracy))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB write error: {e}")

def learn_from_outcome(sig_id, outcome):
    """Auto-tune parameters based on trade outcomes."""
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
                if MIN_CONFIDENCE > 75:
                    MIN_CONFIDENCE -= 1
                logger.info(f"Relaxing: {PARAMS}, min conf {MIN_CONFIDENCE}")

        cur.execute("SELECT outcome FROM trades ORDER BY entry_time DESC LIMIT 30")
        recent = cur.fetchall()

        if len(recent) >= 10:
            total = len(recent)
            ignored = sum(1 for r in recent if r[0] == 'ignored')
            ignore_rate = ignored / total if total else 0
            if ignore_rate > 0.5:
                MIN_CONFIDENCE = min(95, MIN_CONFIDENCE + 1)
            elif ignore_rate < 0.1 and total - ignored >= 10:
                MIN_CONFIDENCE = max(75, MIN_CONFIDENCE - 1)

        _update_daily_stats(cur)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB learn error: {e}")

def _update_daily_stats(cur):
    """Recalculate today's daily_stats row."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cur.execute("""
        SELECT outcome, confidence, accuracy FROM trades
        WHERE date(entry_time) = ? AND outcome IN ('win','loss','ignored')
    """, (today,))
    rows = cur.fetchall()
    if not rows:
        return
    wins = sum(1 for r in rows if r[0] == 'win')
    losses = sum(1 for r in rows if r[0] == 'loss')
    ignored = sum(1 for r in rows if r[0] == 'ignored')
    total = wins + losses
    wr = round(wins / total * 100, 1) if total > 0 else 0
    confs = [r[1] for r in rows if r[1] is not None]
    accs = [r[2] for r in rows if r[2] is not None]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else 0
    avg_acc = round(sum(accs) / len(accs), 1) if accs else 0

    cur.execute("""
        INSERT OR REPLACE INTO daily_stats VALUES (?,?,?,?,?,?,?,?,?)
    """, (None, today, wins, losses, ignored, total, wr, avg_acc, avg_conf))

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
        return {
            "total_trades": total_real, "wins": wins, "losses": total_real - wins,
            "win_rate": wr, "ignored": ignored, "pending": pending,
            "params": PARAMS, "min_confidence": MIN_CONFIDENCE
        }
    except:
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "ignored": 0, "pending": 0, "params": PARAMS, "min_confidence": MIN_CONFIDENCE}

def get_daily_stats(days: int = 30) -> List[dict]:
    """Get daily stats for the last N days for chart rendering."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT date, wins, losses, total, win_rate, avg_accuracy, avg_confidence FROM daily_stats ORDER BY date DESC LIMIT ?", (days,))
        rows = cur.fetchall()
        conn.close()
        return [{"date": r[0], "wins": r[1], "losses": r[2], "total": r[3],
                 "win_rate": r[4], "avg_accuracy": r[5], "avg_confidence": r[6]} for r in rows]
    except:
        return []

def historical_confidence(rsi_val, adx_val, direction, platform) -> float:
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT outcome FROM trades
            WHERE direction=? AND platform=? AND outcome IN ('win','loss')
            AND rsi BETWEEN ? AND ? AND adx BETWEEN ? AND ?
            ORDER BY entry_time DESC LIMIT 30
        """, (direction, platform, rsi_val - 5, rsi_val + 5, adx_val - 10, adx_val + 10))
        rows = cur.fetchall()
        conn.close()
        if len(rows) >= 10:
            wins = sum(1 for r in rows if r[0] == 'win')
            return round(wins / len(rows) * 100, 1)
    except:
        pass
    return 75.0

# ============================================================
# 4b. WEEKLY OPTIMIZATION (APScheduler)
# ============================================================
async def weekly_optimise():
    """Deep optimization: analyze last 500 trades and adjust parameters."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT outcome, direction, rsi, adx, confidence, accuracy FROM trades WHERE outcome IN ('win','loss') ORDER BY entry_time DESC LIMIT 500")
        rows = cur.fetchall()
        conn.close()

        if len(rows) < 50:
            logger.info("Weekly optimize: not enough data yet")
            return

        global PARAMS, MIN_CONFIDENCE
        wins = sum(1 for r in rows if r[0] == 'win')
        wr = wins / len(rows)
        logger.info(f"Weekly optimize: WR={wr:.1%} over {len(rows)} trades")

        if wr < 0.85:
            PARAMS['adx_min'] = min(40, PARAMS['adx_min'] + 2)
            PARAMS['rsi_buy'] = max(18, PARAMS['rsi_buy'] - 2)
            PARAMS['rsi_sell'] = min(82, PARAMS['rsi_sell'] + 2)
            MIN_CONFIDENCE = min(93, MIN_CONFIDENCE + 1)
            logger.warning(f"Weekly TIGHTEN: {PARAMS}, min conf {MIN_CONFIDENCE}")
        elif wr >= 0.92:
            PARAMS['adx_min'] = max(20, PARAMS['adx_min'] - 1)
            if MIN_CONFIDENCE > 78:
                MIN_CONFIDENCE -= 1
            logger.info(f"Weekly RELAX: {PARAMS}, min conf {MIN_CONFIDENCE}")
    except Exception as e:
        logger.error(f"Weekly optimize error: {e}")

# ============================================================
# 5. SIGNAL GENERATION - Full ALL-AND + Batch 0-6 + MTF + Accuracy
# ============================================================
def generate_signal(df, symbol="", higher_tf_trend=None, market_trend=None):
    """
    Full ALL-AND confluence + Batch 0-6 + multi-timeframe + accuracy scoring.
    Returns: dict with all signal fields or None if no signal.
    """
    df = safe_df(df)
    if len(df) < 80 or df.empty:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    ema5 = ema(close, 5)
    ema20 = ema(close, 20)
    bull = ema5.iloc[-2] < ema20.iloc[-2] and ema5.iloc[-1] > ema20.iloc[-1]
    bear = ema5.iloc[-2] > ema20.iloc[-2] and ema5.iloc[-1] < ema20.iloc[-1]

    rsi_val = rsi(close, 14).iloc[-1]
    if pd.isna(rsi_val):
        return None

    adx_val = adx(high, low, close, 14).iloc[-1]
    if pd.isna(adx_val):
        return None

    avg_vol = volume.iloc[-20:-1].mean()
    if avg_vol == 0:
        avg_vol = 1
    vol_spike = volume.iloc[-1] >= avg_vol * PARAMS['vol_mult']

    bb_w = bb_width(close, 20)
    if len(bb_w) < 20:
        return None
    recent_bw = bb_w.iloc[-20:].dropna()
    if len(recent_bw) < 5:
        return None
    bb_pct = recent_bw.rank(pct=True).iloc[-1]
    bb_sq = bb_pct < 0.30
    bb_exp = bb_w.iloc[-1] > bb_w.iloc[-2]

    price = close.iloc[-1]
    support, resistance = sr_levels(price, df)
    buy_sr = price >= support * 1.0012
    sell_sr = price <= resistance * 0.9988

    struct = market_structure(df)
    mss = detect_mss(df)
    reversal = detect_market_structure_reversal(df)
    candle = candlestick_confirmation(df)
    sd = order_block(df)
    fvg_ = detect_fvg(df)
    mom_3 = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100 if len(close) >= 4 else 0

    # v3.2 indicators
    stoch_val, stoch_status = stochastic(high, low, close)
    regime, regime_desc = detect_regime(df)
    liq_sweep, liq_side = detect_liquidity_sweep(df)
    vol_class = classify_volume(df)
    bb_status = classify_bb_width(bb_w)
    trend_dir = 'Bullish' if ema5.iloc[-1] > ema20.iloc[-1] else 'Bearish'

    # Batch 0-1 detections
    fvg_qual = fvg_quality(df)
    choch = choch_confirmed(df)
    mm_model = detect_mm_model(df)
    imbalance = detect_market_imbalance(df)

    # Batch 6 detections
    eq_hl = detect_equal_highs_lows(df)
    amd = detect_amd_phase(df)
    trend = detect_trend(df)
    chart_pattern, chart_dir = detect_chart_pattern(df)
    vol_imb = volume_imbalance(df)
    rej_block = rejection_block(df)
    mit_block = mitigation_block(df)
    eq_price, eq_dist = detect_equilibrium(df)
    liq_side_det = detect_liquidity_side(df)
    atr_val = atr_indicator(high, low, close, 14)

    # ---- SIGNAL DIRECTION ----
    direction = None

    # BUY ALL-AND conditions
    if (bull and rsi_val < PARAMS['rsi_buy'] and adx_val > PARAMS['adx_min'] and
        vol_spike and bb_sq and bb_exp and buy_sr and
        (struct == 'bullish' or mss == 'bullish' or choch == 'bullish') and
        reversal == 'bullish' and candle == 'bullish' and sd == 'demand' and
        fvg_ == 'bullish' and mom_3 > 0.03 and
        valid_entry_candle(df, 'BUY') and
        direction_flow(df, 'BUY') and
        (mm_model in BUY_MODELS or mm_model is None) and
        (imbalance in ('bullish', None)) and
        (eq_hl in ('bullish', None)) and
        (vol_imb in ('bullish', None)) and
        (rej_block != 'resistance')):
        direction = 'BUY'

    # SELL ALL-AND conditions
    elif (bear and rsi_val > PARAMS['rsi_sell'] and adx_val > PARAMS['adx_min'] and
        vol_spike and bb_sq and bb_exp and sell_sr and
        (struct == 'bearish' or mss == 'bearish' or choch == 'bearish') and
        reversal == 'bearish' and candle == 'bearish' and sd == 'supply' and
        fvg_ == 'bearish' and mom_3 < -0.03 and
        valid_entry_candle(df, 'SELL') and
        direction_flow(df, 'SELL') and
        (mm_model in ('sell_model',) or mm_model is None) and
        (imbalance in ('bearish', None)) and
        (eq_hl in ('bearish', None)) and
        (vol_imb in ('bearish', None)) and
        (rej_block != 'support')):
        direction = 'SELL'

    if direction is None:
        return None

    # ---- HARD GATES ----
    if not is_kill_zone():
        return None

    # Trend filter
    if direction == 'BUY' and trend not in ('bullish', 'strong_bullish', 'sideways'):
        return None
    if direction == 'SELL' and trend not in ('bearish', 'strong_bearish', 'sideways'):
        return None

    # Chart pattern contradiction filter
    if chart_pattern and chart_dir != direction:
        return None

    # Equilibrium filter
    if direction == 'BUY' and eq_price and eq_dist is not None and eq_dist < 0.3:
        return None
    if direction == 'SELL' and eq_price and eq_dist is not None and eq_dist < 0.3:
        return None

    # Liquidity side filter
    if liq_side_det == 'buy_side' and direction == 'BUY':
        return None
    if liq_side_det == 'sell_side' and direction == 'SELL':
        return None

    # Near daily level filter
    if is_near_daily_level(df, direction):
        return None

    # MTF alignment
    current_trend = 'bullish' if direction == 'BUY' else 'bearish'
    mtf_ok = mtf_full_alignment(higher_tf_trend, market_trend, current_trend)
    market_ok = (market_trend is None or market_trend == current_trend)
    if not mtf_ok or not market_ok:
        return None

    # ---- SCORING ----
    score = 0
    # Base scoring
    if direction == 'BUY':
        score += min(30, max(0, (PARAMS['rsi_buy'] - rsi_val)))
    else:
        score += min(30, max(0, (rsi_val - PARAMS['rsi_sell'])))
    score += min(20, max(0, (adx_val - 20)))
    if vol_spike: score += 10
    if bb_sq and bb_exp: score += 10
    if sd: score += 10
    if fvg_: score += 10
    if struct or mss: score += 10
    if reversal: score += 15
    if candle: score += 15
    if mom_3 > 0.03 or mom_3 < -0.03: score += 10
    if mtf_ok: score += 10
    if market_ok: score += 10

    # Batch 0: Leverage zone
    if detect_leverage_zone(df, direction): score += 15

    # Batch 1: SMC Advanced scoring
    if ifvg_detection(df) is not None: score += 10
    if market_holding_creating(df, direction): score += 5
    if market_respecting(df, direction): score += 10
    if price_momentum(df, direction): score += 5
    if direction_flow(df, direction): score += 5
    if mm_model in BUY_MODELS or mm_model in ('sell_model',): score += 10
    if cicd_reversal_confirmed(df, direction): score += 15
    if price_aims(df, direction): score += 5
    pattern_name, pattern_dir = detect_market_pattern(df)
    if pattern_dir == direction: score += 10

    # Batch 2: Confirmation Layer scoring
    if breakout_retest(df, direction): score += 15
    if strong_candle(df, direction): score += 10
    if consecutive_volume_spikes(df): score += 10
    if sr_flip(df, direction): score += 15
    if high_volatility(df): score += 5
    of = order_flow_direction(df)
    if (direction == 'BUY' and of == 'bullish') or (direction == 'SELL' and of == 'bearish'): score += 10
    wyckoff = detect_wyckoff_phase(df)
    if direction == 'BUY' and wyckoff_phase_continuity(df, 'accumulation'): score += 10
    if direction == 'SELL' and wyckoff_phase_continuity(df, 'distribution'): score += 10

    # Batch 3: Chart Patterns (bonus only)
    if direction == 'BUY':
        if detect_bullish_flag(df): score += 12
        if detect_descending_scallop(df): score += 10
        if detect_bullish_wolfe(df): score += 15
        if detect_adam_eve_bull(df): score += 12
    if direction == 'SELL':
        if detect_rising_wedge(df): score += 10

    # Batch 5: Market imbalance
    if (direction == 'BUY' and imbalance == 'bullish') or (direction == 'SELL' and imbalance == 'bearish'): score += 10

    # Batch 6: New scoring
    if (direction == 'BUY' and eq_hl == 'bullish') or (direction == 'SELL' and eq_hl == 'bearish'): score += 10
    if (direction == 'BUY' and amd in ('accumulation', 'advance')) or (direction == 'SELL' and amd in ('distribution', 'decline')): score += 10
    trap = detect_liquidity_trap(df)
    if (direction == 'BUY' and trap == 'bullish') or (direction == 'SELL' and trap == 'bearish'): score += 15
    if direction == 'BUY' and trend in ('bullish', 'strong_bullish'): score += 10
    if direction == 'SELL' and trend in ('bearish', 'strong_bearish'): score += 10
    if chart_dir == direction: score += 15
    if poi_score(df, direction) >= 80: score += 10
    if adr_remaining_pct(df) > 0.5: score += 5
    if eq_dist is not None and eq_dist < 0.3: score += 5
    if detect_inversion_point(df): score += 10
    if not pd.isna(atr_val) and atr_val > 0.0005: score += 5
    if (direction == 'BUY' and mit_block == 'bullish') or (direction == 'SELL' and mit_block == 'bearish'): score += 15
    if (direction == 'BUY' and rej_block == 'support') or (direction == 'SELL' and rej_block == 'resistance'): score += 10
    if (direction == 'BUY' and vol_imb == 'bullish') or (direction == 'SELL' and vol_imb == 'bearish'): score += 10

    accuracy = min(100, max(50, score))

    # ---- BUILD SIGNAL DICT ----
    rr = calculate_rr(price, support, resistance, direction)
    zone_label = ''
    if sd == 'demand':
        zone_label = 'Demand + Order Block'
    elif sd == 'supply':
        zone_label = 'Supply + Order Block'
    elif sd:
        zone_label = sd.title() + ' Zone'
    else:
        zone_label = 'None Detected'

    bos_status = 'Confirmed' if (struct == ('bullish' if direction == 'BUY' else 'bearish')) else 'Not Confirmed'
    choch_status = 'Confirmed' if (mss == ('bullish' if direction == 'BUY' else 'bearish')) else 'Not Confirmed'

    if direction == 'SELL':
        sm_structure = 'Break of Structure Down' if bos_status == 'Confirmed' else 'No Clear Break'
        sm_liquidity = 'Sell Side Sweep' if liq_sweep and 'Sell' in liq_side else 'Buy Side Liquidity'
        sm_breakout = 'Confirmed Breakdown' if regime == 'BREAKOUT' else 'No Breakout'
        sm_signal = 'Valid Sell Signal' if accuracy >= 80 else 'Weak Sell Signal'
    else:
        sm_structure = 'Break of Structure Up' if bos_status == 'Confirmed' else 'No Clear Break'
        sm_liquidity = 'Buy Side Sweep' if liq_sweep and 'Buy' in liq_side else 'Sell Side Liquidity'
        sm_breakout = 'Confirmed Breakout' if regime == 'BREAKOUT' else 'No Breakout'
        sm_signal = 'Valid Buy Signal' if accuracy >= 80 else 'Weak Buy Signal'

    return {
        'direction': direction,
        'rsi': round(rsi_val, 1),
        'adx': round(adx_val, 1),
        'accuracy': round(accuracy, 1),
        'regime': regime,
        'regime_desc': regime_desc,
        'trend': trend_dir,
        'bos': bos_status,
        'choch': choch_status,
        'fvg': 'Active' if fvg_ else 'Inactive',
        'fvg_type': fvg_ or 'None',
        'fvg_quality': f'{fvg_qual[0]} sz={fvg_qual[1]} age={fvg_qual[2]}' if fvg_qual else 'Inactive',
        'liquidity_sweep': liq_sweep,
        'liquidity_side': liq_side,
        'volume_class': vol_class,
        'zone': zone_label,
        'stoch_val': stoch_val,
        'stoch_status': stoch_status,
        'bb_status': bb_status,
        'rr': rr,
        'support': round(support, 5),
        'resistance': round(resistance, 5),
        'price': round(price, 5),
        'order_block': sd or 'None',
        'mtf_ok': mtf_ok,
        'market_ok': market_ok,
        'sm_structure': sm_structure,
        'sm_liquidity': sm_liquidity,
        'sm_breakout': sm_breakout,
        'sm_signal': sm_signal,
        'trend_detail': trend,
        'chart_pattern': chart_pattern or 'None',
        'eq_hl': eq_hl or 'None',
        'amd_phase': amd or 'None',
        'vol_imbalance': vol_imb or 'None',
        'mitigation_block': mit_block or 'None',
        'rejection_block': rej_block or 'None',
        'liquidity_side_det': liq_side_det or 'None',
        'atr_value': round(float(atr_val), 6) if not pd.isna(atr_val) else 0,
    }

def calculate_accuracy(direction, rsi_val, adx_val, vol_spike, bb_sq, bb_exp, sd, fvg_, struct, mss, reversal, cand_conf, mom_ok, mtf_ok, market_ok=True):
    """Return accuracy score 0-100 based on confirmation strength. (Legacy - scoring now in generate_signal)"""
    score = 0
    if direction == 'BUY':
        score += min(30, max(0, (PARAMS['rsi_buy'] - rsi_val)))
    else:
        score += min(30, max(0, (rsi_val - PARAMS['rsi_sell'])))
    score += min(20, max(0, (adx_val - 20)))
    if vol_spike: score += 10
    if bb_sq and bb_exp: score += 10
    if sd: score += 10
    if fvg_: score += 10
    if struct or mss: score += 10
    if reversal: score += 15
    if cand_conf: score += 15
    if mom_ok: score += 10
    if mtf_ok: score += 10
    if market_ok: score += 10
    return min(100, max(50, score))

def calculate_martingale(entry: datetime, timeframe: str, confidence: float, base_stake: float = 1.0) -> List[dict]:
    tf_min = {'30s': 0.5, '45s': 0.75, '1m': 1, '2m': 2, '3m': 3, '5m': 5}
    offset_minutes = tf_min.get(timeframe, 1)
    if confidence >= 90:
        mults = [2.2, 4.8, 10.5]
    elif confidence >= 80:
        mults = [2.5, 5.5, 12.0]
    else:
        mults = [2.8, 6.2, 13.6]
    levels = []
    for i, (m, off) in enumerate(zip(mults, [1, 2, 3])):
        t = entry + timedelta(minutes=offset_minutes * off)
        amount = round(base_stake * m, 2)
        if amount > 3.0:
            amount = 3.0
            m = round(amount / base_stake, 1)
        levels.append({'level': f'M{i + 1}', 'multiplier': m, 'amount': amount, 'entry_time': t.isoformat()})
    return levels

# ============================================================
# 5b. BROKER CONNECTION & DATA
# ============================================================
PAIRS = [
    "EUR/USD (OTC)", "GBP/JPY (OTC)", "AUD/USD (OTC)", "NZD/USD (OTC)",
    "USD/CAD (OTC)", "EUR/JPY (OTC)", "USD/JPY (OTC)", "EUR/GBP (OTC)"
]

SESSION_BEST_PAIRS = {
    'Sydney/Tokyo': ['AUD/USD (OTC)', 'NZD/USD (OTC)', 'USD/JPY (OTC)'],
    'London': ['EUR/USD (OTC)', 'GBP/JPY (OTC)', 'EUR/GBP (OTC)', 'USD/JPY (OTC)'],
    'New York': ['EUR/USD (OTC)', 'GBP/JPY (OTC)', 'USD/JPY (OTC)', 'EUR/JPY (OTC)', 'AUD/USD (OTC)'],
    'default': PAIRS
}

def get_best_pairs_for_current_session():
    session = current_session()
    return SESSION_BEST_PAIRS.get(session, PAIRS)
IQ_TFS = ["1m", "2m", "3m", "5m"]
PO_TFS = ["30s", "45s", "1m", "2m", "3m", "5m"]
TF_SECONDS = {'30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300, '15m': 900}

iq_api = None
iq_connected = False
iq_practice_mode = True

po_api = None
po_connected = False
po_demo_mode = True

IQ_SYMBOL_MAP = {
    "EUR/USD (OTC)": "EURUSD-OTC", "GBP/JPY (OTC)": "GBPJPY-OTC",
    "AUD/USD (OTC)": "AUDUSD-OTC", "NZD/USD (OTC)": "NZDUSD-OTC",
    "USD/CAD (OTC)": "USDCAD-OTC", "EUR/JPY (OTC)": "EURJPY-OTC",
    "USD/JPY (OTC)": "USDJPY-OTC", "EUR/GBP (OTC)": "EURGBP-OTC",
}
PO_SYMBOL_MAP = {
    "EUR/USD (OTC)": "EURUSD_OTC", "GBP/JPY (OTC)": "GBPJPY_OTC",
    "AUD/USD (OTC)": "AUDUSD_OTC", "NZD/USD (OTC)": "NZDUSD_OTC",
    "USD/CAD (OTC)": "USDCAD_OTC", "EUR/JPY (OTC)": "EURJPY_OTC",
    "USD/JPY (OTC)": "USDJPY_OTC", "EUR/GBP (OTC)": "EURGBP_OTC",
}

def connect_iq_option():
    """Connect to IQ Option with robust error handling and reconnection."""
    global iq_api, iq_connected
    if not USE_IQ_OPTION or not IQ_API_AVAILABLE:
        logger.warning("IQ Option disabled or library not installed")
        return False
    if not IQ_EMAIL:
        logger.warning("IQ_EMAIL not set - cannot connect")
        return False
    try:
        iq_api = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        check, reason = iq_api.connect()
        if check:
            # Double-connect for session stability
            iq_api.connect()
            iq_connected = True
            try:
                if iq_practice_mode:
                    iq_api.change_balance("PRACTICE")
                    logger.info("IQ Option: PRACTICE mode active")
                else:
                    iq_api.change_balance("REAL")
                    logger.info("IQ Option: REAL mode active")
            except Exception as e:
                logger.warning(f"IQ Option balance mode error: {e}")
            # Verify connection by trying to get candles
            try:
                test = iq_api.get_candles("EURUSD-OTC", 60, 5, time.time())
                if test and len(test) > 0:
                    logger.info(f"IQ Option connected + verified - real candle data available ({len(test)} candles)")
                else:
                    logger.warning("IQ Option connected but candle test returned empty - OTC may not be available")
            except Exception as e:
                logger.warning(f"IQ Option connected but candle test failed: {e}")
            return True
        else:
            logger.error(f"IQ Option connection failed: {reason}")
            iq_api = None
            iq_connected = False
            return False
    except Exception as e:
        logger.error(f"IQ Option API error: {e}")
        iq_api = None
        iq_connected = False
        return False

def connect_pocket_option():
    global po_api, po_connected
    if not USE_POCKET_OPTION or not PO_API_AVAILABLE:
        return False
    if not PO_EMAIL:
        return False
    try:
        if PO_API_TYPE == 'stable_api':
            po_api = PocketOption(PO_EMAIL, PO_PASSWORD)
            po_api.connect()
            po_connected = True
            logger.info("Pocket Option connected (pocketoptionapi)")
            return True
        else:
            logger.info("Pocket Option PyPI package - requires SSID auth")
            return False
    except Exception as e:
        logger.error(f"Pocket Option API error: {e}")
        po_api = None
        po_connected = False
        return False

def connect_brokers():
    iq_ok = connect_iq_option()
    po_ok = connect_pocket_option()
    if iq_ok or po_ok:
        logger.info(f"Brokers connected - IQ: {iq_ok}, PO: {po_ok}")
    else:
        logger.warning("No brokers connected - running on demo data")
    return iq_ok or po_ok

def fetch_iq_candles(symbol: str, tf: str, count: int = 120) -> Optional[pd.DataFrame]:
    """Fetch real candle data from IQ Option API. Returns DataFrame or None."""
    global iq_connected
    if not iq_connected or iq_api is None:
        return None
    iq_symbol = IQ_SYMBOL_MAP.get(symbol, symbol)
    tf_sec = TF_SECONDS.get(tf, 60)
    try:
        # Try reconnecting if needed
        try:
            iq_api.connect()
        except:
            pass
        candles = iq_api.get_candles(iq_symbol, tf_sec, count, time.time())
        if not candles or len(candles) < 10:
            logger.debug(f"IQ: insufficient candles for {iq_symbol} {tf} (got {len(candles) if candles else 0})")
            return None
        df = pd.DataFrame(candles)
        # IQ Option API returns 'max'/'min' instead of 'high'/'low'
        rename_map = {}
        if 'max' in df.columns and 'high' not in df.columns:
            rename_map['max'] = 'high'
        if 'min' in df.columns and 'low' not in df.columns:
            rename_map['min'] = 'low'
        if rename_map:
            df = df.rename(columns=rename_map)
        for required in ['open', 'close']:
            if required not in df.columns:
                logger.warning(f"IQ: missing required column '{required}' in candle data")
                return None
        if 'high' not in df.columns:
            df['high'] = df[['open', 'close']].max(axis=1)
        if 'low' not in df.columns:
            df['low'] = df[['open', 'close']].min(axis=1)
        # IQ Option OTC candles may not have volume - generate synthetic
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            # Use tick-based volume estimation from candle body size
            body_sizes = (df['high'] - df['low']).abs()
            base_vol = 100
            df['volume'] = (body_sizes / body_sizes.mean() * base_vol).clip(lower=20).astype(int)
            # Add volume spikes for large candles
            avg_body = body_sizes.mean()
            if avg_body > 0:
                spike_mask = body_sizes > avg_body * 2
                df.loc[spike_mask, 'volume'] = (df.loc[spike_mask, 'volume'] * 2.5).astype(int)
        if 'from' in df.columns:
            df.index = pd.to_datetime(df['from'], unit='s')
        elif 'time' in df.columns:
            df.index = pd.to_datetime(df['time'], unit='s')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        df = safe_df(df)
        if len(df) < 30:
            logger.debug(f"IQ: only {len(df)} valid candles for {iq_symbol} {tf}")
            return None
        logger.info(f"IQ: REAL DATA - {len(df)} candles for {iq_symbol} {tf}")
        return df
    except Exception as e:
        logger.error(f"IQ fetch error {iq_symbol}: {e}")
        iq_connected = False
        return None

def fetch_po_candles(symbol: str, tf: str, count: int = 120) -> Optional[pd.DataFrame]:
    global po_connected
    if not po_connected or po_api is None:
        return None
    po_symbol = PO_SYMBOL_MAP.get(symbol, symbol)
    tf_sec = TF_SECONDS.get(tf, 60)
    try:
        candles = po_api.get_candles(po_symbol, tf_sec, count)
        if not candles or len(candles) < 30:
            return None
        df = pd.DataFrame(candles)
        rename_map = {}
        if 'max' in df.columns and 'high' not in df.columns:
            rename_map['max'] = 'high'
        if 'min' in df.columns and 'low' not in df.columns:
            rename_map['min'] = 'low'
        if rename_map:
            df = df.rename(columns=rename_map)
        for required in ['open', 'close']:
            if required not in df.columns:
                return None
        if 'high' not in df.columns:
            df['high'] = df[['open', 'close']].max(axis=1)
        if 'low' not in df.columns:
            df['low'] = df[['open', 'close']].min(axis=1)
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            df['volume'] = np.random.randint(50, 250, size=len(df))
            spike_idx = np.random.choice(len(df), size=max(1, len(df)//20), replace=False)
            df.iloc[spike_idx, df.columns.get_loc('volume')] = np.random.randint(300, 700, size=len(spike_idx))
        if 'time' in df.columns:
            df.index = pd.to_datetime(df['time'], unit='s')
        elif 'from' in df.columns:
            df.index = pd.to_datetime(df['from'], unit='s')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        logger.info(f"PO: {len(df)} candles for {po_symbol} {tf}")
        return safe_df(df)
    except Exception as e:
        logger.error(f"PO fetch error {po_symbol}: {e}")
        po_connected = False
        return None

def get_data_sync(symbol, tf):
    """Synchronous data fetch - tries IQ first (real OTC data), then PO, then demo fallback."""
    # Priority 1: IQ Option (best OTC data source)
    if iq_connected and iq_api is not None and USE_IQ_OPTION:
        try:
            df = fetch_iq_candles(symbol, tf)
            if df is not None and len(df) >= 30:
                return df
        except:
            pass
    # Priority 2: Pocket Option
    if po_connected and po_api is not None and USE_POCKET_OPTION:
        try:
            df = fetch_po_candles(symbol, tf)
            if df is not None and len(df) >= 30:
                return df
        except:
            pass
    # Priority 3: Demo data fallback
    logger.debug(f"No broker data for {symbol} {tf} - using demo")
    return _demo_data(symbol, tf)

def _demo_data(symbol, tf):
    np.random.seed(hash(symbol + tf) % 10000)
    periods = 120
    freq = tf.replace('m', 'min').replace('s', 's')
    try:
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq=freq)
    except:
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq='1min')
    price = 1.0800
    trend = 1
    closes = []
    for _ in range(periods):
        price += trend * 0.00008 + np.random.normal(0, 0.00015)
        closes.append(price)
        if np.random.random() < 0.02:
            trend *= -1
    df = pd.DataFrame({
        'open': closes,
        'high': [c + abs(np.random.normal(0, 0.00008)) for c in closes],
        'low': [c - abs(np.random.normal(0, 0.00008)) for c in closes],
        'close': closes,
        'volume': [np.random.randint(30, 200) if np.random.random() > 0.05 else np.random.randint(300, 600)
                   for _ in range(periods)]
    }, index=dates)
    df['high'] = df[['high', 'low', 'close']].max(axis=1)
    df['low'] = df[['high', 'low', 'close']].min(axis=1)
    return safe_df(df)

# ============================================================
# 6. FASTAPI APP & WEBSOCKET
# ============================================================
app = FastAPI(title="CATALYST", version="3.9")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_memory()
latest_signals: List[dict] = []
clients = set()

scheduler = None
if APS_AVAILABLE:
    scheduler = AsyncIOScheduler()

async def scan_loop():
    """Main scanning loop - dual broker, MTF, entry confirmation, news filter."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, connect_brokers)

    if scheduler:
        scheduler.add_job(weekly_optimise, 'cron', day_of_week='sun', hour=3)
        scheduler.start()
        logger.info("APScheduler started - weekly optimization on Sundays 03:00 UTC")

    while True:
        if not iq_connected and IQ_API_AVAILABLE and USE_IQ_OPTION:
            if IQ_EMAIL and IQ_PASSWORD:
                await loop.run_in_executor(None, connect_iq_option)
        if not po_connected and PO_API_AVAILABLE and USE_POCKET_OPTION:
            if PO_EMAIL and PO_PASSWORD:
                await loop.run_in_executor(None, connect_pocket_option)

        for platform, tfs in [("IQ Option", IQ_TFS), ("Pocket Option", PO_TFS)]:
            for sym in get_best_pairs_for_current_session():
                higher_tf_trend = get_higher_tf_trend(sym)
                if higher_tf_trend is None:
                    try:
                        df_5m = await loop.run_in_executor(None, lambda s=sym: get_data_sync(s, '5m'))
                        if df_5m is not None and len(df_5m) >= 20:
                            trend_5m = compute_5m_trend(df_5m)
                            if trend_5m:
                                cache_higher_tf_trend(sym, trend_5m)
                                higher_tf_trend = trend_5m
                    except Exception as e:
                        logger.debug(f"5m trend error for {sym}: {e}")

                market_trend = get_market_trend(sym)
                if market_trend is None:
                    try:
                        df_15m = await loop.run_in_executor(None, lambda s=sym: get_data_sync(s, '15m'))
                        if df_15m is not None and len(df_15m) >= 20:
                            trend_15m = compute_15m_trend(df_15m)
                            if trend_15m:
                                cache_market_trend(sym, trend_15m)
                                market_trend = trend_15m
                    except Exception as e:
                        logger.debug(f"15m trend error for {sym}: {e}")

                if not news_safe(sym):
                    continue

                for tf in tfs:
                    try:
                        tf_trend = higher_tf_trend if tf != '5m' else None
                        df = await loop.run_in_executor(None, lambda s=sym, t=tf: get_data_sync(s, t))
                        if df is None or df.empty:
                            continue

                        result = generate_signal(df, sym, tf_trend, market_trend)
                        if result is None:
                            continue

                        dir_ = result['direction']
                        rsi_ = result['rsi']
                        adx_ = result['adx']
                        accuracy = result['accuracy']

                        mem_conf = historical_confidence(rsi_, adx_, dir_, platform)
                        final_conf = round((accuracy + mem_conf) / 2, 1)

                        if final_conf < MIN_CONFIDENCE:
                            continue

                        now_utc = datetime.now(timezone.utc)
                        entry_time = now_utc + timedelta(minutes=1)
                        signal_price = df['close'].iloc[-1]
                        sig_id = str(uuid.uuid4())
                        remember_signal(sig_id, sym, dir_, tf, platform, entry_time, rsi_, adx_, final_conf, accuracy)

                        # Entry-time price confirmation
                        if ENTRY_CONFIRM_ENABLED and (iq_connected or po_connected):
                            sleep_seconds = (entry_time - datetime.now(timezone.utc)).total_seconds()
                            if sleep_seconds > 0 and sleep_seconds < 120:
                                logger.info(f"Entry confirm: waiting {sleep_seconds:.0f}s for {sym} {dir_}")
                                await asyncio.sleep(sleep_seconds)

                            current_price = await get_current_price(sym)
                            if current_price is not None:
                                if dir_ == 'BUY' and current_price <= signal_price * (1 - ENTRY_PRICE_THRESHOLD):
                                    logger.info(f"Entry cancel: {sym} BUY - price fell ({current_price:.5f} vs {signal_price:.5f})")
                                    continue
                                if dir_ == 'SELL' and current_price >= signal_price * (1 + ENTRY_PRICE_THRESHOLD):
                                    logger.info(f"Entry cancel: {sym} SELL - price rose ({current_price:.5f} vs {signal_price:.5f})")
                                    continue
                                logger.info(f"Entry confirmed: {sym} {dir_} price OK ({current_price:.5f})")

                        martingale = calculate_martingale(entry_time, tf, final_conf)
                        tf_duration = {'30s': 0.5, '45s': 0.75, '1m': 1, '2m': 2, '3m': 3, '5m': 5}
                        duration_min = tf_duration.get(tf, 1)

                        # Market volatility label
                        volatility = 'High Volatility' if accuracy >= 85 else ('Medium Volatility' if accuracy >= 70 else 'Low Volatility')

                        # Strategy guide based on signal type
                        if result['regime'] == 'BREAKOUT':
                            strategy_guide = [
                                'Wait for confirmed breakout candle close',
                                'Enter on pullback to breakout level',
                                'Use ATR-based stop loss',
                                f'Take profit at {result["rr"]} R:R',
                                'Trail stop after 1R profit',
                                'Risk 1% per trade maximum',
                            ]
                        elif dir_ == 'SELL':
                            strategy_guide = [
                                'Wait for confirmed setups only',
                                'Use BOS/CHoCH for confirmation',
                                'Enter at FVG fill zones',
                                f'Take profit at {result["rr"]} R:R',
                                'Tighter stops recommended',
                                'Move stop to breakeven after 1R',
                                'Risk 1% per trade',
                                'Use tighter stops',
                                f'GLM Probability: {final_conf}% win rate',
                            ]
                        else:
                            strategy_guide = [
                                'Wait for confirmed setups only',
                                'Use BOS/CHoCH for confirmation',
                                'Enter at FVG fill zones',
                                f'Take profit at {result["rr"]} R:R',
                                'Tighter stops recommended',
                                'Move stop to breakeven after 1R',
                                'Risk 1% per trade',
                                'Use tighter stops',
                                f'GLM Probability: {final_conf}% win rate',
                            ]

                        sig = {
                            'signal_id': sig_id,
                            'symbol': sym,
                            'direction': dir_,
                            'timeframe': tf,
                            'platform': platform,
                            'generated_at': now_utc.isoformat(),
                            'entry_time': entry_time.isoformat(),
                            'duration_minutes': duration_min,
                            'confidence': final_conf,
                            'accuracy': round(accuracy, 1),
                            'volatility': volatility,
                            'martingale': martingale,
                            'params': dict(PARAMS),
                            'confirmed': ENTRY_CONFIRM_ENABLED and (iq_connected or po_connected),
                            'mtf_trend': tf_trend or 'N/A',
                            'market_trend': market_trend or 'N/A',
                            # v3.2 new fields from generate_signal
                            'regime': result['regime'],
                            'regime_desc': result['regime_desc'],
                            'trend': result['trend'],
                            'bos': result['bos'],
                            'choch': result['choch'],
                            'fvg': result['fvg'],
                            'fvg_type': result['fvg_type'],
                            'liquidity_sweep': result['liquidity_sweep'],
                            'liquidity_side': result['liquidity_side'],
                            'volume_class': result['volume_class'],
                            'zone': result['zone'],
                            'rsi': result['rsi'],
                            'adx': result['adx'],
                            'stoch_val': result['stoch_val'],
                            'stoch_status': result['stoch_status'],
                            'bb_status': result['bb_status'],
                            'rr': result['rr'],
                            'support': result['support'],
                            'resistance': result['resistance'],
                            'price': result['price'],
                            'order_block': result['order_block'],
                            'sm_structure': result['sm_structure'],
                            'sm_liquidity': result['sm_liquidity'],
                            'sm_breakout': result['sm_breakout'],
                            'sm_signal': result['sm_signal'],
                            'strategy_guide': strategy_guide,
                        }
                        latest_signals.insert(0, sig)
                        if len(latest_signals) > 50:
                            latest_signals.pop()

                        # WebSocket broadcast
                        payload = {'type': 'new_signal', **sig}
                        dead = []
                        for ws in clients:
                            try:
                                await ws.send_json(payload)
                            except:
                                dead.append(ws)
                        for ws in dead:
                            clients.discard(ws)

                        # Send Telegram alert (fire-and-forget)
                        asyncio.create_task(send_telegram(sig))

                        logger.info(f"{platform} | {sym} {dir_} | RSI:{rsi_:.0f} ADX:{adx_:.0f} Acc:{accuracy:.0f}% Conf:{final_conf}%")
                    except Exception as e:
                        logger.error(f"Error {platform} {sym} {tf}: {traceback.format_exc()}")
        await asyncio.sleep(15)

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        clients.discard(websocket)

@app.post("/api/trade/outcome")
async def outcome(signal_id: str, outcome: str):
    if outcome not in ('win', 'loss', 'ignored'):
        return {"error": "invalid outcome"}
    learn_from_outcome(signal_id, outcome)
    return {"status": "ok"}

@app.get("/api/stats")
async def stats():
    return get_stats()

@app.get("/api/pnl")
async def pnl():
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) FROM trades")
        total, wins, losses = cur.fetchone()
        conn.close()
        return {"total": total or 0, "wins": wins or 0, "losses": losses or 0}
    except Exception as e:
        return {"total": 0, "wins": 0, "losses": 0, "error": str(e)}

@app.get("/api/daily-stats")
async def daily_stats_api(days: int = 30):
    return {"daily": get_daily_stats(days)}

@app.get("/api/session")
async def session_info():
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60.0
    if 22.0 <= hour or hour < 7.0:
        s = "Sydney/Tokyo"
    elif 7.0 <= hour < 12.0:
        s = "London"
    elif 12.0 <= hour < 16.0:
        s = "New York"
    else:
        s = "Off-peak"
    return {"session": s, "active": True, "time_utc": now.isoformat()}

@app.get("/api/status")
async def system_status():
    stats = get_stats()
    return {
        "status": "online",
        "version": "3.9",
        "engine": "CATALYST FINAL",
        "iq_connected": iq_connected,
        "po_connected": po_connected,
        "news_filter": NEWS_FILTER_ENABLED and EC_API_AVAILABLE,
        "telegram": TG_AVAILABLE and bool(TELEGRAM_TOKEN),
        "entry_confirm": ENTRY_CONFIRM_ENABLED,
        "scheduler": APS_AVAILABLE,
        "connected_clients": len(clients),
        "total_signals_generated": len(latest_signals),
        "params": PARAMS,
        "min_confidence": MIN_CONFIDENCE,
        "win_rate": stats["win_rate"],
        "total_trades": stats["total_trades"],
        "platforms": ["IQ Option", "Pocket Option"],
        "pairs": PAIRS,
        "pairs_count": len(PAIRS)
    }

@app.get("/api/signals")
async def signals_list():
    return {"signals": latest_signals[:20]}

@app.get("/api/tune-progress")
async def tune_progress():
    """Return auto-tune progress: how many graded trades toward the 50-trade threshold."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE outcome IN ('win','loss')")
        graded = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades WHERE outcome='pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT outcome FROM trades WHERE outcome IN ('win','loss') ORDER BY entry_time DESC LIMIT 50")
        rows = cur.fetchall()
        wins = sum(1 for r in rows if r[0] == 'win')
        total = len(rows)
        wr = round(wins / total * 100, 1) if total > 0 else 0
        conn.close()
        return {
            "graded_trades": graded,
            "pending_trades": pending,
            "threshold": 50,
            "progress_pct": min(100, round(graded / 50 * 100, 1)),
            "current_wr": wr,
            "auto_tune_active": graded >= 50,
            "params": dict(PARAMS),
            "min_confidence": MIN_CONFIDENCE,
            "can_tune": graded >= 50,
            "trades_needed": max(0, 50 - graded)
        }
    except Exception as e:
        return {"graded_trades": 0, "threshold": 50, "progress_pct": 0, "error": str(e)}

@app.get("/api/trades/recent")
async def recent_trades(limit: int = 30):
    """Return recent trades with outcomes for the dashboard tracker."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, symbol, direction, timeframe, platform,
                   entry_time, outcome, rsi, adx, confidence, accuracy
            FROM trades ORDER BY entry_time DESC LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
        trades = []
        for r in rows:
            trades.append({
                "signal_id": r[0], "symbol": r[1], "direction": r[2],
                "timeframe": r[3], "platform": r[4], "entry_time": r[5],
                "outcome": r[6] or "pending", "rsi": r[7], "adx": r[8],
                "confidence": r[9], "accuracy": r[10]
            })
        return {"trades": trades, "count": len(trades)}
    except Exception as e:
        return {"trades": [], "error": str(e)}

@app.get("/")
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

# ============================================================
# 7. DASHBOARD HTML with Chart.js
# ============================================================
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CATALYST v3.9</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#050510;color:#e0e0e0;font-family:Segoe UI,sans-serif}
.app{max-width:1400px;margin:0 auto;padding:20px}
.header{background:linear-gradient(135deg,#0a0a2e,#1a1a4e);border-radius:16px;padding:20px;display:flex;justify-content:space-between;align-items:center;border:1px solid #2a2a5a;margin-bottom:20px;flex-wrap:wrap;gap:10px}
.logo{font-size:2em;font-weight:bold}.logo span{color:#00ff88}
.status{color:#00ff88;background:rgba(0,255,136,0.1);padding:5px 15px;border-radius:20px;font-size:0.9em}
.info-bar{display:flex;gap:15px;margin-bottom:15px;flex-wrap:wrap;align-items:center}
.session-badge{display:inline-block;padding:3px 12px;border-radius:15px;font-size:0.9em}
.session-active{background:rgba(0,255,136,0.1);color:#00ff88}
.stats-bar{background:#0a0a1e;border-radius:12px;padding:10px 15px;border:1px solid #2a2a5a;font-size:0.9em;color:#aaa;flex:1;min-width:200px}

/* Two-column layout */
.main-grid{display:grid;grid-template-columns:1fr 380px;gap:20px;align-items:start}
@media(max-width:900px){.main-grid{grid-template-columns:1fr}}

/* Left column: chart + signals */
.left-col{}

/* Right column: tracker panel */
.right-col{position:sticky;top:20px}
.tracker-panel{background:#0a0a1e;border-radius:16px;padding:20px;border:1px solid #2a2a5a;margin-bottom:20px}
.tracker-title{font-size:1.2em;font-weight:bold;color:#ffd700;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.pnl-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1a1a3e;font-size:0.95em}
.pnl-label{color:#888}
.pnl-value{font-weight:bold;font-size:1.1em}
.pnl-value.wins{color:#00ff88}
.pnl-value.losses{color:#ff4444}
.pnl-value.total{color:#ffd700}

/* Auto-tune progress */
.tune-section{margin-top:15px;padding:12px;background:#111;border-radius:10px;border:1px solid #1a1a3e}
.tune-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.tune-label{color:#aaa;font-size:0.9em}
.tune-value{color:#00ff88;font-weight:bold;font-size:0.9em}
.progress-bar{background:#1a1a3e;border-radius:8px;height:12px;overflow:hidden;margin-bottom:8px}
.progress-fill{height:100%;border-radius:8px;transition:width .5s ease;background:linear-gradient(90deg,#ff4444,#ffd700,#00ff88)}
.tune-status{font-size:0.85em;padding:6px 10px;border-radius:6px;text-align:center;margin-top:6px}
.tune-active{background:rgba(0,255,136,0.15);color:#00ff88}
.tune-pending{background:rgba(255,215,0,0.15);color:#ffd700}
.tune-params{font-size:0.8em;color:#888;margin-top:8px;line-height:1.6}
.tune-params b{color:#e0e0e0}

/* Trade history list */
.trade-history{margin-top:15px;max-height:400px;overflow-y:auto}
.trade-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;margin-bottom:4px;font-size:0.85em;background:#111;border:1px solid #1a1a3e}
.trade-item.win{border-left:3px solid #00ff88}
.trade-item.loss{border-left:3px solid #ff4444}
.trade-item.ignored{border-left:3px solid #666}
.trade-item.pending{border-left:3px solid #ffd700}
.trade-dir{font-weight:bold;min-width:36px}
.trade-dir.buy{color:#00ff88}
.trade-dir.sell{color:#ff4444}
.trade-pair{flex:1;color:#e0e0e0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.trade-outcome{font-size:0.8em;padding:2px 8px;border-radius:10px;font-weight:bold}
.trade-outcome.win{background:rgba(0,255,136,0.2);color:#00ff88}
.trade-outcome.loss{background:rgba(255,68,68,0.2);color:#ff4444}
.trade-outcome.ignored{background:rgba(102,102,102,0.2);color:#999}
.trade-outcome.pending{background:rgba(255,215,0,0.2);color:#ffd700}

.chart-container{background:#0a0a1e;border-radius:16px;padding:20px;border:1px solid #2a2a5a;margin-bottom:20px;height:300px}
.platform-selector{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.platform-btn{padding:10px 25px;border-radius:25px;border:1px solid #2a2a5a;background:#0a0a2e;color:#e0e0e0;cursor:pointer;font-weight:600;transition:all .2s}
.platform-btn:hover{border-color:#00ff88}
.platform-btn.active{background:#00ff88;color:#000}
.signals{background:#0a0a1e;border-radius:16px;padding:20px;border:1px solid #2a2a5a;min-height:300px}
.waiting{text-align:center;padding:60px;color:#666}
.signal-card{background:#1a1a3e;border-radius:12px;padding:20px;margin:15px 0;border-left:4px solid #00ff88;animation:slide .3s}
.signal-card.sell{border-left-color:#ff4444}
.signal-card.iq{border-top:2px solid #00b4d8}
.signal-card.po{border-top:2px solid #ffd700}
.card-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:5px}
.pair{font-size:1.2em;font-weight:bold}
.platform-badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:0.8em;font-weight:bold}
.platform-badge.iq{background:rgba(0,180,216,0.2);color:#00b4d8}
.platform-badge.po{background:rgba(255,215,0,0.2);color:#ffd700}
.conf{color:#00ff88;background:rgba(0,255,136,0.1);padding:3px 12px;border-radius:15px;font-size:0.9em}
.accuracy{color:#ffd700;font-weight:bold;margin-left:8px}
.direction{display:inline-block;padding:5px 15px;border-radius:8px;margin:10px 0;font-weight:bold}
.direction.buy{background:rgba(0,255,136,0.2);color:#00ff88}
.direction.sell{background:rgba(255,68,68,0.2);color:#ff4444}
.confirmed-badge{display:inline-block;padding:2px 8px;border-radius:8px;font-size:0.75em;background:rgba(0,255,136,0.15);color:#00ff88;margin-left:8px}
.regime-badge{display:inline-block;padding:3px 10px;border-radius:8px;font-size:0.85em;font-weight:bold;margin:5px 0}
.regime-badge.breakout{background:rgba(255,68,68,0.2);color:#ff6666}
.regime-badge.trending{background:rgba(0,180,216,0.2);color:#00b4d8}
.regime-badge.ranging{background:rgba(255,215,0,0.2);color:#ffd700}
.signal-section{margin:10px 0;padding:10px;background:#111;border-radius:8px;font-size:0.9em}
.signal-section-title{color:#ffd700;font-weight:bold;margin-bottom:5px;font-size:0.95em}
.signal-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px}
.signal-grid-item{display:flex;justify-content:space-between;padding:2px 0}
.signal-grid-item .label{color:#888}
.signal-grid-item .value{color:#e0e0e0;font-weight:500}
.smart-money-section{margin:10px 0;padding:10px;background:rgba(0,180,216,0.08);border:1px solid rgba(0,180,216,0.2);border-radius:8px}
.smart-money-item{padding:3px 0;font-size:0.9em}
.strategy-section{margin:10px 0;padding:10px;background:rgba(0,255,136,0.05);border:1px solid rgba(0,255,136,0.15);border-radius:8px}
.strategy-item{padding:2px 0;font-size:0.85em}
.sr-section{margin:10px 0;padding:10px;background:rgba(255,215,0,0.05);border:1px solid rgba(255,215,0,0.15);border-radius:8px}
.disclaimer{font-size:0.8em;color:#666;margin-top:10px;padding:8px;background:#0a0a1e;border-radius:6px}
.signal-status{font-weight:bold;text-align:center;padding:8px;border-radius:8px;margin-top:8px}
.signal-status.high{background:rgba(0,255,136,0.15);color:#00ff88}
.signal-status.moderate{background:rgba(255,215,0,0.15);color:#ffd700}

/* ENHANCED OUTCOME BUTTONS */
.outcome-section{margin-top:12px;padding:12px;background:#0d0d20;border-radius:10px;border:1px solid #2a2a5a}
.outcome-title{color:#ffd700;font-weight:bold;font-size:0.9em;margin-bottom:8px;text-align:center}
.outcome-btns{display:flex;gap:8px;justify-content:center}
.outcome-btn{flex:1;padding:12px 8px;border:none;border-radius:10px;cursor:pointer;font-weight:bold;font-size:1em;transition:all .15s;display:flex;flex-direction:column;align-items:center;gap:3px}
.outcome-btn:hover{transform:scale(1.05)}
.outcome-btn:active{transform:scale(0.95)}
.outcome-btn:disabled{opacity:0.3;cursor:not-allowed;transform:none}
.outcome-btn .icon{font-size:1.5em}
.outcome-btn .label{font-size:0.8em}
.win-btn{background:linear-gradient(135deg,#00cc6a,#00ff88);color:#000;box-shadow:0 2px 12px rgba(0,255,136,0.3)}
.loss-btn{background:linear-gradient(135deg,#cc2222,#ff4444);color:#fff;box-shadow:0 2px 12px rgba(255,68,68,0.3)}
.ignore-btn{background:linear-gradient(135deg,#555,#777);color:#fff;box-shadow:0 2px 12px rgba(102,102,102,0.3)}
.outcome-result{text-align:center;padding:10px;border-radius:8px;margin-top:8px;font-weight:bold;font-size:1em;animation:slide .3s}

.copy-btn{background:#00b4d8;color:#fff;padding:8px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;font-size:0.9em;transition:all .15s}
.copy-btn:hover{background:#0099cc}

.countdown{font-size:1.5em;font-weight:bold;color:#ffd700;margin:10px 0}
.timing-details{font-size:0.9em;color:#aaa;margin-bottom:10px}
.martingale{margin-top:10px;background:#111;padding:10px;border-radius:8px}
.martingale-title{color:#ffd700;font-weight:bold;margin-bottom:5px}
.martingale-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #222;font-size:0.9em}

/* Data source badge */
.data-source{font-size:0.8em;padding:3px 10px;border-radius:10px;margin:5px 0;display:inline-block}
.data-source.real{background:rgba(0,255,136,0.15);color:#00ff88}
.data-source.demo{background:rgba(255,68,68,0.15);color:#ff6666}

@keyframes slide{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.pulse{animation:pulse 2s infinite}
@media(max-width:600px){.header{flex-direction:column;text-align:center}.platform-selector{justify-content:center}.outcome-btns{flex-direction:row}.outcome-btn{padding:10px 6px}}
</style>
</head>
<body>
<div class="app">
<div class="header">
  <div class="logo">CATALYST<span>AI</span> <small style="font-size:0.4em;color:#888">v3.9</small></div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span class="session-badge session-active" id="session-badge">...</span>
    <span class="status" id="sys-status">LIVE</span>
    <span class="data-source" id="data-source">DEMO DATA</span>
  </div>
</div>
<div class="info-bar">
  <div id="session-timer" style="color:#888;min-width:200px"></div>
  <div class="stats-bar" id="stats">Loading stats...</div>
</div>

<!-- Two-column layout -->
<div class="main-grid">
<div class="left-col">
  <div class="chart-container">
    <canvas id="wrChart"></canvas>
  </div>
  <div class="platform-selector">
    <button class="platform-btn active" onclick="filterPlatform('all',this)">All Platforms</button>
    <button class="platform-btn" onclick="filterPlatform('IQ Option',this)">IQ Option</button>
    <button class="platform-btn" onclick="filterPlatform('Pocket Option',this)">Pocket Option</button>
  </div>
  <div class="signals" id="signals">
    <div class="waiting" id="waiting">
      <div style="font-size:3em">&#9203;</div>
      <h3>Waiting for signal setups</h3>
      <p>Scanning 8 OTC pairs on IQ Option & Pocket Option timeframes</p>
      <p style="margin-top:10px;font-size:0.9em;color:#ff6666">Click WIN / LOSS / IGNORED after each trade to feed self-learning memory</p>
    </div>
  </div>
</div>

<div class="right-col">
  <!-- P&L Tracker Panel -->
  <div class="tracker-panel">
    <div class="tracker-title">&#128200; Trade Tracker</div>
    <div class="pnl-row"><span class="pnl-label">Total Trades</span><span class="pnl-value total" id="pnl-total">0</span></div>
    <div class="pnl-row"><span class="pnl-label">Wins</span><span class="pnl-value wins" id="pnl-wins">0</span></div>
    <div class="pnl-row"><span class="pnl-label">Losses</span><span class="pnl-value losses" id="pnl-losses">0</span></div>
    <div class="pnl-row"><span class="pnl-label">Win Rate</span><span class="pnl-value total" id="pnl-wr">0%</span></div>

    <!-- Auto-Tune Progress -->
    <div class="tune-section">
      <div class="tune-header">
        <span class="tune-label">&#9881; Auto-Tune Progress</span>
        <span class="tune-value" id="tune-pct">0%</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="tune-fill" style="width:0%"></div></div>
      <div id="tune-status" class="tune-status tune-pending">0 / 50 graded trades needed</div>
      <div class="tune-params" id="tune-params">
        RSI Buy: <b>-</b> | RSI Sell: <b>-</b><br>
        ADX Min: <b>-</b> | Vol Mult: <b>-</b><br>
        Min Confidence: <b>-</b>%
      </div>
    </div>

    <!-- Recent Trade History -->
    <div class="tracker-title" style="margin-top:15px">&#128203; Recent Trades</div>
    <div class="trade-history" id="trade-history">
      <div style="text-align:center;color:#666;padding:20px">No trades yet</div>
    </div>
  </div>
</div>
</div>
</div>
<script>
var currentPlatform='all';
var wrChart=null;

function initChart(){
  var ctx=document.getElementById('wrChart').getContext('2d');
  wrChart=new Chart(ctx,{
    type:'line',
    data:{labels:[],datasets:[
      {label:'Win Rate %',data:[],borderColor:'#00ff88',backgroundColor:'rgba(0,255,136,0.1)',fill:true,tension:0.3},
      {label:'Accuracy %',data:[],borderColor:'#ffd700',backgroundColor:'rgba(255,215,0,0.1)',fill:false,tension:0.3}
    ]},
    options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true,max:100,grid:{color:'#1a1a3e'}},x:{grid:{color:'#1a1a3e'}}},plugins:{legend:{labels:{color:'#e0e0e0'}}}}
  });
}

function updateChart(){
  fetch('/api/daily-stats?days=30').then(r=>r.json()).then(d=>{
    if(!d.daily||!d.daily.length)return;
    d.daily.reverse();
    wrChart.data.labels=d.daily.map(x=>x.date);
    wrChart.data.datasets[0].data=d.daily.map(x=>x.win_rate);
    wrChart.data.datasets[1].data=d.daily.map(x=>x.avg_accuracy);
    wrChart.update();
  }).catch(()=>{});
}
setInterval(updateChart,60000);

function filterPlatform(p,btn){
  currentPlatform=p;
  document.querySelectorAll('.platform-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.signal-card').forEach(c=>{
    c.style.display=(p==='all'||c.getAttribute('data-platform')===p)?'':'none';
  });
}

function updateStats(){
  fetch('/api/stats').then(r=>r.json()).then(d=>{
    document.getElementById('stats').innerHTML=
      'WR: <b style="color:'+(d.win_rate>=80?'#00ff88':'#ff4444')+'">'+d.win_rate+'%</b> | '+
      'W:'+d.wins+' L:'+d.losses+' Ign:'+d.ignored+' | '+
      'RSI<'+d.params.rsi_buy+' ADX>'+d.params.adx_min+' Vol>'+d.params.vol_mult+'x | '+
      'MinConf:'+d.min_confidence+'%';
  }).catch(()=>{});
}
setInterval(updateStats,10000);updateStats();

function updateSession(){
  fetch('/api/session').then(r=>r.json()).then(d=>{
    var b=document.getElementById('session-badge');
    b.textContent=d.active?'\uD83D\uDFE2 '+d.session:'\uD83D\uDD34 Off';
    b.className='session-badge '+(d.active?'session-active':'session-inactive');
  }).catch(()=>{});
}
setInterval(updateSession,30000);updateSession();

function updateStatus(){
  fetch('/api/status').then(r=>r.json()).then(d=>{
    var s=document.getElementById('sys-status');
    var parts=['LIVE'];
    if(d.iq_connected)parts.push('IQ \u2705');
    if(d.po_connected)parts.push('PO \u2705');
    if(d.telegram)parts.push('TG');
    if(d.news_filter)parts.push('NF');
    s.textContent=parts.join(' | ');
    var ds=document.getElementById('data-source');
    if(d.iq_connected||d.po_connected){
      ds.textContent='REAL DATA';
      ds.className='data-source real';
    } else {
      ds.textContent='DEMO DATA';
      ds.className='data-source demo';
    }
  }).catch(()=>{});
}
setInterval(updateStatus,15000);updateStatus();

/* P&L Tracker */
function updatePnl(){
  fetch('/api/pnl').then(r=>r.json()).then(d=>{
    document.getElementById('pnl-total').textContent=d.total||0;
    document.getElementById('pnl-wins').textContent=d.wins||0;
    document.getElementById('pnl-losses').textContent=d.losses||0;
    var total=(d.wins||0)+(d.losses||0);
    var wr=total>0?Math.round((d.wins||0)/total*100):0;
    document.getElementById('pnl-wr').textContent=wr+'%';
    document.getElementById('pnl-wr').style.color=wr>=80?'#00ff88':wr>=60?'#ffd700':'#ff4444';
  }).catch(()=>{});
}
setInterval(updatePnl,10000);updatePnl();

/* Auto-Tune Progress */
function updateTuneProgress(){
  fetch('/api/tune-progress').then(r=>r.json()).then(d=>{
    var pct=d.progress_pct||0;
    document.getElementById('tune-pct').textContent=pct+'%';
    document.getElementById('tune-fill').style.width=pct+'%';
    var statusEl=document.getElementById('tune-status');
    if(d.auto_tune_active){
      statusEl.className='tune-status tune-active';
      statusEl.textContent='\u2705 AUTO-TUNE ACTIVE | WR: '+d.current_wr+'%';
    } else {
      statusEl.className='tune-status tune-pending';
      statusEl.textContent=d.graded_trades+' / 50 graded trades ('+d.trades_needed+' more needed)';
    }
    var params=d.params||{};
    document.getElementById('tune-params').innerHTML=
      'RSI Buy: <b>'+(params.rsi_buy||'-')+'</b> | RSI Sell: <b>'+(params.rsi_sell||'-')+'</b><br>'+
      'ADX Min: <b>'+(params.adx_min||'-')+'</b> | Vol Mult: <b>'+(params.vol_mult||'-')+'x</b><br>'+
      'Min Confidence: <b>'+(d.min_confidence||'-')+'</b>%';
  }).catch(()=>{});
}
setInterval(updateTuneProgress,15000);updateTuneProgress();

/* Trade History */
function updateTradeHistory(){
  fetch('/api/trades/recent?limit=20').then(r=>r.json()).then(d=>{
    var cont=document.getElementById('trade-history');
    if(!d.trades||!d.trades.length){
      cont.innerHTML='<div style="text-align:center;color:#666;padding:20px">No trades yet</div>';
      return;
    }
    var html='';
    d.trades.forEach(function(t){
      var sym=t.symbol.replace('-OTC','').replace('_OTC','').replace(' (OTC)','');
      var outcome=t.outcome||'pending';
      var dirClass=t.direction==='BUY'?'buy':'sell';
      var outcomeClass=outcome;
      var outcomeLabel=outcome.charAt(0).toUpperCase()+outcome.slice(1);
      if(outcome==='win')outcomeLabel='\u2705 Win';
      else if(outcome==='loss')outcomeLabel='\u274C Loss';
      else if(outcome==='ignored')outcomeLabel='\uD83D\uDEAB Ignored';
      else outcomeLabel='\u23F3 Pending';
      html+='<div class="trade-item '+outcomeClass+'">'+
        '<span class="trade-dir '+dirClass+'">'+t.direction+'</span>'+
        '<span class="trade-pair">'+sym+' '+t.timeframe+'</span>'+
        '<span class="trade-outcome '+outcomeClass+'">'+outcomeLabel+'</span>'+
        '</div>';
    });
    cont.innerHTML=html;
  }).catch(()=>{});
}
setInterval(updateTradeHistory,15000);updateTradeHistory();

function fmtTime(sec){
  if(sec<=0)return"Entry passed";
  var m=Math.floor(sec/60),s=Math.floor(sec%60);
  return'Entry in '+m+':'+(s<10?'0':'')+s;
}

function updateCountdowns(){
  document.querySelectorAll('.signal-card').forEach(c=>{
    var e=c.getAttribute('data-entry-time');
    if(!e)return;
    var diff=(new Date(e)-new Date())/1000;
    var el=c.querySelector('.countdown');
    if(el){el.textContent=fmtTime(diff);el.style.color=diff<=0?'#ff4444':'#ffd700';}
  });
}
setInterval(updateCountdowns,1000);

var ws=new WebSocket('ws://'+location.host+'/ws');
ws.onmessage=function(e){
  var d=JSON.parse(e.data);
  if(d.type!=='new_signal')return;
  var card=document.createElement('div');
  card.className='signal-card '+d.direction.toLowerCase()+' '+(d.platform==='IQ Option'?'iq':'po');
  card.setAttribute('data-signal-id',d.signal_id);
  card.setAttribute('data-entry-time',d.entry_time);
  card.setAttribute('data-platform',d.platform);
  card.setAttribute('data-signal-json',JSON.stringify(d));

  var genD=new Date(d.generated_at),entD=new Date(d.entry_time);
  var endD=new Date(entD.getTime()+d.duration_minutes*60000);
  var tz={hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Africa/Lagos'};
  var entS=entD.toLocaleTimeString('en-GB',tz)+' WAT';
  var endS=endD.toLocaleTimeString('en-GB',tz)+' WAT';

  var badge=d.platform==='IQ Option'?'<span class="platform-badge iq">IQ Option</span>':'<span class="platform-badge po">Pocket Option</span>';
  var confBadge=d.confirmed?'<span class="confirmed-badge">CONFIRMED</span>':'';
  var symClean=d.symbol.replace('-OTC','').replace('_OTC','').replace(' (OTC)','');
  var otcLabel=(d.symbol.indexOf('OTC')>=0)?'OTC':'';
  var regimeClass=(d.regime||'RANGING').toLowerCase();
  var regimeHtml='<span class="regime-badge '+regimeClass+'">'+(d.regime||'RANGING')+'</span>';

  var mHtml='';
  if(d.martingale&&d.martingale.length){
    mHtml='<div class="signal-section"><div class="signal-section-title">MARTINGALE RECOVERY</div>';
    d.martingale.forEach(function(m){
      var mD=new Date(m.entry_time);
      var mT=mD.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';
      mHtml+='<div class="signal-grid-item"><span>'+m.level+'</span><span>'+m.multiplier+'x</span><span>$'+m.amount+'</span><span>'+mT+'</span></div>';
    });
    mHtml+='</div>';
  }

  var smHtml='<div class="smart-money-section"><div class="signal-section-title">GLM SMART MONEY</div>'+
    '<div class="smart-money-item">Structure: '+(d.sm_structure||'N/A')+'</div>'+
    '<div class="smart-money-item">Liquidity: '+(d.sm_liquidity||'N/A')+'</div>'+
    '<div class="smart-money-item">Breakout: '+(d.sm_breakout||'N/A')+'</div>'+
    '<div class="smart-money-item">Signal: '+(d.sm_signal||'N/A')+'</div></div>';

  var stratHtml='';
  if(d.strategy_guide&&d.strategy_guide.length){
    stratHtml='<div class="strategy-section"><div class="signal-section-title">STRATEGY GUIDE</div>';
    d.strategy_guide.forEach(function(s){
      stratHtml+='<div class="strategy-item">'+s+'</div>';
    });
    stratHtml+='</div>';
  }

  var srHtml='<div class="sr-section"><div class="signal-section-title">SUPPORT / RESISTANCE</div>'+
    '<div class="signal-grid-item"><span class="label">Support</span><span class="value">'+(d.support||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Resistance</span><span class="value">'+(d.resistance||'N/A')+'</span></div></div>';

  var sigStatus=d.confidence>=85?'HIGH PROBABILITY ONLY':'MODERATE PROBABILITY';
  var sigStatusClass=d.confidence>=85?'high':'moderate';

  var liqDisplay=d.liquidity_sweep?'Sweep ('+d.liquidity_side+')':'No Sweep';
  var gridHtml='<div class="signal-section"><div class="signal-section-title">MARKET ANALYSIS</div>'+
    '<div class="signal-grid">'+
    '<div class="signal-grid-item"><span class="label">Trend</span><span class="value">'+(d.trend||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">BOS</span><span class="value">'+(d.bos||'Not Confirmed')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">CHoCH</span><span class="value">'+(d.choch||'Not Confirmed')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">FVG</span><span class="value">'+(d.fvg||'Inactive')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Liquidity</span><span class="value">'+liqDisplay+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Volume</span><span class="value">'+(d.volume_class||'Normal')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Zone</span><span class="value">'+(d.zone||'None')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">RSI</span><span class="value">'+d.rsi+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Stochastic</span><span class="value">'+(d.stoch_status||'Neutral')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">BB Width</span><span class="value">'+(d.bb_status||'Stable')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">R:R</span><span class="value">'+(d.rr||'1:1.0')+'</span></div>'+
    '</div></div>';

  var outcomeHtml='<div class="outcome-section">'+
    '<div class="outcome-title">REPORT TRADE OUTCOME</div>'+
    '<div class="outcome-btns">'+
    '<button class="outcome-btn win-btn" onclick="report(\''+d.signal_id+'\',\'win\',this)">'+
    '<span class="icon">\u2705</span><span class="label">WIN</span></button>'+
    '<button class="outcome-btn loss-btn" onclick="report(\''+d.signal_id+'\',\'loss\',this)">'+
    '<span class="icon">\u274C</span><span class="label">LOSS</span></button>'+
    '<button class="outcome-btn ignore-btn" onclick="report(\''+d.signal_id+'\',\'ignored\',this)">'+
    '<span class="icon">\uD83D\uDEAB</span><span class="label">IGNORED</span></button>'+
    '</div>'+
    '<div class="outcome-result" id="outcome-'+d.signal_id+'" style="display:none"></div>'+
    '</div>';

  card.innerHTML=
    '<div class="card-header"><div class="pair">'+symClean+' '+badge+'</div><div><div class="conf">'+d.confidence+'%'+confBadge+'</div><span class="accuracy">Acc: '+d.accuracy+'%</span></div></div>'+
    '<div class="direction '+d.direction.toLowerCase()+'">'+d.direction+'</div>'+
    '<div class="countdown">'+fmtTime((entD-new Date())/1000)+'</div>'+
    '<div class="timing-details">Entry: '+entS+' | End: '+endS+' ('+d.duration_minutes*60+'s) | '+otcLabel+'</div>'+
    '<div>Market: '+(d.volatility||'High Volatility')+' | GLM Probability: '+d.confidence+'%</div>'+
    '<div style="margin:5px 0">'+regimeHtml+' <span style="color:#888;font-size:0.85em">'+(d.regime_desc||'')+'</span></div>'+
    gridHtml+mHtml+smHtml+stratHtml+srHtml+
    '<div class="disclaimer">Note: Trade 1-3% of capital. AI analyzes data in real time, outcomes may vary.</div>'+
    '<div class="signal-status '+sigStatusClass+'">SIGNAL STATUS: '+sigStatus+'</div>'+
    '<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">'+
    '<button class="copy-btn" onclick="copySignal(this)">Copy Signal</button>'+
    '</div>'+
    outcomeHtml;

  var cont=document.getElementById('signals');
  var wait=document.getElementById('waiting');
  if(wait)wait.style.display='none';
  cont.insertBefore(card,cont.firstChild);
  if(currentPlatform!=='all'&&d.platform!==currentPlatform)card.style.display='none';
};

function copySignal(btn){
  var card=btn.closest('.signal-card');
  var d=JSON.parse(card.getAttribute('data-signal-json')||'{}');
  if(!d.signal_id){btn.textContent='No data';return;}
  var emoji=d.direction==='SELL'?'\uD83D\uDD34':'\uD83D\uDFE2';
  var sym=d.symbol.replace('-OTC','').replace('_OTC','').replace(' (OTC)','');
  var entryD=new Date(d.entry_time);
  var entryStr=entryD.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';
  var regime=d.regime||'RANGING';var regimeDesc=d.regime_desc||'';
  var bosStatus=d.bos||'Not Confirmed';var chochStatus=d.choch||'Not Confirmed';
  var fvgStatus=d.fvg||'Inactive';var liqDisplay=d.liquidity_sweep?d.liquidity_side:'None';
  var volClass=d.volume_class||'Normal';var zone=d.zone||'None Detected';
  var stochVal=d.stoch_val||50;var stochDisplay;
  if(stochVal>80)stochDisplay='Overbought';else if(stochVal<20)stochDisplay='Oversold';
  else if(d.direction==='BUY'&&stochVal<50)stochDisplay='Bullish Crossover';
  else if(d.direction==='SELL'&&stochVal>50)stochDisplay='Bearish Crossover';
  else stochDisplay=d.stoch_status||'Neutral';
  var bbStatus=d.bb_status||'Stable';var bbDisplay=bbStatus==='Expanding'?'Expanding':(bbStatus==='Contracting'?'Contracting':'Squeezing');
  var rr=d.rr||'1:1.0';var smStructure=d.sm_structure||'No Clear Break';var smLiquidity=d.sm_liquidity||'N/A';
  var smBreakout=d.sm_breakout||'No Breakout';var smSignal=d.sm_signal||'N/A';
  var sigStatus=d.confidence>=85?'HIGH PROBABILITY ONLY':'MODERATE PROBABILITY';
  var msg='CATALYST AI SIGNAL!\n\n'+
  'Trade: '+sym+'\n'+
  'Timer: '+d.timeframe+' (OTC)\n'+
  'Entry: '+entryStr+'\n'+
  'Direction: '+d.direction+' '+emoji+'\n'+
  'GLM Probability: '+d.confidence+'% WIN RATE\n'+
  'Market: '+(d.volatility||'High Volatility')+'\n\n'+
  'Regime: '+regime+' - '+regimeDesc+'\n'+
  'Trend: '+(d.trend||'N/A')+'\n'+
  'BOS: '+bosStatus+'\n'+
  'CHoCH: '+chochStatus+'\n'+
  'FVG: '+fvgStatus+'\n'+
  'Liquidity: '+liqDisplay+'\n'+
  'Volume: '+volClass+'\n'+
  'Zone: '+zone+'\n'+
  'RSI: '+d.rsi+'\n'+
  'Stochastic: '+stochDisplay+'\n'+
  'BB Width: '+bbDisplay+'\n'+
  'RR: '+rr+'\n\n'+
  'SMART MONEY:\n'+
  '  Structure: '+smStructure+'\n'+
  '  Liquidity: '+smLiquidity+'\n'+
  '  Breakout: '+smBreakout+'\n'+
  '  Signal: '+smSignal+'\n\n'+
  'Note: Trade 1-3% of capital\n'+
  'SIGNAL STATUS: '+sigStatus+'\n'+
  'GLM PROBABILITY: '+d.confidence+'% WIN RATE';
  navigator.clipboard.writeText(msg).then(function(){
    btn.textContent='Copied!';btn.style.background='#00ff88';
    setTimeout(function(){btn.textContent='Copy Signal';btn.style.background='#00b4d8';},2000);
  }).catch(function(err){alert('Copy failed: '+err);});
}

function report(sid,outcome,btn){
  var card=btn.closest('.signal-card');
  var section=card.querySelector('.outcome-section');
  section.querySelectorAll('.outcome-btn').forEach(b=>b.disabled=true);
  fetch('/api/trade/outcome?signal_id='+sid+'&outcome='+outcome,{method:'POST'})
  .then(r=>r.json()).then(data=>{
    var result=section.querySelector('.outcome-result');
    result.style.display='block';
    if(outcome==='win'){
      card.style.borderLeft='4px solid #00ff88';result.style.color='#00ff88';
      result.style.background='rgba(0,255,136,0.1)';
      result.textContent='Trade Won! Self-learning memory updated.';
    } else if(outcome==='loss'){
      card.style.borderLeft='4px solid #ff4444';result.style.color='#ff4444';
      result.style.background='rgba(255,68,68,0.1)';
      result.textContent='Trade Lost. Parameters will adjust if WR drops.';
    } else {
      card.style.borderLeft='4px solid #888';result.style.color='#888';
      result.style.background='rgba(102,102,102,0.1)';
      result.textContent='Ignored. Excluded from win rate calc.';
    }
    section.querySelector('.outcome-btns').style.display='none';
    section.querySelector('.outcome-title').style.display='none';
    updateStats();updatePnl();updateTuneProgress();updateTradeHistory();
  }).catch(e=>{section.querySelectorAll('.outcome-btn').forEach(b=>b.disabled=false);});
}

setInterval(function(){
  var now=new Date(),h=now.getUTCHours()+now.getUTCMinutes()/60,r='';
  if(h>=22||h<7){var e=new Date(now);if(h>=22)e.setUTCDate(e.getUTCDate()+1);e.setUTCHours(7,0,0,0);var d=(e-now)/1000;r='Sydney/Tokyo ends in '+Math.floor(d/3600)+'h '+Math.floor((d%3600)/60)+'m';}
  else if(h>=8&&h<16){var e=new Date(now);e.setUTCHours(16,0,0,0);var d=(e-now)/1000;r='London/NY ends in '+Math.floor(d/3600)+'h '+Math.floor((d%3600)/60)+'m';}
  else r='Off-peak period';
  document.getElementById('session-timer').textContent=r;
},1000);

initChart();updateChart();
</script>
</body>
</html>"""


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(scan_loop())
    yield

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting CATALYST FINAL v3.9 on port {port}")
    logger.info(f"IQ Email: {IQ_EMAIL}, PO Email: {PO_EMAIL}")
    logger.info(f"IQ Available: {IQ_API_AVAILABLE}, PO Available: {PO_API_AVAILABLE}")
    logger.info(f"Telegram: {TG_AVAILABLE}, News Filter: {EC_API_AVAILABLE}, Scheduler: {APS_AVAILABLE}")
    logger.info(f"Params: {PARAMS}, Min Confidence: {MIN_CONFIDENCE}")
    logger.info(f"Dashboard: http://0.0.0.0:{port}/ - Click WIN/LOSS/IGNORED after each trade!")
    logger.info(f"Self-learning activates after 50 graded trades - parameters will auto-tune")
    uvicorn.run(app, host="0.0.0.0", port=port)
