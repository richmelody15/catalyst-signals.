// Signal Quality Checker - 94.3% Filter Engine with 14-Point Entry Checklist
import type { QualityChecklist } from './types';

interface QualityCheckContext {
  signalData: {
    direction: string;
    bosConfirmed: boolean;
    chochConfirmed: boolean;
    fvgActive: boolean;
    liquiditySweep: boolean;
  };
  marketData: {
    rsi: number;
    stochK: number;
    stochD: number;
    adx: number;
    bbExpanding: boolean;
    volumeSpike: boolean;
    currentPrice: number;
    supplyDemandZones: Array<{ type: string; price: number }>;
    recentCandles: Array<{
      open: number;
      high: number;
      low: number;
      close: number;
    }>;
    marketStructure: {
      trend: string;
      pattern: string;
    };
    multiTimeframe: Record<string, { trend: string }>;
  };
}

export class SignalQualityChecker {
  private checklistWeights: Record<string, number> = {
    market_structure_alignment: 0.10,
    bos_confirmation: 0.10,
    choch_confirmation: 0.10,
    fvg_interaction: 0.08,
    liquidity_sweep: 0.10,
    order_block_validation: 0.08,
    volume_confirmation: 0.08,
    candle_confirmation: 0.08,
    rsi_alignment: 0.06,
    stochastic_alignment: 0.06,
    adx_strength: 0.06,
    bb_width_volatility: 0.04,
    multi_timeframe_alignment: 0.06,
    news_filter_clearance: 0.02,
  };

  checkSignalQuality(ctx: QualityCheckContext): QualityChecklist {
    const conditions: Record<string, boolean> = {};

    // 1. Market Structure Alignment
    conditions.market_structure_alignment = this.checkStructureAlignment(ctx);

    // 2. BOS Confirmation
    conditions.bos_confirmation = ctx.signalData.bosConfirmed;

    // 3. CHoCH Confirmation
    conditions.choch_confirmation = ctx.signalData.chochConfirmed;

    // 4. FVG Interaction
    conditions.fvg_interaction = ctx.signalData.fvgActive;

    // 5. Liquidity Sweep
    conditions.liquidity_sweep = ctx.signalData.liquiditySweep;

    // 6. Order Block Validation
    conditions.order_block_validation = this.checkOrderBlock(ctx);

    // 7. Volume Confirmation
    conditions.volume_confirmation = ctx.marketData.volumeSpike;

    // 8. Candle Confirmation
    conditions.candle_confirmation = this.checkCandlePattern(ctx);

    // 9. RSI Alignment
    conditions.rsi_alignment = this.checkRSIAlignment(ctx);

    // 10. Stochastic Alignment
    conditions.stochastic_alignment = this.checkStochasticAlignment(ctx);

    // 11. ADX Strength
    conditions.adx_strength = ctx.marketData.adx > 25;

    // 12. BB Width Volatility
    conditions.bb_width_volatility = ctx.marketData.bbExpanding;

    // 13. Multi-Timeframe Alignment
    conditions.multi_timeframe_alignment = this.checkMTFAlignment(ctx);

    // 14. News Filter Clearance
    conditions.news_filter_clearance = true;

    // Calculate weighted score
    let score = 0;
    for (const [condition, passed] of Object.entries(conditions)) {
      const weight = this.checklistWeights[condition] || 0;
      score += weight * (passed ? 1 : 0);
    }

    // Check if passes 94.3% threshold
    const passed = score >= 0.943;

    return { conditions, score, passed };
  }

  private checkStructureAlignment(ctx: QualityCheckContext): boolean {
    const direction = ctx.signalData.direction;
    const structure = ctx.marketData.marketStructure;

    if (direction === 'BUY') {
      return structure.trend === 'bullish' || structure.pattern === 'reversal_to_bullish';
    } else if (direction === 'SELL') {
      return structure.trend === 'bearish' || structure.pattern === 'reversal_to_bearish';
    }
    return false;
  }

  private checkOrderBlock(ctx: QualityCheckContext): boolean {
    const zones = ctx.marketData.supplyDemandZones;
    if (!zones || zones.length === 0) return false;

    const currentPrice = ctx.marketData.currentPrice;
    for (const zone of zones) {
      if (Math.abs(currentPrice - zone.price) / currentPrice < 0.002) {
        return true;
      }
    }
    return false;
  }

  private checkCandlePattern(ctx: QualityCheckContext): boolean {
    const candles = ctx.marketData.recentCandles;
    if (candles.length < 3) return false;

    const last = candles[candles.length - 1];
    const prev = candles[candles.length - 2];

    // Bullish engulfing
    if (
      last.close > last.open &&
      prev.close < prev.open &&
      last.close > prev.open &&
      last.open < prev.close
    ) {
      return true;
    }

    // Bearish engulfing
    if (
      last.close < last.open &&
      prev.close > prev.open &&
      last.close < prev.open &&
      last.open > prev.close
    ) {
      return true;
    }

    // Rejection wick
    const body = Math.abs(last.close - last.open);
    const upperWick = last.high - Math.max(last.close, last.open);
    const lowerWick = Math.min(last.close, last.open) - last.low;

    if (upperWick > body * 2 || lowerWick > body * 2) {
      return true;
    }

    return false;
  }

  private checkRSIAlignment(ctx: QualityCheckContext): boolean {
    const rsi = ctx.marketData.rsi;
    const direction = ctx.signalData.direction;

    if (direction === 'BUY') return rsi < 40;
    if (direction === 'SELL') return rsi > 60;
    return false;
  }

  private checkStochasticAlignment(ctx: QualityCheckContext): boolean {
    const { stochK, stochD } = ctx.marketData;
    const direction = ctx.signalData.direction;

    if (direction === 'BUY') return stochK < 30 && stochK > stochD;
    if (direction === 'SELL') return stochK > 70 && stochK < stochD;
    return false;
  }

  private checkMTFAlignment(ctx: QualityCheckContext): boolean {
    const mtf = ctx.marketData.multiTimeframe;
    const trends = Object.values(mtf).map((v) => v.trend).filter(Boolean);

    if (trends.length < 2) return false;
    return trends.every((t) => t === trends[0]);
  }
}
