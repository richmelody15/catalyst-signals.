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

    const recentGains = gains.slice(-period);
    const recentLosses = losses.slice(-period);

    const avgGain = recentGains.reduce((a, b) => a + b, 0) / period;
    const avgLoss = recentLosses.reduce((a, b) => a + b, 0) / period;

    if (avgLoss === 0) return 100.0;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  static calculateStochastic(
    high: number[],
    low: number[],
    close: number[],
    kPeriod: number = TRADING_CONFIG.STOCHASTIC_K,
    _dPeriod: number = TRADING_CONFIG.STOCHASTIC_D
  ): StochasticResult {
    if (high.length < kPeriod) return { k: 50, d: 50 };

    const recentHigh = high.slice(-kPeriod);
    const recentLow = low.slice(-kPeriod);
    const lowestLow = Math.min(...recentLow);
    const highestHigh = Math.max(...recentHigh);

    if (highestHigh - lowestLow === 0) return { k: 50, d: 50 };

    const k = 100 * ((close[close.length - 1] - lowestLow) / (highestHigh - lowestLow));

    // Simplified %D calculation
    const d = k;

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
    if (close.length < period + 1) return 20;

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

    const recentTr = trList.slice(-period);
    const recentPlusDm = plusDmList.slice(-period);
    const recentMinusDm = minusDmList.slice(-period);

    const atr = recentTr.reduce((a, b) => a + b, 0) / period;
    const avgPlusDm = recentPlusDm.reduce((a, b) => a + b, 0) / period;
    const avgMinusDm = recentMinusDm.reduce((a, b) => a + b, 0) / period;

    if (atr === 0) return 0;

    const plusDi = 100 * (avgPlusDm / atr);
    const minusDi = 100 * (avgMinusDm / atr);

    if (plusDi + minusDi === 0) return 0;

    const dx = 100 * Math.abs(plusDi - minusDi) / (plusDi + minusDi);

    return dx;
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
}
