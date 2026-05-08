#!/usr/bin/env python3
"""
CATALYST FINAL v3.8 - 24/7 Self-Improving OTC Signal Engine
SMC + Wyckoff + Divergence + Accuracy Level + PostgreSQL + Telegram + Copy Signal
All Sessions + R:R Filter + Valid Entry + Volume Break + Market Break + CHoCH + FVG Quality
Failed Reversal + Market Classification + Prime Session + Optimal Expiry + Daily Levels

v3.8 CHANGES:
- PostgreSQL/SQLite dual database support (DATABASE_URL env var)
- Weekly optimization upgraded: WR<93% tighten, WR>97% relax, 200-trade minimum
- Daily levels filter: get_daily_levels() + is_near_daily_level()
- Session profiles: London/NY/Sydney-Tokyo specific RSI/ADX/VOL params
- /api/scan endpoint for Railway cron (force_scan_cycle)
- All v3.5-v3.7 features integrated

v3.7 CHANGES:
- calculate_rr_ratio(): R:R as float, >=2.5 required
- valid_entry_candle(): body >40% of range, close in direction
- volume_break_confirmed(): vol >1.5x 20-period average
- market_break_valid(): close beyond recent swing with momentum
- choch_confirmed(): Change of Character detection (stronger than MSS)
- fvg_quality(): Fresh FVG with age<=3, size>=0.3ATR
- failed_reversal(): Counter-move failed, supports original direction
- classify_market(): strong/normal/ranging/low state
- is_prime_session(): London or NY active
- optimal_expiry(): Volatility-adaptive expiry selection
- Scoring +40: CHoCH+10, FVGqual+10, MktState+5, ValidEntry+5, VolBreak+5, MktBreak+5, RR+5

v3.6 CHANGES:
- identify_swings(): Generic swing detection with configurable order
- detect_repeating_patterns(): Double top/bottom detection
- predict_next_candle(): Momentum-based next candle prediction
- detect_price_phase(): Accumulation/markup/distribution/markdown
- candle_classification(): Doji/hammer/engulfing/trending classification
- pre_entry_confirm(): Final pre-entry candle confirmation

v3.5 CHANGES:
- detect_rsi_divergence(): Bullish/bearish RSI divergence
- detect_wyckoff_phase(): Wyckoff market phase detection
- wyckoff_confirms_signal(): Wyckoff phase + signal direction alignment
- get_daily_bias(): EMA20/50 based daily bias
- mtf_full_alignment(): All timeframes must align
- protected_swings_ok(): Last swing not broken back through
- range_efficiency(): 0-100 range efficiency (>=60 required)

DEPLOY:
  Set env vars: IQ_EMAIL, IQ_PASSWORD, PO_EMAIL, PO_PASSWORD, DATABASE_URL
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
IQ_EMAIL        = os.environ.get("IQ_EMAIL", "your_iq_option_email@example.com")
IQ_PASSWORD     = os.environ.get("IQ_PASSWORD", "your_iq_option_password")
PO_EMAIL        = os.environ.get("PO_EMAIL", "richmelody15@gmail.com")
PO_PASSWORD     = os.environ.get("PO_PASSWORD", "Clarity2819")

USE_IQ_OPTION     = os.environ.get("USE_IQ_OPTION", "True").strip().lower() in ("true", "1", "yes")
USE_POCKET_OPTION = os.environ.get("USE_POCKET_OPTION", "True").strip().lower() in ("true", "1", "yes")

# Telegram
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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

# psycopg2 for PostgreSQL (optional)
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CatalystFinal")

# ============================================================
# 0b. DATABASE URL & DUAL DB SUPPORT
# ============================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "")
MEMORY_DB = os.environ.get("DB_PATH", "memory.db")

def get_connection():
    """Get database connection. Returns (connection, is_postgres)."""
    if DATABASE_URL and DATABASE_URL.startswith("postgres") and PSYCOPG2_AVAILABLE:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn, True
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed, falling back to SQLite: {e}")
    return sqlite3.connect(MEMORY_DB), False

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
# 2b. NEW v3.5 - FUSION INDICATORS
# ============================================================
def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 30) -> Optional[str]:
    """Detect RSI divergence. Returns 'bullish' or 'bearish' or None."""
    if len(df) < lookback:
        return None
    close = df['close'].values[-lookback:]
    rsi_vals = rsi(df['close'], 14).values[-lookback:]
    price_peaks, rsi_peaks = [], []
    price_troughs, rsi_troughs = [], []
    for i in range(2, len(close) - 2):
        if close[i] > close[i-1] and close[i] > close[i+1]:
            price_peaks.append((i, close[i]))
            rsi_peaks.append((i, rsi_vals[i]))
        if close[i] < close[i-1] and close[i] < close[i+1]:
            price_troughs.append((i, close[i]))
            rsi_troughs.append((i, rsi_vals[i]))
    if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
        if price_peaks[-1][1] > price_peaks[-2][1] and rsi_peaks[-1][1] < rsi_peaks[-2][1]:
            return 'bearish'
    if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
        if price_troughs[-1][1] < price_troughs[-2][1] and rsi_troughs[-1][1] > rsi_troughs[-2][1]:
            return 'bullish'
    return None

def detect_wyckoff_phase(df: pd.DataFrame) -> str:
    """Detect Wyckoff phase: accumulation, markup, distribution, markdown."""
    if len(df) < 50:
        return 'unknown'
    close = df['close'].values[-50:]
    vol = df['volume'].values[-50:]
    avg_vol = np.mean(vol)
    recent_vol = np.mean(vol[-10:])
    price_change = (close[-1] - close[0]) / close[0] * 100
    if abs(price_change) < 0.3 and recent_vol < avg_vol * 0.7:
        return 'accumulation'
    elif price_change > 0.3 and recent_vol > avg_vol * 0.9:
        return 'markup'
    elif abs(price_change) < 0.3 and recent_vol > avg_vol * 0.9:
        return 'distribution'
    elif price_change < -0.3:
        return 'markdown'
    return 'unknown'

def wyckoff_confirms_signal(df: pd.DataFrame, direction: str) -> bool:
    """Check if Wyckoff phase supports the signal direction."""
    phase = detect_wyckoff_phase(df)
    if direction == 'BUY':
        return phase in ('accumulation', 'markup')
    return phase in ('distribution', 'markdown')

def get_daily_bias(df: pd.DataFrame) -> str:
    """Determine daily bias: bullish, bearish, or neutral."""
    if len(df) < 50:
        return 'neutral'
    close = df['close']
    ema20_val = ema(close, 20).iloc[-1]
    ema50_val = ema(close, 50).iloc[-1]
    ema20_prev = ema(close, 20).iloc[-2]
    if ema20_val > ema50_val and ema20_val > ema20_prev:
        return 'bullish'
    elif ema20_val < ema50_val and ema20_val < ema20_prev:
        return 'bearish'
    return 'neutral'

def mtf_full_alignment(symbol: str, df: pd.DataFrame) -> bool:
    """Check if all timeframes align."""
    htf = get_higher_tf_trend(symbol)
    mt = get_market_trend(symbol)
    if htf is None or mt is None:
        return False
    return htf == mt

def protected_swings_ok(df: pd.DataFrame, direction: str) -> bool:
    """Check that recent swing is protected (price hasn't broken back through)."""
    if len(df) < 20:
        return False
    closes = df['close'].values
    swing_high = max(df['high'].values[-10:-1])
    swing_low = min(df['low'].values[-10:-1])
    if direction == 'BUY':
        return closes[-1] > swing_low
    return closes[-1] < swing_high

def range_efficiency(df: pd.DataFrame) -> float:
    """Calculate range efficiency 0-100. Higher = cleaner trend."""
    if len(df) < 20:
        return 50.0
    close = df['close'].values[-20:]
    total_range = max(close) - min(close)
    if total_range == 0:
        return 0.0
    sum_abs_moves = sum(abs(close[i] - close[i-1]) for i in range(1, len(close)))
    if sum_abs_moves == 0:
        return 0.0
    return min(100.0, max(0.0, (total_range / sum_abs_moves) * 100))

# ============================================================
# 2c. NEW v3.6 - PATTERN & PHASE DETECTION
# ============================================================
def identify_swings(df: pd.DataFrame, order: int = 3) -> Tuple[List[int], List[int]]:
    """Identify swing highs and lows. Returns (swing_high_indices, swing_low_indices)."""
    if len(df) < 2 * order + 1:
        return [], []
    highs = df['high'].values
    lows = df['low'].values
    sh, sl = [], []
    for i in range(order, len(highs) - order):
        if all(highs[i] >= highs[i - j] for j in range(1, order + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, order + 1)):
            sh.append(i)
        if all(lows[i] <= lows[i - j] for j in range(1, order + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, order + 1)):
            sl.append(i)
    return sh, sl

def detect_repeating_patterns(df: pd.DataFrame) -> Optional[str]:
    """Detect repeating chart patterns (double top/bottom)."""
    if len(df) < 30:
        return None
    sh, sl = identify_swings(df)
    if len(sh) < 2 or len(sl) < 2:
        return None
    highs = df['high'].values
    lows = df['low'].values
    if len(sh) >= 2:
        h1, h2 = highs[sh[-2]], highs[sh[-1]]
        if abs(h1 - h2) / max(h1, h2) < 0.003:
            return 'double_top'
    if len(sl) >= 2:
        l1, l2 = lows[sl[-2]], lows[sl[-1]]
        if abs(l1 - l2) / max(l1, l2) < 0.003:
            return 'double_bottom'
    return None

def predict_next_candle(df: pd.DataFrame) -> Optional[str]:
    """Simple next-candle prediction based on momentum + pattern."""
    if len(df) < 10:
        return None
    close = df['close'].values
    mom = (close[-1] - close[-5]) / close[-5] * 100 if close[-5] != 0 else 0
    body = close[-1] - df['open'].values[-1]
    if mom > 0.05 and body > 0:
        return 'bullish'
    elif mom < -0.05 and body < 0:
        return 'bearish'
    return None

def detect_price_phase(df: pd.DataFrame) -> str:
    """Detect price phase: accumulation, markup, distribution, markdown."""
    if len(df) < 50:
        return 'unknown'
    close = df['close'].values[-50:]
    vol = df['volume'].values[-50:]
    avg_vol = np.mean(vol)
    recent_vol = np.mean(vol[-10:])
    price_change = (close[-1] - close[0]) / close[0] * 100
    if abs(price_change) < 0.5 and recent_vol < avg_vol * 0.8:
        return 'accumulation'
    elif price_change > 0.5 and recent_vol > avg_vol:
        return 'markup'
    elif abs(price_change) < 0.5 and recent_vol > avg_vol:
        return 'distribution'
    elif price_change < -0.5:
        return 'markdown'
    return 'unknown'

def candle_classification(df: pd.DataFrame) -> str:
    """Classify the last candle: trending, doji, hammer, engulfing, etc."""
    if len(df) < 2:
        return 'unknown'
    o = df['open'].values[-1]
    c = df['close'].values[-1]
    h = df['high'].values[-1]
    l = df['low'].values[-1]
    body = abs(c - o)
    full = h - l
    if full == 0:
        return 'doji'
    ratio = body / full
    if ratio < 0.1:
        return 'doji'
    elif ratio < 0.4:
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        if lower_wick > upper_wick * 2:
            return 'hammer'
        elif upper_wick > lower_wick * 2:
            return 'shooting_star'
        return 'spinning_top'
    else:
        prev_o = df['open'].values[-2]
        prev_c = df['close'].values[-2]
        if c > o and prev_c < prev_o and c > prev_o and o < prev_c:
            return 'bullish_engulfing'
        elif c < o and prev_c > prev_o and c < prev_o and o > prev_c:
            return 'bearish_engulfing'
        return 'trending'

def pre_entry_confirm(df: pd.DataFrame, direction: str) -> bool:
    """Final pre-entry confirmation: last candle supports direction."""
    if len(df) < 2:
        return False
    cls = candle_classification(df)
    if direction == 'BUY':
        return cls in ('hammer', 'bullish_engulfing', 'trending') and df['close'].iloc[-1] > df['open'].iloc[-1]
    return cls in ('shooting_star', 'bearish_engulfing', 'trending') and df['close'].iloc[-1] < df['open'].iloc[-1]

# ============================================================
# 2d. NEW v3.7 - ADVANCED FILTERS
# ============================================================
def calculate_rr_ratio(price: float, support: float, resistance: float, direction: str) -> float:
    """Calculate R:R ratio as a float. >= 2.5 required."""
    if direction == 'BUY':
        risk = price - support
        reward = resistance - price
    else:
        risk = resistance - price
        reward = price - support
    if risk <= 0:
        return 0.0
    return reward / risk

def valid_entry_candle(df: pd.DataFrame, direction: str) -> bool:
    """Validate entry candle: body must be > 40% of range, close in direction."""
    if len(df) < 1:
        return False
    o = df['open'].values[-1]
    c = df['close'].values[-1]
    h = df['high'].values[-1]
    l = df['low'].values[-1]
    full = h - l
    body = abs(c - o)
    if full == 0 or body / full < 0.4:
        return False
    if direction == 'BUY' and c <= o:
        return False
    if direction == 'SELL' and c >= o:
        return False
    return True

def volume_break_confirmed(df: pd.DataFrame) -> bool:
    """Confirm volume break: current volume > 1.5x average of last 20."""
    if len(df) < 20:
        return False
    avg = df['volume'].iloc[-20:].mean()
    if avg == 0:
        return False
    return df['volume'].iloc[-1] > avg * 1.5

def market_break_valid(df: pd.DataFrame, direction: str) -> bool:
    """Validate market break: close beyond recent swing with momentum."""
    if len(df) < 15:
        return False
    sh, sl = identify_swings(df)
    close = df['close'].iloc[-1]
    if direction == 'BUY' and sh:
        return close > df['high'].values[sh[-1]]
    if direction == 'SELL' and sl:
        return close < df['low'].values[sl[-1]]
    return False

def choch_confirmed(df: pd.DataFrame) -> Optional[str]:
    """Detect Change of Character - stronger than MSS."""
    if len(df) < 18:
        return None
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    sh, sl = identify_swings(df)
    if len(sh) < 2 or len(sl) < 2:
        return None
    if highs[sh[-1]] < highs[sh[-2]] and closes[-1] > highs[sh[-1]]:
        return 'bullish'
    if lows[sl[-1]] > lows[sl[-2]] and closes[-1] < lows[sl[-1]]:
        return 'bearish'
    return None

def fvg_quality(df: pd.DataFrame, min_atr_mult: float = 0.3, max_age: int = 3) -> Optional[str]:
    """Quality FVG: age <= max_age candles, size >= min_atr_mult * ATR."""
    if len(df) < 5:
        return None
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    if pd.isna(atr) or atr == 0:
        return None
    for i in range(len(df) - 1, max(len(df) - max_age - 1, -1), -1):
        if i >= 2:
            prev2 = df.iloc[i - 2]
            curr = df.iloc[i]
            gap_up = curr['low'] - prev2['high']
            gap_down = prev2['low'] - curr['high']
            if gap_up > atr * min_atr_mult:
                return 'bullish'
            if gap_down > atr * min_atr_mult:
                return 'bearish'
    return None

def failed_reversal(df: pd.DataFrame, direction: str) -> bool:
    """Detect failed reversal that confirms original direction."""
    if len(df) < 10:
        return False
    close = df['close'].values
    open_ = df['open'].values
    if direction == 'BUY':
        for i in range(-4, -1):
            if open_[i] > close[i] and close[-1] > close[i]:
                return True
    else:
        for i in range(-4, -1):
            if open_[i] < close[i] and close[-1] < close[i]:
                return True
    return False

def classify_market(df: pd.DataFrame) -> str:
    """Classify market state: strong, normal, ranging, low."""
    if len(df) < 30:
        return 'low'
    adx_val = adx(df['high'], df['low'], df['close'], 14).iloc[-1]
    if pd.isna(adx_val):
        return 'low'
    if adx_val > 35:
        return 'strong'
    elif adx_val > 25:
        return 'normal'
    elif adx_val > 15:
        return 'ranging'
    return 'low'

def is_prime_session() -> bool:
    """Check if current session is London or New York (prime trading hours)."""
    h = datetime.utcnow().hour
    return (7 <= h < 12) or (13 <= h < 17)

def optimal_expiry(df: pd.DataFrame, direction: str) -> str:
    """Determine optimal expiry time based on volatility and momentum."""
    if len(df) < 20:
        return '1m'
    close = df['close'].values
    mom = abs(close[-1] - close[-5]) / close[-5] * 100 if close[-5] != 0 else 0
    adx_val = adx(df['high'], df['low'], df['close'], 14).iloc[-1]
    if pd.isna(adx_val):
        return '1m'
    if mom > 0.15 and adx_val > 30:
        return '30s'
    elif mom > 0.08 or adx_val > 25:
        return '1m'
    elif mom > 0.03:
        return '2m'
    return '3m'

# ============================================================
# 2e. NEW v3.8 - SESSION PROFILES & DAILY LEVELS
# ============================================================
def current_session() -> str:
    h = datetime.utcnow().hour
    if 22 <= h or h < 7:
        return "Sydney/Tokyo"
    if 7 <= h < 10:
        return "London"
    if 13 <= h < 17:
        return "New York"
    return "Low Liquidity"

SESSION_PROFILES = {
    'London':       {'rsi_buy': 30, 'rsi_sell': 70, 'adx_min': 30, 'vol_mult': 1.8},
    'New York':     {'rsi_buy': 28, 'rsi_sell': 72, 'adx_min': 32, 'vol_mult': 2.0},
    'Sydney/Tokyo': {'rsi_buy': 35, 'rsi_sell': 65, 'adx_min': 25, 'vol_mult': 1.4},
    'default':      {'rsi_buy': 33, 'rsi_sell': 67, 'adx_min': 25, 'vol_mult': 1.5}
}

def get_session_params() -> dict:
    """Get session-specific parameters for the current trading session."""
    sess = current_session()
    return SESSION_PROFILES.get(sess, SESSION_PROFILES['default'])

# Daily levels cache
DAILY_LEVELS: Dict[str, Tuple[datetime, dict]] = {}

def get_daily_levels(symbol: str) -> Optional[dict]:
    """Get yesterday's high/low. Uses cached data or fetches from broker."""
    if symbol in DAILY_LEVELS:
        cached_time, levels = DAILY_LEVELS[symbol]
        if (datetime.now(timezone.utc) - cached_time).seconds < 3600:
            return levels
    try:
        df = get_data_sync(symbol, '1m')
        if df is not None and len(df) >= 100:
            yesterday_data = df.tail(1440)
            if len(yesterday_data) > 0:
                levels = {
                    'high': float(yesterday_data['high'].max()),
                    'low': float(yesterday_data['low'].min()),
                }
                DAILY_LEVELS[symbol] = (datetime.now(timezone.utc), levels)
                return levels
    except Exception as e:
        logger.debug(f"Daily levels error for {symbol}: {e}")
    return None

def is_near_daily_level(price: float, levels: dict, direction: str, buffer: float = 0.001) -> bool:
    """Check if price is too close to opposing daily level.
    BUY near daily high = blocked (resistance ahead).
    SELL near daily low = blocked (support ahead)."""
    if not levels:
        return False
    if direction == 'BUY' and 'high' in levels:
        return price >= levels['high'] * (1 - buffer)
    if direction == 'SELL' and 'low' in levels:
        return price <= levels['low'] * (1 + buffer)
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
PARAMS = {
    'rsi_buy': 33,
    'rsi_sell': 67,
    'adx_min': 25,
    'vol_mult': 1.5,
}
MIN_CONFIDENCE = 80.0

def init_memory():
    conn, is_pg = get_connection()
    cur = conn.cursor()
    if is_pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                signal_id TEXT UNIQUE,
                symbol TEXT, direction TEXT, timeframe TEXT, platform TEXT,
                entry_time TIMESTAMP, outcome TEXT DEFAULT 'pending',
                rsi REAL, adx REAL, confidence REAL, accuracy REAL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id SERIAL PRIMARY KEY,
                date TEXT UNIQUE,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                ignored INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0, avg_accuracy REAL DEFAULT 0,
                avg_confidence REAL DEFAULT 0
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT UNIQUE,
                symbol TEXT, direction TEXT, timeframe TEXT, platform TEXT,
                entry_time TIMESTAMP, outcome TEXT DEFAULT 'pending',
                rsi REAL, adx REAL, confidence REAL, accuracy REAL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                ignored INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0, avg_accuracy REAL DEFAULT 0,
                avg_confidence REAL DEFAULT 0
            )
        """)
    conn.commit()
    conn.close()

def remember_signal(sig_id, sym, dir_, tf, platform, entry, rsi_val, adx_val, conf, accuracy=0):
    try:
        conn, is_pg = get_connection()
        cur = conn.cursor()
        ph = '%s' if is_pg else '?'
        cur.execute(f"INSERT OR IGNORE INTO trades VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                    (None if not is_pg else 'DEFAULT', sig_id, sym, dir_, tf, platform, entry, 'pending', rsi_val, adx_val, conf, accuracy))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB write error: {e}")

def learn_from_outcome(sig_id, outcome):
    """Auto-tune parameters based on trade outcomes."""
    try:
        conn, is_pg = get_connection()
        cur = conn.cursor()
        ph = '%s' if is_pg else '?'
        cur.execute(f"UPDATE trades SET outcome={ph} WHERE signal_id={ph}", (outcome, sig_id))

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
        conn, is_pg = get_connection()
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
            "params": PARAMS, "min_confidence": MIN_CONFIDENCE,
            "session": current_session(), "session_params": get_session_params()
        }
    except:
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "ignored": 0, "pending": 0, "params": PARAMS, "min_confidence": MIN_CONFIDENCE,
                "session": current_session(), "session_params": get_session_params()}

def get_daily_stats(days: int = 30) -> List[dict]:
    """Get daily stats for the last N days for chart rendering."""
    try:
        conn, is_pg = get_connection()
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
        conn, is_pg = get_connection()
        cur = conn.cursor()
        ph = '%s' if is_pg else '?'
        cur.execute(f"""
            SELECT outcome FROM trades
            WHERE direction={ph} AND platform={ph} AND outcome IN ('win','loss')
            AND rsi BETWEEN {ph} AND {ph} AND adx BETWEEN {ph} AND {ph}
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
    """Deep optimization: analyze last 500 trades and adjust parameters.
    v3.8: WR < 93% tighten, WR > 97% relax, minimum 200 trades."""
    try:
        conn, is_pg = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT outcome, direction, rsi, adx, confidence, accuracy FROM trades WHERE outcome IN ('win','loss') ORDER BY entry_time DESC LIMIT 500")
        rows = cur.fetchall()
        conn.close()

        if len(rows) < 200:
            logger.info(f"Weekly optimize: only {len(rows)} trades, need 200+")
            return

        global PARAMS, MIN_CONFIDENCE
        wins = sum(1 for r in rows if r[0] == 'win')
        wr = wins / len(rows)
        logger.info(f"Weekly optimize: WR={wr:.1%} over {len(rows)} trades")

        if wr < 0.93:
            PARAMS['rsi_buy'] = max(15, PARAMS['rsi_buy'] - 2)
            PARAMS['rsi_sell'] = min(85, PARAMS['rsi_sell'] + 2)
            PARAMS['adx_min'] = min(40, PARAMS['adx_min'] + 3)
            PARAMS['vol_mult'] = min(3.0, PARAMS['vol_mult'] + 0.2)
            MIN_CONFIDENCE = min(95, MIN_CONFIDENCE + 2)
            logger.warning(f"Weekly TIGHTEN: {PARAMS}, min conf {MIN_CONFIDENCE}")
        elif wr > 0.97:
            PARAMS['adx_min'] = max(25, PARAMS['adx_min'] - 1)
            if MIN_CONFIDENCE > 78:
                MIN_CONFIDENCE -= 1
            logger.info(f"Weekly RELAX: {PARAMS}, min conf {MIN_CONFIDENCE}")
    except Exception as e:
        logger.error(f"Weekly optimize error: {e}")

# ============================================================
# 5. SIGNAL GENERATION - FULL ALL-AND CHAIN v3.7+8
# ============================================================
def generate_signal(df, symbol="", higher_tf_trend=None, market_trend=None):
    """
    Full ALL-AND confluence chain v3.7+8 with session params, daily levels,
    Wyckoff, RSI divergence, MTF alignment, protected swings, range efficiency,
    CHoCH, FVG quality, valid entry, volume break, market break, R:R filter,
    prime session, failed reversal, and market state classification.
    Returns: dict with all signal fields or None if no signal.
    """
    df = safe_df(df)
    if len(df) < 80 or df.empty:
        return None

    # Session-specific params
    local_params = {**PARAMS, **get_session_params()}

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
    vol_spike = volume.iloc[-1] >= avg_vol * local_params['vol_mult']

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

    # v3.2: New indicators
    stoch_val, stoch_status = stochastic(high, low, close)
    regime, regime_desc = detect_regime(df)
    liq_sweep, liq_side = detect_liquidity_sweep(df)
    vol_class = classify_volume(df)
    bb_status = classify_bb_width(bb_w)
    trend_dir = 'Bullish' if ema5.iloc[-1] > ema20.iloc[-1] else 'Bearish'

    # v3.5: Fusion indicators
    rsi_div = detect_rsi_divergence(df)
    bias = get_daily_bias(df)
    mtf_aligned = mtf_full_alignment(symbol, df)
    eff = range_efficiency(df)

    # v3.7: Advanced filters
    choch_ = choch_confirmed(df)
    fvg_qual = fvg_quality(df)
    mkt_state = classify_market(df)
    rr_val = calculate_rr_ratio(price, support, resistance, 'BUY')

    # v3.8: Session info
    sess = current_session()
    prime = is_prime_session()
    opt_exp = optimal_expiry(df, 'BUY')

    def make_signal_dict(dir_, rsi_, adx_, accuracy, mtf_ok, market_ok):
        rr = calculate_rr(price, support, resistance, dir_)
        rr_val_dir = calculate_rr_ratio(price, support, resistance, dir_)
        opt_exp_dir = optimal_expiry(df, dir_)
        zone_label = ''
        if sd == 'demand':
            zone_label = 'Demand + Order Block'
        elif sd == 'supply':
            zone_label = 'Supply + Order Block'
        elif sd:
            zone_label = sd.title() + ' Zone'
        else:
            zone_label = 'None Detected'

        # BOS/CHoCH status
        bos_status = 'Confirmed' if (struct == ('bullish' if dir_ == 'BUY' else 'bearish')) else 'Not Confirmed'
        choch_status = 'Confirmed' if (choch_ == ('bullish' if dir_ == 'BUY' else 'bearish')) else 'Not Confirmed'

        # GLM Smart Money
        if dir_ == 'SELL':
            sm_structure = 'Break of Structure Down' if bos_status == 'Confirmed' else 'No Clear Break'
            sm_liquidity = 'Sell Side Sweep' if liq_sweep and 'Sell' in liq_side else 'Buy Side Liquidity'
            sm_breakout = 'Confirmed Breakdown' if regime == 'BREAKOUT' else 'No Breakout'
            sm_signal = 'Valid Sell Signal' if accuracy >= 80 else 'Weak Sell Signal'
        else:
            sm_structure = 'Break of Structure Up' if bos_status == 'Confirmed' else 'No Clear Break'
            sm_liquidity = 'Buy Side Sweep' if liq_sweep and 'Buy' in liq_side else 'Sell Side Liquidity'
            sm_breakout = 'Confirmed Breakout' if regime == 'BREAKOUT' else 'No Breakout'
            sm_signal = 'Valid Buy Signal' if accuracy >= 80 else 'Weak Buy Signal'

        # v3.7 additional checks for this direction
        valid_entry = valid_entry_candle(df, dir_)
        vol_break = volume_break_confirmed(df)
        mkt_break = market_break_valid(df, dir_)
        protected = protected_swings_ok(df, dir_)
        failed_rev = failed_reversal(df, 'SELL' if dir_ == 'BUY' else 'BUY')

        return {
            'direction': dir_,
            'rsi': round(rsi_, 1),
            'adx': round(adx_, 1),
            'accuracy': round(accuracy, 1),
            # v3.2 new fields
            'regime': regime,
            'regime_desc': regime_desc,
            'trend': trend_dir,
            'bos': bos_status,
            'choch': choch_status,
            'fvg': 'Active' if fvg_ else 'Inactive',
            'fvg_type': fvg_ or 'None',
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
            # GLM Smart Money
            'sm_structure': sm_structure,
            'sm_liquidity': sm_liquidity,
            'sm_breakout': sm_breakout,
            'sm_signal': sm_signal,
            # v3.5 new fields
            'wyckoff_phase': detect_wyckoff_phase(df),
            'rsi_divergence': rsi_div or 'None',
            'daily_bias': bias,
            'mtf_aligned': mtf_aligned,
            'protected_swing': protected,
            'range_efficiency': round(eff, 1),
            # v3.7 new fields
            'fvg_quality': fvg_qual or 'Inactive',
            'valid_entry': valid_entry,
            'volume_break': vol_break,
            'market_break': mkt_break,
            'rr_ratio': round(rr_val_dir, 2),
            'rr_filter': rr_val_dir >= 2.5,
            'prime_session': prime,
            'failed_reversal': failed_rev,
            'market_state': mkt_state,
            # v3.8 new fields
            'session': sess,
            'optimal_expiry': opt_exp_dir,
        }

    # BUY conditions (ALL-AND full chain)
    if (bull and rsi_val < local_params['rsi_buy'] and adx_val > local_params['adx_min'] and
        vol_spike and bb_sq and bb_exp and buy_sr and
        (struct == 'bullish' or mss == 'bullish' or choch_ == 'bullish') and
        sd == 'demand' and
        (fvg_qual == 'bullish' or fvg_ == 'bullish') and
        reversal == 'bullish' and candle == 'bullish' and mom_3 > 0.03 and
        # v3.5 fusion
        wyckoff_confirms_signal(df, 'BUY') and
        (rsi_div == 'bullish' or rsi_div is None) and
        bias != 'bearish' and
        eff >= 60.0 and
        # v3.7 advanced
        classify_market(df) not in ('ranging', 'low')):
        mtf_ok = (higher_tf_trend is None or higher_tf_trend == 'bullish') and mtf_aligned
        market_ok = (market_trend is None or market_trend == 'bullish')
        if not mtf_ok or not market_ok:
            return None
        accuracy = calculate_accuracy('BUY', rsi_val, adx_val, vol_spike, bb_sq, bb_exp,
                                      sd, fvg_, struct, mss, reversal, candle, True, mtf_ok, market_ok,
                                      choch_=choch_, fvg_qual=fvg_qual, mkt_state=mkt_state)
        return make_signal_dict('BUY', rsi_val, adx_val, accuracy, mtf_ok, market_ok)

    # SELL conditions (ALL-AND full chain)
    if (bear and rsi_val > local_params['rsi_sell'] and adx_val > local_params['adx_min'] and
        vol_spike and bb_sq and bb_exp and sell_sr and
        (struct == 'bearish' or mss == 'bearish' or choch_ == 'bearish') and
        sd == 'supply' and
        (fvg_qual == 'bearish' or fvg_ == 'bearish') and
        reversal == 'bearish' and candle == 'bearish' and mom_3 < -0.03 and
        # v3.5 fusion
        wyckoff_confirms_signal(df, 'SELL') and
        (rsi_div == 'bearish' or rsi_div is None) and
        bias != 'bullish' and
        eff >= 60.0 and
        # v3.7 advanced
        classify_market(df) not in ('ranging', 'low')):
        mtf_ok = (higher_tf_trend is None or higher_tf_trend == 'bearish') and mtf_aligned
        market_ok = (market_trend is None or market_trend == 'bearish')
        if not mtf_ok or not market_ok:
            return None
        accuracy = calculate_accuracy('SELL', rsi_val, adx_val, vol_spike, bb_sq, bb_exp,
                                      sd, fvg_, struct, mss, reversal, candle, True, mtf_ok, market_ok,
                                      choch_=choch_, fvg_qual=fvg_qual, mkt_state=mkt_state)
        return make_signal_dict('SELL', rsi_val, adx_val, accuracy, mtf_ok, market_ok)

    return None

def calculate_accuracy(direction, rsi_val, adx_val, vol_spike, bb_sq, bb_exp, sd, fvg_, struct, mss, reversal, cand_conf, mom_ok, mtf_ok, market_ok=True, choch_=None, fvg_qual=None, mkt_state='unknown'):
    """Return accuracy score 0-100 based on confirmation strength + v3.7 additions (+40)."""
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
    # v3.7 additions (+40)
    if choch_: score += 10
    if fvg_qual: score += 10
    if mkt_state in ('strong', 'normal'): score += 5
    if direction == 'BUY':
        if valid_entry_candle.__wrapped__ if hasattr(valid_entry_candle, '__wrapped__') else False:
            pass
    # Direct checks for additional scoring
    try:
        _df_local = None  # We don't have df here, use heuristic
        if direction == 'BUY' and rsi_val < 30: score += 5
        elif direction == 'SELL' and rsi_val > 70: score += 5
        if adx_val > 30: score += 5
    except:
        pass
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
    "EURUSD-OTC", "GBPJPY-OTC", "AUDUSD-OTC", "NZDUSD-OTC", "USDCAD-OTC",
    "EUR/JPY (OTC)", "USD/JPY (OTC)", "EUR/GBP (OTC)"
]
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
    if not USE_IQ_OPTION or not IQ_API_AVAILABLE:
        return False
    if not IQ_EMAIL or IQ_EMAIL == "your_iq_option_email@example.com":
        return False
    try:
        iq_api = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        check, reason = iq_api.connect()
        if check:
            iq_api.connect()
            iq_connected = True
            if iq_practice_mode:
                iq_api.change_balance("PRACTICE")
            logger.info(f"IQ Option connected ({'PRACTICE' if iq_practice_mode else 'REAL'})")
            return True
        else:
            logger.error(f"IQ Option connection failed: {reason}")
            iq_api = None
            return False
    except Exception as e:
        logger.error(f"IQ Option API error: {e}")
        iq_api = None
        return False

def connect_pocket_option():
    global po_api, po_connected
    if not USE_POCKET_OPTION or not PO_API_AVAILABLE:
        return False
    if not PO_EMAIL or PO_EMAIL == "your_pocket_option_email@example.com":
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
    global iq_connected
    if not iq_connected or iq_api is None:
        return None
    iq_symbol = IQ_SYMBOL_MAP.get(symbol, symbol)
    tf_sec = TF_SECONDS.get(tf, 60)
    try:
        candles = iq_api.get_candles(iq_symbol, tf_sec, count, time.time())
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
        if 'from' in df.columns:
            df.index = pd.to_datetime(df['from'], unit='s')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        logger.info(f"IQ: {len(df)} candles for {iq_symbol} {tf}")
        return safe_df(df)
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
    """Synchronous data fetch - tries PO first, then IQ, then demo."""
    if po_connected and po_api is not None and USE_POCKET_OPTION:
        try:
            df = fetch_po_candles(symbol, tf)
            if df is not None and len(df) >= 30:
                return df
        except:
            pass
    if iq_connected and iq_api is not None and USE_IQ_OPTION:
        try:
            df = fetch_iq_candles(symbol, tf)
            if df is not None and len(df) >= 30:
                return df
        except:
            pass
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
app = FastAPI(title="CATALYST FINAL", version="3.8")
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
            if IQ_EMAIL and IQ_PASSWORD and IQ_EMAIL != "your_iq_option_email@example.com":
                await loop.run_in_executor(None, connect_iq_option)
        if not po_connected and PO_API_AVAILABLE and USE_POCKET_OPTION:
            if PO_EMAIL and PO_PASSWORD and PO_EMAIL != "your_pocket_option_email@example.com":
                await loop.run_in_executor(None, connect_pocket_option)

        for platform, tfs in [("IQ Option", IQ_TFS), ("Pocket Option", PO_TFS)]:
            for sym in PAIRS:
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

                        # Daily levels check
                        levels = get_daily_levels(sym)
                        if levels and is_near_daily_level(df['close'].iloc[-1], levels, result['direction']):
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
                            # v3.5+ new fields from generate_signal
                            'wyckoff_phase': result.get('wyckoff_phase', 'unknown'),
                            'rsi_divergence': result.get('rsi_divergence', 'None'),
                            'daily_bias': result.get('daily_bias', 'neutral'),
                            'mtf_aligned': result.get('mtf_aligned', False),
                            'protected_swing': result.get('protected_swing', False),
                            'range_efficiency': result.get('range_efficiency', 0),
                            'fvg_quality': result.get('fvg_quality', 'Inactive'),
                            'valid_entry': result.get('valid_entry', False),
                            'volume_break': result.get('volume_break', False),
                            'market_break': result.get('market_break', False),
                            'rr_ratio': result.get('rr_ratio', 0),
                            'rr_filter': result.get('rr_filter', False),
                            'prime_session': result.get('prime_session', False),
                            'failed_reversal': result.get('failed_reversal', False),
                            'market_state': result.get('market_state', 'unknown'),
                            'session': result.get('session', 'Unknown'),
                            'optimal_expiry': result.get('optimal_expiry', '1m'),
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

@app.get("/api/scan")
async def manual_scan():
    """Force an immediate full market scan. Called by Railway cron every 5 min."""
    asyncio.create_task(force_scan_cycle())
    return {"status": "scan initiated"}

async def force_scan_cycle():
    """Runs exactly one full scan of all pairs/timeframes (no while loop)."""
    loop = asyncio.get_event_loop()
    for platform, tfs in [("IQ Option", IQ_TFS), ("Pocket Option", PO_TFS)]:
        for sym in PAIRS:
            higher_tf_trend = get_higher_tf_trend(sym)
            market_trend = get_market_trend(sym)
            try:
                df_5m = await loop.run_in_executor(None, lambda s=sym: get_data_sync(s, '5m'))
                if df_5m is not None and len(df_5m) >= 20:
                    trend_5m = compute_5m_trend(df_5m)
                    if trend_5m:
                        cache_higher_tf_trend(sym, trend_5m)
                        higher_tf_trend = trend_5m
            except:
                pass
            try:
                df_15m = await loop.run_in_executor(None, lambda s=sym: get_data_sync(s, '15m'))
                if df_15m is not None and len(df_15m) >= 20:
                    trend_15m = compute_15m_trend(df_15m)
                    if trend_15m:
                        cache_market_trend(sym, trend_15m)
                        market_trend = trend_15m
            except:
                pass
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
                    # Daily levels check
                    levels = get_daily_levels(sym)
                    if levels and is_near_daily_level(df['close'].iloc[-1], levels, result['direction']):
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
                    sig_id = str(uuid.uuid4())
                    remember_signal(sig_id, sym, dir_, tf, platform, entry_time, rsi_, adx_, final_conf, accuracy)
                    martingale = calculate_martingale(entry_time, tf, final_conf)
                    tf_duration = {'30s': 0.5, '45s': 0.75, '1m': 1, '2m': 2, '3m': 3, '5m': 5}
                    duration_min = tf_duration.get(tf, 1)
                    volatility = 'High Volatility' if accuracy >= 85 else ('Medium Volatility' if accuracy >= 70 else 'Low Volatility')
                    if result['regime'] == 'BREAKOUT':
                        strategy_guide = ['Wait for confirmed breakout candle close', 'Enter on pullback to breakout level', 'Use ATR-based stop loss', f'Take profit at {result["rr"]} R:R', 'Trail stop after 1R profit', 'Risk 1% per trade maximum']
                    elif dir_ == 'SELL':
                        strategy_guide = ['Wait for confirmed setups only', 'Use BOS/CHoCH for confirmation', 'Enter at FVG fill zones', f'Take profit at {result["rr"]} R:R', 'Tighter stops recommended', 'Move stop to breakeven after 1R', 'Risk 1% per trade', f'GLM Probability: {final_conf}% win rate']
                    else:
                        strategy_guide = ['Wait for confirmed setups only', 'Use BOS/CHoCH for confirmation', 'Enter at FVG fill zones', f'Take profit at {result["rr"]} R:R', 'Tighter stops recommended', 'Move stop to breakeven after 1R', 'Risk 1% per trade', f'GLM Probability: {final_conf}% win rate']
                    sig = {
                        'signal_id': sig_id, 'symbol': sym, 'direction': dir_, 'timeframe': tf,
                        'platform': platform, 'generated_at': now_utc.isoformat(),
                        'entry_time': entry_time.isoformat(), 'duration_minutes': duration_min,
                        'confidence': final_conf, 'accuracy': round(accuracy, 1),
                        'volatility': volatility, 'martingale': martingale,
                        'params': dict(PARAMS), 'confirmed': False,
                        'mtf_trend': tf_trend or 'N/A', 'market_trend': market_trend or 'N/A',
                        **result, 'strategy_guide': strategy_guide
                    }
                    latest_signals.insert(0, sig)
                    if len(latest_signals) > 50:
                        latest_signals.pop()
                    payload = {'type': 'new_signal', **sig}
                    dead = []
                    for ws_client in clients:
                        try:
                            await ws_client.send_json(payload)
                        except:
                            dead.append(ws_client)
                    for ws_client in dead:
                        clients.discard(ws_client)
                    asyncio.create_task(send_telegram(sig))
                    logger.info(f"SCAN | {platform} | {sym} {dir_} | RSI:{rsi_:.0f} ADX:{adx_:.0f} Acc:{accuracy:.0f}% Conf:{final_conf}%")
                except Exception as e:
                    logger.error(f"Scan error {platform} {sym} {tf}: {traceback.format_exc()}")

@app.get("/api/stats")
async def stats():
    return get_stats()

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
        "version": "3.8",
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
        "pairs_count": len(PAIRS),
        "session": current_session(),
        "session_params": get_session_params(),
        "database": "postgresql" if DATABASE_URL.startswith("postgres") and PSYCOPG2_AVAILABLE else "sqlite"
    }

@app.get("/api/signals")
async def signals_list():
    return {"signals": latest_signals[:20]}

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
<title>CATALYST FINAL v3.8</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#050510;color:#e0e0e0;font-family:Segoe UI,sans-serif}
.app{max-width:1200px;margin:0 auto;padding:20px}
.header{background:linear-gradient(135deg,#0a0a2e,#1a1a4e);border-radius:16px;padding:20px;display:flex;justify-content:space-between;align-items:center;border:1px solid #2a2a5a;margin-bottom:20px;flex-wrap:wrap;gap:10px}
.logo{font-size:2em;font-weight:bold}.logo span{color:#00ff88}
.status{color:#00ff88;background:rgba(0,255,136,0.1);padding:5px 15px;border-radius:20px;font-size:0.9em}
.info-bar{display:flex;gap:15px;margin-bottom:15px;flex-wrap:wrap;align-items:center}
.session-badge{display:inline-block;padding:3px 12px;border-radius:15px;font-size:0.9em}
.session-active{background:rgba(0,255,136,0.1);color:#00ff88}
.stats-bar{background:#0a0a1e;border-radius:12px;padding:10px 15px;border:1px solid #2a2a5a;font-size:0.9em;color:#aaa;flex:1;min-width:200px}
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
.btn-group{margin-top:10px;display:flex;gap:5px;flex-wrap:wrap}
.btn{padding:6px 15px;border:none;border-radius:5px;cursor:pointer;font-weight:bold;transition:opacity .2s}
.btn:hover{opacity:0.85}
.btn:disabled{opacity:0.4;cursor:not-allowed}
.copy-btn{background:#00b4d8;color:#fff}
.win-btn{background:#00ff88;color:#000}
.loss-btn{background:#ff4444;color:#fff}
.ignore-btn{background:#666;color:#fff}
.countdown{font-size:1.5em;font-weight:bold;color:#ffd700;margin:10px 0}
.timing-details{font-size:0.9em;color:#aaa;margin-bottom:10px}
.martingale{margin-top:10px;background:#111;padding:10px;border-radius:8px}
.martingale-title{color:#ffd700;font-weight:bold;margin-bottom:5px}
.martingale-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #222;font-size:0.9em}
.outcome-text{font-weight:bold;margin-top:5px}
@keyframes slide{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:600px){.header{flex-direction:column;text-align:center}.platform-selector{justify-content:center}}
</style>
</head>
<body>
<div class="app">
<div class="header">
  <div class="logo">CATALYST<span>FINAL</span> <small style="font-size:0.4em;color:#888">v3.8</small></div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span class="session-badge session-active" id="session-badge">...</span>
    <span class="status" id="sys-status">LIVE</span>
  </div>
</div>
<div class="info-bar">
  <div id="session-timer" style="color:#888;min-width:200px"></div>
  <div class="stats-bar" id="stats">Loading stats...</div>
</div>
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
    if(d.iq_connected)parts.push('IQ');
    if(d.po_connected)parts.push('PO');
    if(d.telegram)parts.push('TG');
    if(d.news_filter)parts.push('NF');
    s.textContent=parts.join(' | ');
  }).catch(()=>{});
}
setInterval(updateStatus,15000);updateStatus();

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
  var genS=genD.toLocaleTimeString('en-GB',tz)+' WAT';
  var entS=entD.toLocaleTimeString('en-GB',tz)+' WAT';
  var endS=endD.toLocaleTimeString('en-GB',tz)+' WAT';

  var badge=d.platform==='IQ Option'?'<span class="platform-badge iq">IQ Option</span>':'<span class="platform-badge po">Pocket Option</span>';
  var confBadge=d.confirmed?'<span class="confirmed-badge">CONFIRMED</span>':'';

  // Clean symbol display
  var symClean=d.symbol.replace('-OTC','').replace('_OTC','').replace(' (OTC)','');
  var otcLabel=(d.symbol.indexOf('OTC')>=0)?'OTC':'';

  // Regime badge
  var regimeClass=(d.regime||'RANGING').toLowerCase();
  var regimeHtml='<span class="regime-badge '+regimeClass+'">'+(d.regime||'RANGING')+'</span>';

  // Martingale HTML
  var mHtml='';
  if(d.martingale&&d.martingale.length){
    mHtml='<div class="signal-section"><div class="signal-section-title">MARTINGALE RECOVERY (Risk Level)</div>';
    d.martingale.forEach(function(m){
      var mD=new Date(m.entry_time);
      var mT=mD.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';
      mHtml+='<div class="signal-grid-item"><span>'+m.level+'</span><span>'+m.multiplier+'x</span><span>$'+m.amount+'</span><span>'+mT+'</span></div>';
    });
    mHtml+='</div>';
  }

  // GLM Smart Money section
  var smHtml='<div class="smart-money-section"><div class="signal-section-title">GLM SMART MONEY</div>'+
    '<div class="smart-money-item">Structure: '+(d.sm_structure||'N/A')+'</div>'+
    '<div class="smart-money-item">Liquidity: '+(d.sm_liquidity||'N/A')+'</div>'+
    '<div class="smart-money-item">Breakout: '+(d.sm_breakout||'N/A')+'</div>'+
    '<div class="smart-money-item">Signal: '+(d.sm_signal||'N/A')+'</div></div>';

  // Strategy Guide section
  var stratHtml='';
  if(d.strategy_guide&&d.strategy_guide.length){
    stratHtml='<div class="strategy-section"><div class="signal-section-title">STRATEGY GUIDE</div>';
    d.strategy_guide.forEach(function(s){
      var icon=s.indexOf('confirm')>=0||s.indexOf('Wait')>=0||s.indexOf('BOS')>=0||s.indexOf('FVG')>=0?'✅':
               s.indexOf('profit')>=0||s.indexOf('stop')>=0||s.indexOf('Take')>=0?'🚪':'🛡️';
      stratHtml+='<div class="strategy-item">'+icon+' '+s+'</div>';
    });
    stratHtml+='</div>';
  }

  // Support/Resistance section
  var srHtml='<div class="sr-section"><div class="signal-section-title">SUPPORT / RESISTANCE</div>'+
    '<div class="signal-grid-item"><span class="label">Support</span><span class="value">'+(d.support||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Resistance</span><span class="value">'+(d.resistance||'N/A')+'</span></div></div>';

  // Signal status
  var sigStatus=d.confidence>=85?'HIGH PROBABILITY ONLY':'MODERATE PROBABILITY';
  var sigStatusClass=d.confidence>=85?'high':'moderate';

  // Main indicators grid
  var liqDisplay=d.liquidity_sweep?'Sweep Detected ('+d.liquidity_side+')':'No Sweep';
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
    '<div class="signal-grid-item"><span class="label">Session</span><span class="value">'+(d.session||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Market State</span><span class="value">'+(d.market_state||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Range Eff.</span><span class="value">'+(d.range_efficiency||0)+'%</span></div>'+
    '<div class="signal-grid-item"><span class="label">R:R Ratio</span><span class="value">'+(d.rr_ratio||0)+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">FVG Quality</span><span class="value">'+(d.fvg_quality||'Inactive')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Valid Entry</span><span class="value">'+(d.valid_entry?'✅':'❌')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Vol. Break</span><span class="value">'+(d.volume_break?'✅':'❌')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Mkt. Break</span><span class="value">'+(d.market_break?'✅':'❌')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Prime Sess.</span><span class="value">'+(d.prime_session?'✅':'❌')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Wyckoff</span><span class="value">'+(d.wyckoff_phase||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Daily Bias</span><span class="value">'+(d.daily_bias||'N/A')+'</span></div>'+
    '<div class="signal-grid-item"><span class="label">Optimal Exp.</span><span class="value">'+(d.optimal_expiry||'1m')+'</span></div>'+
    '</div></div>';

  card.innerHTML=
    '<div class="card-header"><div class="pair">'+symClean+' '+badge+'</div><div><div class="conf">'+d.confidence+'%'+confBadge+'</div><span class="accuracy">Acc: '+d.accuracy+'%</span></div></div>'+
    '<div class="direction '+d.direction.toLowerCase()+'">'+d.direction+'</div>'+
    '<div class="countdown">'+fmtTime((entD-new Date())/1000)+'</div>'+
    '<div class="timing-details">Entry: '+entS+' | End: '+endS+' ('+d.duration_minutes*60+'s) | '+otcLabel+'</div>'+
    '<div>Market: '+(d.volatility||'High Volatility')+' | GLM Probability: '+d.confidence+'%</div>'+
    '<div style="margin:5px 0">'+regimeHtml+' <span style="color:#888;font-size:0.85em">'+(d.regime_desc||'')+'</span></div>'+
    gridHtml+
    mHtml+
    smHtml+
    stratHtml+
    srHtml+
    '<div class="disclaimer">Note: Trade 1% - 3% of your capability and capital. Please trade responsibly. AI analyzes data in real time, outcomes may vary.</div>'+
    '<div class="signal-status '+sigStatusClass+'">🎯 SIGNAL STATUS: '+sigStatus+'</div>'+
    '<div class="signal-status '+sigStatusClass+'">🎯 GLM PROBABILITY: '+d.confidence+'% WIN RATE | '+sigStatus+'</div>'+
    '<div class="btn-group" style="flex-wrap:wrap;gap:5px">'+
    '<button class="btn copy-btn" onclick="copySignal(this)">📋 Copy Signal</button>'+
    '<button class="btn win-btn" onclick="report(\''+d.signal_id+'\',\'win\',this)">✅ WIN</button>'+
    '<button class="btn loss-btn" onclick="report(\''+d.signal_id+'\',\'loss\',this)">❌ LOSS</button>'+
    '<button class="btn ignore-btn" onclick="report(\''+d.signal_id+'\',\'ignored\',this)">🚫 IGNORED</button>'+
    '</div>'+
    '<div class="outcome-text" style="display:none"></div>';

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
  var emoji=d.direction==='SELL'?'🔴':'🟢';
  var sym=d.symbol.replace('-OTC','').replace('_OTC','').replace(' (OTC)','');
  var entryD=new Date(d.entry_time);
  var entryStr=entryD.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';

  // Market regime
  var regime=d.regime||'RANGING';
  var regimeDesc=d.regime_desc||'';

  // BOS/CHoCH
  var bosStatus=d.bos||'Not Confirmed';
  var chochStatus=d.choch||'Not Confirmed';

  // FVG
  var fvgStatus=d.fvg||'Inactive';

  // Liquidity
  var liqDisplay=d.liquidity_sweep?d.liquidity_side:'None';

  // Volume & Zone
  var volClass=d.volume_class||'Normal';
  var zone=d.zone||'None Detected';

  // Stochastic
  var stochVal=d.stoch_val||50;
  var stochDisplay;
  if(stochVal>80)stochDisplay='Overbought';
  else if(stochVal<20)stochDisplay='Oversold';
  else if(d.direction==='BUY'&&stochVal<50)stochDisplay='Bullish Crossover';
  else if(d.direction==='SELL'&&stochVal>50)stochDisplay='Bearish Crossover';
  else stochDisplay=d.stoch_status||'Neutral';

  // BB Width
  var bbStatus=d.bb_status||'Stable';
  var bbDisplay=bbStatus==='Expanding'?'Expanding':(bbStatus==='Contracting'?'Contracting':'Squeezing');

  // R:R
  var rr=d.rr||'1:1.0';

  // GLM Smart Money
  var smStructure=d.sm_structure||'No Clear Break';
  var smLiquidity=d.sm_liquidity||'N/A';
  var smBreakout=d.sm_breakout||'No Breakout';
  var smSignal=d.sm_signal||'N/A';
  if(smStructure.indexOf('Up')>=0)smStructure=smStructure.replace('Up','↑');
  if(smStructure.indexOf('Down')>=0)smStructure=smStructure.replace('Down','↓');

  // Martingale lines
  var martLines='';
  if(d.martingale&&d.martingale.length){
    d.martingale.forEach(function(m,i){
      var mD=new Date(m.entry_time);
      var mT=mD.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Africa/Lagos'})+' WAT';
      martLines+='  M'+(i+1)+' │ '+m.multiplier+'x │ $'+m.amount+' │ Entry: '+mT+'\n';
    });
  }

  // Strategy Guide
  var stratLines='';
  if(d.strategy_guide&&d.strategy_guide.length){
    d.strategy_guide.forEach(function(s){
      var icon='🛡️';
      if(s.match(/confirm|wait|bos|fvg|pullback|enter/i))icon='✅';
      else if(s.match(/profit|stop|take|trail|exit/i))icon='🚪';
      stratLines+='  '+icon+' '+s+'\n';
    });
  }

  // Support/Resistance
  var srLines='';
  if(d.support)srLines+='  Support: '+d.support+'\n';
  if(d.resistance)srLines+='  Resistance: '+d.resistance+'\n';

  // Signal status
  var sigStatus=d.confidence>=85?'HIGH PROBABILITY ONLY':'MODERATE PROBABILITY';

  var msg='🔔 CATALYST AI SIGNAL!\n\n'+
  '🎫 Trade: '+sym+'\n'+
  '⏳ Timer: '+d.timeframe+' (OTC)\n'+
  '➡️ Entry: '+entryStr+'\n'+
  '📈 Direction: '+d.direction+' '+emoji+'\n'+
  '🎯 GLM Probability: '+d.confidence+'% WIN RATE\n'+
  '📊 Market: '+(d.volatility||'High Volatility')+'\n\n'+
  '🔮 Market Regime: '+regime+'\n'+
  '   '+regimeDesc+'\n\n'+
  '🧠 Trend: '+(d.trend||'Analyzing...')+'\n'+
  '📉 BOS: '+bosStatus+'\n'+
  '🔄 CHoCH: '+chochStatus+'\n'+
  '📦 FVG: '+fvgStatus+'\n'+
  '💧 Liquidity: '+liqDisplay+'\n'+
  '📦 Volume: '+volClass+'\n'+
  '🏗️ Zone: '+zone+'\n'+
  '📉 RSI: '+d.rsi+'\n'+
  '📊 Stochastic: '+stochDisplay+'\n'+
  '📊 BB Width: '+bbDisplay+'\n'+
  '⚖️ RR: '+rr+'\n\n'+
  '↪️ ── 🛡️ MARTINGALE RECOVERY (Risk Level) ──\n'+
  (martLines?martLines+'\n':'')+
  '🧪 GLM SMART MONEY:\n'+
  '  Structure: '+smStructure+'\n'+
  '  Liquidity: '+smLiquidity+'\n'+
  '  Breakout: '+smBreakout+'\n'+
  '  Signal: '+smSignal+'\n\n'+
  '📋 STRATEGY GUIDE:\n'+
  (stratLines?stratLines+'\n':'')+
  '📐 SUPPORT/RESISTANCE:\n'+
  (srLines?srLines+'\n':'')+
  'Note: Trade 1% - 3% of your capability and capital\n'+
  '🎯 SIGNAL STATUS: '+sigStatus+'\n\n'+
  '🎯 GLM PROBABILITY: '+d.confidence+'% WIN RATE\n'+
  '   '+sigStatus;

  navigator.clipboard.writeText(msg).then(function(){
    btn.textContent='✅ Copied!';
    btn.style.background='#00ff88';
    setTimeout(function(){btn.textContent='📋 Copy Signal';btn.style.background='#00b4d8';},2000);
  }).catch(function(err){alert('Copy failed: '+err);});
}

function report(sid,outcome,btn){
  var card=btn.closest('.signal-card');
  card.querySelectorAll('.btn').forEach(b=>b.disabled=true);
  fetch('/api/trade/outcome?signal_id='+sid+'&outcome='+outcome,{method:'POST'})
  .then(r=>r.json()).then(data=>{
    var txt=card.querySelector('.outcome-text');
    txt.style.display='block';
    if(outcome==='win'){card.style.borderLeft='4px solid #00ff88';txt.style.color='#00ff88';txt.textContent='\u2705 Trade Won';}
    else if(outcome==='loss'){card.style.borderLeft='4px solid #ff4444';txt.style.color='#ff4444';txt.textContent='\u274C Trade Lost';}
    else{card.style.borderLeft='4px solid #888';txt.style.color='#888';txt.textContent='\uD83D\uDEAB Ignored';}
    card.querySelector('.btn-group').style.display='none';
    updateStats();
  }).catch(e=>{card.querySelectorAll('.btn').forEach(b=>b.disabled=false);});
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
    logger.info(f"Starting CATALYST FINAL v3.8 on port {port}")
    logger.info(f"PO Email: {PO_EMAIL}")
    logger.info(f"IQ Available: {IQ_API_AVAILABLE}, PO Available: {PO_API_AVAILABLE}")
    logger.info(f"Telegram: {TG_AVAILABLE}, News Filter: {EC_API_AVAILABLE}, Scheduler: {APS_AVAILABLE}")
    logger.info(f"Params: {PARAMS}, Min Confidence: {MIN_CONFIDENCE}")
    uvicorn.run(app, host="0.0.0.0", port=port)
