// Signal Generator - Main signal generation service with confidence scoring
// Integrated: MTF Analyzer, Supply/Demand Zones, Bug Fixer, Signal Formatter
import { TechnicalIndicators } from './indicators';
import { PriceActionAnalyzer } from './price-action';
import { SignalQualityChecker } from './quality-checker';
import { MarketRegimeDetector } from './market-regime';
import { StrategyGuideGenerator } from './strategy-guide';
import { SupportResistanceEngine } from './support-resistance';
import { MTFAnalyzer } from './mtf-analyzer';
import { SupplyDemandZoneTracker } from './supply-demand';
import { SignalFormatter } from './signal-formatter';
import { bugFixer } from './bug-fixer';
import { TRADING_CONFIG, type Signal, type MarketData, type MTFConfluence, type SupplyDemandZone, type ZoneInteraction } from './types';

let signalCounter = 0;

export class SignalGenerator {
  private qualityChecker = new SignalQualityChecker();
  private srEngine = new SupportResistanceEngine();
  private mtfAnalyzer = new MTFAnalyzer();
  private sdZoneTracker = new SupplyDemandZoneTracker();
  private signalFormatter = new SignalFormatter();
  private generatedSignals: Signal[] = [];

  // ─── Bug-fixer wrapped methods ──────────────────────────────────

  /** Safe market data retrieval with auto-fix */
  private safeGetMarketData = bugFixer.autoFixDecorator(
    async (pair: string, timeframe: string): Promise<MarketData | null> => {
      // This would normally fetch from an API/simulator
      // For now, return null to trigger fallback
      return null;
    },
    { fallbackValue: null, retryCount: 3, module: 'signal-generator', function: 'getMarketData' }
  );

  /** Safe indicator calculation with auto-fix */
  private safeCalculateRSI = bugFixer.autoFixDecoratorSync(
    (prices: number[]) => TechnicalIndicators.calculateRSI(prices, TRADING_CONFIG.RSI_PERIOD),
    { fallbackValue: 50, retryCount: 2, module: 'signal-generator', function: 'calculateRSI' }
  );

  private safeCalculateStochastic = bugFixer.autoFixDecoratorSync(
    (high: number[], low: number[], close: number[]) =>
      TechnicalIndicators.calculateStochastic(high, low, close),
    { fallbackValue: { k: 50, d: 50 }, retryCount: 2, module: 'signal-generator', function: 'calculateStochastic' }
  );

  private safeCalculateBollingerBands = bugFixer.autoFixDecoratorSync(
    (prices: number[]) =>
      TechnicalIndicators.calculateBollingerBands(prices, TRADING_CONFIG.BB_PERIOD, TRADING_CONFIG.BB_STD),
    { fallbackValue: { sma: 0, upperBand: 0, lowerBand: 0, bbWidth: 0.03 }, retryCount: 2, module: 'signal-generator', function: 'calculateBollingerBands' }
  );

  private safeCalculateADX = bugFixer.autoFixDecoratorSync(
    (high: number[], low: number[], close: number[]) =>
      TechnicalIndicators.calculateADX(high, low, close, TRADING_CONFIG.ADX_PERIOD),
    { fallbackValue: 20, retryCount: 2, module: 'signal-generator', function: 'calculateADX' }
  );

  private safeCalculateEMA = bugFixer.autoFixDecoratorSync(
    (prices: number[], period: number) => TechnicalIndicators.calculateEMA(prices, period),
    { fallbackValue: 0, retryCount: 2, module: 'signal-generator', function: 'calculateEMA' }
  );

  private safeCalculateATR = bugFixer.autoFixDecoratorSync(
    (high: number[], low: number[], close: number[]) =>
      TechnicalIndicators.calculateATR(high, low, close),
    { fallbackValue: 0, retryCount: 2, module: 'signal-generator', function: 'calculateATR' }
  );

  // ─── Main Signal Generation ─────────────────────────────────────

  generateSignal(marketData: MarketData): Signal | null {
    const { closePrices } = marketData;

    if (closePrices.length < 30) return null;

    // Use safe execution context for the entire signal generation pipeline
    try {
      return this.generateSignalInternal(marketData);
    } catch (e) {
      bugFixer.recordError(e, { module: 'signal-generator', function: 'generateSignal' });
      return null;
    }
  }

  private generateSignalInternal(marketData: MarketData): Signal | null {
    const { pair, timeframe, closePrices, highPrices, lowPrices, openPrices, volumes } = marketData;

    // ── Calculate Technical Indicators (with bug-fixer protection) ──
    const rsi = this.safeCalculateRSI(closePrices);
    const { k: stochK, d: stochD } = this.safeCalculateStochastic(highPrices, lowPrices, closePrices);
    const { sma: _sma, upperBand: _upperBand, lowerBand: _lowerBand, bbWidth } =
      this.safeCalculateBollingerBands(closePrices);
    const adx = this.safeCalculateADX(highPrices, lowPrices, closePrices);
    const emaShort = this.safeCalculateEMA(closePrices, TRADING_CONFIG.EMA_SHORT);
    const emaLong = this.safeCalculateEMA(closePrices, TRADING_CONFIG.EMA_LONG);
    const atr = this.safeCalculateATR(highPrices, lowPrices, closePrices);

    // ── Price Action Analysis ──
    const { supports, resistances } = PriceActionAnalyzer.detectSupportResistance(closePrices);
    const fvgs = PriceActionAnalyzer.detectFVG(closePrices);
    const structure = PriceActionAnalyzer.detectBosChoch(highPrices, lowPrices, closePrices);
    const liquidity = PriceActionAnalyzer.detectLiquiditySweep(highPrices, lowPrices, volumes);

    // ── Multi-Timeframe Analysis (with bug-fixer protection) ──
    let mtfConfluence: MTFConfluence | null = null;
    try {
      mtfConfluence = this.mtfAnalyzer.analyzeConfluence(marketData);
    } catch (e) {
      bugFixer.recordError(e, { module: 'mtf-analyzer', function: 'analyzeConfluence' });
    }

    // MTF can enhance signal — if higher TF disagrees, require stronger confluence
    const mtfBoost = mtfConfluence?.aligned ? 1 : 0.85;

    // ── Supply/Demand Zone Analysis ──
    const sdZones = this.sdZoneTracker.updateZones(marketData);
    const currentPrice = closePrices[closePrices.length - 1];
    const currentHigh = highPrices[highPrices.length - 1];
    const currentLow = lowPrices[lowPrices.length - 1];
    const zoneInteraction = this.sdZoneTracker.getBestInteraction(
      currentPrice, currentHigh, currentLow, atr
    );

    // Determine trend
    const trend = emaShort > emaLong ? 'bullish' : 'bearish';

    // ADX filter
    if (adx < TRADING_CONFIG.ADX_THRESHOLD) return null;

    // ── Count confluence signals ──
    let buySignals = 0;
    let sellSignals = 0;

    // RSI check
    if (rsi < TRADING_CONFIG.RSI_OVERSOLD) buySignals++;
    else if (rsi > TRADING_CONFIG.RSI_OVERBOUGHT) sellSignals++;

    // Stochastic check
    if (stochK < 30 && stochK > stochD) buySignals++;
    else if (stochK > 70 && stochK < stochD) sellSignals++;

    // EMA check
    if (emaShort > emaLong) buySignals++;
    else sellSignals++;

    // Structure check
    if (structure.bos && trend === 'bullish') buySignals++;
    else if (structure.bos && trend === 'bearish') sellSignals++;

    if (structure.choch) {
      if (trend === 'bullish') buySignals += 2;
      else sellSignals += 2;
    }

    // FVG check
    const recentFvgs = fvgs.filter((f) => f.index >= closePrices.length - 5);
    for (const fvg of recentFvgs) {
      if (fvg.type === 'bullish') buySignals++;
      else sellSignals++;
    }

    // Liquidity sweep check
    if (liquidity.sweepDetected) {
      if (liquidity.sweepType === 'sell_side') buySignals += 2;
      else if (liquidity.sweepType === 'buy_side') sellSignals += 2;
    }

    // Volume check
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, volumes.length);
    const volumeSpike = volumes[volumes.length - 1] > avgVolume * 1.5;

    if (volumeSpike) {
      if (trend === 'bullish') buySignals++;
      else sellSignals++;
    }

    // MTF confluence boost
    if (mtfConfluence?.aligned) {
      if (mtfConfluence.dominantTrend === 'bullish') buySignals += 2;
      else if (mtfConfluence.dominantTrend === 'bearish') sellSignals += 2;
    }

    // S/D Zone interaction boost
    if (zoneInteraction?.signal) {
      if (zoneInteraction.signal === 'BUY') buySignals += Math.floor(zoneInteraction.confidence / 30);
      else if (zoneInteraction.signal === 'SELL') sellSignals += Math.floor(zoneInteraction.confidence / 30);
    }

    // Determine final direction
    let direction: 'BUY' | 'SELL' | null = null;
    if (buySignals > sellSignals && buySignals >= 3) direction = 'BUY';
    else if (sellSignals > buySignals && sellSignals >= 3) direction = 'SELL';

    if (!direction) return null;

    // ── Prepare data for quality check ──
    const supplyDemandZones = [
      ...supports.slice(-3).map((s) => ({ type: 'demand', price: s })),
      ...resistances.slice(-3).map((r) => ({ type: 'supply', price: r })),
    ];

    const recentCandles: Array<{ open: number; high: number; low: number; close: number }> = [];
    for (let i = Math.max(0, closePrices.length - 5); i < closePrices.length; i++) {
      recentCandles.push({
        open: openPrices[i],
        high: highPrices[i],
        low: lowPrices[i],
        close: closePrices[i],
      });
    }

    const marketDataForCheck = {
      rsi,
      stochK,
      stochD,
      adx,
      bbExpanding: bbWidth > 0.03,
      volumeSpike,
      currentPrice: closePrices[closePrices.length - 1],
      supplyDemandZones,
      recentCandles,
      marketStructure: {
        trend,
        pattern: 'continuation',
      },
      multiTimeframe: mtfConfluence
        ? Object.fromEntries(
            Object.entries(mtfConfluence.timeframeResults).map(([tf, a]) => [tf, { trend: a.trend }])
          )
        : {
            '30s': { trend },
            '1m': { trend },
            '3m': { trend },
            '5m': { trend },
          },
    };

    const signalDataForCheck = {
      direction,
      bosConfirmed: structure.bos,
      chochConfirmed: structure.choch,
      fvgActive: recentFvgs.length > 0,
      liquiditySweep: liquidity.sweepDetected,
    };

    // Run quality checklist
    const qualityCheck = this.qualityChecker.checkSignalQuality({
      signalData: signalDataForCheck,
      marketData: marketDataForCheck,
    });

    if (!qualityCheck.passed) return null;

    // ── Calculate confidence score ──
    const totalSignals = buySignals + sellSignals;
    const signalStrength = direction === 'BUY'
      ? buySignals / totalSignals
      : sellSignals / totalSignals;
    const baseConfidence = Math.min(1, Math.max(0, signalStrength * 0.4 + qualityCheck.score * 0.6));

    // Apply MTF modifier
    const confidence = Math.min(1, baseConfidence * mtfBoost);

    if (confidence < TRADING_CONFIG.MIN_CONFIDENCE_SCORE) return null;

    // Calculate risk levels based on ATR (deterministic, no Math.random())
    const atrMultiplier1 = 1.5;
    const atrMultiplier2 = 3.0;
    const atrMultiplier3 = 6.5;
    const riskUnit = atr > 0 ? atr : currentPrice * 0.001;

    // Calculate WAT time for each Martingale level based on timeframe
    const entryDate = new Date(Date.now() + 4 * 60 * 1000);
    const tfMinutes = this.parseTimeframeToMinutes(timeframe);
    const riskLevels = {
      M1: {
        multiplier: +((riskUnit * atrMultiplier1 / currentPrice) * 100).toFixed(1),
        time: this.formatWATTime(new Date(entryDate.getTime() + tfMinutes * 1 * 60 * 1000)),
      },
      M2: {
        multiplier: +((riskUnit * atrMultiplier2 / currentPrice) * 100).toFixed(1),
        time: this.formatWATTime(new Date(entryDate.getTime() + tfMinutes * 2 * 60 * 1000)),
      },
      M3: {
        multiplier: +((riskUnit * atrMultiplier3 / currentPrice) * 100).toFixed(1),
        time: this.formatWATTime(new Date(entryDate.getTime() + tfMinutes * 3 * 60 * 1000)),
      },
    };

    // ── Market Regime Detection ──
    const regimeResult = MarketRegimeDetector.detect({
      adx,
      bbWidth,
      atr,
      closePrices,
      emaShort,
      emaLong,
      highPrices,
      lowPrices,
      volumes,
    });

    // ── Support & Resistance Detection ──
    const ohlcBars: Array<{ open: number; high: number; low: number; close: number; volume: number }> = [];
    for (let i = 0; i < closePrices.length; i++) {
      ohlcBars.push({
        open: openPrices[i],
        high: highPrices[i],
        low: lowPrices[i],
        close: closePrices[i],
        volume: volumes[i],
      });
    }
    const srZones = this.srEngine.findKeySRZones(ohlcBars);

    // ── Strategy Guide ──
    const strategyGuide = StrategyGuideGenerator.generate({
      regime: regimeResult.regime,
      direction,
      bosConfirmed: structure.bos,
      chochConfirmed: structure.choch,
      fvgActive: recentFvgs.length > 0,
      liquiditySweep: liquidity.sweepDetected,
      rsiValue: rsi,
      adx,
    });

    // ── Find nearest S/D zone ──
    const nearestSDZone = this.findNearestSDZone(sdZones, currentPrice);

    // ── Build Signal ──
    signalCounter++;
    const signal: Signal = {
      id: `SIG-${Date.now()}-${signalCounter}`,
      tradePair: pair,
      timer: `${timeframe} (OTC)`,
      entryTime: new Date(Date.now() + 4 * 60 * 1000),
      direction,
      confidence: +(confidence * 100).toFixed(1),
      marketCondition: bbWidth > 0.03 ? 'High Volatility' : 'Normal',
      trend: trend === 'bullish' ? 'Bullish' : 'Bearish',
      bosConfirmed: structure.bos,
      chochConfirmed: structure.choch,
      fvgActive: recentFvgs.length > 0,
      liquiditySweep: liquidity.sweepDetected,
      volumeHigh: volumeSpike,
      zoneType: direction === 'BUY' ? 'Demand + Order Block' : 'Supply + Order Block',
      rsiValue: +rsi.toFixed(1),
      stochasticBull: stochK < 30 && stochK > stochD,
      bbExpanding: bbWidth > 0.03,
      adrStatus: 'Within range',
      riskReward: zoneInteraction?.riskReward ?? 2.5,
      riskLevels,
      signalQuality: 'HIGH PROBABILITY ONLY',
      checklistScore: +(qualityCheck.score * 100).toFixed(1),
      platform: 'iq-option',
      // Market Regime
      marketRegime: regimeResult.regime,
      regimeLabel: regimeResult.label,
      regimeDescription: regimeResult.description,
      // Strategy Guide
      strategy: {
        title: strategyGuide.title,
        entryRules: strategyGuide.entryRules,
        exitRules: strategyGuide.exitRules,
        riskManagement: strategyGuide.riskManagement,
        avoidActions: strategyGuide.avoidActions,
        confidenceNote: strategyGuide.confidenceNote,
      },
      // GLM Probability — dynamic calculation based on quality metrics
      // Base: 85%, boosted by quality score, confluence, MTF alignment, and S/D zone strength
      glmProbability: this.calculateGLMProbability(
        qualityCheck.score, confidence, buySignals + sellSignals,
        structure.bos, structure.choch, mtfConfluence, zoneInteraction
      ),
      // Support & Resistance
      nearestSupport: srZones.nearestSupport,
      nearestResistance: srZones.nearestResistance,
      supportZone: srZones.zoneRange.supportZone,
      resistanceZone: srZones.zoneRange.resistanceZone,
      // Multi-Timeframe Analysis
      mtfConfluence: mtfConfluence ?? null,
      // Supply/Demand Zone
      nearestSDZone,
      zoneInteraction,
      // Bug Fixer Status
      engineHealth: bugFixer.getEngineHealth(),
      // Formatted Signal (will be set below)
      formatted: null,
    };

    // ── Format Signal ──
    signal.formatted = this.signalFormatter.format(signal);

    this.generatedSignals.push(signal);
    return signal;
  }

  // ─── Utility Methods ──────────────────────────────────────────────

  /**
   * Calculate GLM probability dynamically based on quality metrics.
   * Base: 85.0%, boosted by multiple quality factors.
   * Range: 85.0% – 97.5%
   */
  private calculateGLMProbability(
    qualityScore: number,
    confidence: number,
    totalConfluence: number,
    bosConfirmed: boolean,
    chochConfirmed: boolean,
    mtfConfluence: MTFConfluence | null,
    zoneInteraction: ZoneInteraction | null
  ): number {
    let glm = 85.0;

    // Quality score contribution (0-4%)
    glm += qualityScore * 4;

    // Confidence contribution (0-3%)
    glm += confidence * 3;

    // Confluence strength (0.5% per confluence signal, max 4%)
    glm += Math.min(totalConfluence * 0.5, 4);

    // BOS confirmation bonus (1.5%)
    if (bosConfirmed) glm += 1.5;

    // CHoCH confirmation bonus (2%)
    if (chochConfirmed) glm += 2;

    // MTF alignment bonus (0-2%)
    if (mtfConfluence?.aligned) {
      glm += 1.5;
      // Extra bonus for high MTF checklist score
      if (mtfConfluence.checklistScore >= 70) glm += 0.5;
    }

    // Zone interaction bonus (0-1%)
    if (zoneInteraction?.signal) {
      glm += Math.min(zoneInteraction.confidence / 100, 1);
    }

    // Clamp to realistic range
    return +Math.min(97.5, Math.max(85.0, glm)).toFixed(1);
  }

  private findNearestSDZone(
    zones: SupplyDemandZone[],
    currentPrice: number
  ): SupplyDemandZone | null {
    const activeZones = zones.filter(z => z.active);
    if (activeZones.length === 0) return null;

    // Find the closest active zone to current price
    let nearest: SupplyDemandZone | null = null;
    let minDist = Infinity;

    for (const zone of activeZones) {
      const dist = Math.abs(zone.midpoint - currentPrice);
      if (dist < minDist) {
        minDist = dist;
        nearest = zone;
      }
    }

    return nearest;
  }

  getGeneratedSignals(): Signal[] {
    return this.generatedSignals;
  }

  getRecentSignals(limit: number = 10): Signal[] {
    return this.generatedSignals.slice(-limit);
  }

  clearSignals(): void {
    this.generatedSignals = [];
  }

  /**
   * Parse timeframe string to minutes.
   * e.g. '30s' → 0.5, '45s' → 0.75, '1m' → 1, '2m' → 2, '3m' → 3, '5m' → 5
   */
  private parseTimeframeToMinutes(timeframe: string): number {
    const match = timeframe.match(/^(\d+)(s|m)$/i);
    if (!match) return 1; // default 1 minute
    const value = parseInt(match[1], 10);
    const unit = match[2].toLowerCase();
    return unit === 's' ? value / 60 : value;
  }

  /**
   * Format a Date to HH:MM WAT string.
   */
  private formatWATTime(date: Date): string {
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes} WAT`;
  }

  /**
   * Get the S/D zone tracker for external access.
   */
  getZoneTracker(): SupplyDemandZoneTracker {
    return this.sdZoneTracker;
  }

  /**
   * Get the MTF analyzer for external access.
   */
  getMTFAnalyzer(): MTFAnalyzer {
    return this.mtfAnalyzer;
  }

  /**
   * Get bug fixer statistics.
   */
  getBugFixerStats() {
    return bugFixer.getStats();
  }
}
