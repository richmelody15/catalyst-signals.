// Price Action Analyzer - Smart Money / Price Action System
import type { StructureResult, LiquidityResult, FVG } from './types';

export class PriceActionAnalyzer {
  static detectSupportResistance(
    prices: number[],
    window: number = 20
  ): { supports: number[]; resistances: number[] } {
    const supports: number[] = [];
    const resistances: number[] = [];

    for (let i = window; i < prices.length - window; i++) {
      let isSupport = true;
      let isResistance = true;

      for (let j = 1; j <= window; j++) {
        if (prices[i] > prices[i - j]) isSupport = false;
        if (prices[i] < prices[i - j]) isResistance = false;
        if (prices[i] > prices[i + j]) isSupport = false;
        if (prices[i] < prices[i + j]) isResistance = false;
      }

      if (isSupport) supports.push(prices[i]);
      if (isResistance) resistances.push(prices[i]);
    }

    return { supports, resistances };
  }

  static detectFVG(prices: number[], threshold: number = 0.001): FVG[] {
    const fvgs: FVG[] = [];

    for (let i = 2; i < prices.length; i++) {
      // Bullish FVG
      if (prices[i - 2] < prices[i] && prices[i - 1] < prices[i - 2]) {
        const gapSize = Math.abs(prices[i] - prices[i - 2]) / prices[i - 2];
        if (gapSize > threshold) {
          fvgs.push({
            type: 'bullish',
            index: i,
            gapTop: prices[i],
            gapBottom: prices[i - 2],
          });
        }
      }
      // Bearish FVG
      else if (prices[i - 2] > prices[i] && prices[i - 1] > prices[i - 2]) {
        const gapSize = Math.abs(prices[i - 2] - prices[i]) / prices[i - 2];
        if (gapSize > threshold) {
          fvgs.push({
            type: 'bearish',
            index: i,
            gapTop: prices[i - 2],
            gapBottom: prices[i],
          });
        }
      }
    }

    return fvgs;
  }

  static detectBosChoch(
    highs: number[],
    lows: number[],
    _closes: number[]
  ): StructureResult {
    const swingHighs: Array<{ price: number; index: number }> = [];
    const swingLows: Array<{ price: number; index: number }> = [];

    for (let i = 2; i < highs.length - 2; i++) {
      if (
        highs[i] > highs[i - 1] &&
        highs[i] > highs[i - 2] &&
        highs[i] > highs[i + 1] &&
        highs[i] > highs[i + 2]
      ) {
        swingHighs.push({ price: highs[i], index: i });
      }

      if (
        lows[i] < lows[i - 1] &&
        lows[i] < lows[i - 2] &&
        lows[i] < lows[i + 1] &&
        lows[i] < lows[i + 2]
      ) {
        swingLows.push({ price: lows[i], index: i });
      }
    }

    // Detect BOS
    let bosDetected = false;
    if (swingHighs.length >= 2) {
      const lastClose = _closes[_closes.length - 1] || 0;
      if (lastClose > swingHighs[swingHighs.length - 2].price) {
        bosDetected = true;
      }
    }

    // Detect CHoCH
    let chochDetected = false;
    if (swingHighs.length >= 3 && swingLows.length >= 3) {
      if (
        swingHighs[swingHighs.length - 1].price < swingHighs[swingHighs.length - 2].price &&
        swingLows[swingLows.length - 1].price < swingLows[swingLows.length - 2].price
      ) {
        chochDetected = true;
      }
    }

    return {
      bos: bosDetected,
      choch: chochDetected,
      swingHighs: swingHighs.slice(-3),
      swingLows: swingLows.slice(-3),
    };
  }

  static detectLiquiditySweep(
    highs: number[],
    lows: number[],
    volumes: number[]
  ): LiquidityResult {
    const recentHigh = Math.max(...highs.slice(-20));
    const recentLow = Math.min(...lows.slice(-20));

    let sweepDetected = false;
    let sweepType: 'buy_side' | 'sell_side' | null = null;
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / 20;

    // Check for buy-side liquidity sweep
    if (highs[highs.length - 1] > recentHigh * 1.001 && volumes[volumes.length - 1] > avgVolume) {
      sweepDetected = true;
      sweepType = 'buy_side';
    }
    // Check for sell-side liquidity sweep
    else if (lows[lows.length - 1] < recentLow * 0.999 && volumes[volumes.length - 1] > avgVolume) {
      sweepDetected = true;
      sweepType = 'sell_side';
    }

    return {
      sweepDetected,
      sweepType,
      recentHigh,
      recentLow,
    };
  }
}
