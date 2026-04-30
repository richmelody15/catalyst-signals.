// Support & Resistance Detection Engine
// Converted from Python — Advanced multi-method S/R detection with clustering & scoring

export interface SRLevel {
  price: number;
  strength: number; // Number of touches
  type: 'support' | 'resistance';
  zoneWidth: number; // Zone width as percentage
  timeframe: string;
  score: number; // Quality score 0-100
  isMajor: boolean;
  lastTest: string; // ISO timestamp
  breakout: boolean; // Has it been broken?
}

export interface SRLevels {
  support: SRLevel[];
  resistance: SRLevel[];
}

export interface KeySRZones {
  currentPrice: number;
  nearestSupport: SRLevel | null;
  nearestResistance: SRLevel | null;
  allSupports: SRLevel[];
  allResistances: SRLevel[];
  zoneRange: {
    supportZone: { start: number | null; end: number | null };
    resistanceZone: { start: number | null; end: number | null };
  };
}

interface OHLCBar {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp?: string;
}

export class SupportResistanceEngine {
  private clusterThreshold = 0.003; // 0.3% clustering threshold
  private minTouches = 2; // Minimum touches for valid level
  private zoneWidthPct = 0.002; // 0.2% zone width

  /**
   * Find support and resistance levels using multiple methods
   *
   * Methods:
   * - pivot_points: Classic pivot point calculation
   * - swing_points: Swing high/low detection
   * - horizontal: Horizontal price levels
   * - fibonacci: Fibonacci retracement levels
   */
  findSupportResistance(ohlcData: OHLCBar[], method: string = 'all'): SRLevels {
    const levels: SRLevels = { support: [], resistance: [] };

    if (ohlcData.length < 20) return levels;

    if (method === 'all' || method === 'pivot_points') {
      const pivotLevels = this.pivotPointsMethod(ohlcData);
      levels.support.push(...pivotLevels.support);
      levels.resistance.push(...pivotLevels.resistance);
    }

    if (method === 'all' || method === 'swing_points') {
      const swingLevels = this.swingPointsMethod(ohlcData, 5);
      levels.support.push(...swingLevels.support);
      levels.resistance.push(...swingLevels.resistance);
    }

    if (method === 'all' || method === 'horizontal') {
      const horizontalLevels = this.horizontalLevelsMethod(ohlcData, 10);
      levels.support.push(...horizontalLevels.support);
      levels.resistance.push(...horizontalLevels.resistance);
    }

    if (method === 'all' || method === 'fibonacci') {
      const fibLevels = this.fibonacciMethod(ohlcData);
      levels.support.push(...fibLevels.support);
      levels.resistance.push(...fibLevels.resistance);
    }

    // Cluster and merge nearby levels
    const clusteredLevels = this.clusterLevels(levels);

    // Score and rank levels
    const scoredLevels = this.scoreLevels(clusteredLevels, ohlcData);

    return scoredLevels;
  }

  /**
   * Find key support and resistance zones for trading decisions
   */
  findKeySRZones(ohlcData: OHLCBar[]): KeySRZones {
    const allLevels = this.findSupportResistance(ohlcData);
    const currentPrice = ohlcData[ohlcData.length - 1].close;

    // Find nearest support and resistance
    let nearestSupport: SRLevel | null = null;
    let nearestResistance: SRLevel | null = null;

    // Sort supports below current price (closest first)
    const supportsBelow = allLevels.support
      .filter((level) => level.price < currentPrice)
      .sort((a, b) => (currentPrice - a.price) - (currentPrice - b.price));

    if (supportsBelow.length > 0) {
      nearestSupport = supportsBelow[0];
    }

    // Sort resistances above current price (closest first)
    const resistancesAbove = allLevels.resistance
      .filter((level) => level.price > currentPrice)
      .sort((a, b) => (a.price - currentPrice) - (b.price - currentPrice));

    if (resistancesAbove.length > 0) {
      nearestResistance = resistancesAbove[0];
    }

    return {
      currentPrice,
      nearestSupport,
      nearestResistance,
      allSupports: allLevels.support.slice(0, 5),
      allResistances: allLevels.resistance.slice(0, 5),
      zoneRange: {
        supportZone: {
          start: nearestSupport ? nearestSupport.price * (1 - nearestSupport.zoneWidth) : null,
          end: nearestSupport ? nearestSupport.price * (1 + nearestSupport.zoneWidth) : null,
        },
        resistanceZone: {
          start: nearestResistance ? nearestResistance.price * (1 - nearestResistance.zoneWidth) : null,
          end: nearestResistance ? nearestResistance.price * (1 + nearestResistance.zoneWidth) : null,
        },
      },
    };
  }

  // ─── Private Methods ──────────────────────────────────────────────

  /** Classic Pivot Points calculation */
  private pivotPointsMethod(bars: OHLCBar[]): SRLevels {
    if (bars.length < 2) return { support: [], resistance: [] };

    const prevBar = bars[bars.length - 2];
    const high = prevBar.high;
    const low = prevBar.low;
    const close = prevBar.close;
    const nowISO = new Date().toISOString();

    // Pivot point
    const pp = (high + low + close) / 3;

    // Support levels
    const s1 = 2 * pp - high;
    const s2 = pp - (high - low);
    const s3 = low - 2 * (high - pp);

    // Resistance levels
    const r1 = 2 * pp - low;
    const r2 = pp + (high - low);
    const r3 = high + 2 * (pp - low);

    const supportLevels: SRLevel[] = [
      this.makeLevel(s1, 3, 'support', 0.002, 'pivot', 80, true, nowISO, false),
      this.makeLevel(s2, 2, 'support', 0.003, 'pivot', 70, false, nowISO, false),
      this.makeLevel(s3, 1, 'support', 0.004, 'pivot', 60, false, nowISO, false),
    ];

    const resistanceLevels: SRLevel[] = [
      this.makeLevel(r1, 3, 'resistance', 0.002, 'pivot', 80, true, nowISO, false),
      this.makeLevel(r2, 2, 'resistance', 0.003, 'pivot', 70, false, nowISO, false),
      this.makeLevel(r3, 1, 'resistance', 0.004, 'pivot', 60, false, nowISO, false),
    ];

    return { support: supportLevels, resistance: resistanceLevels };
  }

  /** Detect swing highs and lows */
  private swingPointsMethod(bars: OHLCBar[], window: number = 5): SRLevels {
    if (bars.length < window * 2) return { support: [], resistance: [] };

    const highPrices = bars.map((b) => b.high);
    const lowPrices = bars.map((b) => b.low);
    const nowISO = new Date().toISOString();

    // Find local maxima (swing highs)
    const swingHighIndices = this.argRelExtrema(highPrices, window, 'greater');
    // Find local minima (swing lows)
    const swingLowIndices = this.argRelExtrema(lowPrices, window, 'less');

    const supportLevels: SRLevel[] = [];
    const resistanceLevels: SRLevel[] = [];

    // Process swing lows (potential support)
    for (const idx of swingLowIndices) {
      const price = lowPrices[idx];
      const touches = this.countTouches(price, bars, 'support');

      if (touches >= this.minTouches) {
        supportLevels.push(
          this.makeLevel(
            price, touches, 'support', this.zoneWidthPct, 'swing',
            this.calculateSwingScore(price, bars, 'support'),
            touches >= 4, nowISO, false
          )
        );
      }
    }

    // Process swing highs (potential resistance)
    for (const idx of swingHighIndices) {
      const price = highPrices[idx];
      const touches = this.countTouches(price, bars, 'resistance');

      if (touches >= this.minTouches) {
        resistanceLevels.push(
          this.makeLevel(
            price, touches, 'resistance', this.zoneWidthPct, 'swing',
            this.calculateSwingScore(price, bars, 'resistance'),
            touches >= 4, nowISO, false
          )
        );
      }
    }

    return { support: supportLevels, resistance: resistanceLevels };
  }

  /** Find horizontal S/R based on price clustering */
  private horizontalLevelsMethod(bars: OHLCBar[], numLevels: number = 10): SRLevels {
    if (bars.length < 20) return { support: [], resistance: [] };

    const allPrices = [
      ...bars.map((b) => b.high),
      ...bars.map((b) => b.low),
      ...bars.map((b) => b.close),
    ];

    const pricePrecision = this.getPricePrecision(allPrices);
    const roundedPrices = allPrices.map((p) => Math.round(p / pricePrecision) * pricePrecision);

    // Count frequency of each price level
    const priceCounts = new Map<number, number>();
    for (const p of roundedPrices) {
      priceCounts.set(p, (priceCounts.get(p) || 0) + 1);
    }

    // Sort by count descending and take top levels
    const sortedEntries = [...priceCounts.entries()].sort((a, b) => b[1] - a[1]);
    const topLevels = sortedEntries.slice(0, numLevels);

    const currentPrice = bars[bars.length - 1].close;
    const nowISO = new Date().toISOString();

    const supportLevels: SRLevel[] = [];
    const resistanceLevels: SRLevel[] = [];

    for (const [price, count] of topLevels) {
      const levelType: 'support' | 'resistance' = price < currentPrice ? 'support' : 'resistance';

      const level = this.makeLevel(
        price, count, levelType,
        this.zoneWidthPct * (1 + count * 0.1),
        'horizontal',
        this.calculateHorizontalScore(price, bars, levelType),
        count >= 5, nowISO,
        this.checkBreakout(price, bars, levelType)
      );

      if (levelType === 'support') {
        supportLevels.push(level);
      } else {
        resistanceLevels.push(level);
      }
    }

    return { support: supportLevels, resistance: resistanceLevels };
  }

  /** Calculate Fibonacci retracement levels */
  private fibonacciMethod(bars: OHLCBar[]): SRLevels {
    if (bars.length < 50) return { support: [], resistance: [] };

    const recentHigh = Math.max(...bars.map((b) => b.high));
    const recentLow = Math.min(...bars.map((b) => b.low));
    const priceRange = recentHigh - recentLow;
    const currentPrice = bars[bars.length - 1].close;
    const nowISO = new Date().toISOString();

    // Fibonacci levels
    const fibRatios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618];
    const majorRatios = [0.0, 0.382, 0.5, 0.618, 1.0];

    const supportLevels: SRLevel[] = [];
    const resistanceLevels: SRLevel[] = [];

    for (const ratio of fibRatios) {
      const price = recentLow + ratio * priceRange;
      const levelType: 'support' | 'resistance' = price < currentPrice ? 'support' : 'resistance';
      const reactionScore = this.checkFibReaction(price, bars);

      const level = this.makeLevel(
        price,
        Math.min(5, Math.floor(reactionScore / 20)),
        levelType,
        0.003,
        'fibonacci',
        reactionScore,
        majorRatios.includes(ratio),
        nowISO,
        false
      );

      if (levelType === 'support') {
        supportLevels.push(level);
      } else {
        resistanceLevels.push(level);
      }
    }

    return { support: supportLevels, resistance: resistanceLevels };
  }

  /** Cluster nearby support/resistance levels together */
  private clusterLevels(levels: SRLevels): SRLevels {
    const clustered: SRLevels = { support: [], resistance: [] };

    for (const levelType of ['support', 'resistance'] as const) {
      const levelList = levels[levelType];
      if (levelList.length === 0) continue;

      // Sort by price (resistance descending, support ascending)
      const sortedLevels = [...levelList].sort((a, b) =>
        levelType === 'resistance' ? b.price - a.price : a.price - b.price
      );

      const clusters: SRLevel[][] = [];
      let currentCluster: SRLevel[] = [sortedLevels[0]];

      for (let i = 1; i < sortedLevels.length; i++) {
        const prevPrice = sortedLevels[i - 1].price;
        const currPrice = sortedLevels[i].price;

        // Check if price is within clustering threshold
        if (prevPrice > 0 && Math.abs(currPrice - prevPrice) / prevPrice < this.clusterThreshold) {
          currentCluster.push(sortedLevels[i]);
        } else {
          clusters.push(currentCluster);
          currentCluster = [sortedLevels[i]];
        }
      }
      clusters.push(currentCluster);

      // Merge each cluster into a single level
      for (const cluster of clusters) {
        if (cluster.length === 0) continue;

        // Calculate weighted average price
        const totalWeight = cluster.reduce((sum, l) => sum + l.strength, 0);
        const avgPrice = totalWeight > 0
          ? cluster.reduce((sum, l) => sum + l.price * l.strength, 0) / totalWeight
          : cluster[0].price;

        // Create merged level
        const mergedLevel = this.makeLevel(
          avgPrice,
          cluster.reduce((sum, l) => sum + l.strength, 0),
          levelType,
          Math.max(...cluster.map((l) => l.zoneWidth)),
          'merged',
          Math.max(...cluster.map((l) => l.score)),
          cluster.some((l) => l.isMajor),
          cluster.reduce((a, b) => a.lastTest > b.lastTest ? a : b).lastTest,
          cluster.some((l) => l.breakout)
        );

        clustered[levelType].push(mergedLevel);
      }
    }

    return clustered;
  }

  /** Score and rank support/resistance levels */
  private scoreLevels(levels: SRLevels, bars: OHLCBar[]): SRLevels {
    const currentPrice = bars[bars.length - 1].close;

    for (const levelType of ['support', 'resistance'] as const) {
      for (const level of levels[levelType]) {
        let score = level.score;

        // Bonus for recent touches
        const recentTouches = this.countRecentTouches(level.price, bars, levelType, 20);
        score += recentTouches * 5;

        // Bonus for round numbers (psychological levels)
        if (this.isRoundNumber(level.price)) {
          score += 10;
        }

        // Penalty for broken levels
        if (level.breakout) {
          score *= 0.5;
        }

        // Bonus for levels near current price
        if (currentPrice > 0) {
          const distancePct = Math.abs(level.price - currentPrice) / currentPrice;
          if (distancePct < 0.01) { // Within 1%
            score += 15;
          } else if (distancePct < 0.03) { // Within 3%
            score += 10;
          }
        }

        // Bonus for high strength (multiple touches)
        score += Math.min(level.strength * 3, 20);

        // Cap score at 100 and update
        level.score = Math.min(score, 100);

        // Update major status based on score
        if (level.score >= 80) {
          level.isMajor = true;
        }
      }

      // Sort by score descending, keep top 10
      levels[levelType] = levels[levelType]
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);
    }

    return levels;
  }

  /** Count how many times price has touched a level */
  private countTouches(levelPrice: number, bars: OHLCBar[], levelType: 'support' | 'resistance', tolerance: number = 0.002): number {
    let touches = 0;

    for (const bar of bars) {
      if (levelPrice === 0) continue;
      if (levelType === 'support') {
        if (Math.abs(bar.low - levelPrice) / levelPrice < tolerance) {
          touches++;
        }
      } else {
        if (Math.abs(bar.high - levelPrice) / levelPrice < tolerance) {
          touches++;
        }
      }
    }

    return touches;
  }

  /** Count touches in recent periods */
  private countRecentTouches(levelPrice: number, bars: OHLCBar[], levelType: 'support' | 'resistance', periods: number = 20): number {
    const recentBars = bars.slice(-periods);
    return this.countTouches(levelPrice, recentBars, levelType);
  }

  /** Check if price is a psychological round number */
  private isRoundNumber(price: number): boolean {
    for (let precision = 3; precision >= 0; precision--) {
      const factor = Math.pow(10, precision);
      const rounded = Math.round(price * factor) / factor;
      if (price > 0 && Math.abs(price - rounded) / price < 0.0001) {
        const niceNumber = Math.round(rounded * factor);
        const mod = Math.pow(10, Math.max(0, 3 - precision));
        if (niceNumber % mod === 0) return true;
      }
    }
    return false;
  }

  /** Check if a level has been broken */
  private checkBreakout(levelPrice: number, bars: OHLCBar[], levelType: 'support' | 'resistance'): boolean {
    const recentClose = bars[bars.length - 1].close;

    if (levelType === 'support' && recentClose < levelPrice * 0.99) return true;
    if (levelType === 'resistance' && recentClose > levelPrice * 1.01) return true;

    return false;
  }

  /** Calculate quality score for swing levels */
  private calculateSwingScore(price: number, bars: OHLCBar[], levelType: 'support' | 'resistance'): number {
    let baseScore = 60;

    // More touches = higher score
    const touches = this.countTouches(price, bars, levelType);
    baseScore += Math.min(touches * 5, 20);

    // Check if it's a round number
    if (this.isRoundNumber(price)) {
      baseScore += 10;
    }

    return Math.min(baseScore, 100);
  }

  /** Calculate quality score for horizontal levels */
  private calculateHorizontalScore(price: number, bars: OHLCBar[], levelType: 'support' | 'resistance'): number {
    let baseScore = 50;

    // Volume at level
    const volumeScore = this.checkVolumeAtLevel(price, bars);
    baseScore += volumeScore;

    // Time spent at level
    const timeScore = this.checkTimeAtLevel(price, bars);
    baseScore += timeScore;

    return Math.min(baseScore, 100);
  }

  /** Check how price reacted to a Fibonacci level */
  private checkFibReaction(levelPrice: number, bars: OHLCBar[]): number {
    let touches = 0;
    let reversals = 0;

    for (let i = 1; i < bars.length; i++) {
      if (levelPrice === 0) continue;
      // Check if price touched the level
      if (
        Math.abs(bars[i].low - levelPrice) / levelPrice < 0.002 ||
        Math.abs(bars[i].high - levelPrice) / levelPrice < 0.002
      ) {
        touches++;

        // Check if it reversed
        if (i < bars.length - 1) {
          if (bars[i].low <= levelPrice && bars[i].close > levelPrice) {
            reversals++;
          } else if (bars[i].high >= levelPrice && bars[i].close < levelPrice) {
            reversals++;
          }
        }
      }
    }

    if (touches === 0) return 30;

    const score = 50 + (reversals / touches) * 50;
    return Math.min(score, 100);
  }

  /** Check volume at a specific price level */
  private checkVolumeAtLevel(price: number, bars: OHLCBar[]): number {
    const avgVolume = bars.reduce((s, b) => s + b.volume, 0) / bars.length;
    if (avgVolume === 0) return 0;

    // Find bars near this price level
    const nearLevel = bars.filter((b) => price > 0 && Math.abs(b.close - price) / price < 0.01);
    if (nearLevel.length === 0) return 0;

    const levelVolume = nearLevel.reduce((s, b) => s + b.volume, 0) / nearLevel.length;
    const volumeRatio = levelVolume / avgVolume;

    if (volumeRatio > 2) return 20;
    if (volumeRatio > 1.5) return 15;
    if (volumeRatio > 1) return 10;
    return 5;
  }

  /** Check time spent at a price level */
  private checkTimeAtLevel(price: number, bars: OHLCBar[]): number {
    if (price === 0) return 0;
    const nearLevelCount = bars.filter((b) => Math.abs(b.close - price) / price < 0.005).length;
    const timeRatio = nearLevelCount / bars.length;

    if (timeRatio > 0.1) return 20;
    if (timeRatio > 0.05) return 15;
    if (timeRatio > 0.02) return 10;
    return 5;
  }

  /** Determine appropriate price precision for binning */
  private getPricePrecision(prices: number[]): number {
    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;

    // For forex pairs (typically around 1-2)
    if (avgPrice < 100) return 0.001; // 1 pip precision
    // For indices/commodities
    return 0.1;
  }

  /** Find local extrema indices (replaces scipy.signal.argrelextrema) */
  private argRelExtrema(data: number[], order: number, comparator: 'greater' | 'less'): number[] {
    const results: number[] = [];

    for (let i = order; i < data.length - order; i++) {
      let isExtrema = true;

      for (let j = 1; j <= order; j++) {
        if (comparator === 'greater') {
          if (data[i] <= data[i - j] || data[i] <= data[i + j]) {
            isExtrema = false;
            break;
          }
        } else {
          if (data[i] >= data[i - j] || data[i] >= data[i + j]) {
            isExtrema = false;
            break;
          }
        }
      }

      if (isExtrema) results.push(i);
    }

    return results;
  }

  /** Helper to create SRLevel objects */
  private makeLevel(
    price: number,
    strength: number,
    type: 'support' | 'resistance',
    zoneWidth: number,
    timeframe: string,
    score: number,
    isMajor: boolean,
    lastTest: string,
    breakout: boolean
  ): SRLevel {
    return { price, strength, type, zoneWidth, timeframe, score, isMajor, lastTest, breakout };
  }
}
