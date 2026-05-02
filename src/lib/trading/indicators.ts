// Technical Indicators Engine
import { TRADING_CONFIG, type StochasticResult, type BBResult } from './types';

export class TechnicalIndicators {
  static calculateRSI(prices: number[], period: number = TRADING_CONFIG.RSI_PERIOD): number {
    if (prices.length < period + 1) return 50;

    const deltas: number[] = [];
    for (let i = 1; i < prices.length; i++) {
      deltas.push(prices[i] - prices[i - 1]);
    }

    const gains = deltas.map(d => d > 0 ? d : 0);
    const losses = deltas.map(d => d < 0 ? -d : 0);

    // Wilder's smoothing: first average = SMA, then EMA with alpha = 1/period
    let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

    for (let i = period; i < deltas.length; i++) {
      avgGain = (avgGain * (period - 1) + gains[i]) / period;
      avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    }

    if (avgLoss === 0) return 100.0;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  static calculateStochastic(
    high: number[],
    low: number[],
    close: number[],
    kPeriod: number = TRADING_CONFIG.STOCHASTIC_K,
    dPeriod: number = TRADING_CONFIG.STOCHASTIC_D
  ): StochasticResult {
    if (high.length < kPeriod) return { k: 50, d: 50 };

    // Calculate %K values for the last (dPeriod) windows
    const kValues: number[] = [];
    const lookback = Math.min(close.length, kPeriod + dPeriod - 1);

    for (let i = lookback - 1; i >= 0; i--) {
      const startIdx = Math.max(0, i - kPeriod + 1);
      const windowHigh = high.slice(startIdx, i + 1);
      const windowLow = low.slice(startIdx, i + 1);

      const highestHigh = Math.max(...windowHigh);
      const lowestLow = Math.min(...windowLow);

      if (highestHigh - lowestLow === 0) {
        kValues.push(50);
      } else {
        kValues.push(100 * ((close[i] - lowestLow) / (highestHigh - lowestLow)));
      }
    }

    // Current %K = latest value
    const k = kValues[0] ?? 50;

    // %D = SMA of the last dPeriod %K values
    const dSlice = kValues.slice(0, Math.min(dPeriod, kValues.length));
    const d = dSlice.reduce((a, b) => a + b, 0) / dSlice.length;

    return { k, d };
  }

  static calculateBollingerBands(
    prices: number[],
    period: number = TRADING_CONFIG.BB_PERIOD,
    stdDev: number = TRADING_CONFIG.BB_STD
  ): BBResult {
    if (prices.length < period) {
      const sma = prices.reduce((a, b) => a + b, 0) / prices.length;
      return { sma, upperBand: sma * 1.02, lowerBand: sma * 0.98, bbWidth: 0.04 };
    }

    const recentPrices = prices.slice(-period);
    const sma = recentPrices.reduce((a, b) => a + b, 0) / period;
    const variance = recentPrices.reduce((sum, p) => sum + Math.pow(p - sma, 2), 0) / period;
    const std = Math.sqrt(variance);

    const upperBand = sma + (stdDev * std);
    const lowerBand = sma - (stdDev * std);
    const bbWidth = sma !== 0 ? (upperBand - lowerBand) / sma : 0;

    return { sma, upperBand, lowerBand, bbWidth };
  }

  static calculateADX(
    high: number[],
    low: number[],
    close: number[],
    period: number = TRADING_CONFIG.ADX_PERIOD
  ): number {
    if (close.length < period * 2) return 20;

    const trList: number[] = [];
    const plusDmList: number[] = [];
    const minusDmList: number[] = [];

    for (let i = 1; i < close.length; i++) {
      const highDiff = high[i] - high[i - 1];
      const lowDiff = low[i - 1] - low[i];

      const tr = Math.max(
        high[i] - low[i],
        Math.abs(high[i] - close[i - 1]),
        Math.abs(low[i] - close[i - 1])
      );
      trList.push(tr);

      const plusDm = (highDiff > lowDiff && highDiff > 0) ? highDiff : 0;
      const minusDm = (lowDiff > highDiff && lowDiff > 0) ? lowDiff : 0;
      plusDmList.push(plusDm);
      minusDmList.push(minusDm);
    }

    // Wilder's smoothing for ATR, +DM, -DM
    let smoothTR = trList.slice(0, period).reduce((a, b) => a + b, 0);
    let smoothPlusDM = plusDmList.slice(0, period).reduce((a, b) => a + b, 0);
    let smoothMinusDM = minusDmList.slice(0, period).reduce((a, b) => a + b, 0);

    const dxValues: number[] = [];

    // First DX from initial smoothed values
    if (smoothTR > 0) {
      const plusDi = 100 * (smoothPlusDM / smoothTR);
      const minusDi = 100 * (smoothMinusDM / smoothTR);
      if (plusDi + minusDi > 0) {
        dxValues.push(100 * Math.abs(plusDi - minusDi) / (plusDi + minusDi));
      }
    }

    // Continue smoothing and calculate DX for each subsequent bar
    for (let i = period; i < trList.length; i++) {
      smoothTR = smoothTR - (smoothTR / period) + trList[i];
      smoothPlusDM = smoothPlusDM - (smoothPlusDM / period) + plusDmList[i];
      smoothMinusDM = smoothMinusDM - (smoothMinusDM / period) + minusDmList[i];

      if (smoothTR > 0) {
        const plusDi = 100 * (smoothPlusDM / smoothTR);
        const minusDi = 100 * (smoothMinusDM / smoothTR);
        if (plusDi + minusDi > 0) {
          dxValues.push(100 * Math.abs(plusDi - minusDi) / (plusDi + minusDi));
        }
      }
    }

    if (dxValues.length === 0) return 20;

    // ADX = Wilder's smoothed average of DX values
    if (dxValues.length <= period) {
      // Not enough DX values for full smoothing, return average
      return +(dxValues.reduce((a, b) => a + b, 0) / dxValues.length).toFixed(1);
    }

    // First ADX = SMA of first 'period' DX values
    let adx = dxValues.slice(0, period).reduce((a, b) => a + b, 0) / period;

    // Subsequent ADX values use Wilder's smoothing
    for (let i = period; i < dxValues.length; i++) {
      adx = (adx * (period - 1) + dxValues[i]) / period;
    }

    return +adx.toFixed(1);
  }

  static calculateEMA(prices: number[], period: number): number {
    if (prices.length === 0) return 0;

    const multiplier = 2 / (period + 1);
    let ema = prices[0];

    for (let i = 1; i < prices.length; i++) {
      ema = (prices[i] - ema) * multiplier + ema;
    }

    return ema;
  }

  static calculateATR(
    high: number[],
    low: number[],
    close: number[],
    period: number = 14
  ): number {
    if (close.length < 2) return 0;

    const trList: number[] = [];
    for (let i = 1; i < close.length; i++) {
      const tr = Math.max(
        high[i] - low[i],
        Math.abs(high[i] - close[i - 1]),
        Math.abs(low[i] - close[i - 1])
      );
      trList.push(tr);
    }

    const recentTr = trList.slice(-period);
    return recentTr.reduce((a, b) => a + b, 0) / recentTr.length;
  }

  // ── Candle Pattern Detection (from Python Indicators) ───────────

  /**
   * Detect engulfing candlestick pattern.
   * Returns { detected, direction } where direction is 'bullish' or 'bearish'.
   *
   * Bullish engulfing: previous candle bearish, current candle bullish,
   *   current body engulfs previous body.
   * Bearish engulfing: previous candle bullish, current candle bearish,
   *   current body engulfs previous body.
   */
  static detectEngulfing(
    opens: number[],
    highs: number[],
    lows: number[],
    closes: number[]
  ): { detected: boolean; direction: 'bullish' | 'bearish' | 'none' } {
    if (closes.length < 2) return { detected: false, direction: 'none' };

    const prevClose = closes[closes.length - 2];
    const prevOpen = opens[opens.length - 2];
    const currClose = closes[closes.length - 1];
    const currOpen = opens[opens.length - 1];

    const prevBody = Math.abs(prevClose - prevOpen);
    const currBody = Math.abs(currClose - currOpen);

    // Current body must be larger than previous
    if (currBody < prevBody) return { detected: false, direction: 'none' };

    // Bullish engulfing: prev bearish, curr bullish, curr engulfs prev
    if (
      prevClose < prevOpen && // prev bearish
      currClose > currOpen && // curr bullish
      currOpen <= prevClose && // curr open below prev close
      currClose >= prevOpen    // curr close above prev open
    ) {
      return { detected: true, direction: 'bullish' };
    }

    // Bearish engulfing: prev bullish, curr bearish, curr engulfs prev
    if (
      prevClose > prevOpen && // prev bullish
      currClose < currOpen && // curr bearish
      currOpen >= prevClose && // curr open above prev close
      currClose <= prevOpen    // curr close below prev open
    ) {
      return { detected: true, direction: 'bearish' };
    }

    return { detected: false, direction: 'none' };
  }

  /**
   * Detect rejection (pin bar) candlestick pattern.
   * Returns { detected, direction } where direction is 'bullish' or 'bearish'.
   *
   * Bearish rejection: long upper wick (>2x body), short lower wick (<30% range)
   * Bullish rejection: long lower wick (>2x body), short upper wick (<30% range)
   */
  static detectRejection(
    opens: number[],
    highs: number[],
    lows: number[],
    closes: number[]
  ): { detected: boolean; direction: 'bullish' | 'bearish' | 'none' } {
    if (closes.length < 1) return { detected: false, direction: 'none' };

    const currOpen = opens[opens.length - 1];
    const currHigh = highs[highs.length - 1];
    const currLow = lows[lows.length - 1];
    const currClose = closes[closes.length - 1];

    const body = Math.abs(currClose - currOpen);
    const range = currHigh - currLow;

    if (range === 0) return { detected: false, direction: 'none' };

    const upperWick = currHigh - Math.max(currOpen, currClose);
    const lowerWick = Math.min(currOpen, currClose) - currLow;

    // Bearish rejection: long upper wick
    if (upperWick > 2 * body && lowerWick < 0.3 * range) {
      return { detected: true, direction: 'bearish' };
    }

    // Bullish rejection: long lower wick
    if (lowerWick > 2 * body && upperWick < 0.3 * range) {
      return { detected: true, direction: 'bullish' };
    }

    return { detected: false, direction: 'none' };
  }

  /**
   * Detect volume profile spike.
   * Returns true if current volume > 1.8x the 20-period average.
   */
  static detectVolumeProfile(volumes: number[], lookback: number = 20): boolean {
    if (volumes.length < lookback + 1) return false;
    const avg = volumes.slice(-lookback - 1, -1).reduce((a, b) => a + b, 0) / lookback;
    return avg > 0 && volumes[volumes.length - 1] > avg * 1.8;
  }

  /**
   * Detect volume trend (increasing, decreasing, or normal).
   * Compares recent 3-bar average to prior 3-bar average.
   */
  static detectVolumeTrend(volumes: number[]): 'increasing' | 'decreasing' | 'normal' {
    if (volumes.length < 6) return 'normal';
    const recentAvg = volumes.slice(-3).reduce((a, b) => a + b, 0) / 3;
    const priorAvg = volumes.slice(-6, -3).reduce((a, b) => a + b, 0) / 3;
    if (recentAvg > priorAvg * 1.1) return 'increasing';
    if (recentAvg < priorAvg * 0.9) return 'decreasing';
    return 'normal';
  }

  /**
   * Calculate momentum (percentage change over N bars).
   */
  static calculateMomentum(prices: number[], bars: number = 10): number {
    if (prices.length < bars + 1) return 0;
    const current = prices[prices.length - 1];
    const past = prices[prices.length - 1 - bars];
    if (past === 0) return 0;
    return ((current - past) / past) * 100;
  }

  /**
   * Calculate BB width for previous period (for expansion/contraction detection).
   */
  static calculateBBWidthPrev(prices: number[], period: number = 20): number {
    if (prices.length < period + 1) return 0.1;
    const prevPrices = prices.slice(-period - 1, -1);
    const sma = prevPrices.reduce((a, b) => a + b, 0) / period;
    if (sma === 0) return 0.1;
    const variance = prevPrices.reduce((sum, p) => sum + Math.pow(p - sma, 2), 0) / period;
    const std = Math.sqrt(variance);
    return (4 * std) / sma;
  }
}
