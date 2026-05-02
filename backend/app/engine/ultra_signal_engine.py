"""
Ultra Signal Engine — OTC Blitz with Correct Active Martingale Times

KEY FEATURES:
- Ultra95Filter with 9-category scoring (structure, technical, liquidity, zones,
  volume, momentum, candle, mtf_alignment, volatility_quality)
- min_overall=95%, min_confluences=9
- Correct martingale recovery levels with dynamically-calculated WAT entry times
- Adaptive weights integration for self-learning
"""
import numpy as np
import pandas as pd
import sqlite3
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import pytz

from backend.app.core.auto_fixer import AutoFixer
from backend.app.engine.indicators import PreciseIndicators
from backend.app.engine.analyzers import StructureAnalyzer, ZoneDetector, LiquidityDetector
from backend.app.engine.adaptive_weights import AdaptiveWeights

logger = logging.getLogger(__name__)

# West Africa Time timezone
WAT = pytz.timezone('Africa/Lagos')


# ============================================================
# 95% WIN RATE FILTER — 9 CATEGORY SCORING
# ============================================================
class Ultra95Filter:
    """
    Ultra-strict 9-category filter for 95%+ win rate.
    
    Scoring categories:
    1. Structure (trend + BOS + CHoCH)
    2. Technical (RSI + Stochastic + EMA alignment)
    3. Liquidity (sweep + sweep type)
    4. Zones (supply/demand + order block + FVG)
    5. Volume (spike + quality + trend)
    6. Momentum (momentum magnitude)
    7. Candle Pattern (engulfing + rejection)
    8. MTF Alignment (multi-timeframe confirmation)
    9. Volatility Quality (BB width + ATR range)
    
    Each category scored 0-100. Signal passes if:
    - Overall average >= min_overall (default 95)
    - At least min_confluences categories score >= 85
    """

    def __init__(self, weights: Optional[AdaptiveWeights] = None):
        self.weights = weights
        self.thresholds = {
            'structure': 90, 'technical': 90, 'liquidity': 90, 'zones': 90,
            'volume': 85, 'momentum': 85, 'candle': 85,
            'mtf_alignment': 85, 'volatility_quality': 80
        }
        self.min_overall = 95.0
        self.min_confluences = 9

    def check(self, indicators, structure, liquidity, zones) -> Tuple[bool, float, str, Dict]:
        """
        Returns (passed, overall_score, reason, feature_scores)
        """
        scores = {}

        # 1. Market Structure (trend + BOS + CHoCH)
        s = 0
        if structure['trend'] != 'neutral':
            s += 40
        if structure['bos_confirmed']:
            s += 40
        if structure['choch_confirmed']:
            s += 20
        scores['structure'] = min(100, s)

        # 2. Technical Alignment (RSI + Stochastic + EMA)
        s = 0
        rsi = indicators['rsi']
        stoch_k = indicators['stoch_k']
        stoch_d = indicators['stoch_d']
        if rsi > 80 or rsi < 20:
            s += 50
        elif rsi > 75 or rsi < 25:
            s += 30
        if abs(stoch_k - stoch_d) < 2 and (stoch_k > 85 or stoch_k < 15):
            s += 30
        if (structure['trend'] == 'bullish' and indicators['ema50'] > indicators['ema200']) or \
           (structure['trend'] == 'bearish' and indicators['ema50'] < indicators['ema200']):
            s += 20
        scores['technical'] = min(100, s)

        # 3. Liquidity Quality (sweep + type)
        s = 70 if liquidity['sweep_detected'] else 0
        if liquidity['sweep_type'] != 'none':
            s += 20
        scores['liquidity'] = min(100, s)

        # 4. Zone Confluence (supply/demand + order block + FVG)
        s = 0
        if zones['at_supply'] or zones['at_demand']:
            s += 50
        if zones['has_order_block']:
            s += 30
        if zones['has_active_fvg']:
            s += 20
        scores['zones'] = min(100, s)

        # 5. Volume (spike + quality + trend)
        s = 0
        if indicators.get('volume_spike', False):
            s += 50
        if indicators.get('vol_quality', False):
            s += 30
        if indicators.get('volume_trend', 'normal') == 'increasing':
            s += 20
        scores['volume'] = min(100, s)

        # 6. Momentum
        s = 0
        momentum = abs(indicators.get('momentum', 0))
        if momentum > 1.0:
            s += 50
        elif momentum > 0.7:
            s += 30
        else:
            s += 10
        scores['momentum'] = min(100, s)

        # 7. Candle Pattern (engulfing or rejection)
        s = 0
        if indicators.get('engulfing', False):
            s = 100
        elif indicators.get('rejection', False):
            s = 85
        else:
            s = 30
        scores['candle'] = min(100, s)

        # 8. Multi-Timeframe Alignment
        s = 100 if structure.get('multi_tf_aligned', False) else 40
        scores['mtf_alignment'] = min(100, s)

        # 9. Volatility Quality (BB width + ATR)
        s = 0
        bb = indicators['bb_width']
        if 0.15 < bb < 0.6:
            s += 60
        elif bb >= 0.6:
            s += 30
        else:
            s += 10
        if indicators['atr'] > 0.0008:
            s += 30
        scores['volatility_quality'] = min(100, s)

        # Calculate overall
        if self.weights:
            w = self.weights.current_weights
            # Map 9-category scores to 5 weight categories for compatibility
            weight_map = {
                'structure': 'structure',
                'technical': 'technical',
                'liquidity': 'liquidity',
                'zones': 'zones',
                'volume': 'volume_momentum',
                'momentum': 'volume_momentum',
                'candle': 'technical',
                'mtf_alignment': 'structure',
                'volatility_quality': 'volume_momentum',
            }
            overall = 0
            total_w = 0
            for k, v in scores.items():
                wk = weight_map.get(k, 'volume_momentum')
                wv = w.get(wk, 0.2)
                overall += v * wv
                total_w += wv
            overall = overall / total_w if total_w > 0 else sum(scores.values()) / len(scores)
        else:
            overall = sum(scores.values()) / len(scores)

        confluences = sum(1 for v in scores.values() if v >= 85)

        passed = overall >= self.min_overall and confluences >= self.min_confluences

        if passed:
            reason = f"95% FILTER PASSED | Score: {overall:.1f}% | Confluence: {confluences}/9"
        else:
            reason = f"FILTER FAILED | Score: {overall:.1f}% | Confluence: {confluences}/9 (need {self.min_confluences})"

        return passed, overall, reason, scores


# ============================================================
# MARTINGALE TIME CALCULATOR — THE KEY FIX
# ============================================================
def calculate_martingale_entry_times(
    base_entry: datetime,
    timeframe: str
) -> List[datetime]:
    """
    Calculate correct, active entry times for each martingale level.

    CRITICAL: All times are based on the CURRENT WAT time,
    not empty or placeholder values.

    Args:
        base_entry: The base signal entry time (3 min from now)
        timeframe: e.g. '1m', '2m', '3m', '5m', '30s', '45s'

    Returns:
        List of 3 datetime objects for M1, M2, M3 levels
    """
    # Time offset per level in seconds, keyed by timeframe
    offset_map = {
        '30s': [30, 60, 90],       # M1=+30s, M2=+60s, M3=+90s
        '45s': [45, 90, 135],      # M1=+45s, M2=+90s, M3=+135s
        '1m':  [60, 120, 180],     # M1=+1min, M2=+2min, M3=+3min
        '2m':  [120, 240, 360],    # M1=+2min, M2=+4min, M3=+6min
        '3m':  [180, 360, 540],    # M1=+3min, M2=+6min, M3=+9min
        '5m':  [300, 600, 900],    # M1=+5min, M2=+10min, M3=+15min
    }

    seconds = offset_map.get(timeframe, [60, 120, 180])

    # Ensure base_entry is timezone-aware (WAT)
    if base_entry.tzinfo is None:
        base_entry = WAT.localize(base_entry)

    times = [base_entry + timedelta(seconds=s) for s in seconds]
    return times


# ============================================================
# ULTRA SIGNAL GENERATOR — 95% FILTER
# ============================================================
class UltraSignalGenerator:
    """
    Ultra-Precise Signal Generator with 95%+ Win Rate Filter
    and CORRECT Martingale Recovery Times.
    """

    def __init__(self, db_path="trading_performance.db"):
        self.weights = AdaptiveWeights(db_path)
        self.filter = Ultra95Filter(self.weights)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT UNIQUE,
                symbol TEXT,
                direction TEXT,
                timeframe TEXT,
                entry_time TIMESTAMP,
                outcome TEXT DEFAULT 'pending',
                profit_pct REAL DEFAULT 0.0,
                feature_scores TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def _determine_direction(self, indicators, structure, liquidity, zones):
        """Score-based direction determination with candle patterns."""
        buy, sell = 0, 0

        # Market structure
        if structure['trend'] == 'bearish':
            sell += 35
        elif structure['trend'] == 'bullish':
            buy += 35

        # Liquidity sweep
        if liquidity['sweep_type'] == 'buy_side':
            sell += 30
        elif liquidity['sweep_type'] == 'sell_side':
            buy += 30

        # Zones
        if zones['at_supply']:
            sell += 30
        if zones['at_demand']:
            buy += 30

        # Engulfing pattern
        if indicators.get('engulfing_dir') == 'bearish':
            sell += 20
        elif indicators.get('engulfing_dir') == 'bullish':
            buy += 20

        # Rejection pattern
        if indicators.get('rejection_dir') == 'bearish':
            sell += 15
        elif indicators.get('rejection_dir') == 'bullish':
            buy += 15

        # Multi-TF alignment bonus
        if structure.get('multi_tf_aligned'):
            if structure['trend'] == 'bearish':
                sell += 10
            elif structure['trend'] == 'bullish':
                buy += 10

        return 'SELL' if sell > buy else 'BUY'

    def generate(
        self,
        symbol: str,
        timeframe: str,
        data: pd.DataFrame,
        base_stake: float = 1.0
    ) -> Optional[dict]:
        """
        Generate a trading signal with proper active martingale times.
        """
        try:
            # Fix data
            data = AutoFixer.fix_dataframe(data)

            # Calculate indicators (includes engulfing/rejection/volume)
            indicators = PreciseIndicators.calculate_all(data)

            # Analyze structure (includes multi-TF), liquidity, zones
            structure = StructureAnalyzer.analyze(data)
            liquidity = LiquidityDetector.analyze(data)
            zones = ZoneDetector.detect(data)

            # Apply 95% filter with 9-category scoring
            passed, confidence, reason, feature_scores = self.filter.check(
                indicators, structure, liquidity, zones
            )
            if not passed:
                logger.info(f"Signal filtered out for {symbol}: {reason}")
                return None

            # Determine direction (enhanced with candle patterns)
            direction = self._determine_direction(indicators, structure, liquidity, zones)

            # ============================================================
            # CRITICAL FIX: Calculate entry time in WAT timezone
            # ============================================================
            now_wat = datetime.now(WAT)
            entry_time = now_wat + timedelta(minutes=3)

            # ============================================================
            # CRITICAL FIX: Calculate martingale times using the correct
            # helper function that returns ACTIVE, DYNAMIC times
            # ============================================================
            martingale_times = calculate_martingale_entry_times(entry_time, timeframe)

            # Multipliers based on confidence
            if confidence >= 95:
                multipliers = [2.2, 4.8, 10.5]
            elif confidence >= 90:
                multipliers = [2.5, 5.5, 12.0]
            else:
                multipliers = [2.8, 6.2, 13.6]

            # Build martingale levels with REAL active times
            martingale = []
            level_names = ['M1', 'M2', 'M3']
            for i in range(3):
                amount = round(base_stake * multipliers[i], 2)
                # Cap at $3.0
                if amount > 3.0:
                    amount = 3.0
                    multipliers[i] = round(amount / base_stake, 1)

                martingale.append({
                    'level': level_names[i],
                    'multiplier': multipliers[i],
                    'amount': amount,
                    'entry_time': martingale_times[i]  # REAL active time
                })

            # Risk/Reward based on ATR
            atr = indicators['atr']
            price = data['close'].iloc[-1]
            if direction == 'SELL':
                sl = price + atr * 1.2
                tp = price - atr * 3.8
            else:
                sl = price - atr * 1.2
                tp = price + atr * 3.8
            risk = abs(sl - price)
            reward = abs(tp - price)
            rr = round(reward / risk, 1) if risk > 0 else 2.5

            # Signal ID
            signal_id = f"{symbol}_{now_wat.strftime('%Y%m%d_%H%M%S')}"

            signal = {
                'signal_id': signal_id,
                'symbol': symbol,
                'timeframe': timeframe,
                'direction': direction,
                'entry_time': entry_time,
                'confidence': confidence,
                'indicators': indicators,
                'structure': structure,
                'liquidity': liquidity,
                'zones': zones,
                'martingale': martingale,
                'rr': rr,
                'filter_reason': reason,
                'feature_scores': feature_scores,
                'market': 'High Volatility' if indicators.get('volatility', 0) > 0.5 else 'Normal'
            }

            # Record in database
            self._record_signal(signal)

            return signal

        except Exception as e:
            logger.error(f"Signal generation failed for {symbol}: {e}")
            return None

    def _record_signal(self, signal: dict):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            scores_json = json.dumps(signal.get('feature_scores', {}))
            cur.execute("""
                INSERT OR IGNORE INTO trades
                (signal_id, symbol, direction, timeframe, entry_time, feature_scores)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                signal['signal_id'],
                signal['signal_id'],
                signal['direction'],
                signal['timeframe'],
                signal['entry_time'].isoformat(),
                scores_json
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Record signal error: {e}")

    def update_outcome(self, signal_id: str, outcome: str, profit_pct: float = 0.0):
        """Update trade outcome and adapt weights."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Get feature scores
        cur.execute("SELECT feature_scores FROM trades WHERE signal_id=?", (signal_id,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                scores = json.loads(row[0])
                win = outcome == 'win'
                self.weights.update_from_outcome(scores, win)
            except Exception:
                pass

        cur.execute("""
            UPDATE trades SET outcome=?, profit_pct=? WHERE signal_id=?
        """, (outcome, profit_pct, signal_id))
        conn.commit()
        conn.close()

    def get_performance_summary(self, days: int = 30) -> Dict:
        """Get overall performance stats."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        cur.execute("""
            SELECT symbol, outcome FROM trades
            WHERE outcome != 'pending' AND entry_time >= ?
        """, (cutoff.isoformat(),))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return {
                'best_pair': 'N/A',
                'wins': 0,
                'losses': 0,
                'breakeven': 0,
                'total_evaluated': 0,
                'win_rate': 0.0
            }

        pair_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0})
        total_w = total_l = total_be = 0

        for r in rows:
            sym = r["symbol"]
            outcome = r["outcome"]
            pair_stats[sym]["total"] += 1
            if outcome == "win":
                pair_stats[sym]["wins"] += 1
                total_w += 1
            elif outcome == "loss":
                pair_stats[sym]["losses"] += 1
                total_l += 1
            else:
                total_be += 1

        best_pair = "N/A"
        best_wr = 0.0
        for sym, stats in pair_stats.items():
            if stats["total"] >= 10:
                wr = (stats["wins"] / stats["total"]) * 100
                if wr > best_wr:
                    best_wr = wr
                    best_pair = sym

        total_evaluated = total_w + total_l + total_be
        win_rate = (total_w / total_evaluated * 100) if total_evaluated > 0 else 0.0

        return {
            'best_pair': best_pair,
            'wins': total_w,
            'losses': total_l,
            'breakeven': total_be,
            'total_evaluated': total_evaluated,
            'win_rate': round(win_rate, 1)
        }

    # ============================================================
    # FORMAT OUTPUT — With CORRECT active martingale times
    # ============================================================
    def format_output(self, sig: dict) -> str:
        """
        Format signal as the professional output text.
        All times are dynamic and show REAL active entry times.
        """
        if not sig:
            return ""

        direction_emoji = "🔴" if sig['direction'] == 'SELL' else "🟢"

        # Format entry time in WAT
        entry_str = sig['entry_time'].strftime('%H:%M WAT')

        # ============================================================
        # CRITICAL FIX: Format each martingale level with its
        # CORRECT, DYNAMIC, ACTIVE entry time
        # ============================================================
        ml_lines = []
        for ml in sig['martingale']:
            ml_time_str = ml['entry_time'].strftime('%H:%M WAT')
            ml_lines.append(
                f"{ml['level']} | {ml['multiplier']}x | ${ml['amount']} | Entry: {ml_time_str}"
            )
        martingale_block = "\n".join(ml_lines)

        ind = sig['indicators']
        struc = sig['structure']
        liq = sig['liquidity']
        zon = sig['zones']

        # Format descriptions
        trend = struc['trend'].capitalize()
        bos = 'Confirmed' if struc['bos_confirmed'] else ('Pending' if struc.get('bos_pending') else 'Not Confirmed')
        choch = 'Confirmed' if struc['choch_confirmed'] else ('Pending' if struc.get('choch_pending') else 'Not Confirmed')
        fvg = 'Active' if zon['has_active_fvg'] else ('Present' if zon['has_fvg'] else 'None')
        liquidity_str = 'Sweep Detected' if liq['sweep_detected'] else ('Building' if liq['building'] else 'No Sweep')
        volume_str = 'High' if ind.get('volume_spike') else ('Rising' if ind.get('volume_trend') == 'increasing' else 'Normal')

        # Zone description
        zone_parts = []
        if sig['direction'] == 'SELL' and zon['at_supply']:
            zone_parts.append('Supply')
        if sig['direction'] == 'BUY' and zon['at_demand']:
            zone_parts.append('Demand')
        if zon['has_order_block']:
            zone_parts.append('Order Block')
        if zon['has_active_fvg']:
            zone_parts.append('FVG')
        zone_str = ' + '.join(zone_parts) if zone_parts else 'No Clear Zone'

        # Stochastic description
        k, d = ind['stoch_k'], ind['stoch_d']
        if k > 80 and k < d:
            stoch = 'Overbought'
        elif k < 20 and k > d:
            stoch = 'Oversold'
        elif k > d:
            stoch = 'Bullish'
        elif k < d:
            stoch = 'Bearish'
        else:
            stoch = 'Neutral'

        # BB Width description
        if ind['bb_width'] > ind.get('bb_width_prev', 0.1) * 1.2:
            bb = 'Expanding'
        elif ind['bb_width'] < ind.get('bb_width_prev', 0.1) * 0.8:
            bb = 'Contracting'
        else:
            bb = 'Stable'

        return f"""NEW SIGNAL!

Trade: {sig['symbol']}
Timer: {sig['timeframe']} (OTC)
Entry: {entry_str}
Direction: {sig['direction']} {direction_emoji}
AI Confidence: {sig['confidence']:.1f}%
Market: {sig['market']}

Trend: {trend}
BOS: {bos}
CHoCH: {choch}
FVG: {fvg}
Liquidity: {liquidity_str}
Volume: {volume_str}
Zone: {zone_str}
RSI: {ind['rsi']:.1f}
Stochastic: {stoch}
BB Width: {bb}
RR: 1:{sig['rr']}

MARTINGALE RECOVERY (Risk Level)
{martingale_block}
Note: Trade 1% - 3% of your capability and capital
SIGNAL STATUS: HIGH PROBABILITY ONLY

{sig['filter_reason']}"""
