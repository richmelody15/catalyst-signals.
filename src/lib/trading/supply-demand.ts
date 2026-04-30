// CATALYST AI - Supply & Demand Zone Engine
// Converted from Python: SupplyDemandAnalyzer + SupplyDemandZoneTracker
// Features: Zone detection (RBR/DBR/flip/failed_breakout/volume_profile),
//           Belief scoring (0-100), Zone interaction signals (SL/TP),
//           Zone performance tracking & learning

import { TechnicalIndicators } from './indicators';
import { PriceActionAnalyzer } from './price-action';
import { bugFixer } from './bug-fixer';
import {
  type MarketData,
  type ZoneType,
  type ZoneStrength,
  type SupplyDemandZone,
  type ZoneInteraction,
  type ZoneTrackerStats,
} from './types';

/**
 * SupplyDemandAnalyzer — Detects supply/demand zones from market data.
 *
 * Zone Types:
 * - RBR (Rally-Base-Rally): Bullish continuation zone
 * - DBR (Drop-Base-Rally): Bullish reversal zone
 * - RBD (Rally-Base-Drop): Bearish reversal zone
 * - DBD (Drop-Base-Drop): Bearish continuation zone
 * - flip: Zone that flipped from supply to demand or vice versa
 * - failed_breakout: Zone that caused a failed breakout
 * - volume_profile: Zone identified by volume concentration
 */
export class SupplyDemandAnalyzer {
  private minBaseLength = 1;  // Minimum bars in the base
  private maxBaseLength = 10; // Maximum bars in the base
  private zoneProximityPct = 0.003; // 0.3% proximity for interaction

  /**
   * Detect all supply/demand zones from market data.
   */
  detectZones(marketData: MarketData): SupplyDemandZone[] {
    const { closePrices, highPrices, lowPrices, openPrices, volumes } = marketData;

    if (closePrices.length < 20) return [];

    const zones: SupplyDemandZone[] = [];
    const atr = TechnicalIndicators.calculateATR(highPrices, lowPrices, closePrices);

    // Detect RBR/DBR/RBD/DBD zones
    const patternZones = this.detectPatternZones(
      closePrices, highPrices, lowPrices, openPrices, volumes, atr
    );
    zones.push(...patternZones);

    // Detect volume profile zones
    const volumeZones = this.detectVolumeProfileZones(
      closePrices, highPrices, lowPrices, volumes, atr
    );
    zones.push(...volumeZones);

    // Detect flip zones
    const flipZones = this.detectFlipZones(
      closePrices, highPrices, lowPrices, volumes, atr
    );
    zones.push(...flipZones);

    // Detect failed breakout zones
    const failedBreakoutZones = this.detectFailedBreakoutZones(
      closePrices, highPrices, lowPrices, volumes, atr
    );
    zones.push(...failedBreakoutZones);

    // Score zones
    const scoredZones = this.scoreZones(zones, closePrices, highPrices, lowPrices, volumes);

    return scoredZones;
  }

  /**
   * Check for zone interactions at the current price.
   * Returns interaction signals with SL/TP levels.
   */
  checkZoneInteractions(
    zones: SupplyDemandZone[],
    currentPrice: number,
    currentHigh: number,
    currentLow: number,
    atr: number
  ): ZoneInteraction[] {
    const interactions: ZoneInteraction[] = [];

    for (const zone of zones) {
      if (!zone.active) continue;

      const proximity = this.zoneProximityPct;

      // Check if price is approaching the zone
      const zoneMidpoint = zone.midpoint;
      const priceDistance = currentPrice > 0 ? Math.abs(currentPrice - zoneMidpoint) / currentPrice : 0;

      if (priceDistance > proximity * 3) continue; // Too far away

      let interactionType: ZoneInteraction['interactionType'];
      let signal: 'BUY' | 'SELL' | null = null;
      let confidence = 0;

      // Determine interaction type
      if (priceDistance <= proximity * 0.5) {
        // Price is inside the zone
        if (this.isTestingZone(currentLow, currentHigh, zone)) {
          interactionType = 'test';
          confidence = zone.beliefScore * 0.7;

          // Signal based on zone direction
          if (zone.direction === 'bullish' && currentLow <= zone.high) {
            signal = 'BUY';
            confidence += 15;
          } else if (zone.direction === 'bearish' && currentHigh >= zone.low) {
            signal = 'SELL';
            confidence += 15;
          }
        } else if (this.isBouncingFromZone(currentPrice, currentLow, currentHigh, zone)) {
          interactionType = 'bounce';
          confidence = zone.beliefScore * 0.85;
          signal = zone.direction === 'bullish' ? 'BUY' : 'SELL';
          confidence += 10;
        } else if (this.isBreakingZone(currentPrice, zone)) {
          interactionType = 'break';
          confidence = zone.beliefScore * 0.5;
          // Breaking a demand zone = bearish, breaking supply = bullish
          signal = zone.direction === 'bullish' ? 'SELL' : 'BUY';
          confidence = Math.max(confidence - 20, 10);
        } else {
          interactionType = 'approach';
          confidence = zone.beliefScore * 0.4;
        }
      } else if (priceDistance <= proximity) {
        interactionType = 'approach';
        confidence = zone.beliefScore * 0.5;
        signal = zone.direction === 'bullish' ? 'BUY' : 'SELL';
      } else {
        interactionType = 'approach';
        confidence = zone.beliefScore * 0.3;
      }

      // Only create interactions with meaningful confidence
      if (confidence >= 30) {
        // Calculate SL/TP based on zone and ATR
        const { stopLoss, takeProfit, riskReward } = this.calculateSLTP(
          currentPrice, zone, atr, signal
        );

        interactions.push({
          zone,
          interactionType,
          signal,
          confidence: +Math.min(confidence, 100).toFixed(1),
          entryPrice: currentPrice,
          stopLoss,
          takeProfit,
          riskReward,
        });
      }
    }

    // Sort by confidence descending
    return interactions.sort((a, b) => b.confidence - a.confidence);
  }

  // ─── Private: Zone Detection Methods ──────────────────────────────

  /**
   * Detect RBR, DBR, RBD, DBD pattern zones.
   */
  private detectPatternZones(
    close: number[], high: number[], low: number[], open: number[],
    volume: number[], atr: number
  ): SupplyDemandZone[] {
    const zones: SupplyDemandZone[] = [];

    for (let i = this.minBaseLength + 2; i < close.length - 2; i++) {
      // Look for base patterns
      const prevMove = close[i - 2] - close[i - 3];
      const baseMove = Math.abs(close[i - 1] - close[i - 2]);
      const nextMove = close[i] - close[i - 1];

      const prevMoveStrong = Math.abs(prevMove) > atr * 0.5;
      const baseSmall = baseMove < atr * 0.3;
      const nextMoveStrong = Math.abs(nextMove) > atr * 0.5;

      if (!prevMoveStrong || !nextMoveStrong) continue;

      let zoneType: ZoneType | null = null;
      let direction: 'bullish' | 'bearish' | null = null;

      if (prevMove > 0 && baseSmall && nextMove > 0) {
        // Rally-Base-Rally (bullish continuation)
        zoneType = 'RBR';
        direction = 'bullish';
      } else if (prevMove < 0 && baseSmall && nextMove > 0) {
        // Drop-Base-Rally (bullish reversal)
        zoneType = 'DBR';
        direction = 'bullish';
      } else if (prevMove > 0 && baseSmall && nextMove < 0) {
        // Rally-Base-Drop (bearish reversal)
        zoneType = 'RBD';
        direction = 'bearish';
      } else if (prevMove < 0 && baseSmall && nextMove < 0) {
        // Drop-Base-Drop (bearish continuation)
        zoneType = 'DBD';
        direction = 'bearish';
      }

      if (!zoneType || !direction) continue;

      const baseHigh = Math.max(high[i - 2], high[i - 1]);
      const baseLow = Math.min(low[i - 2], low[i - 1]);

      zones.push(this.createZone(
        zoneType, direction, baseHigh, baseLow,
        i, volume[i], atr, close.length
      ));
    }

    return zones;
  }

  /**
   * Detect zones based on volume concentration at price levels.
   */
  private detectVolumeProfileZones(
    close: number[], high: number[], low: number[],
    volume: number[], atr: number
  ): SupplyDemandZone[] {
    const zones: SupplyDemandZone[] = [];
    if (close.length < 30) return zones;

    // Calculate average volume
    const avgVolume = volume.reduce((a, b) => a + b, 0) / volume.length;

    // Find price levels with high volume concentration
    const priceVolumeMap = new Map<number, number>();
    const precision = this.getPricePrecision(close);

    for (let i = 0; i < close.length; i++) {
      const roundedPrice = Math.round(close[i] / precision) * precision;
      priceVolumeMap.set(roundedPrice, (priceVolumeMap.get(roundedPrice) || 0) + volume[i]);
    }

    // Find high-volume nodes (above 1.5x average)
    for (const [price, vol] of priceVolumeMap) {
      if (vol > avgVolume * 1.5) {
        const currentPrice = close[close.length - 1];
        const direction: 'bullish' | 'bearish' = price < currentPrice ? 'bullish' : 'bearish';

        zones.push(this.createZone(
          'volume_profile',
          direction,
          price + atr * 0.5,
          price - atr * 0.5,
          close.length - 1,
          vol,
          atr,
          close.length
        ));
      }
    }

    return zones.slice(-5); // Keep top 5 volume zones
  }

  /**
   * Detect flip zones (supply→demand or demand→supply).
   */
  private detectFlipZones(
    close: number[], high: number[], low: number[],
    volume: number[], atr: number
  ): SupplyDemandZone[] {
    const zones: SupplyDemandZone[] = [];
    if (close.length < 30) return zones;

    // Look for areas where price spent time consolidating then broke out
    for (let i = 10; i < close.length - 5; i++) {
      const range = high.slice(i - 10, i);
      const rangeLow = Math.min(...low.slice(i - 10, i));
      const rangeHigh = Math.max(...range);
      const rangeWidth = rangeHigh - rangeLow;

      if (rangeWidth > atr * 3) continue; // Too wide to be a flip zone

      // Check if price broke out of this range
      const breakoutUp = close[i] > rangeHigh;
      const breakoutDown = close[i] < rangeLow;

      if (!breakoutUp && !breakoutDown) continue;

      // Check if price retested the zone
      const retested = breakoutUp
        ? low.slice(i + 1).some(l => l <= rangeHigh + atr * 0.1)
        : high.slice(i + 1).some(h => h >= rangeLow - atr * 0.1);

      if (!retested) continue;

      const direction: 'bullish' | 'bearish' = breakoutUp ? 'bullish' : 'bearish';

      zones.push(this.createZone(
        'flip',
        direction,
        rangeHigh,
        rangeLow,
        i,
        volume[i],
        atr,
        close.length
      ));
    }

    return zones.slice(-3); // Keep last 3 flip zones
  }

  /**
   * Detect failed breakout zones.
   */
  private detectFailedBreakoutZones(
    close: number[], high: number[], low: number[],
    volume: number[], atr: number
  ): SupplyDemandZone[] {
    const zones: SupplyDemandZone[] = [];
    if (close.length < 30) return zones;

    // Look for bars that broke above/below a level then reversed
    for (let i = 5; i < close.length - 3; i++) {
      const prevHigh = Math.max(...high.slice(i - 5, i));
      const prevLow = Math.min(...low.slice(i - 5, i));

      // Failed breakout above
      if (high[i] > prevHigh && close[i] < prevHigh) {
        zones.push(this.createZone(
          'failed_breakout',
          'bearish',
          high[i],
          prevHigh - atr * 0.3,
          i,
          volume[i],
          atr,
          close.length
        ));
      }

      // Failed breakout below
      if (low[i] < prevLow && close[i] > prevLow) {
        zones.push(this.createZone(
          'failed_breakout',
          'bullish',
          prevLow + atr * 0.3,
          low[i],
          i,
          volume[i],
          atr,
          close.length
        ));
      }
    }

    return zones.slice(-3);
  }

  // ─── Private: Scoring Methods ─────────────────────────────────────

  /**
   * Score all zones based on multiple factors.
   */
  private scoreZones(
    zones: SupplyDemandZone[],
    close: number[],
    high: number[],
    low: number[],
    volume: number[]
  ): SupplyDemandZone[] {
    const currentPrice = close[close.length - 1];

    for (const zone of zones) {
      let beliefScore = 50; // Start at neutral

      // Factor 1: Zone type quality
      const typeScores: Record<ZoneType, number> = {
        RBR: 70, DBR: 75, RBD: 75, DBD: 70,
        flip: 85, failed_breakout: 80, volume_profile: 60,
      };
      beliefScore += (typeScores[zone.type] - 50) * 0.3;

      // Factor 2: Zone freshness (newer zones score higher)
      const age = close.length - zone.creationIndex;
      if (age < 10) beliefScore += 15;
      else if (age < 30) beliefScore += 10;
      else if (age < 60) beliefScore += 5;
      else beliefScore -= 5;

      // Factor 3: Zone width (tighter = stronger)
      const widthPct = zone.width / zone.midpoint;
      if (widthPct < 0.005) beliefScore += 15;
      else if (widthPct < 0.01) beliefScore += 10;
      else if (widthPct > 0.03) beliefScore -= 10;

      // Factor 4: Volume at creation
      const avgVol = volume.reduce((a, b) => a + b, 0) / Math.max(1, volume.length);
      if (zone.volumeAtCreation > avgVol * 2) beliefScore += 15;
      else if (zone.volumeAtCreation > avgVol * 1.5) beliefScore += 10;
      else if (zone.volumeAtCreation < avgVol * 0.5) beliefScore -= 10;

      // Factor 5: Touch count (more touches = tested & valid)
      if (zone.touches >= 3) beliefScore += 15;
      else if (zone.touches >= 2) beliefScore += 10;
      else if (zone.touches === 0) beliefScore -= 5;

      // Factor 6: Proximity to current price (closer = more relevant)
      if (currentPrice > 0) {
        const distPct = Math.abs(zone.midpoint - currentPrice) / currentPrice;
        if (distPct < 0.005) beliefScore += 20;
        else if (distPct < 0.01) beliefScore += 15;
        else if (distPct < 0.02) beliefScore += 10;
        else if (distPct > 0.05) beliefScore -= 10;
      }

      // Factor 7: Performance history
      if (zone.performance.timesTested > 0) {
        beliefScore += (zone.performance.holdRate - 50) * 0.2;
      }

      // Clamp to 0-100
      zone.beliefScore = +Math.max(0, Math.min(100, beliefScore)).toFixed(1);

      // Determine strength based on belief score
      zone.strength = this.beliefToStrength(zone.beliefScore);
    }

    // Filter out weak zones and sort by belief score
    return zones
      .filter(z => z.beliefScore >= 30)
      .sort((a, b) => b.beliefScore - a.beliefScore)
      .slice(0, 20); // Keep top 20 zones
  }

  private beliefToStrength(score: number): ZoneStrength {
    if (score >= 85) return 'extreme';
    if (score >= 70) return 'strong';
    if (score >= 50) return 'moderate';
    return 'weak';
  }

  // ─── Private: Interaction Helpers ──────────────────────────────────

  private isTestingZone(currentLow: number, currentHigh: number, zone: SupplyDemandZone): boolean {
    return currentLow <= zone.high && currentHigh >= zone.low;
  }

  private isBouncingFromZone(currentPrice: number, currentLow: number, currentHigh: number, zone: SupplyDemandZone): boolean {
    if (zone.direction === 'bullish') {
      return currentLow <= zone.high && currentPrice > zone.midpoint;
    } else {
      return currentHigh >= zone.low && currentPrice < zone.midpoint;
    }
  }

  private isBreakingZone(currentPrice: number, zone: SupplyDemandZone): boolean {
    if (zone.direction === 'bullish') {
      return currentPrice < zone.low;
    } else {
      return currentPrice > zone.high;
    }
  }

  private calculateSLTP(
    currentPrice: number,
    zone: SupplyDemandZone,
    atr: number,
    signal: 'BUY' | 'SELL' | null
  ): { stopLoss: number; takeProfit: number; riskReward: number } {
    if (!signal) {
      return { stopLoss: currentPrice, takeProfit: currentPrice, riskReward: 0 };
    }

    let stopLoss: number;
    let takeProfit: number;

    if (signal === 'BUY') {
      // SL below the zone with ATR buffer
      stopLoss = zone.low - atr * 0.5;
      // TP at 2.5:1 RR or zone-measured target
      takeProfit = currentPrice + (currentPrice - stopLoss) * 2.5;
    } else {
      // SL above the zone with ATR buffer
      stopLoss = zone.high + atr * 0.5;
      // TP at 2.5:1 RR
      takeProfit = currentPrice - (stopLoss - currentPrice) * 2.5;
    }

    const risk = Math.abs(currentPrice - stopLoss);
    const reward = Math.abs(takeProfit - currentPrice);
    const riskReward = risk > 0 ? +(reward / risk).toFixed(1) : 0;

    return { stopLoss: +stopLoss.toFixed(5), takeProfit: +takeProfit.toFixed(5), riskReward };
  }

  // ─── Private: Utility Methods ──────────────────────────────────────

  private createZone(
    type: ZoneType,
    direction: 'bullish' | 'bearish',
    high: number,
    low: number,
    creationIndex: number,
    volumeAtCreation: number,
    atrAtCreation: number,
    currentLength: number
  ): SupplyDemandZone {
    const midpoint = (high + low) / 2;
    const width = high - low;

    return {
      id: `ZONE-${type}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type,
      direction,
      high,
      low,
      midpoint,
      width,
      strength: 'moderate', // Will be updated by scoreZones
      beliefScore: 50,       // Will be updated by scoreZones
      creationIndex,
      touches: 0,
      lastTouchIndex: creationIndex,
      active: true,
      tested: false,
      broken: false,
      volumeAtCreation,
      atrAtCreation,
      age: currentLength - creationIndex,
      performance: {
        timesTested: 0,
        timesHeld: 0,
        timesBroken: 0,
        holdRate: 0,
      },
    };
  }

  private getPricePrecision(prices: number[]): number {
    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
    if (avg < 100) return 0.001;
    return 0.1;
  }
}

/**
 * SupplyDemandZoneTracker — Tracks zone performance over time.
 * Learns which zone types perform best and adjusts belief scores.
 */
export class SupplyDemandZoneTracker {
  private zones: SupplyDemandZone[] = [];
  private analyzer = new SupplyDemandAnalyzer();

  /**
   * Update zones with new market data.
   * Checks for zone interactions, updates performance tracking.
   */
  updateZones(marketData: MarketData): SupplyDemandZone[] {
    const { closePrices, highPrices, lowPrices, volumes } = marketData;

    if (closePrices.length < 20) return this.zones;

    const currentPrice = closePrices[closePrices.length - 1];
    const currentHigh = highPrices[highPrices.length - 1];
    const currentLow = lowPrices[lowPrices.length - 1];
    const atr = TechnicalIndicators.calculateATR(highPrices, lowPrices, closePrices);

    // Update existing zones
    for (const zone of this.zones) {
      if (!zone.active) continue;

      zone.age++;

      // Check if price is interacting with zone
      if (currentLow <= zone.high && currentHigh >= zone.low) {
        zone.touches++;
        zone.lastTouchIndex = closePrices.length - 1;
        zone.tested = true;

        // Update performance
        zone.performance.timesTested++;

        // Check if zone held or broke
        if (zone.direction === 'bullish') {
          if (currentPrice > zone.low) {
            zone.performance.timesHeld++;
          } else {
            zone.performance.timesBroken++;
            zone.broken = true;
            zone.active = false;
          }
        } else {
          if (currentPrice < zone.high) {
            zone.performance.timesHeld++;
          } else {
            zone.performance.timesBroken++;
            zone.broken = true;
            zone.active = false;
          }
        }

        // Update hold rate
        if (zone.performance.timesTested > 0) {
          zone.performance.holdRate = +(
            (zone.performance.timesHeld / zone.performance.timesTested) * 100
          ).toFixed(1);
        }
      }

      // Deactivate very old zones
      if (zone.age > 200) {
        zone.active = false;
      }
    }

    // Detect new zones
    const newZones = bugFixer.autoFixDecoratorSync(
      () => this.analyzer.detectZones(marketData),
      { fallbackValue: [], retryCount: 2, module: 'supply-demand', function: 'detectZones' }
    )();

    // Merge new zones (avoid duplicates)
    for (const newZone of newZones) {
      const isDuplicate = this.zones.some(
        existing => existing.active &&
          Math.abs(existing.midpoint - newZone.midpoint) / existing.midpoint < 0.003
      );

      if (!isDuplicate) {
        this.zones.push(newZone);
      }
    }

    // Keep only active zones + recently broken (for learning)
    this.zones = this.zones.filter(z => z.active || z.performance.timesTested > 0);
    this.zones = this.zones.slice(-50); // Keep max 50 zones

    return this.getActiveZones();
  }

  /**
   * Get the best zone interaction for the current price.
   */
  getBestInteraction(
    currentPrice: number,
    currentHigh: number,
    currentLow: number,
    atr: number
  ): ZoneInteraction | null {
    const interactions = this.analyzer.checkZoneInteractions(
      this.getActiveZones(), currentPrice, currentHigh, currentLow, atr
    );

    return interactions.length > 0 ? interactions[0] : null;
  }

  /**
   * Get all active zones.
   */
  getActiveZones(): SupplyDemandZone[] {
    return this.zones.filter(z => z.active).sort((a, b) => b.beliefScore - a.beliefScore);
  }

  /**
   * Get tracker statistics for dashboard display.
   */
  getStats(): ZoneTrackerStats {
    const activeZones = this.zones.filter(z => z.active);
    const brokenZones = this.zones.filter(z => z.broken);
    const testedZones = this.zones.filter(z => z.performance.timesTested > 0);

    const avgHoldRate = testedZones.length > 0
      ? testedZones.reduce((sum, z) => sum + z.performance.holdRate, 0) / testedZones.length
      : 0;

    // Count zones by type
    const zonesByType: Record<ZoneType, number> = {
      RBR: 0, DBR: 0, RBD: 0, DBD: 0,
      flip: 0, failed_breakout: 0, volume_profile: 0,
    };
    for (const zone of activeZones) {
      zonesByType[zone.type]++;
    }

    // Find best/worst performing types
    const typePerformance: Record<ZoneType, number> = {
      RBR: 0, DBR: 0, RBD: 0, DBD: 0,
      flip: 0, failed_breakout: 0, volume_profile: 0,
    };
    for (const zone of testedZones) {
      typePerformance[zone.type] += zone.performance.holdRate;
    }
    for (const type of Object.keys(zonesByType) as ZoneType[]) {
      if (zonesByType[type] > 0) {
        typePerformance[type] /= zonesByType[type];
      }
    }

    const sortedTypes = (Object.entries(typePerformance) as [ZoneType, number][])
      .sort((a, b) => b[1] - a[1]);
    const bestPerformingType = sortedTypes[0]?.[0] || 'RBR';
    const worstPerformingType = sortedTypes[sortedTypes.length - 1]?.[0] || 'DBD';

    return {
      totalZones: this.zones.length,
      activeZones: activeZones.length,
      brokenZones: brokenZones.length,
      averageHoldRate: +avgHoldRate.toFixed(1),
      zonesByType,
      bestPerformingType,
      worstPerformingType,
    };
  }

  /**
   * Clear all zones.
   */
  reset(): void {
    this.zones = [];
  }
}
