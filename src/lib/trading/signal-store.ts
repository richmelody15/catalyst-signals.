// Signal Store - Zustand state management for trading signals
import { create } from 'zustand';
import type { Signal, PerformanceData } from './types';

interface TradingState {
  signals: Signal[];
  isConnected: boolean;
  platform: 'iq-option' | 'pocket-option';
  performance: PerformanceData;
  isLoading: boolean;

  setSignals: (signals: Signal[]) => void;
  addSignal: (signal: Signal) => void;
  setConnected: (connected: boolean) => void;
  setPlatform: (platform: 'iq-option' | 'pocket-option') => void;
  setPerformance: (performance: PerformanceData) => void;
  setLoading: (loading: boolean) => void;
  clearSignals: () => void;
}

/**
 * Normalize a signal that may have come from the API (where entryTime is ISO string
 * and nested objects may be missing or incomplete).
 */
function normalizeSignal(raw: Partial<Signal> & Record<string, unknown>): Signal {
  return {
    id: raw.id ?? `SIG-${Date.now()}`,
    tradePair: raw.tradePair ?? 'UNKNOWN',
    timer: raw.timer ?? '1m (OTC)',
    entryTime: raw.entryTime instanceof Date ? raw.entryTime : new Date((raw.entryTime as string | number) ?? Date.now()),
    direction: raw.direction === 'BUY' || raw.direction === 'SELL' ? raw.direction : 'BUY',
    confidence: typeof raw.confidence === 'number' ? raw.confidence : 0,
    marketCondition: raw.marketCondition ?? 'Normal',
    trend: raw.trend ?? 'Bullish',
    bosConfirmed: !!raw.bosConfirmed,
    chochConfirmed: !!raw.chochConfirmed,
    fvgActive: !!raw.fvgActive,
    liquiditySweep: !!raw.liquiditySweep,
    volumeHigh: !!raw.volumeHigh,
    zoneType: raw.zoneType ?? 'N/A',
    rsiValue: typeof raw.rsiValue === 'number' ? raw.rsiValue : 50,
    stochasticBull: !!raw.stochasticBull,
    bbExpanding: !!raw.bbExpanding,
    adrStatus: raw.adrStatus ?? 'Within range',
    riskReward: typeof raw.riskReward === 'number' ? raw.riskReward : 2.5,
    riskLevels: normalizeRiskLevels(raw.riskLevels),
    signalQuality: raw.signalQuality ?? 'HIGH PROBABILITY ONLY',
    checklistScore: typeof raw.checklistScore === 'number' ? raw.checklistScore : 0,
    platform: raw.platform ?? 'iq-option',
    marketRegime: raw.marketRegime ?? 'weak_trend',
    regimeLabel: raw.regimeLabel ?? 'Weak Trend',
    regimeDescription: raw.regimeDescription ?? '',
    strategy: normalizeStrategy(raw.strategy),
    glmProbability: typeof raw.glmProbability === 'number' ? raw.glmProbability : 94.3,
    nearestSupport: raw.nearestSupport ?? null,
    nearestResistance: raw.nearestResistance ?? null,
    supportZone: raw.supportZone ?? { start: null, end: null },
    resistanceZone: raw.resistanceZone ?? { start: null, end: null },
    mtfConfluence: raw.mtfConfluence ?? null,
    nearestSDZone: raw.nearestSDZone ?? null,
    zoneInteraction: raw.zoneInteraction ?? null,
    engineHealth: raw.engineHealth ?? { errorsRecovered: 0, fallbacksUsed: 0, recoveryRate: 100, lastError: null },
    glmSmartMoney: raw.glmSmartMoney ?? {
      price: 0,
      structure: 'RANGE',
      liquidity: 'NO_SWEEP',
      breakout: 'NO_BREAKOUT',
      signal: 'WAIT',
      labels: { structure: 'Range', liquidity: 'No Sweep', breakout: 'No Breakout', signal: 'Wait' },
      structureHistory: [],
      liquidityHistory: [],
    },
    formatted: raw.formatted ?? null,
  };
}

/**
 * Normalize risk levels from API: accept both number[] and {multiplier, time}[]
 */
function normalizeRiskLevels(raw: unknown): Record<string, { multiplier: number; time: string }> {
  const result: Record<string, { multiplier: number; time: string }> = {};
  if (!raw || typeof raw !== 'object') return result;
  for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
    if (val != null && typeof val === 'object' && 'multiplier' in (val as object)) {
      const obj = val as { multiplier?: number; time?: string };
      result[key] = { multiplier: obj.multiplier ?? 0, time: obj.time ?? '--:-- WAT' };
    } else if (typeof val === 'number') {
      result[key] = { multiplier: val, time: '--:-- WAT' };
    }
  }
  return result;
}

/**
 * Normalize strategy from API
 */
function normalizeStrategy(raw: unknown): Signal['strategy'] {
  if (!raw || typeof raw !== 'object') {
    return { title: '', entryRules: [], exitRules: [], riskManagement: [], avoidActions: [], confidenceNote: '' };
  }
  const s = raw as Record<string, unknown>;
  return {
    title: typeof s.title === 'string' ? s.title : '',
    entryRules: Array.isArray(s.entryRules) ? s.entryRules : [],
    exitRules: Array.isArray(s.exitRules) ? s.exitRules : [],
    riskManagement: Array.isArray(s.riskManagement) ? s.riskManagement : [],
    avoidActions: Array.isArray(s.avoidActions) ? s.avoidActions : [],
    confidenceNote: typeof s.confidenceNote === 'string' ? s.confidenceNote : '',
  };
}

export const useTradingStore = create<TradingState>((set) => ({
  signals: [],
  isConnected: false,
  platform: 'iq-option',
  performance: {
    winRate: 0,
    totalTrades: 0,
    wins: 0,
    losses: 0,
    bestPair: 'EURUSD-OTC',
    dailyPnl: 0,
    confidenceAccuracy: {
      accuracy: 0,
      total: 0,
      wins: 0,
      losses: 0,
    },
  },
  isLoading: false,

  setSignals: (signals) => set({ signals: signals.map(normalizeSignal) }),
  addSignal: (signal) =>
    set((state) => ({
      signals: [normalizeSignal(signal), ...state.signals].slice(0, 50),
    })),
  setConnected: (connected) => set({ isConnected: connected }),
  setPlatform: (platform) => set({ platform }),
  setPerformance: (performance) => set({ performance }),
  setLoading: (loading) => set({ isLoading: loading }),
  clearSignals: () => set({ signals: [] }),
}));
