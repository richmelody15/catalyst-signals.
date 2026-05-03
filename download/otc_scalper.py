"""
OTC Blitz Scalper Engine – High-win-rate momentum signals.
Targets short-expiry trades on OTC pairs for IQ Option & Pocket Option.

Filters:
  1. Volume spike  (> 1.5x average)
  2. Momentum      (last 3 candles, min 0.02% price change)
  3. RSI guard     (avoid overbought >70 / oversold <30)
  4. ADX trend     (>= 20, weak trend still tradable)
  5. Session gate  (London/NY only, 08:00–17:00 UTC)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import pytz

WAT = pytz.timezone("Africa/Lagos")

# Pocket Option valid timeframes
PO_TIMEFRAMES = ["S3", "S15", "S30", "M1", "M3", "M5"]
# IQ Option valid timeframes
IQ_TIMEFRAMES = ["30s", "45s", "1m", "2m", "3m", "5m"]

SCALPER_CONFIG = {
    "volume_spike": 1.5,
    "momentum_period": 3,
    "min_momentum_pct": 0.0002,
    "adx_threshold": 20,
    "rsi_limit": 70,
    "rsi_floor": 30,
    "max_spread_risk": 0.0003,
    "trade_sessions": [(8, 17)],
}


class OTCScalper:
    """Dual-platform OTC momentum scalper (IQ Option + Pocket Option)."""

    def generate_signal(self, df: pd.DataFrame, pair: str, timeframe: str, platform: str) -> dict | None:
        """
        Scan for a momentum setup and return a formatted signal dict, or None.
        """
        if len(df) < 10:
            return None
        close = df["close"].values
        volume = df.get("volume", pd.Series([1] * len(df))).values
        avg_vol = np.mean(volume[-10:-1])
        if volume[-1] < avg_vol * SCALPER_CONFIG["volume_spike"]:
            return None

        # Momentum
        if len(close) < 4:
            return None
        pct = close[-1] / close[-4] - 1
        if abs(pct) < SCALPER_CONFIG["min_momentum_pct"]:
            return None
        direction = "BUY" if pct > 0 else "SELL"

        # RSI filter
        rsi = self._rsi(close, 14)
        if direction == "BUY" and rsi > SCALPER_CONFIG["rsi_limit"]:
            return None
        if direction == "SELL" and rsi < SCALPER_CONFIG["rsi_floor"]:
            return None

        # ADX
        adx = self._adx(df, 14)
        if adx < SCALPER_CONFIG["adx_threshold"]:
            return None

        # Session
        now = datetime.now(pytz.UTC)
        if not any(start <= now.hour < end for (start, end) in SCALPER_CONFIG["trade_sessions"]):
            return None

        # Time calculation
        tf_seconds = {
            "30s": 30, "45s": 45, "1m": 60, "2m": 120, "3m": 180, "5m": 300,
            "S3": 3, "S15": 15, "S30": 30, "M1": 60, "M3": 180, "M5": 300,
        }
        duration = tf_seconds.get(timeframe, 60)
        entry_time = now + timedelta(minutes=1)
        expiry = entry_time + timedelta(seconds=duration)

        entry_price = close[-1]
        confidence = min(90, int(abs(pct) * 200000))

        # Martingale
        martingale = []
        ent_wat = entry_time.astimezone(WAT)
        for lvl, mult, delay in [("M1", 1.5, 1), ("M2", 2.5, 2), ("M3", 4.0, 3)]:
            t = ent_wat + timedelta(minutes=delay)
            martingale.append(
                {
                    "level": lvl,
                    "multiplier": mult,
                    "amount": round(mult, 2),
                    "entry_time": t.strftime("%H:%M"),
                }
            )

        color = "\U0001f7e2" if direction == "BUY" else "\U0001f534"
        arrow = "\u25b2" if direction == "BUY" else "\u25bc"
        lines = [
            "\u2501" * 24,
            f"\U0001f525 OTC SCALPER ({platform.upper()})",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')}",
            f"\u23f1\ufe0f Expiry: {expiry.astimezone(WAT).strftime('%H:%M:%S')} ({timeframe})",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {adx:.1f} | RSI: {rsi:.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500",
        ]
        for m in martingale:
            lines.append(
                f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}"
            )
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Scalp & exit", "\u2501" * 24]
        return {
            "formatted_signal": "\n".join(lines),
            "direction": direction,
            "entry_price": entry_price,
            "confidence": confidence,
            "expiry": expiry.isoformat(),
            "timeframe": timeframe,
            "platform": platform,
            "martingale": martingale,
            "indicators": {"adx": adx, "rsi": rsi},
        }

    def _rsi(self, close, period=14):
        delta = np.diff(close)
        gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
        loss = -np.mean(delta[delta < 0]) if any(delta < 0) else 0
        if loss == 0:
            return 100
        return 100 - (100 / (1 + gain / loss))

    def _adx(self, df, period=14):
        high, low, close = df["high"], df["low"], df["close"]
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
        atr = tr.rolling(period).mean().iloc[-1]
        if atr == 0:
            return 0
        up = high.diff().clip(lower=0)
        down = -low.diff().clip(upper=0)
        di_plus = 100 * up.rolling(period).mean().iloc[-1] / atr
        di_minus = 100 * down.rolling(period).mean().iloc[-1] / atr
        dx = (
            100 * abs(di_plus - di_minus) / (di_plus + di_minus)
            if (di_plus + di_minus) != 0
            else 0
        )
        return dx
