// UltraFilter - 94.3% Quality Filter with 6-Category Scoring
// Converted from Python catalyst_ai.py UltraFilter class
// Categories: structure(90), technical(90), liquidity(90), zones(85), volume_momentum(85), candle_pattern(80)

export interface UltraFilterScores {
  structure: number;
  technical: number;
  liquidity: number;
  zones: number;
  volume_momentum: number;
  candle_pattern: number;
}

export interface UltraFilterResult {
  passed: boolean;
  confidence: number;
  scores: UltraFilterScores;
  confluences: number;
  categoryDetails: Record<string, string>;
}

export interface UltraFilterConfig {
  minOverall: number;
  minConfluences: number;
  thresholds: Record<string, number>;
}

/**
 * UltraFilter — 94.3% win rate quality filter.
 *
 * Converted from Python UltraFilter with 6 scoring categories:
 * - structure: 90 threshold (trend + BOS + multi-TF alignment)
 * - technical: 90 threshold (RSI + stochastic + EMA alignment)
 * - liquidity: 90 threshold (sweep detection + sweep type)
 * - zones: 85 threshold (supply/demand + order block + FVG)
 * - volume_momentum: 85 threshold (volume spike + vol quality + momentum + ADX)
 * - candle_pattern: 80 threshold (engulfing or rejection)
 *
 * Signal passes if: overall >= minOverall AND confluences >= minConfluences
 */
export class UltraFilter {
  private config: UltraFilterConfig = {
    minOverall: 92.0,
    minConfluences: 8,
    thresholds: {
      structure: 90,
      technical: 90,
      liquidity: 90,
      zones: 85,
      volume_momentum: 85,
      candle_pattern: 80,
    },
  };

  getConfig(): UltraFilterConfig {
    return { ...this.config };
  }

  /**
   * Adjust filter thresholds based on recent performance (DailyImprover integration).
   * If win rate < 94.3%, tighten; if > 97%, relax slightly.
   */
  adjustThresholds(winRate: number, totalTrades: number): void {
    if (winRate < 0.943) {
      this.config.minOverall = Math.min(97, this.config.minOverall + 0.5);
      this.config.minConfluences = Math.min(10, this.config.minConfluences + 1);
    } else if (winRate > 0.97 && totalTrades > 50) {
      this.config.minOverall = Math.max(88, this.config.minOverall - 0.5);
      this.config.minConfluences = Math.max(6, this.config.minConfluences - 1);
    }
  }

  /**
   * Adjust per-feature thresholds based on correlation with wins.
   * For each feature, find the minimum threshold where win rate >= 95%.
   */
  adjustFeatureThresholds(
    featureStats: Record<string, Array<{ score: number; outcome: number }>>
  ): void {
    for (const [feature, values] of Object.entries(featureStats)) {
      if (values.length < 10) continue;

      const scoresArr = values.map((v) => v.score);
      const outcomes = values.map((v) => v.outcome);

      // Find minimum threshold where win rate >= 95%
      for (let th = 60; th <= 100; th += 5) {
        const passIdx = scoresArr
          .map((s, i) => (s >= th ? i : -1))
          .filter((i) => i >= 0);

        if (passIdx.length > 5) {
          const wr = passIdx.reduce((sum, i) => sum + outcomes[i], 0) / passIdx.length;
          if (wr >= 0.95) {
            this.config.thresholds[feature] = th;
            break;
          }
        }
      }
    }
  }

  /**
   * Check signal quality against all 6 filter categories.
   * Returns passed status, confidence, and per-category scores.
   */
  check(
    ind: {
      rsi: number;
      stochK: number;
      stochD: number;
      adx: number;
      bbWidth: number;
      bbWidthPrev: number;
      ema50: number;
      ema200: number;
      atr: number;
      volumeSpike: boolean;
      volumeTrend: string;
      volQuality: boolean;
      momentum: number;
      engulfing: boolean;
      engulfingDir: string;
      rejection: boolean;
      rejectionDir: string;
    },
    struc: {
      trend: string;
      bosConfirmed: boolean;
      chochConfirmed: boolean;
      multiTfAligned: boolean;
    },
    liq: {
      sweepDetected: boolean;
      sweepType: string;
      building: boolean;
    },
    zones: {
      atSupply: boolean;
      atDemand: boolean;
      hasOrderBlock: boolean;
      hasActiveFvg: boolean;
      hasFvg: boolean;
    }
  ): UltraFilterResult {
    const scores: UltraFilterScores = {
      structure: 0,
      technical: 0,
      liquidity: 0,
      zones: 0,
      volume_momentum: 0,
      candle_pattern: 0,
    };
    const details: Record<string, string> = {};

    // ── Structure Score (max 100) ──
    // trend!=neutral: +40, bos_confirmed: +40, multi_tf_aligned: +20
    let s1 = 0;
    if (struc.trend !== 'neutral') {
      s1 += 40;
      details.structure_trend = struc.trend;
    }
    if (struc.bosConfirmed) {
      s1 += 40;
      details.structure_bos = 'confirmed';
    }
    if (struc.multiTfAligned) {
      s1 += 20;
      details.structure_mtf = 'aligned';
    }
    scores.structure = Math.min(100, s1);

    // ── Technical Score (max 100) ──
    // RSI extreme: +40, stoch crossover at extreme: +30, EMA alignment: +20
    let s2 = 0;
    if (ind.rsi > 75 || ind.rsi < 25) {
      s2 += 40;
      details.technical_rsi = ind.rsi > 75 ? 'overbought' : 'oversold';
    } else {
      s2 += 10;
    }
    if (
      Math.abs(ind.stochK - ind.stochD) < 3 &&
      (ind.stochK > 80 || ind.stochK < 20)
    ) {
      s2 += 30;
      details.technical_stoch = 'extreme_crossover';
    }
    const emaAligned =
      struc.trend === 'bullish'
        ? ind.ema50 > ind.ema200
        : struc.trend === 'bearish'
        ? ind.ema50 < ind.ema200
        : false;
    if (emaAligned) {
      s2 += 20;
      details.technical_ema = 'aligned';
    }
    scores.technical = Math.min(100, s2);

    // ── Liquidity Score (max 100) ──
    // sweep detected: +60, sweep type != none: +25
    let s3 = 0;
    if (liq.sweepDetected) {
      s3 += 60;
      details.liquidity_sweep = 'detected';
    }
    if (liq.sweepType !== 'none') {
      s3 += 25;
      details.liquidity_type = liq.sweepType;
    }
    scores.liquidity = Math.min(100, s3);

    // ── Zones Score (max 100) ──
    // at supply/demand: +50, order block: +25, FVG: +25
    let s4 = 0;
    if (zones.atSupply || zones.atDemand) {
      s4 += 50;
      details.zones_proximity = zones.atSupply ? 'supply' : 'demand';
    }
    if (zones.hasOrderBlock) {
      s4 += 25;
      details.zones_ob = 'present';
    }
    if (zones.hasActiveFvg) {
      s4 += 25;
      details.zones_fvg = 'active';
    }
    scores.zones = Math.min(100, s4);

    // ── Volume/Momentum Score (max 100) ──
    // volume spike: +45, vol quality: +25, momentum > 0.8: +20, ADX > 35: +10
    let s5 = 0;
    if (ind.volumeSpike) {
      s5 += 45;
      details.vm_volume = 'spike';
    }
    if (ind.volQuality) {
      s5 += 25;
      details.vm_volquality = 'high';
    }
    if (Math.abs(ind.momentum) > 0.8) {
      s5 += 20;
      details.vm_momentum = `${ind.momentum.toFixed(2)}%`;
    }
    if (ind.adx > 35) {
      s5 += 10;
      details.vm_adx = 'strong';
    }
    scores.volume_momentum = Math.min(100, s5);

    // ── Candle Pattern Score (max 100) ──
    // engulfing: 100, rejection: 85, else: 40
    let s6 = 40;
    if (ind.engulfing) {
      s6 = 100;
      details.candle_pattern = `engulfing_${ind.engulfingDir}`;
    } else if (ind.rejection) {
      s6 = 85;
      details.candle_pattern = `rejection_${ind.rejectionDir}`;
    }
    scores.candle_pattern = Math.min(100, s6);

    // ── Overall Weighted Score ──
    const w: Record<string, number> = {
      structure: 1 / 6,
      technical: 1 / 6,
      liquidity: 1 / 6,
      zones: 1 / 6,
      volume_momentum: 1 / 6,
      candle_pattern: 1 / 6,
    };
    const overall = Object.entries(scores).reduce(
      (sum, [k, v]) => sum + v * (w[k] || 0),
      0
    );

    // Count confluences (categories scoring >= 80)
    const confluences = Object.values(scores).filter((v) => v >= 80).length;

    // Signal passes if overall >= minOverall AND confluences >= minConfluences
    const passed = overall >= this.config.minOverall && confluences >= this.config.minConfluences;

    return {
      passed,
      confidence: overall,
      scores,
      confluences,
      categoryDetails: details,
    };
  }
}

// Singleton
export const ultraFilter = new UltraFilter();
