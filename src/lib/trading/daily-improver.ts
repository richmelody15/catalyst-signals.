// DailyImprover - Adaptive threshold adjustment system
// Converted from Python DailyImprover + Daily95Optimiser
// Adjusts UltraFilter thresholds based on recent win rate performance

import { ultraFilter, type UltraFilterConfig } from './ultra-filter';

interface TradeRecord {
  outcome: 'win' | 'loss' | 'pending';
  featureScores: Record<string, number>;
  entryTime: string;
}

/**
 * DailyImprover — Automatically adjusts the UltraFilter thresholds based on
 * recent trading performance. Runs daily to maintain 95%+ win rate targets.
 *
 * Logic (from Python):
 * - If win rate < 94.3%: tighten minOverall by +0.5 (max 97), minConfluences +1 (max 10)
 * - If win rate > 97% with 50+ trades: relax minOverall by -0.5 (min 88), minConfluences -1 (min 6)
 * - Per-feature threshold adjustment: find minimum threshold where win rate >= 95%
 */
export class DailyImprover {
  private trades: TradeRecord[] = [];
  private lastRunDate: string = '';
  private adjustmentLog: Array<{
    date: string;
    winRate: number;
    totalTrades: number;
    action: string;
    newConfig: UltraFilterConfig;
  }> = [];

  /**
   * Record a trade outcome for the improver to analyze.
   */
  recordTrade(outcome: 'win' | 'loss', featureScores: Record<string, number>): void {
    this.trades.push({
      outcome,
      featureScores,
      entryTime: new Date().toISOString(),
    });

    // Keep only last 500 trades
    if (this.trades.length > 500) {
      this.trades = this.trades.slice(-300);
    }
  }

  /**
   * Run the daily improvement cycle.
   * Adjusts UltraFilter thresholds based on recent 7-day win rate.
   */
  run(): {
    winRate: number;
    totalTrades: number;
    action: string;
    newConfig: UltraFilterConfig;
  } | null {
    const today = new Date().toISOString().split('T')[0];
    if (this.lastRunDate === today) return null; // Already ran today

    // Get recent trades (last 7 days)
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 7);
    const recentTrades = this.trades.filter(
      (t) => new Date(t.entryTime) >= cutoff && t.outcome !== 'pending'
    );

    if (recentTrades.length < 20) {
      return null; // Not enough data
    }

    const wins = recentTrades.filter((t) => t.outcome === 'win').length;
    const total = recentTrades.length;
    const winRate = wins / total;

    let action = 'no_change';

    // ── Adjust overall thresholds ──
    if (winRate < 0.943) {
      // Win rate below target: tighten filter
      ultraFilter.adjustThresholds(winRate, total);
      action = `tightened (wr=${(winRate * 100).toFixed(1)}%)`;
    } else if (winRate > 0.97 && total > 50) {
      // Win rate well above target: relax slightly to get more signals
      ultraFilter.adjustThresholds(winRate, total);
      action = `relaxed (wr=${(winRate * 100).toFixed(1)}%)`;
    }

    // ── Adjust per-feature thresholds ──
    const featureStats: Record<string, Array<{ score: number; outcome: number }>> = {};

    for (const trade of recentTrades) {
      if (!trade.featureScores) continue;
      for (const [feature, score] of Object.entries(trade.featureScores)) {
        if (!featureStats[feature]) featureStats[feature] = [];
        featureStats[feature].push({
          score,
          outcome: trade.outcome === 'win' ? 1 : 0,
        });
      }
    }

    ultraFilter.adjustFeatureThresholds(featureStats);

    const newConfig = ultraFilter.getConfig();

    // Log the adjustment
    const logEntry = {
      date: today,
      winRate,
      totalTrades: total,
      action,
      newConfig,
    };
    this.adjustmentLog.push(logEntry);
    this.lastRunDate = today;

    // Keep only last 30 log entries
    if (this.adjustmentLog.length > 30) {
      this.adjustmentLog = this.adjustmentLog.slice(-15);
    }

    return logEntry;
  }

  /**
   * Get the recent win rate from stored trades.
   */
  getRecentWinRate(days: number = 7): number {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const recent = this.trades.filter(
      (t) => new Date(t.entryTime) >= cutoff && t.outcome !== 'pending'
    );
    if (recent.length === 0) return 0;
    return recent.filter((t) => t.outcome === 'win').length / recent.length;
  }

  /**
   * Get the adjustment log history.
   */
  getAdjustmentLog(limit: number = 10): typeof this.adjustmentLog {
    return this.adjustmentLog.slice(-limit);
  }

  /**
   * Get total trade counts.
   */
  getTradeCounts(): { wins: number; losses: number; total: number; winRate: number } {
    const completed = this.trades.filter((t) => t.outcome !== 'pending');
    const wins = completed.filter((t) => t.outcome === 'win').length;
    const total = completed.length;
    return {
      wins,
      losses: total - wins,
      total,
      winRate: total > 0 ? wins / total : 0,
    };
  }
}

// Singleton
export const dailyImprover = new DailyImprover();
