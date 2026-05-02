// Structure, Zones, and Liquidity Analyzers
// Converted from Python catalyst_ai.py StructureAnalyzer, Zones, Liquidity classes
// These provide the inputs to the UltraFilter for 94.3% quality scoring

export interface StructureResult {
  trend: 'bullish' | 'bearish' | 'neutral';
  bosConfirmed: boolean;
  chochConfirmed: boolean;
  multiTfAligned: boolean;
}

export interface ZonesResult {
  atSupply: boolean;
  atDemand: boolean;
  hasOrderBlock: boolean;
  hasActiveFvg: boolean;
  hasFvg: boolean;
}

export interface LiquidityResult {
  sweepDetected: boolean;
  sweepType: 'buy_side' | 'sell_side' | 'none';
  building: boolean;
}

/**
 * StructureAnalyzer — Detects market structure (trend, BOS, CHoCH, multi-TF alignment).
 * Converted from Python StructureAnalyzer.analyze()
 */
export class StructureAnalyzer {
  static analyze(data: {
    high: number[];
    low: number[];
    close: number[];
  }): StructureResult {
    const { high, low, close } = data;
    let trend: 'bullish' | 'bearish' | 'neutral' = 'neutral';
    let bos = false;
    let choch = false;
    let mlt = false;

    if (high.length >= 20) {
      // Find swing highs and lows using 5-bar window
      const swingHighs: number[] = [];
      const swingLows: number[] = [];

      for (let i = 5; i < high.length - 5; i++) {
        let isSwingHigh = true;
        let isSwingLow = true;

        for (let j = 1; j <= 5; j++) {
          if (high[i] < high[i - j] || high[i] < high[i + j]) isSwingHigh = false;
          if (low[i] > low[i - j] || low[i] > low[i + j]) isSwingLow = false;
        }

        if (isSwingHigh) swingHighs.push(high[i]);
        if (isSwingLow) swingLows.push(low[i]);
      }

      // Determine trend from swing points
      if (swingHighs.length >= 2 && swingLows.length >= 2) {
        const lastSH = swingHighs[swingHighs.length - 1];
        const prevSH = swingHighs[swingHighs.length - 2];
        const lastSL = swingLows[swingLows.length - 1];
        const prevSL = swingLows[swingLows.length - 2];

        if (lastSH > prevSH && lastSL > prevSL) trend = 'bullish';
        else if (lastSH < prevSH && lastSL < prevSL) trend = 'bearish';
      }

      // BOS: price breaks above/below recent 10-bar range
      const recentHighs = high.slice(-10, -1);
      const recentLows = low.slice(-10, -1);
      if (recentHighs.length > 0 && recentLows.length > 0) {
        const maxHigh = Math.max(...recentHighs);
        const minLow = Math.min(...recentLows);
        if (close[close.length - 1] > maxHigh || close[close.length - 1] < minLow) {
          bos = true;
        }
      }

      // CHoCH: trend reversal detection
      if (trend === 'bullish') {
        const recentLows5 = low.slice(-5, -1);
        if (recentLows5.length > 0 && close[close.length - 1] < Math.min(...recentLows5)) {
          choch = true;
        }
      } else if (trend === 'bearish') {
        const recentHighs5 = high.slice(-5, -1);
        if (recentHighs5.length > 0 && close[close.length - 1] > Math.max(...recentHighs5)) {
          choch = true;
        }
      }

      // Multi-TF alignment (simplified: check if close breaks above 5-period swing)
      // In Python this resamples to 5min; here we approximate with last 40 bars
      if (close.length >= 40) {
        const higherHighs = high.slice(-40);
        const maxHH = Math.max(...higherHighs.slice(0, -1));
        if (close[close.length - 1] > maxHH) mlt = true;
      }
    }

    return {
      trend,
      bosConfirmed: bos,
      chochConfirmed: choch,
      multiTfAligned: mlt,
    };
  }
}

/**
 * Zones — Detects supply/demand zones, order blocks, and fair value gaps.
 * Converted from Python Zones.detect()
 */
export class ZonesAnalyzer {
  static detect(data: {
    high: number[];
    low: number[];
    close: number[];
    open: number[];
  }): ZonesResult {
    const { high, low, close, open } = data;
    const hi = high[high.length - 1];
    const lo = low[low.length - 1];

    // Recent range (20 bars back)
    const recentHighs = high.slice(-21, -1);
    const recentLows = low.slice(-21, -1);
    const rh = recentHighs.length > 0 ? Math.max(...recentHighs) : hi;
    const rl = recentLows.length > 0 ? Math.min(...recentLows) : lo;

    // At supply: current high near resistance (within 0.3%)
    const atSupply = hi >= rh * 0.997;
    // At demand: current low near support (within 0.3%)
    const atDemand = lo <= rl * 1.003;

    // Order block: large candle body relative to previous
    let hasOrderBlock = false;
    if (data.high.length >= 3) {
      const lastRange = hi - lo;
      const prevRange = high[high.length - 2] - low[low.length - 2];
      if (prevRange > 0 && lastRange > 2 * prevRange) {
        hasOrderBlock = true;
      }
    }

    // Fair Value Gap: price gap between candle 3 bars ago and current
    let hasActiveFvg = false;
    let hasFvg = false;
    if (close.length >= 3) {
      const c1 = low[low.length - 1];
      const c3 = high[high.length - 3];
      const p2l = low[low.length - 2];
      const p2h = high[high.length - 3];

      // Bullish FVG: current low > 3-bars-ago high
      if (c1 > p2h) {
        hasFvg = true;
        hasActiveFvg = true;
      }
      // Bearish FVG: current high < 3-bars-ago low
      if (high[high.length - 1] < p2l) {
        hasFvg = true;
        hasActiveFvg = true;
      }
    }

    return {
      atSupply,
      atDemand,
      hasOrderBlock,
      hasActiveFvg,
      hasFvg,
    };
  }
}

/**
 * Liquidity — Detects liquidity sweeps and liquidity building.
 * Converted from Python Liquidity.analyze()
 */
export class LiquidityAnalyzer {
  static analyze(data: {
    high: number[];
    low: number[];
    close: number[];
  }): LiquidityResult {
    const { high, low, close } = data;
    let sweepDetected = false;
    let sweepType: 'buy_side' | 'sell_side' | 'none' = 'none';

    const h = high.slice(-10);
    const l = low.slice(-10);

    if (h.length >= 5) {
      const rh = Math.max(...h.slice(0, -1)); // recent high excluding current
      const rl = Math.min(...l.slice(0, -1)); // recent low excluding current

      // Buy-side sweep: current high > recent high, but close < recent high
      if (h[h.length - 1] > rh && close[close.length - 1] < rh) {
        sweepDetected = true;
        sweepType = 'buy_side';
      }
      // Sell-side sweep: current low < recent low, but close > recent low
      else if (l[l.length - 1] < rl && close[close.length - 1] > rl) {
        sweepDetected = true;
        sweepType = 'sell_side';
      }
    }

    // Liquidity building: tight range (consolidation)
    let building = false;
    if (h.length >= 3 && l.length >= 3) {
      const hRange = Math.max(...h) - Math.min(...h);
      const lRange = Math.max(...l) - Math.min(...l);
      const avgH = h.reduce((a, b) => a + b, 0) / h.length;
      const avgL = l.reduce((a, b) => a + b, 0) / l.length;
      if ((hRange < avgH * 0.001) || (lRange < avgL * 0.001)) {
        building = true;
      }
    }

    return {
      sweepDetected,
      sweepType,
      building,
    };
  }
}
