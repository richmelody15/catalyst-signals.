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
      try {
        const timeframe = TIMEFRAMES[Math.floor(Math.random() * TIMEFRAMES.length)];
        const marketData = marketSimulator.generateMarketData(pair, timeframe);

        if (marketData) {
          const signal = signalGenerator.generateSignal(marketData);
          if (signal) {
            newSignals.push(signal);
          }
        }
      } catch (e) {
        // Skip this pair if generation fails — don't crash the whole batch
        console.error(`[generate] Failed for ${pair}:`, e);
      }
    }

    // Safely serialize signals — ensure no NaN, Infinity, or circular refs
    const safeSignals = newSignals.map((s) => safeSerializeSignal(s));

    return NextResponse.json({
      success: true,
      signalsGenerated: newSignals.length,
      signals: safeSignals,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Signal generation error:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to generate signals', signals: [] },
      { status: 500 }
    );
  }
}

/**
 * Safely serialize a Signal for JSON response.
 * Converts Date objects to ISO strings, replaces NaN/Infinity with null,
 * and ensures all nested objects are present.
 */
function safeSerializeSignal(signal: Signal): Record<string, unknown> {
  try {
    // Deep clone by serializing and parsing — this strips undefined values
    // and catches any circular references
    const raw = JSON.parse(JSON.stringify(signal, (key, value) => {
      // Replace NaN and Infinity with null
      if (typeof value === 'number' && (!isFinite(value) || isNaN(value))) {
        return null;
      }
      return value;
    }));

    // Convert entryTime to ISO string (Date → string for JSON transport)
    raw.entryTime = signal.entryTime instanceof Date
      ? signal.entryTime.toISOString()
      : new Date(signal.entryTime || Date.now()).toISOString();

    return raw;
  } catch (e) {
    // If serialization fails, return a minimal safe object
    console.error('[safeSerializeSignal] Fallback:', e);
    return {
      id: signal.id || `SIG-${Date.now()}`,
      tradePair: signal.tradePair || 'UNKNOWN',
      timer: signal.timer || '1m (OTC)',
      entryTime: new Date().toISOString(),
      direction: signal.direction || 'BUY',
      confidence: 0,
      marketCondition: 'Normal',
      trend: 'Bullish',
      bosConfirmed: false,
      chochConfirmed: false,
      fvgActive: false,
      liquiditySweep: false,
      volumeHigh: false,
      zoneType: 'N/A',
      rsiValue: 50,
      stochasticBull: false,
      bbExpanding: false,
      adrStatus: 'Within range',
      riskReward: 2.5,
      riskLevels: {},
      signalQuality: 'HIGH PROBABILITY ONLY',
      checklistScore: 0,
      platform: 'iq-option',
      marketRegime: 'weak_trend',
      regimeLabel: 'Weak Trend',
      regimeDescription: '',
      strategy: { title: '', entryRules: [], exitRules: [], riskManagement: [], avoidActions: [], confidenceNote: '' },
      glmProbability: 94.3,
      nearestSupport: null,
      nearestResistance: null,
      supportZone: { start: null, end: null },
      resistanceZone: { start: null, end: null },
      mtfConfluence: null,
      nearestSDZone: null,
      zoneInteraction: null,
      engineHealth: { errorsRecovered: 0, fallbacksUsed: 0, recoveryRate: 100, lastError: null },
      glmSmartMoney: {
        price: 0, structure: 'RANGE', liquidity: 'NO_SWEEP', breakout: 'NO_BREAKOUT', signal: 'WAIT',
        labels: { structure: 'Range', liquidity: 'No Sweep', breakout: 'No Breakout', signal: 'Wait' },
        structureHistory: [], liquidityHistory: [],
      },
      formatted: null,
    };
  }
}
