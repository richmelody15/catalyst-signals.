// POST /api/v1/signals/generate - Generate new signals (for demo/simulation)
import { NextResponse } from 'next/server';
import { signalGenerator, marketSimulator, ensureInitialized } from '@/lib/trading/engine-singleton';
import type { Signal } from '@/lib/trading/types';

export async function POST(request: Request) {
  try {
    ensureInitialized();

    // Simulate market tick
    marketSimulator.tick();

    // Try generating signals for multiple pairs
    const { TRADING_PAIRS, TIMEFRAMES } = await import('@/lib/trading/types');
    const newSignals: Signal[] = [];

    // Generate for 5-8 random pairs
    const pairsToCheck = TRADING_PAIRS
      .sort(() => Math.random() - 0.5)
      .slice(0, 8);

    for (const pair of pairsToCheck) {
      const timeframe = TIMEFRAMES[Math.floor(Math.random() * TIMEFRAMES.length)];
      const marketData = marketSimulator.generateMarketData(pair, timeframe);

      if (marketData) {
        const signal = signalGenerator.generateSignal(marketData);
        if (signal) {
          newSignals.push(signal);
        }
      }
    }

    return NextResponse.json({
      success: true,
      signalsGenerated: newSignals.length,
      signals: newSignals.map((s) => ({
        ...s,
        entryTime: s.entryTime.toISOString(),
      })),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Signal generation error:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to generate signals' },
      { status: 500 }
    );
  }
}
