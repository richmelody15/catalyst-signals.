"""
OTC Blitz Scalper Engine – High-win-rate momentum signals.
Targets 2-minute expiry trades on OTC pairs.

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


class OTCScalperEngine:
    def __init__(self):
        self.config = {
            "volume_spike": 1.5,         # volume > 1.5x average
            "momentum_period": 3,        # look at last 3 candles
            "min_momentum_pct": 0.0002,  # 0.02% price change in 3 candles
            "adx_threshold": 20,         # weak trend is still tradable
            "rsi_limit": 70,             # avoid overbought extremes
            "rsi_floor": 30,             # avoid oversold extremes
            "max_spread_risk": 0.0003,   # avoid whipsaw
            "tradeable_sessions": True,   # London/NY only
        }

    # ────────────────────────────────────────────────────────
    #  Main entry: scan for a momentum setup
    # ────────────────────────────────────────────────────────
    def generate(self, df: pd.DataFrame, pair: str, timeframe: str = "M1") -> dict | None:
        """
        Scans the last few 1-minute candles for a momentum setup.
        Returns a formatted signal dict or None.
        """
        if len(df) < 10:
            return None

        close = df["close"].values
        open_ = df["open"].values
        high = df["high"].values
        low = df["low"].values
        volume = df.get("volume", pd.Series([1] * len(df))).values

        # ── 1. Volume spike ──
        avg_vol = np.mean(volume[-10:-1])
        current_vol = volume[-1]
        if current_vol < avg_vol * self.config["volume_spike"]:
            return None

        # ── 2. Momentum check (last 3 candles) ──
        if len(close) < 4:
            return None
        pct_change = (close[-1] / close[-4] - 1)
        direction = "BUY" if pct_change > 0 else "SELL"
        if abs(pct_change) < self.config["min_momentum_pct"]:
            return None

        # ── 3. Avoid extreme RSI (price exhaustion) ──
        rsi = self._rsi(close, 14)
        if direction == "BUY" and rsi > self.config["rsi_limit"]:
            return None
        if direction == "SELL" and rsi < self.config["rsi_floor"]:
            return None

        # ── 4. Basic trend filter (ADX) ──
        adx_val = self._adx(df, 14)
        if adx_val < self.config["adx_threshold"]:
            return None

        # ── 5. Session filter (avoid dead hours) ──
        now = datetime.now(pytz.UTC)
        if not (8 <= now.hour < 17):
            return None  # only London / early NY

        # ── 6. Entry logic ──
        entry_time = now + timedelta(minutes=1)
        expiry_time = entry_time + timedelta(minutes=2)  # 2-min expiry
        entry_price = close[-1]
        confidence = min(90, int(abs(pct_change) * 200000))  # scale momentum

        # Martingale table (recovery)
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

        # Format signal
        color = "\U0001f7e2" if direction == "BUY" else "\U0001f534"
        arrow = "\u25b2" if direction == "BUY" else "\u25bc"
        lines = [
            "\u2501" * 24,
            "\U0001f525 OTC SCALPER SIGNAL",
            "\u2501" * 24,
            f"{color} {direction} {arrow}",
            f"\U0001f4ca Asset: {pair}",
            f"\U0001f4b0 Entry: {entry_price:.5f}",
            f"\u23f0 Entry: {ent_wat.strftime('%H:%M:%S')} (Lead 1 min)",
            f"\u23f1\ufe0f Expiry: {expiry_time.astimezone(WAT).strftime('%H:%M:%S')} (2 min)",
            f"\U0001f3af Confidence: {confidence}%",
            f"\U0001f4c8 ADX: {adx_val:.1f} | RSI: {rsi:.1f}",
            "\u2500\u2500 \U0001f6e1\ufe0f RECOVERY \u2500\u2500",
        ]
        for m in martingale:
            lines.append(
                f"{m['level']} \u2502 {m['multiplier']}x \u2502 ${m['amount']} \u2502 Entry: {m['entry_time']}"
            )
        lines += ["\u2501" * 24, "\u26a0\ufe0f Risk 1% only", "\U0001f4a1 Scalp & exit", "\u2501" * 24]
        formatted = "\n".join(lines)

        return {
            "formatted_signal": formatted,
            "direction": direction,
            "entry_price": entry_price,
            "confidence": confidence,
            "expiry": expiry_time.isoformat(),
            "timeframe": "M2",
            "platform": "iq",
            "indicators": {"adx": adx_val, "rsi": rsi},
        }

    # ────────────────────────────────────────────────────────
    #  RSI calculation
    # ────────────────────────────────────────────────────────
    def _rsi(self, close, period=14):
        deltas = np.diff(close)
        gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
        loss = -np.mean(deltas[deltas < 0]) if any(deltas < 0) else 0
        if loss == 0:
            return 100
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    # ────────────────────────────────────────────────────────
    #  ADX calculation
    # ────────────────────────────────────────────────────────
    def _adx(self, df, period=14):
        high, low, close = df["high"], df["low"], df["close"]
        tr = np.maximum(
            high - low,
            np.maximum(abs(high - close.shift()), abs(low - close.shift())),
        )
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
