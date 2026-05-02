"""
Precise Technical Indicator Calculator
No NaN, no Inf — every value is guaranteed valid.
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict
from backend.app.core.auto_fixer import AutoFixer

logger = logging.getLogger(__name__)


class PreciseIndicators:

    @staticmethod
    def rsi(prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices[-period - 1:])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return min(100.0, max(0.0, 100.0 - (100.0 / (1.0 + rs))))

    @staticmethod
    def stoch(high, low, close, k_period=14, d_period=3):
        if len(close) < k_period:
            return 50.0, 50.0
        lowest_low = np.min(low[-k_period:])
        highest_high = np.max(high[-k_period:])
        if highest_high == lowest_low:
            k = 50.0
        else:
            k = 100.0 * (close[-1] - lowest_low) / (highest_high - lowest_low)

        k_vals = []
        for i in range(d_period):
            if len(close) > i + k_period:
                start = -(k_period + i) if i > 0 else -k_period
                end = -i if i > 0 else None
                ll = np.min(low[start:end])
                hh = np.max(high[start:end])
                if hh != ll:
                    k_vals.append(100.0 * (close[-(1 + i)] - ll) / (hh - ll))
        d = float(np.mean(k_vals)) if k_vals else k
        return float(k), float(d)

    @staticmethod
    def adx(high, low, close, period=14):
        if len(close) < period + 1:
            return 0.0
        tr = np.zeros(len(high))
        plus_dm = np.zeros(len(high))
        minus_dm = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
            up = high[i] - high[i - 1]
            down = low[i - 1] - low[i]
            plus_dm[i] = up if (up > down and up > 0) else 0.0
            minus_dm[i] = down if (down > up and down > 0) else 0.0
        atr = pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean()
        plus_di = 100.0 * pd.Series(plus_dm).ewm(alpha=1.0 / period, adjust=False).mean() / atr
        minus_di = 100.0 * pd.Series(minus_dm).ewm(alpha=1.0 / period, adjust=False).mean() / atr
        dx = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx_val = dx.ewm(alpha=1.0 / period, adjust=False).mean()
        v = adx_val.iloc[-1]
        return float(v) if not pd.isna(v) else 0.0

    @staticmethod
    def bb_width(prices, period=20):
        if len(prices) < period:
            return 0.1
        series = pd.Series(prices)
        sma = series.rolling(period).mean().iloc[-1]
        std = series.rolling(period).std().iloc[-1]
        if sma == 0 or pd.isna(sma) or pd.isna(std):
            return 0.1
        upper = sma + 2 * std
        lower = sma - 2 * std
        return float((upper - lower) / sma)

    @staticmethod
    def ema(prices, period):
        if len(prices) < period:
            return float(prices[-1]) if len(prices) > 0 else 0.0
        return float(pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1])

    @staticmethod
    def atr(high, low, close, period=14):
        if len(close) < period:
            return 0.001
        tr = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        atr_val = pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        return float(atr_val) if not pd.isna(atr_val) else 0.001

    @staticmethod
    def calculate_all(data: pd.DataFrame) -> dict:
        """Calculate all indicators with guaranteed valid output."""
        data = AutoFixer.fix_dataframe(data)
        close = data['close'].values
        high = data['high'].values
        low = data['low'].values
        vol = data['volume'].values
        price = float(close[-1]) if len(close) > 0 else 0.0

        rsi_val = PreciseIndicators.rsi(close)
        stoch_k, stoch_d = PreciseIndicators.stoch(high, low, close)
        adx_val = PreciseIndicators.adx(high, low, close)
        bb = PreciseIndicators.bb_width(close)
        bb_prev = PreciseIndicators.bb_width(close[:-1]) if len(close) > 1 else bb
        ema50 = PreciseIndicators.ema(close, 50)
        ema200 = PreciseIndicators.ema(close, 200)
        atr_val = PreciseIndicators.atr(high, low, close)

        # Volume spike
        avg_vol = float(np.mean(vol[-20:-1])) if len(vol) >= 21 else float(np.mean(vol))
        vol_spike = bool(vol[-1] > avg_vol * 1.5) if avg_vol > 0 else False

        # Volume trend
        if len(vol) >= 6:
            recent_avg = np.mean(vol[-3:])
            prev_avg = np.mean(vol[-6:-3])
            if recent_avg > prev_avg * 1.1:
                vol_trend = 'increasing'
            elif recent_avg < prev_avg * 0.9:
                vol_trend = 'decreasing'
            else:
                vol_trend = 'normal'
        else:
            vol_trend = 'normal'

        # Momentum
        momentum = float((close[-1] - close[-10]) / close[-10] * 100) if len(close) >= 10 else 0.0

        # Squeeze
        squeeze = bb < 0.05

        return AutoFixer.fix_indicators({
            'rsi': rsi_val, 'stoch_k': stoch_k, 'stoch_d': stoch_d,
            'adx': adx_val, 'bb_width': bb, 'bb_width_prev': bb_prev,
            'ema50': ema50, 'ema200': ema200, 'atr': atr_val,
            'volatility': bb * 10,
            'volume_spike': vol_spike, 'volume_trend': vol_trend,
            'current_price': price, 'momentum': momentum, 'squeeze': squeeze
        })
