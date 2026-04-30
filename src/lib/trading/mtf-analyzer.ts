// CATALYST AI - Multi-Timeframe (MTF) Analyzer
// Analyzes market data across 6 timeframes (30s, 45s, 1m, 2m, 3m, 5m)
// Provides 8-point advanced checklist for multi-timeframe confluence
// Converted from Python: MTFAnalyzer with advanced checklist integration

import { TechnicalIndicators } from './indicators';
import { PriceActionAnalyzer } from './price-action';
import { bugFixer } from './bug-fixer';
import { TRADING_CONFIG, type MarketData, type MTFTimeframe, type MTFAnalysis, type MTFConfluence } from './types';

/**
 * Timeframe hierarchy for MTF analysis.
 * Higher timeframes carry more weight in confluence scoring.
 */
const TIMEFRAME_HIERARCHY: Record<MTFTimeframe, { weight: number; barMultiplier: number }> = {
  '5m':  { weight: 0.30, barMultiplier: 10 },  // Highest weight — anchors the analysis
  '3m':  { weight: 0.25, barMultiplier: 6 },
  '2m':  { weight: 0.20, barMultiplier: 4 },
  '1m':  { weight: 0.15, barMultiplier: 2 },
  '45s': { weight: 0.05, barMultiplier: 1.5 },
  '30s': { weight: 0.05, barMultiplier: 1 },    // Lowest weight — fine-grained
};

const MTF_TIMEFRAMES: MTFTimeframe[] = ['30s', '45s', '1m', '2m', '3m', '5m'];

export class MTFAnalyzer {
  /**
   * Analyze a single timeframe using the market data.
   * Aggregates bars to simulate the higher timeframe view.
   */
  analyzeTimeframe(
    marketData: MarketData,
    timeframe: MTFTimeframe
  ): MTFAnalysis {
    const { closePrices, highPrices, lowPrices, openPrices, volumes } = marketData;

    // Aggregate data to the target timeframe
    const multiplier = TIMEFRAME_HIERARCHY[timeframe].barMultiplier;
    const aggregated = this.aggregateBars(
      closePrices, highPrices, lowPrices, openPrices, volumes, multiplier
    );

    if (aggregated.close.length < 10) {
      return this.defaultMTFAnalysis(timeframe);
    }

    // Calculate indicators on aggregated data
    const rsi = TechnicalIndicators.calculateRSI(aggregated.close, TRADING_CONFIG.RSI_PERIOD);
    const { k: stochK, d: stochD } = TechnicalIndicators.calculateStochastic(
      aggregated.high, aggregated.low, aggregated.close
    );
    const adx = TechnicalIndicators.calculateADX(
      aggregated.high, aggregated.low, aggregated.close, TRADING_CONFIG.ADX_PERIOD
    );
    const emaShort = TechnicalIndicators.calculateEMA(aggregated.close, TRADING_CONFIG.EMA_SHORT);
    const emaLong = TechnicalIndicators.calculateEMA(aggregated.close, TRADING_CONFIG.EMA_LONG);
    const { bbWidth } = TechnicalIndicators.calculateBollingerBands(
      aggregated.close, TRADING_CONFIG.BB_PERIOD, TRADING_CONFIG.BB_STD
    );

    // Price action on aggregated data
    const structure = PriceActionAnalyzer.detectBosChoch(
      aggregated.high, aggregated.low, aggregated.close
    );
    const fvgs = PriceActionAnalyzer.detectFVG(aggregated.close);
    const liquidity = PriceActionAnalyzer.detectLiquiditySweep(
      aggregated.high, aggregated.low, aggregated.volume
    );

    // Determine trend
    const trend = this.determineTrend(emaShort, emaLong, adx, rsi);
    const trendStrength = this.calculateTrendStrength(emaShort, emaLong, adx, aggregated.close);

    // Volume spike detection
    const avgVol = aggregated.volume.length >= 20
      ? aggregated.volume.slice(-20).reduce((a, b) => a + b, 0) / 20
      : aggregated.volume.reduce((a, b) => a + b, 0) / Math.max(1, aggregated.volume.length);
    const volumeSpike = aggregated.volume[aggregated.volume.length - 1] > avgVol * 1.5;

    // Recent FVGs (within last 3 aggregated bars)
    const recentFvgs = fvgs.filter(f => f.index >= aggregated.close.length - 3);

    return {
      timeframe,
      trend,
      trendStrength,
      rsi: +rsi.toFixed(1),
      stochK: +stochK.toFixed(1),
      stochD: +stochD.toFixed(1),
      adx: +adx.toFixed(1),
      bosConfirmed: structure.bos,
      chochConfirmed: structure.choch,
      fvgActive: recentFvgs.length > 0,
      liquiditySweep: liquidity.sweepDetected,
      emaShort: +emaShort.toFixed(5),
      emaLong: +emaLong.toFixed(5),
      bbWidth: +bbWidth.toFixed(4),
      volumeSpike,
    };
  }

  /**
   * Run full MTF confluence analysis across all 6 timeframes.
   * Includes the 8-point advanced checklist.
   */
  analyzeConfluence(marketData: MarketData): MTFConfluence {
    const timeframeResults: Partial<Record<MTFTimeframe, MTFAnalysis>> = {};

    // Analyze each timeframe with bug fixer protection
    for (const tf of MTF_TIMEFRAMES) {
      const result = bugFixer.autoFixDecoratorSync(
        () => this.analyzeTimeframe(marketData, tf),
        {
          fallbackValue: this.defaultMTFAnalysis(tf),
          retryCount: 2,
          module: 'mtf-analyzer',
          function: `analyzeTimeframe_${tf}`,
        }
      )();
      timeframeResults[tf] = result;
    }

    // Cast to full record since all timeframes are covered
    const results = timeframeResults as Record<MTFTimeframe, MTFAnalysis>;

    // Count trend directions
    let bullishCount = 0;
    let bearishCount = 0;
    let neutralCount = 0;

    for (const tf of MTF_TIMEFRAMES) {
      const trend = results[tf].trend;
      if (trend === 'bullish') bullishCount++;
      else if (trend === 'bearish') bearishCount++;
      else neutralCount++;
    }

    // Determine dominant trend (weighted by timeframe hierarchy)
    let bullishWeight = 0;
    let bearishWeight = 0;
    for (const tf of MTF_TIMEFRAMES) {
      const weight = TIMEFRAME_HIERARCHY[tf].weight;
      if (results[tf].trend === 'bullish') bullishWeight += weight;
      else if (results[tf].trend === 'bearish') bearishWeight += weight;
    }

    const dominantTrend: 'bullish' | 'bearish' | 'neutral' =
      bullishWeight > bearishWeight + 0.15 ? 'bullish' :
      bearishWeight > bullishWeight + 0.15 ? 'bearish' : 'neutral';

    // Alignment check: are the majority of timeframes aligned?
    const aligned = bullishCount >= 4 || bearishCount >= 4;

    // Weighted alignment score
    const alignedWeight = Math.max(bullishWeight, bearishWeight);
    const alignmentScore = +(alignedWeight * 100).toFixed(1);

    // ─── 8-Point Advanced Checklist ──────────────────────────────
    const higherTF = results['5m'];
    const middleTF = results['2m'];
    const lowerTF = results['30s'];

    const checklist = {
      // 1. Higher timeframe trend alignment
      higher_tf_trend_alignment: higherTF.trend === dominantTrend && dominantTrend !== 'neutral',

      // 2. Structure break confirmed on at least 2 timeframes
      structure_break_confirmed: this.countConfirmations(results, 'bosConfirmed') >= 2,

      // 3. Momentum convergence — RSI agrees across timeframes
      momentum_convergence: this.checkMomentumConvergence(results, dominantTrend),

      // 4. Volume confirmation on at least one timeframe
      volume_confirmation: MTF_TIMEFRAMES.some(tf => results[tf].volumeSpike),

      // 5. RSI divergence check (no contradictory divergence)
      rsi_divergence_check: this.checkRSIDivergence(results, dominantTrend),

      // 6. EMA stack alignment — EMAs properly ordered
      ema_stack_alignment: this.checkEMAStack(results, dominantTrend),

      // 7. Volatility filter — BB width is reasonable
      volatility_filter: this.checkVolatilityFilter(results),

      // 8. Liquidity pool proximity — sweep detected on at least one TF
      liquidity_pool_proximity: MTF_TIMEFRAMES.some(tf => results[tf].liquiditySweep),
    };

    // Calculate checklist score (weighted)
    const checklistWeights: Record<string, number> = {
      higher_tf_trend_alignment: 0.20,
      structure_break_confirmed: 0.15,
      momentum_convergence: 0.15,
      volume_confirmation: 0.10,
      rsi_divergence_check: 0.10,
      ema_stack_alignment: 0.12,
      volatility_filter: 0.08,
      liquidity_pool_proximity: 0.10,
    };

    let checklistScore = 0;
    for (const [key, weight] of Object.entries(checklistWeights)) {
      if (checklist[key as keyof typeof checklist]) {
        checklistScore += weight;
      }
    }
    checklistScore = +(checklistScore * 100).toFixed(1);

    return {
      aligned,
      alignmentScore,
      dominantTrend,
      bullishCount,
      bearishCount,
      neutralCount,
      timeframeResults: results,
      checklist,
      checklistScore,
    };
  }

  // ─── Private Helpers ──────────────────────────────────────────────

  /**
   * Aggregate bars to simulate higher timeframes.
   * For example, 30s bars aggregated by 2x become 1m bars.
   */
  private aggregateBars(
    close: number[],
    high: number[],
    low: number[],
    open: number[],
    volume: number[],
    multiplier: number
  ): { close: number[]; high: number[]; low: number[]; open: number[]; volume: number[] } {
    if (multiplier <= 1) {
      return { close, high, low, open, volume };
    }

    const aggClose: number[] = [];
    const aggHigh: number[] = [];
    const aggLow: number[] = [];
    const aggOpen: number[] = [];
    const aggVolume: number[] = [];

    for (let i = 0; i < close.length; i += multiplier) {
      const end = Math.min(i + multiplier, close.length);
      const sliceClose = close.slice(i, end);
      const sliceHigh = high.slice(i, end);
      const sliceLow = low.slice(i, end);
      const sliceOpen = open.slice(i, end);
      const sliceVol = volume.slice(i, end);

      if (sliceClose.length === 0) break;

      aggClose.push(sliceClose[sliceClose.length - 1]);
      aggHigh.push(Math.max(...sliceHigh));
      aggLow.push(Math.min(...sliceLow));
      aggOpen.push(sliceOpen[0]);
      aggVolume.push(sliceVol.reduce((a, b) => a + b, 0));
    }

    return { close: aggClose, high: aggHigh, low: aggLow, open: aggOpen, volume: aggVolume };
  }

  /**
   * Determine trend based on multiple indicator confluence.
   */
  private determineTrend(
    emaShort: number,
    emaLong: number,
    adx: number,
    rsi: number
  ): 'bullish' | 'bearish' | 'neutral' {
    let score = 0;

    // EMA alignment
    if (emaShort > emaLong) score += 2;
    else if (emaShort < emaLong) score -= 2;

    // ADX confirms trend strength
    if (adx > 25) {
      if (score > 0) score += 1;
      else if (score < 0) score -= 1;
    }

    // RSI direction
    if (rsi > 55) score += 1;
    else if (rsi < 45) score -= 1;

    if (score >= 3) return 'bullish';
    if (score <= -3) return 'bearish';
    return 'neutral';
  }

  /**
   * Calculate trend strength (0-100).
   */
  private calculateTrendStrength(
    emaShort: number,
    emaLong: number,
    adx: number,
    closePrices: number[]
  ): number {
    if (closePrices.length === 0) return 0;

    const currentPrice = closePrices[closePrices.length - 1];

    // EMA spread contribution
    const emaSpread = currentPrice > 0 ? Math.abs(emaShort - emaLong) / currentPrice : 0;
    const emaScore = Math.min(50, emaSpread * 5000); // Scale to 0-50

    // ADX contribution
    const adxScore = Math.min(50, (adx / 50) * 50); // Scale 0-50 ADX to 0-50 score

    return +Math.min(100, emaScore + adxScore).toFixed(1);
  }

  /**
   * Count how many timeframes have a specific confirmation.
   */
  private countConfirmations(
    results: Record<MTFTimeframe, MTFAnalysis>,
    field: 'bosConfirmed' | 'chochConfirmed' | 'liquiditySweep' | 'fvgActive'
  ): number {
    let count = 0;
    for (const tf of MTF_TIMEFRAMES) {
      if (results[tf][field]) count++;
    }
    return count;
  }

  /**
   * Check if RSI is convergent across timeframes (not divergent).
   */
  private checkMomentumConvergence(
    results: Record<MTFTimeframe, MTFAnalysis>,
    dominantTrend: 'bullish' | 'bearish' | 'neutral'
  ): boolean {
    if (dominantTrend === 'neutral') return false;

    let convergent = 0;
    let total = 0;

    for (const tf of MTF_TIMEFRAMES) {
      const rsi = results[tf].rsi;
      total++;

      if (dominantTrend === 'bullish' && rsi > 45) convergent++;
      else if (dominantTrend === 'bearish' && rsi < 55) convergent++;
    }

    return convergent / total >= 0.6; // 60% of timeframes agree
  }

  /**
   * Check for RSI divergence across timeframes.
   * Returns true if NO harmful divergence is detected.
   */
  private checkRSIDivergence(
    results: Record<MTFTimeframe, MTFAnalysis>,
    dominantTrend: 'bullish' | 'bearish' | 'neutral'
  ): boolean {
    if (dominantTrend === 'neutral') return true;

    // Check that no higher TF shows strong divergence
    const higherTFs: MTFTimeframe[] = ['3m', '5m'];
    for (const tf of higherTFs) {
      const rsi = results[tf].rsi;
      if (dominantTrend === 'bullish' && rsi > 80) return false; // Overbought divergence
      if (dominantTrend === 'bearish' && rsi < 20) return false; // Oversold divergence
    }

    return true;
  }

  /**
   * Check if EMAs are properly stacked for the trend direction.
   */
  private checkEMAStack(
    results: Record<MTFTimeframe, MTFAnalysis>,
    dominantTrend: 'bullish' | 'bearish' | 'neutral'
  ): boolean {
    if (dominantTrend === 'neutral') return false;

    let aligned = 0;
    let total = 0;

    for (const tf of MTF_TIMEFRAMES) {
      total++;
      if (dominantTrend === 'bullish' && results[tf].emaShort > results[tf].emaLong) aligned++;
      else if (dominantTrend === 'bearish' && results[tf].emaShort < results[tf].emaLong) aligned++;
    }

    return aligned / total >= 0.5; // At least 50% of TFs have EMA alignment
  }

  /**
   * Check if volatility (BB width) is within acceptable range.
   */
  private checkVolatilityFilter(results: Record<MTFTimeframe, MTFAnalysis>): boolean {
    // Volatility is acceptable if BB width is between 0.005 and 0.06 on the middle TFs
    const middleTFs: MTFTimeframe[] = ['1m', '2m', '3m'];
    let acceptable = 0;

    for (const tf of middleTFs) {
      if (results[tf].bbWidth >= 0.005 && results[tf].bbWidth <= 0.06) {
        acceptable++;
      }
    }

    return acceptable >= 2; // At least 2 of 3 middle TFs have acceptable volatility
  }

  /**
   * Return a default MTF analysis for a timeframe when data is insufficient.
   */
  private defaultMTFAnalysis(timeframe: MTFTimeframe): MTFAnalysis {
    return {
      timeframe,
      trend: 'neutral',
      trendStrength: 0,
      rsi: 50,
      stochK: 50,
      stochD: 50,
      adx: 20,
      bosConfirmed: false,
      chochConfirmed: false,
      fvgActive: false,
      liquiditySweep: false,
      emaShort: 0,
      emaLong: 0,
      bbWidth: 0.02,
      volumeSpike: false,
    };
  }
}
