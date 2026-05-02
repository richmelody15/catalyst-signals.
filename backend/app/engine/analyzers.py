"""
Market Structure, Supply/Demand Zone, and Liquidity Analyzers
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict, List
from backend.app.core.auto_fixer import AutoFixer

logger = logging.getLogger(__name__)


class StructureAnalyzer:
    """Smart Money Concepts market structure analysis."""

    @staticmethod
    def analyze(data: pd.DataFrame) -> dict:
        data = AutoFixer.fix_dataframe(data)
        highs = data['high'].values
        lows = data['low'].values
        closes = data['close'].values

        trend = 'neutral'
        bos = False
        choch = False

        if len(highs) >= 20:
            # Swing detection
            swing_high = []
            swing_low = []
            for i in range(5, len(highs) - 5):
                if all(highs[i] >= highs[i - j] for j in range(1, 6)) and \
                   all(highs[i] >= highs[i + j] for j in range(1, 6)):
                    swing_high.append(highs[i])
                if all(lows[i] <= lows[i - j] for j in range(1, 6)) and \
                   all(lows[i] <= lows[i + j] for j in range(1, 6)):
                    swing_low.append(lows[i])

            if len(swing_high) >= 2 and len(swing_low) >= 2:
                hh = swing_high[-1] > swing_high[-2]
                hl = swing_low[-1] > swing_low[-2]
                lh = swing_high[-1] < swing_high[-2]
                ll = swing_low[-1] < swing_low[-2]
                if hh and hl:
                    trend = 'bullish'
                elif lh and ll:
                    trend = 'bearish'

            # Break of Structure
            if closes[-1] > np.max(highs[-10:-1]):
                bos = True
            elif closes[-1] < np.min(lows[-10:-1]):
                bos = True

            # Change of Character
            if trend == 'bullish' and closes[-1] < np.min(lows[-5:-1]):
                choch = True
            elif trend == 'bearish' and closes[-1] > np.max(highs[-5:-1]):
                choch = True

        # BOS pending (near structural level)
        bos_pending = False
        if not bos and len(highs) > 10:
            near_high = abs(closes[-1] - np.max(highs[-10:-1])) / np.max(highs[-10:-1]) < 0.002
            near_low = abs(closes[-1] - np.min(lows[-10:-1])) / np.min(lows[-10:-1]) < 0.002
            bos_pending = near_high or near_low

        # CHoCH pending (reversal candle patterns)
        choch_pending = False
        if not choch and len(data) >= 3:
            last = data.iloc[-1]
            body = abs(last['close'] - last['open'])
            rng = last['high'] - last['low']
            if rng > 0:
                upper_wick = last['high'] - max(last['open'], last['close'])
                lower_wick = min(last['open'], last['close']) - last['low']
                if upper_wick > rng * 0.6 or lower_wick > rng * 0.6:
                    choch_pending = True

        return {
            'trend': trend,
            'bos_confirmed': bos,
            'choch_confirmed': choch,
            'bos_pending': bos_pending,
            'choch_pending': choch_pending
        }


class ZoneDetector:
    """Institutional Supply/Demand Zone Detection."""

    @staticmethod
    def detect(data: pd.DataFrame) -> dict:
        data = AutoFixer.fix_dataframe(data)
        current_high = data['high'].iloc[-1]
        current_low = data['low'].iloc[-1]
        recent_high = data['high'].iloc[-20:-1].max() if len(data) > 20 else current_high
        recent_low = data['low'].iloc[-20:-1].min() if len(data) > 20 else current_low

        at_supply = current_high >= recent_high * 0.997
        at_demand = current_low <= recent_low * 1.003

        # Order block detection
        ob = False
        if len(data) >= 3:
            last_range = data['high'].iloc[-1] - data['low'].iloc[-1]
            prev_range = data['high'].iloc[-2] - data['low'].iloc[-2]
            if prev_range > 0 and last_range > 2 * prev_range:
                ob = True

        # Fair Value Gap detection
        fvg_active = False
        if len(data) >= 3:
            c = data.iloc[-1]
            p1 = data.iloc[-2]
            p2 = data.iloc[-3]
            # Bullish FVG: current low > 2-candles-ago high
            if c['low'] > p2['high']:
                fvg_active = True
            # Bearish FVG: current high < 2-candles-ago low
            elif c['high'] < p2['low']:
                fvg_active = True

        return {
            'at_supply': at_supply,
            'at_demand': at_demand,
            'has_order_block': ob,
            'has_active_fvg': fvg_active,
            'has_fvg': fvg_active
        }


class LiquidityDetector:
    """Liquidity Analysis and Sweep Detection."""

    @staticmethod
    def analyze(data: pd.DataFrame) -> dict:
        data = AutoFixer.fix_dataframe(data)
        highs = data['high'].values[-10:]
        lows = data['low'].values[-10:]

        sweep = False
        sweep_type = 'none'
        if len(highs) >= 5:
            recent_high = max(highs[:-1])
            recent_low = min(lows[:-1])
            # Buy-side liquidity sweep: price spikes above recent high then closes below
            if highs[-1] > recent_high and data['close'].iloc[-1] < recent_high:
                sweep = True
                sweep_type = 'buy_side'
            # Sell-side liquidity sweep: price drops below recent low then closes above
            elif lows[-1] < recent_low and data['close'].iloc[-1] > recent_low:
                sweep = True
                sweep_type = 'sell_side'

        # Equal highs/lows detection
        eq_high = len(highs) >= 3 and (max(highs) - min(highs)) < np.mean(highs) * 0.001
        eq_low = len(lows) >= 3 and (max(lows) - min(lows)) < np.mean(lows) * 0.001

        return {
            'sweep_detected': sweep,
            'sweep_type': sweep_type,
            'building': eq_high or eq_low,
            'has_equal_highs': eq_high,
            'has_equal_lows': eq_low
        }
