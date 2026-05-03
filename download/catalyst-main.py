"""
CATALYST AI v6.0 – Dual-Engine OTC Signal System
=================================================
Engine 1: OTCScalper       – 5-filter momentum scalper (fast signals)
Engine 2: StrictSignalEngine – 9-filter confluence engine (high-probability)

Both engines run in parallel. The /signal endpoint tries Strict first
(fewer but higher-quality signals), then falls back to Scalper.
Each signal includes the engine source and check details.
"""

import asyncio
import httpx
import os
import json
import numpy as np
import pandas as pd
import pytz
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

# ═══════════════════════════════════════════════════════════════════
#  GLOBAL CONFIG
# ═══════════════════════════════════════════════════════════════════
WAT = pytz.timezone('Africa/Lagos')
API_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://0.0.0.0:8000')

# Platform timeframes
IQ_TIMEFRAMES = ['30s', '45s', '1m', '2m', '3m', '5m']
PO_TIMEFRAMES = ['S3', 'S15', 'S30', 'M1', 'M3', 'M5']

# OTC pairs
OTC_PAIRS = [
    'EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'GBPCAD-OTC',
    'AUDCAD-OTC', 'EURJPY-OTC', 'GBPJPY-OTC', 'USDCAD-OTC', 'XAUUSD-OTC'
]

# Seconds map for all timeframes
TF_SECONDS = {
    '30s': 30, '45s': 45, '1m': 60, '2m': 120, '3m': 180, '5m': 300,
    'S3': 3, 'S15': 15, 'S30': 30, 'M1': 60, 'M3': 180, 'M5': 300
}

# ─── Scalper Config ───
SCALPER_CONFIG = {
    'volume_spike': 1.5,
    'momentum_period': 3,
    'min_momentum_pct': 0.0002,
    'adx_threshold': 20,
    'rsi_limit': 70,
    'rsi_floor': 30,
    'trade_sessions': [(8, 17)]
}

# ─── Strict Confluence Config ───
STRICT_CONFIG = {
    'ADX_THRESHOLD': 25,
    'MOMENTUM_MIN_PCT': 0.0002,
    'VOLUME_SPIKE_MULT': 1.5,
    'RSI_OB': 70,
    'RSI_OS': 30,
    'MTF_MIN_CONFIRM': 2,
    'SR_PROXIMITY': 0.005,
    'NEWS_AVOID_HOURS': [(12, 14)],
    'LIQUIDITY_WINDOW': 20,
    'MARTINGALE': [('M1', 1.5, 1), ('M2', 2.5, 2), ('M3', 4.0, 3)]
}


# ═══════════════════════════════════════════════════════════════════
#  INDICATOR HELPERS (shared by both engines)
# ═══════════════════════════════════════════════════════════════════
def calc_rsi(close: np.ndarray, period: int = 14) -> float:
    delta = np.diff(close)
    gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
    loss = -np.mean(delta[delta < 0]) if any(delta < 0) else 0
    if loss == 0:
        return 100.0
    return float(100 - (100 / (1 + gain / loss)))


def calc_adx(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df['high'], df['low'], df['close']
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
    atr = tr.rolling(period).mean().iloc[-1]
    if atr == 0 or np.isnan(atr):
        return 0.0
    up = high.diff().clip(lower=0)
    down = -low.diff().clip(upper=0)
    di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
    di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) != 0 else 0
    return float(dx)


def is_trade_session() -> bool:
    now = datetime.now(pytz.UTC)
    return any(start <= now.hour < end for (start, end) in SCALPER_CONFIG['trade_sessions'])


def is_news_safe() -> bool:
    now = datetime.now(pytz.UTC)
    for start, end in STRICT_CONFIG['NEWS_AVOID_HOURS']:
        if start <= now.hour < end:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════
#  ENGINE 1: OTC SCALPER (5 filters – fast momentum signals)
# ═══════════════════════════════════════════════════════════════════
class OTCScalper:
    def generate_signal(self, df: pd.DataFrame, pair: str, timeframe: str, platform: str) -> Optional[Dict]:
        if len(df) < 10:
            return None
        close = df['close'].values
        volume = df.get('volume', pd.Series([1] * len(df))).values

        # 1. Volume spike
        avg_vol = np.mean(volume[-10:-1])
        vol_pass = volume[-1] >= avg_vol * SCALPER_CONFIG['volume_spike']
        if not vol_pass:
            return None

        # 2. Momentum
        if len(close) < 4:
            return None
        pct = (close[-1] / close[-4] - 1)
        if abs(pct) < SCALPER_CONFIG['min_momentum_pct']:
            return None
        direction = 'BUY' if pct > 0 else 'SELL'

        # 3. RSI guard
        rsi = calc_rsi(close, 14)
        rsi_pass = True
        if direction == 'BUY' and rsi > SCALPER_CONFIG['rsi_limit']:
            rsi_pass = False
        if direction == 'SELL' and rsi < SCALPER_CONFIG['rsi_floor']:
            rsi_pass = False
        if not rsi_pass:
            return None

        # 4. ADX trend
        adx = calc_adx(df, 14)
        adx_pass = adx >= SCALPER_CONFIG['adx_threshold']
        if not adx_pass:
            return None

        # 5. Session gate
        if not is_trade_session():
            return None

        # Build signal
        now = datetime.now(pytz.UTC)
        duration = TF_SECONDS.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(close[-1])
        confidence = min(85, int(abs(pct) * 200000))

        checks = {
            'volume_spike': bool(vol_pass),
            'momentum': True,
            'rsi_guard': rsi_pass,
            'adx_trend': adx_pass,
            'session': True
        }

        martingale = self._build_martingale(entry_time)
        formatted = self._format_signal(
            direction, pair, platform, timeframe, entry_price,
            entry_time, expiry, confidence, adx, rsi, martingale
        )

        return {
            'engine': 'SCALPER',
            'formatted_signal': formatted,
            'direction': direction,
            'entry_price': entry_price,
            'confidence': confidence,
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform,
            'martingale': martingale,
            'checks': checks,
            'indicators': {'adx': round(adx, 1), 'rsi': round(rsi, 1)}
        }

    def _build_martingale(self, entry_time: datetime) -> List[Dict]:
        ent_wat = entry_time.astimezone(WAT)
        result = []
        for lvl, mult, delay in STRICT_CONFIG['MARTINGALE']:
            t = ent_wat + timedelta(minutes=delay)
            result.append({
                'level': lvl, 'multiplier': mult,
                'amount': round(mult, 2),
                'entry_time': t.strftime('%H:%M')
            })
        return result

    def _format_signal(self, direction, pair, platform, timeframe,
                       entry_price, entry_time, expiry, confidence,
                       adx, rsi, martingale) -> str:
        ent_wat = entry_time.astimezone(WAT)
        color = "\U0001f7e2" if direction == 'BUY' else "\U0001f534"
        arrow = "\u25b2" if direction == 'BUY' else "\u25bc"
        lines = [
            "\u2501" * 24,
            f"\U0001f525 SCALPER SIGNAL ({platform.upper()})",
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
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════
#  ENGINE 2: STRICT CONFLUENCE ENGINE (9 filters – high probability)
# ═══════════════════════════════════════════════════════════════════
class SupplyDemand:
    """S/R detection using rolling highs/lows"""
    @staticmethod
    def get_key_levels(df: pd.DataFrame) -> Dict[str, float]:
        if len(df) < 20:
            return {}
        return {
            'resistance': float(df['high'].rolling(20).max().iloc[-1]),
            'support': float(df['low'].rolling(20).min().iloc[-1])
        }

    @staticmethod
    def is_favorable(current_price: float, levels: Dict[str, float], direction: str) -> bool:
        if not levels:
            return False
        if direction == 'BUY' and 'support' in levels:
            return abs(current_price - levels['support']) / current_price < STRICT_CONFIG['SR_PROXIMITY']
        if direction == 'SELL' and 'resistance' in levels:
            return abs(levels['resistance'] - current_price) / current_price < STRICT_CONFIG['SR_PROXIMITY']
        return False


def get_trend_structure(df: pd.DataFrame) -> str:
    """BULLISH, BEARISH, or CONSOLIDATION based on swing comparison"""
    if len(df) < 10:
        return 'CONSOLIDATION'
    highs = df['high'].values
    lows = df['low'].values
    prev_high = max(highs[-10:-5])
    prev_low = min(lows[-10:-5])
    recent_high = max(highs[-5:])
    recent_low = min(lows[-5:])
    if recent_high > prev_high * 1.0005 and recent_low > prev_low * 0.9995:
        return 'BULLISH'
    elif recent_high < prev_high * 0.9995 and recent_low < prev_low * 1.0005:
        return 'BEARISH'
    return 'CONSOLIDATION'


def mtf_aligned(df_dict: Dict[str, pd.DataFrame], direction: str) -> bool:
    """At least 2 of 3 timeframes have EMA50 > EMA200 (BUY) or EMA50 < EMA200 (SELL)"""
    count = 0
    for tf in ['1m', '3m', '5m']:
        if tf in df_dict and len(df_dict[tf]) >= 200:
            df = df_dict[tf]
            ema50 = df['close'].ewm(span=50).mean().iloc[-1]
            ema200 = df['close'].ewm(span=200).mean().iloc[-1]
            if direction == 'BUY' and ema50 > ema200:
                count += 1
            elif direction == 'SELL' and ema50 < ema200:
                count += 1
    return count >= STRICT_CONFIG['MTF_MIN_CONFIRM']


def detect_liquidity_sweep(df: pd.DataFrame) -> Optional[str]:
    """Returns 'buy_side' or 'sell_side' if a sweep with volume is detected"""
    if len(df) < STRICT_CONFIG['LIQUIDITY_WINDOW']:
        return None
    highs = df['high'].values
    lows = df['low'].values
    vol = df.get('volume', pd.Series([1] * len(df))).values
    recent_high = np.max(highs[-STRICT_CONFIG['LIQUIDITY_WINDOW']:])
    recent_low = np.min(lows[-STRICT_CONFIG['LIQUIDITY_WINDOW']:])
    avg_vol = np.mean(vol[-20:])
    cur_vol = vol[-1]
    if cur_vol < avg_vol * STRICT_CONFIG['VOLUME_SPIKE_MULT']:
        return None
    if highs[-1] > recent_high:
        return 'buy_side'
    if lows[-1] < recent_low:
        return 'sell_side'
    return None


def has_candle_confirmation(df: pd.DataFrame, direction: str) -> bool:
    """Check for engulfing, hammer, or shooting star"""
    if len(df) < 2:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last['close'] - last['open'])
    if body == 0:
        return False
    if direction == 'BUY':
        # Bullish engulfing
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['open']:
            return True
        # Hammer
        lower_wick = min(last['open'], last['close']) - last['low']
        if last['close'] > last['open'] and lower_wick > 2 * body:
            return True
    else:
        # Bearish engulfing
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['open']:
            return True
        # Shooting star
        upper_wick = last['high'] - max(last['open'], last['close'])
        if last['close'] < last['open'] and upper_wick > 2 * body:
            return True
    return False


class StrictSignalEngine:
    def __init__(self):
        self.sr = SupplyDemand()

    def check_all(self, df_1m: pd.DataFrame, df_3m: pd.DataFrame,
                  df_5m: pd.DataFrame, direction: str, pair: str) -> Tuple[bool, Dict]:
        details = {}
        checks = {}

        # 1. ADX >= 25
        adx = calc_adx(df_1m)
        checks['adx'] = bool(adx >= STRICT_CONFIG['ADX_THRESHOLD'])
        details['adx'] = round(adx, 1)

        # 2. Trend Structure
        structure = get_trend_structure(df_1m)
        details['structure'] = structure
        if direction == 'BUY':
            checks['trend_structure'] = structure == 'BULLISH'
        else:
            checks['trend_structure'] = structure == 'BEARISH'

        # 3. MTF Confirmation
        df_dict = {'1m': df_1m, '3m': df_3m, '5m': df_5m}
        checks['mtf'] = bool(mtf_aligned(df_dict, direction))

        # 4. News filter
        checks['news'] = is_news_safe()

        # 5. Candle confirmation
        checks['candle'] = bool(has_candle_confirmation(df_1m, direction))

        # 6. S/R zone
        levels = self.sr.get_key_levels(df_1m)
        price = float(df_1m['close'].iloc[-1])
        checks['sr_zone'] = bool(self.sr.is_favorable(price, levels, direction))
        details['sr_levels'] = levels

        # 7. Liquidity sweep
        sweep = detect_liquidity_sweep(df_1m)
        checks['liquidity'] = (direction == 'BUY' and sweep == 'sell_side') or \
                              (direction == 'SELL' and sweep == 'buy_side')

        # 8. Volume spike
        if len(df_1m) >= 20 and df_1m['volume'].rolling(20).mean().iloc[-1] > 0:
            vol_ratio = float(df_1m['volume'].iloc[-1] / df_1m['volume'].rolling(20).mean().iloc[-1])
        else:
            vol_ratio = 1.0
        checks['volume_spike'] = bool(vol_ratio >= STRICT_CONFIG['VOLUME_SPIKE_MULT'])
        details['vol_ratio'] = round(vol_ratio, 2)

        # 9. Momentum
        if len(df_1m) < 4:
            return False, details
        pct = (df_1m['close'].iloc[-1] / df_1m['close'].iloc[-4] - 1)
        checks['momentum'] = bool(abs(pct) >= STRICT_CONFIG['MOMENTUM_MIN_PCT'])
        details['momentum_pct'] = round(pct * 100, 4)

        # RSI for display
        rsi = calc_rsi(df_1m['close'].values, 14)
        details['rsi'] = round(rsi, 1)

        # All must pass
        passed = all(checks.values())
        details['checks'] = checks
        return passed, details

    def generate_signal(self, market_data: Dict[str, pd.DataFrame], pair: str,
                        platform: str, timeframe: str) -> Optional[Dict]:
        df_1m = market_data.get('1m')
        df_3m = market_data.get('3m')
        df_5m = market_data.get('5m')
        if any(df is None or len(df) < 30 for df in [df_1m, df_3m, df_5m]):
            return None

        # Determine direction from short-term momentum
        pct = (df_1m['close'].iloc[-1] / df_1m['close'].iloc[-4] - 1)
        direction = 'BUY' if pct > 0 else 'SELL'

        passed, details = self.check_all(df_1m, df_3m, df_5m, direction, pair)
        if not passed:
            # Try opposite direction
            opp = 'SELL' if direction == 'BUY' else 'BUY'
            passed2, details2 = self.check_all(df_1m, df_3m, df_5m, opp, pair)
            if passed2:
                direction = opp
                details = details2
            else:
                return None

        # Timing
        now = datetime.now(pytz.UTC)
        duration = TF_SECONDS.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)
        entry_price = float(df_1m['close'].iloc[-1])
        confidence = 90  # All 9 hard filters passed

        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in STRICT_CONFIG['MARTINGALE']:
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
            f"\U0001f3af STRICT SIGNAL ({platform.upper()})",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {details.get('adx', 0):.1f} | RSI: {details.get('rsi', 0):.1f} | Structure: {details.get('structure', '')}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500"
        ]
        for m in martingale:
            lines.append(f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}")
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 9/9 confluence passed", "\u2501" * 24]

        return {
            'engine': 'STRICT',
            'formatted_signal': '\n'.join(lines),
            'direction': direction,
            'entry_price': entry_price,
            'confidence': confidence,
            'expiry': expiry.isoformat(),
            'timeframe': timeframe,
            'platform': platform,
            'martingale': martingale,
            'checks': details['checks'],
            'indicators': {
                'adx': details.get('adx', 0),
                'rsi': details.get('rsi', 0),
                'structure': details.get('structure', ''),
                'vol_ratio': details.get('vol_ratio', 0),
                'momentum_pct': details.get('momentum_pct', 0)
            }
        }


# ═══════════════════════════════════════════════════════════════════
#  DATA SIMULATION (replace with real live feed in production)
# ═══════════════════════════════════════════════════════════════════
def simulate_df(pair: str, periods: int = 100) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.now(), periods=periods, freq='1min')
    np.random.seed(hash(pair) % 2**32)
    trend = np.linspace(0, 0.0003, periods) + np.random.randn(periods) * 0.0001
    close = 1.0 + trend
    if 'JPY' in pair:
        close = 148.0 + trend * 100
    elif 'XAU' in pair:
        close = 2350.0 + trend * 10000
    elif 'GBP' in pair or 'CAD' in pair:
        close = 1.35 + trend
    elif 'AUD' in pair:
        close = 0.65 + trend

    spread = 0.0005 if 'XAU' not in pair else 0.5
    return pd.DataFrame({
        'open': close - 0.0002,
        'high': close + spread,
        'low': close - spread,
        'close': close,
        'volume': np.random.randint(50, 200, periods)
    })


def simulate_mtf_data(pair: str) -> Dict[str, pd.DataFrame]:
    """Generate multi-timeframe data for the strict engine"""
    def make_df(n_periods):
        np.random.seed(hash(pair) % 2**32 + n_periods)
        trend = np.linspace(0, 0.0003, n_periods) + np.random.randn(n_periods) * 0.0001
        close = 1.0 + trend
        if 'JPY' in pair:
            close = 148.0 + trend * 100
        elif 'XAU' in pair:
            close = 2350.0 + trend * 10000
        elif 'GBP' in pair or 'CAD' in pair:
            close = 1.35 + trend
        elif 'AUD' in pair:
            close = 0.65 + trend
        spread = 0.0005 if 'XAU' not in pair else 0.5
        return pd.DataFrame({
            'open': close - 0.0002,
            'high': close + spread,
            'low': close - spread,
            'close': close,
            'volume': np.random.randint(50, 200, n_periods)
        })
    return {
        '1m': make_df(200),
        '3m': make_df(200),
        '5m': make_df(200)
    }


# ═══════════════════════════════════════════════════════════════════
#  KEEP ALIVE
# ═══════════════════════════════════════════════════════════════════
async def keep_alive():
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(f"{API_URL}/health", timeout=10)
                print(f"[keep-alive] ping ok ({r.status_code})")
            except Exception as e:
                print(f"[keep-alive] ping failed: {e}")
            await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()


# ═══════════════════════════════════════════════════════════════════
#  FASTAPI APP
# ═══════════════════════════════════════════════════════════════════
app = FastAPI(lifespan=lifespan, title="CATALYST AI", version="6.0")
scalper = OTCScalper()
strict_engine = StrictSignalEngine()
latest_signals: list = []


# ═══════════════════════════════════════════════════════════════════
#  EMBEDDED FRONTEND
# ═══════════════════════════════════════════════════════════════════
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

/* Header */
.header{display:flex;justify-content:space-between;align-items:center;padding:14px 0;margin-bottom:12px;border-bottom:1px solid #1a1f2e}
.logo{font-size:1.4em;font-weight:bold;color:#00ff88;letter-spacing:-0.5px}
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

/* Engine Toggle */
.engine-toggle{display:flex;justify-content:center;gap:6px;margin-bottom:10px}
.eng-btn{padding:6px 16px;border-radius:16px;border:1px solid #2a2f3d;background:#131829;color:#aaa;font-size:.78em;cursor:pointer;transition:all .2s;font-weight:500}
.eng-btn.active{border-color:#00ff88;color:#00ff88;background:rgba(0,255,136,.08);font-weight:700}
.eng-btn .badge{display:inline-block;padding:1px 6px;border-radius:8px;font-size:.7em;margin-left:4px;font-weight:700}
.eng-btn .badge.strict{background:rgba(0,255,136,.15);color:#00ff88}
.eng-btn .badge.scalper{background:rgba(255,215,0,.15);color:#ffd700}

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
.signal-card.strict-buy{border-color:#00ff88;box-shadow:0 0 20px rgba(0,255,136,.08)}
.signal-card.strict-sell{border-color:#ff5252;box-shadow:0 0 20px rgba(255,82,82,.08)}
.signal-card.no-signal{border-color:#333;background:#0d1117;text-align:center;padding:40px 20px}
@keyframes fadeSlide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.dir-row{display:flex;align-items:center;justify-content:space-between;margin:8px 0}
.direction{font-size:1.8rem;font-weight:bold}
.direction.buy{color:#00ff88}
.direction.sell{color:#ff5252}
.pair-name{font-size:1.1em;font-weight:600;color:#fff}
.engine-tag{display:inline-block;padding:2px 10px;border-radius:10px;font-size:.7em;font-weight:700;margin-left:6px}
.engine-tag.strict{background:rgba(0,255,136,.12);color:#00ff88}
.engine-tag.scalper{background:rgba(255,215,0,.12);color:#ffd700}

/* Detail Row */
.detail-row{display:flex;justify-content:space-between;margin:5px 0;font-size:.85em;color:#aaa}
.detail-row .val{color:#e0e0e0;font-weight:500}

/* Confidence Bar */
.confidence-bar{width:100%;height:6px;background:#1e2436;border-radius:3px;margin:10px 0 4px;overflow:hidden}
.confidence-fill{height:100%;border-radius:3px;transition:width .5s}
.confidence-fill.high{background:linear-gradient(90deg,#00ff88,#00cc6a)}
.confidence-fill.med{background:linear-gradient(90deg,#ffd700,#ffaa00)}
.confidence-fill.low{background:linear-gradient(90deg,#ff5252,#cc0000)}
.conf-label{font-size:.75em;color:#888;text-align:right}

/* Check Badges */
.checks-row{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}
.check-badge{padding:3px 8px;border-radius:8px;font-size:.68em;font-weight:600;border:1px solid}
.check-badge.pass{background:rgba(0,255,136,.06);color:#00ff88;border-color:rgba(0,255,136,.2)}
.check-badge.fail{background:rgba(255,68,68,.06);color:#ff5252;border-color:rgba(255,68,68,.2)}
.check-badge.strict-only{background:rgba(255,215,0,.06);color:#ffd700;border-color:rgba(255,215,0,.2)}

/* Martingale */
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
    <div class="logo">CATALYST<span>AI</span> <span style="font-size:.5em;color:#888">v6.0</span></div>
    <div class="status-pill" id="status">Connecting</div>
  </div>

  <div class="wake-banner" id="wakeBanner">
    <div class="spinner"></div>
    <span id="wakeText">Backend is waking up...</span>
  </div>

  <!-- Engine Toggle -->
  <div class="engine-toggle">
    <div class="eng-btn active" data-engine="strict" onclick="setEngine(this,'strict')">STRICT <span class="badge strict">9/9</span></div>
    <div class="eng-btn" data-engine="scalper" onclick="setEngine(this,'scalper')">SCALPER <span class="badge scalper">5/5</span></div>
    <div class="eng-btn" data-engine="both" onclick="setEngine(this,'both')">BOTH</div>
  </div>

  <!-- Platform Tabs -->
  <div class="platform-tabs">
    <div class="ptab active" data-platform="iq" onclick="setPlatform(this,'iq')">IQ Option</div>
    <div class="ptab" data-platform="pocket" onclick="setPlatform(this,'pocket')">Pocket Option</div>
  </div>

  <!-- Timeframe Tabs -->
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
const API = window.location.origin;
const PAIRS = ['EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','GBPCAD-OTC','AUDCAD-OTC','EURJPY-OTC','GBPJPY-OTC','USDCAD-OTC','XAUUSD-OTC'];
const IQ_TFS = ['30s','45s','1m','2m','3m','5m'];
const PO_TFS = ['S3','S15','S30','M1','M3','M5'];

let platform = 'iq';
let tf = '1m';
let engineMode = 'strict';
let activePair = PAIRS[0];
let signalCache = {};

// ── fetchWithRetry ──
async function fetchWithRetry(url, retries = 5) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        if (i > 0) { hideWake(); }
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

// ── UI Helpers ──
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
function setEngine(btn, mode) {
  document.querySelectorAll('.eng-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  engineMode = mode;
  fetchSignal();
}
function setPlatform(btn, p) {
  document.querySelectorAll('.ptab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  platform = p;
  buildTfTabs();
  fetchSignal();
}

// ── Timeframe Tabs ──
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

// ── Pair Tabs ──
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

// ── Fetch Signal ──
async function fetchSignal() {
  try {
    const res = await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${activePair}&timeframe=${tf}&engine=${engineMode}`);
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
      const res = await fetchWithRetry(`${API}/signal?platform=${platform}&pair=${p}&timeframe=${tf}&engine=${engineMode}`);
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

// ── Render Signal ──
function renderSignal(s) {
  const cont = document.getElementById('signalsContainer');
  if (!s || !s.formatted_signal) { renderNoSignal('No momentum setup'); return; }

  const cls = s.direction.toLowerCase();
  const isStrict = s.engine === 'STRICT';
  const cardCls = isStrict ? 'strict-' + cls : cls;
  const confClass = s.confidence >= 70 ? 'high' : s.confidence >= 50 ? 'med' : 'low';
  const engineTag = isStrict
    ? '<span class="engine-tag strict">STRICT 9/9</span>'
    : '<span class="engine-tag scalper">SCALPER 5/5</span>';

  // Check badges
  let checksHtml = '';
  if (s.checks) {
    const strictOnlyChecks = ['adx','trend_structure','mtf','news','candle','sr_zone','liquidity'];
    checksHtml = '<div class="checks-row">';
    for (const [key, val] of Object.entries(s.checks)) {
      const label = key.replace(/_/g,' ').toUpperCase();
      const isStrictOnly = strictOnlyChecks.includes(key);
      const badgeCls = val ? 'pass' : 'fail';
      const extra = isStrictOnly && !isStrict ? ' strict-only' : '';
      checksHtml += `<span class="check-badge ${badgeCls}${extra}">${val ? '&#10003;' : '&#10007;'} ${label}</span>`;
    }
    checksHtml += '</div>';
  }

  // Martingale
  let martHtml = '';
  if (s.martingale && s.martingale.length) {
    martHtml = '<div class="martingale"><div class="mart-title">\u{1F6E1}\uFE0F RECOVERY</div>';
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

  const emoji = cls === 'buy' ? '\u{1F7E2}' : '\u{1F534}';
  const arrow = cls === 'buy' ? '\u25B2' : '\u25BC';

  cont.innerHTML =
    '<div class="signal-card ' + cardCls + '">' +
      '<div class="dir-row">' +
        '<span class="direction ' + cls + '">' + emoji + ' ' + s.direction + ' ' + arrow + '</span>' +
        '<span class="pair-name">' + s.platform.toUpperCase() + ' \u00B7 ' + (s.pair || activePair).replace('-OTC','') + engineTag + '</span>' +
      '</div>' +
      '<div class="detail-row"><span>Entry Price</span><span class="val">' + (s.entry_price ? s.entry_price.toFixed(5) : '--') + '</span></div>' +
      '<div class="detail-row"><span>Expiry</span><span class="val">' + s.timeframe + '</span></div>' +
      '<div class="detail-row"><span>ADX</span><span class="val">' + (s.indicators ? s.indicators.adx : '--') + '</span></div>' +
      '<div class="detail-row"><span>RSI</span><span class="val">' + (s.indicators ? s.indicators.rsi : '--') + '</span></div>' +
      (isStrict && s.indicators && s.indicators.structure ? '<div class="detail-row"><span>Structure</span><span class="val">' + s.indicators.structure + '</span></div>' : '') +
      (isStrict && s.indicators && s.indicators.vol_ratio ? '<div class="detail-row"><span>Vol Ratio</span><span class="val">' + s.indicators.vol_ratio + 'x</span></div>' : '') +
      checksHtml +
      '<div class="confidence-bar"><div class="confidence-fill ' + confClass + '" style="width:' + s.confidence + '%"></div></div>' +
      '<div class="conf-label">' + s.confidence + '% confidence</div>' +
      martHtml +
      '<div class="risk-note">\u26A0\uFE0F Risk 1% only \u00B7 ' + (isStrict ? '9/9 confluence passed' : 'Scalp & exit') + '</div>' +
      '<button class="copy-btn" onclick="navigator.clipboard.writeText(\`' + s.formatted_signal.replace(/`/g,"\\`").replace(/\\/g,"\\\\") + '\`)">\u{1F4CB} Copy Signal</button>' +
    '</div>';
}

function renderNoSignal(msg) {
  document.getElementById('signalsContainer').innerHTML =
    '<div class="signal-card no-signal">' +
      '<div style="font-size:2em;margin-bottom:10px">\u23F3</div>' +
      '<div style="color:#888">' + msg + '</div>' +
    '</div>';
}

// ── Init ──
buildTfTabs();
buildPairTabs();
fetchSignal();
setInterval(fetchSignal, 15000);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {
        "status": "online",
        "version": "6.0",
        "engines": ["SCALPER", "STRICT"],
        "platforms": {"iq": IQ_TIMEFRAMES, "pocket": PO_TIMEFRAMES},
        "pairs": OTC_PAIRS,
        "signals_cached": len(latest_signals),
    }


@app.get("/signal")
async def get_signal(
    platform: str = "iq",
    pair: str = "EURUSD-OTC",
    timeframe: str = "1m",
    engine: str = "strict"
):
    """
    Generate a signal using the selected engine.

    Engine modes:
      - strict:  Try StrictSignalEngine first (9/9 confluence) — highest accuracy
      - scalper: Use OTCScalper only (5/5 momentum) — faster, more signals
      - both:    Try strict first, fall back to scalper if no strict signal
    """
    # Validate platform
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")

    # Validate timeframe
    valid_tfs = IQ_TIMEFRAMES if platform == 'iq' else PO_TIMEFRAMES
    if timeframe not in valid_tfs:
        raise HTTPException(400, f"Invalid timeframe for {platform}. Use one of: {valid_tfs}")

    signal = None

    # ─── STRICT ENGINE ───
    if engine in ('strict', 'both'):
        market_data = simulate_mtf_data(pair)
        signal = strict_engine.generate_signal(market_data, pair, platform, timeframe)

    # ─── SCALPER ENGINE (fallback or primary) ───
    if signal is None and engine in ('scalper', 'both'):
        df = simulate_df(pair, 100)
        signal = scalper.generate_signal(df, pair, timeframe, platform)

    # ─── NO SIGNAL ───
    if not signal:
        return {
            "formatted_signal": None,
            "direction": None,
            "message": f"No {'strict' if engine == 'strict' else 'momentum'} setup detected for {pair}",
            "pair": pair,
            "platform": platform,
            "timeframe": timeframe,
            "confidence": 0,
            "engine": engine.upper()
        }

    signal["pair"] = pair
    latest_signals.insert(0, signal)
    if len(latest_signals) > 50:
        latest_signals.pop()

    return signal


@app.get("/signal/all")
async def scan_all(platform: str = "iq", timeframe: str = "1m", engine: str = "strict"):
    """Scan all OTC pairs for signals."""
    # Validate
    if platform not in ('iq', 'pocket'):
        raise HTTPException(400, "platform must be 'iq' or 'pocket'")
    valid_tfs = IQ_TIMEFRAMES if platform == 'iq' else PO_TIMEFRAMES
    if timeframe not in valid_tfs:
        raise HTTPException(400, f"Invalid timeframe. Use: {valid_tfs}")

    results = []
    for pair in OTC_PAIRS:
        signal = None
        if engine in ('strict', 'both'):
            market_data = simulate_mtf_data(pair)
            signal = strict_engine.generate_signal(market_data, pair, platform, timeframe)
        if signal is None and engine in ('scalper', 'both'):
            df = simulate_df(pair, 100)
            signal = scalper.generate_signal(df, pair, timeframe, platform)
        if signal:
            signal["pair"] = pair
            results.append(signal)

    return {"count": len(results), "signals": results}


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
