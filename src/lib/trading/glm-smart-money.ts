// GLM Smart Money Engine — Converted from Python reference
// Combines Market Structure detection, Liquidity Sweep analysis,
// Breakout Confirmation, and Fake Signal Filtering into one engine.

// ─── Types ──────────────────────────────────────────────────────────────

export type StructureSignal = 'BOS_UP' | 'BOS_DOWN' | 'RANGE';
export type LiquiditySignal = 'BUY_SWEEP' | 'SELL_SWEEP' | 'NO_SWEEP';
export type BreakoutSignal =
  | 'CONFIRMED_BREAKOUT_BUY'
  | 'CONFIRMED_BREAKDOWN_SELL'
  | 'NO_BREAKOUT';
export type FilteredSignal =
  | 'VALID_BUY'
  | 'VALID_SELL'
  | 'FILTERED_NO_TRADE'
  | 'WAIT';

export interface GLMSmartMoneyResult {
  /** Current price at time of analysis */
  price: number;
  /** Last market structure signal */
  structure: StructureSignal;
  /** Last liquidity sweep signal */
  liquidity: LiquiditySignal;
  /** Breakout confirmation result */
  breakout: BreakoutSignal;
  /** Final filtered signal — the ultimate trade decision */
  signal: FilteredSignal;
  /** Human-readable labels for display */
  labels: {
    structure: string;
    liquidity: string;
    breakout: string;
    signal: string;
  };
  /** Detailed breakdown for each bar (last 5) */
  structureHistory: StructureSignal[];
  liquidityHistory: LiquiditySignal[];
}

// ─── Market Structure Detector ──────────────────────────────────────────

class MarketStructure {
  /**
   * Detect Break of Structure across closing prices.
   * Uses a 5-bar rolling window: if close breaks above the 5-bar high → BOS_UP,
   * if close breaks below the 5-bar low → BOS_DOWN, else RANGE.
   */
  detect(closes: number[]): StructureSignal[] {
    const structure: StructureSignal[] = [];

    for (let i = 5; i < closes.length; i++) {
      const window = closes.slice(i - 5, i);
      const prevHigh = Math.max(...window);
      const prevLow = Math.min(...window);

      if (closes[i] > prevHigh) {
        structure.push('BOS_UP');
      } else if (closes[i] < prevLow) {
        structure.push('BOS_DOWN');
      } else {
        structure.push('RANGE');
      }
    }

    return structure;
  }
}

// ─── Liquidity Engine ───────────────────────────────────────────────────

class LiquidityEngine {
  /**
   * Detect liquidity sweeps using high/low/close data.
   * BUY_SWEEP: fake drop (low < prev low) then reverse up (close > prev close)
   * SELL_SWEEP: fake spike (high > prev high) then drop (close < prev close)
   */
  detect(highs: number[], lows: number[], closes: number[]): LiquiditySignal[] {
    const signals: LiquiditySignal[] = [];

    for (let i = 2; i < closes.length; i++) {
      // Buy-side liquidity sweep: fake drop then reverse up
      if (lows[i] < lows[i - 1] && closes[i] > closes[i - 1]) {
        signals.push('BUY_SWEEP');
      }
      // Sell-side liquidity sweep: fake spike then drop
      else if (highs[i] > highs[i - 1] && closes[i] < closes[i - 1]) {
        signals.push('SELL_SWEEP');
      } else {
        signals.push('NO_SWEEP');
      }
    }

    return signals;
  }
}

// ─── Breakout Confirmation ──────────────────────────────────────────────

/**
 * Confirm a breakout when structure break aligns with price clearing
 * key resistance (for buys) or support (for sells).
 */
function breakoutConfirmation(
  price: number,
  structureSignal: StructureSignal,
  resistance: number[],
  support: number[]
): BreakoutSignal {
  const maxResistance = resistance.length > 0 ? Math.max(...resistance) : Infinity;
  const minSupport = support.length > 0 ? Math.min(...support) : -Infinity;

  if (structureSignal === 'BOS_UP' && price > maxResistance) {
    return 'CONFIRMED_BREAKOUT_BUY';
  }

  if (structureSignal === 'BOS_DOWN' && price < minSupport) {
    return 'CONFIRMED_BREAKDOWN_SELL';
  }

  return 'NO_BREAKOUT';
}

// ─── Fake Signal Filter ─────────────────────────────────────────────────

/**
 * Filter out weak or conflicting signals:
 * - NO_SWEEP + RANGE → FILTERED (no trade)
 * - BUY_SWEEP + CONFIRMED_BREAKOUT_BUY → VALID BUY
 * - SELL_SWEEP + CONFIRMED_BREAKDOWN_SELL → VALID SELL
 * - Everything else → WAIT
 */
function fakeSignalFilter(
  liquidity: LiquiditySignal,
  structure: StructureSignal,
  breakout: BreakoutSignal
): FilteredSignal {
  // Reject weak signals — no sweep + no structure break = no trade
  if (liquidity === 'NO_SWEEP' && structure === 'RANGE') {
    return 'FILTERED_NO_TRADE';
  }

  // Validate alignment: sell sweep + confirmed breakdown = valid sell
  if (liquidity === 'SELL_SWEEP' && breakout === 'CONFIRMED_BREAKDOWN_SELL') {
    return 'VALID_SELL';
  }

  // Validate alignment: buy sweep + confirmed breakout = valid buy
  if (liquidity === 'BUY_SWEEP' && breakout === 'CONFIRMED_BREAKOUT_BUY') {
    return 'VALID_BUY';
  }

  return 'WAIT';
}

// ─── Label Mappings ─────────────────────────────────────────────────────

const STRUCTURE_LABELS: Record<StructureSignal, string> = {
  BOS_UP: 'BOS ↑ Bullish Break',
  BOS_DOWN: 'BOS ↓ Bearish Break',
  RANGE: 'RANGE ↔ Consolidation',
};

const LIQUIDITY_LABELS: Record<LiquiditySignal, string> = {
  BUY_SWEEP: 'Buy Sweep 🟢 (Fake Drop → Reverse Up)',
  SELL_SWEEP: 'Sell Sweep 🔴 (Fake Spike → Drop)',
  NO_SWEEP: 'No Sweep',
};

const BREAKOUT_LABELS: Record<BreakoutSignal, string> = {
  CONFIRMED_BREAKOUT_BUY: 'Confirmed Breakout Buy 🚀',
  CONFIRMED_BREAKDOWN_SELL: 'Confirmed Breakdown Sell 📉',
  NO_BREAKOUT: 'No Breakout',
};

const SIGNAL_LABELS: Record<FilteredSignal, string> = {
  VALID_BUY: 'VALID BUY ✔ 🟢',
  VALID_SELL: 'VALID SELL ✔ 🔴',
  FILTERED_NO_TRADE: 'FILTERED ❌ (NO TRADE)',
  WAIT: 'WAIT ⏸',
};

// ─── Main Engine ────────────────────────────────────────────────────────

export class GLM_SmartMoneyEngine {
  private structureDetector = new MarketStructure();
  private liquidityDetector = new LiquidityEngine();

  /**
   * Run full GLM Smart Money analysis on market data.
   *
   * @param highs - Array of high prices
   * @param lows - Array of low prices
   * @param closes - Array of closing prices
   * @param support - Array of support price levels
   * @param resistance - Array of resistance price levels
   * @returns GLMSmartMoneyResult with all analysis components
   */
  analyze(
    highs: number[],
    lows: number[],
    closes: number[],
    support: number[],
    resistance: number[]
  ): GLMSmartMoneyResult {
    const price = closes[closes.length - 1];

    // Run structure detection across all closes
    const structureHistory = this.structureDetector.detect(closes);
    const liquidityHistory = this.liquidityDetector.detect(highs, lows, closes);

    // Get the latest signals
    const lastStructure: StructureSignal = structureHistory.length > 0
      ? structureHistory[structureHistory.length - 1]
      : 'RANGE';
    const lastLiquidity: LiquiditySignal = liquidityHistory.length > 0
      ? liquidityHistory[liquidityHistory.length - 1]
      : 'NO_SWEEP';

    // Confirm breakout using current price + structure + S/R levels
    const breakout = breakoutConfirmation(price, lastStructure, resistance, support);

    // Apply fake signal filter for final trade decision
    const signal = fakeSignalFilter(lastLiquidity, lastStructure, breakout);

    return {
      price,
      structure: lastStructure,
      liquidity: lastLiquidity,
      breakout,
      signal,
      labels: {
        structure: STRUCTURE_LABELS[lastStructure],
        liquidity: LIQUIDITY_LABELS[lastLiquidity],
        breakout: BREAKOUT_LABELS[breakout],
        signal: SIGNAL_LABELS[signal],
      },
      // Keep last 5 entries for history display
      structureHistory: structureHistory.slice(-5),
      liquidityHistory: liquidityHistory.slice(-5),
    };
  }

  /**
   * Quick check if the engine validates a buy signal.
   */
  isBuySignal(result: GLMSmartMoneyResult): boolean {
    return result.signal === 'VALID_BUY';
  }

  /**
   * Quick check if the engine validates a sell signal.
   */
  isSellSignal(result: GLMSmartMoneyResult): boolean {
    return result.signal === 'VALID_SELL';
  }

  /**
   * Check if signal is filtered (no trade recommended).
   */
  isFiltered(result: GLMSmartMoneyResult): boolean {
    return result.signal === 'FILTERED_NO_TRADE';
  }

  /**
   * Get signal strength score (0-100) based on alignment quality.
   * Higher scores indicate stronger confluence between all components.
   */
  getSignalStrength(result: GLMSmartMoneyResult): number {
    let score = 0;

    // Structure contribution (0-30)
    if (result.structure === 'BOS_UP' || result.structure === 'BOS_DOWN') {
      score += 30;
    } else {
      score += 5; // Small credit for being in a range (at least we know)
    }

    // Liquidity contribution (0-30)
    if (result.liquidity === 'BUY_SWEEP' || result.liquidity === 'SELL_SWEEP') {
      score += 30;
    }

    // Breakout contribution (0-25)
    if (result.breakout === 'CONFIRMED_BREAKOUT_BUY' || result.breakout === 'CONFIRMED_BREAKDOWN_SELL') {
      score += 25;
    }

    // Final filter contribution (0-15)
    if (result.signal === 'VALID_BUY' || result.signal === 'VALID_SELL') {
      score += 15;
    } else if (result.signal === 'WAIT') {
      score += 5;
    }

    return score;
  }
}
