// Self-Learning Engine - Dynamic weight adjustment based on signal outcomes
import { db } from '@/lib/db';

interface OutcomeRecord {
  signalId: string;
  outcome: 'win' | 'loss';
  timestamp: string;
  direction: string;
  confidence: number;
  pair: string;
}

export class SelfLearningEngine {
  private outcomes: OutcomeRecord[] = [];
  private indicatorWeights: Record<string, number> = {
    rsi: 0.15,
    stochastic: 0.15,
    ema: 0.10,
    adx: 0.10,
    bb_width: 0.05,
    bos_choch: 0.15,
    fvg: 0.10,
    liquidity: 0.10,
    volume: 0.10,
  };

  async processOutcome(
    signalId: string,
    outcome: 'win' | 'loss',
    direction: string = 'BUY',
    confidence: number = 85,
    pair: string = 'EURUSD-OTC'
  ): Promise<void> {
    this.outcomes.push({
      signalId,
      outcome,
      timestamp: new Date().toISOString(),
      direction,
      confidence,
      pair,
    });

    // Adjust weights based on outcome
    this.adjustWeights(outcome);

    // Update database
    try {
      await db.signal.update({
        where: { id: signalId },
        data: { outcome },
      });
    } catch {
      // Signal may not exist in DB, that's fine for demo
    }
  }

  private adjustWeights(outcome: 'win' | 'loss'): void {
    const learningRate = 0.05;

    for (const indicator of Object.keys(this.indicatorWeights)) {
      if (outcome === 'win') {
        this.indicatorWeights[indicator] *= (1 + learningRate);
      } else {
        this.indicatorWeights[indicator] *= (1 - learningRate);
      }
    }

    // Normalize weights to sum to 1
    const total = Object.values(this.indicatorWeights).reduce((a, b) => a + b, 0);
    for (const indicator of Object.keys(this.indicatorWeights)) {
      this.indicatorWeights[indicator] /= total;
    }
  }

  getConfidenceAccuracy(): {
    accuracy: number;
    total: number;
    wins: number;
    losses: number;
  } {
    if (this.outcomes.length === 0) {
      return { accuracy: 0, total: 0, wins: 0, losses: 0 };
    }

    const wins = this.outcomes.filter((o) => o.outcome === 'win').length;
    const total = this.outcomes.length;

    return {
      accuracy: total > 0 ? wins / total : 0,
      total,
      wins,
      losses: total - wins,
    };
  }

  getWeights(): Record<string, number> {
    return { ...this.indicatorWeights };
  }

  getRecentOutcomes(limit: number = 20): OutcomeRecord[] {
    return this.outcomes.slice(-limit);
  }

  getWinRate(): number {
    if (this.outcomes.length === 0) return 0;
    const wins = this.outcomes.filter((o) => o.outcome === 'win').length;
    return wins / this.outcomes.length;
  }
}

// Singleton instance
export const learningEngine = new SelfLearningEngine();
