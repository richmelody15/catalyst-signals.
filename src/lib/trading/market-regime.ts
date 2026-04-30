// Market Regime Detection Engine
// Detects current market regime: Trending, Ranging, Volatile, Quiet, Breakout

export type MarketRegime = 'strong_trend' | 'weak_trend' | 'ranging' | 'volatile' | 'breakout' | 'quiet';

export interface RegimeResult {
  regime: MarketRegime;
  label: string;
  description: string;
  strategy: string;
  confidence: number;
  indicators: {
    adx: number;
    bbWidth: number;
    volatility: number;
    trendStrength: number;
  };
}

export class MarketRegimeDetector {

  static detect(data: {
    adx: number;
    bbWidth: number;
    atr: number;
    closePrices: number[];
    emaShort: number;
    emaLong: number;
    highPrices: number[];
    lowPrices: number[];
    volumes: number[];
  }): RegimeResult {
    const { adx, bbWidth, atr, closePrices, emaShort, emaLong, highPrices, lowPrices, volumes } = data;

    // Calculate volatility percentile
    const currentPrice = closePrices[closePrices.length - 1];
    const volatility = currentPrice > 0 ? atr / currentPrice : 0;

    // Trend strength from EMA alignment
    const emaSpread = currentPrice > 0 ? Math.abs(emaShort - emaLong) / currentPrice : 0;
    const trendStrength = Math.min(1, emaSpread * 100);

    // Volume surge detection
    const avgVolume = volumes.length >= 20
      ? volumes.slice(-20).reduce((a, b) => a + b, 0) / 20
      : volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const volumeRatio = avgVolume > 0 ? volumes[volumes.length - 1] / avgVolume : 1;

    // Range detection - check price compression
    const recentHighs = highPrices.slice(-20);
    const recentLows = lowPrices.slice(-20);
    const rangeHigh = Math.max(...recentHighs);
    const rangeLow = Math.min(...recentLows);
    const rangeWidth = currentPrice > 0 ? (rangeHigh - rangeLow) / currentPrice : 0;

    // Determine regime
    let regime: MarketRegime;
    let label: string;
    let description: string;
    let strategy: string;
    let confidence: number;

    if (adx > 40 && bbWidth > 0.03 && volumeRatio > 1.5) {
      regime = 'strong_trend';
      label = 'STRONG TREND';
      description = 'Market is in a strong directional move with high momentum and expanding volatility. ADX above 40 confirms trend strength with volume surge backing the move.';
      strategy = 'Follow the trend with momentum entries. Use pullbacks to EMA for entry. Avoid counter-trend trades. Set wider stops due to volatility. Scale in on confirmation candles.';
      confidence = 0.95;
    } else if (adx > 25 && trendStrength > 0.3) {
      regime = 'weak_trend';
      label = 'WEAK TREND';
      description = 'Market shows directional bias but momentum is moderate. ADX between 25-40 suggests the trend is developing or fading. Trade with caution and wait for confirmation.';
      strategy = 'Trade in the trend direction on confirmed setups only. Use BOS/CHoCH for entry confirmation. Tighter stops recommended. Look for FVG fills as entry zones.';
      confidence = 0.88;
    } else if (adx < 20 && rangeWidth < 0.01 && bbWidth < 0.02) {
      regime = 'quiet';
      label = 'QUIET MARKET';
      description = 'Market is in a low-activity consolidation phase. ADX below 20 shows no directional momentum. Price is compressed within narrow range. Ideal for breakout preparation.';
      strategy = 'Do not trade inside the range. Mark support/resistance boundaries. Set breakout alerts. Prepare orders above/below range. Risk is low but so is opportunity.';
      confidence = 0.75;
    } else if (adx < 20 && rangeWidth < 0.015) {
      regime = 'ranging';
      label = 'RANGING';
      description = 'Market is moving sideways between defined support and resistance levels. No clear trend direction. Price respects horizontal boundaries. Range trading strategies apply.';
      strategy = 'Buy at support, sell at resistance. Use RSI overbought/oversold for timing. Stochastic crossovers work well in ranges. Avoid trend-following strategies. Keep risk tight.';
      confidence = 0.82;
    } else if (bbWidth > 0.04 && volatility > 0.005) {
      regime = 'volatile';
      label = 'HIGH VOLATILITY';
      description = 'Market is experiencing extreme price swings with expanding Bollinger Bands. Large candles and wicks indicate uncertainty and aggressive institutional activity. High risk environment.';
      strategy = 'Reduce position size significantly. Wait for volatility contraction before entry. Use wider stops. Focus on liquidity sweeps and rejection wicks. Only take A+ setups with 94.3%+ filter.';
      confidence = 0.70;
    } else if (volumeRatio > 2.0 && bbWidth > 0.025) {
      regime = 'breakout';
      label = 'BREAKOUT';
      description = 'Market is breaking out of a defined range with surging volume. Price is moving decisively beyond previous support/resistance. Momentum is shifting and new trends may be forming.';
      strategy = 'Enter on retest of the broken level. Confirm with volume and BOS. Use the breakout range height for target projection. Aggressive entries on first pullback after breakout. Trail stops.';
      confidence = 0.90;
    } else {
      regime = 'weak_trend';
      label = 'DEVELOPING';
      description = 'Market conditions are transitional. No clear regime detected. Price action is mixed with conflicting signals. Wait for clarity before committing to a direction.';
      strategy = 'Stay on the sidelines until a clear regime forms. Monitor ADX for trend development. Watch for BOS/CHoCH signals. Prepare for both continuation and reversal scenarios.';
      confidence = 0.78;
    }

    return {
      regime,
      label,
      description,
      strategy,
      confidence,
      indicators: {
        adx,
        bbWidth,
        volatility,
        trendStrength,
      },
    };
  }
}
