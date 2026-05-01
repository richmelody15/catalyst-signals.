// Signal Store - Zustand state management for trading signals
import { create } from 'zustand';
import type { Signal, PerformanceData, SupplyDemandZone, ZoneInteraction, MTFConfluence, MTFTimeframe, MTFAnalysis, GLMSmartMoneyResult } from './types';
import type { SRLevel } from './support-resistance';

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
    nearestSupport: normalizeSRLevel(raw.nearestSupport),
    nearestResistance: normalizeSRLevel(raw.nearestResistance),
    supportZone: raw.supportZone ?? { start: null, end: null },
    resistanceZone: raw.resistanceZone ?? { start: null, end: null },
    mtfConfluence: normalizeMTFConfluence(raw.mtfConfluence),
    nearestSDZone: normalizeSDZone(raw.nearestSDZone),
    zoneInteraction: normalizeZoneInteraction(raw.zoneInteraction),
    engineHealth: raw.engineHealth ?? { errorsRecovered: 0, fallbacksUsed: 0, recoveryRate: 100, lastError: null },
    glmSmartMoney: normalizeGLMSmartMoney(raw.glmSmartMoney),
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
 * Normalize GLM Smart Money result from API — ensure all required fields exist
 */
function normalizeGLMSmartMoney(raw: unknown): GLMSmartMoneyResult {
  if (!raw || typeof raw !== 'object') {
    return {
      price: 0, structure: 'RANGE', liquidity: 'NO_SWEEP', breakout: 'NO_BREAKOUT', signal: 'WAIT',
      labels: { structure: 'Range', liquidity: 'No Sweep', breakout: 'No Breakout', signal: 'Wait' },
      structureHistory: [], liquidityHistory: [],
    };
  }
  const g = raw as Record<string, unknown>;
  const validStructures = ['BOS_UP', 'BOS_DOWN', 'RANGE'];
  const validLiquidity = ['BUY_SWEEP', 'SELL_SWEEP', 'NO_SWEEP'];
  const validBreakout = ['CONFIRMED_BREAKOUT_BUY', 'CONFIRMED_BREAKDOWN_SELL', 'NO_BREAKOUT'];
  const validSignal = ['VALID_BUY', 'VALID_SELL', 'FILTERED_NO_TRADE', 'WAIT'];

  const structure = validStructures.includes(g.structure as string) ? g.structure as GLMSmartMoneyResult['structure'] : 'RANGE';
  const liquidity = validLiquidity.includes(g.liquidity as string) ? g.liquidity as GLMSmartMoneyResult['liquidity'] : 'NO_SWEEP';
  const breakout = validBreakout.includes(g.breakout as string) ? g.breakout as GLMSmartMoneyResult['breakout'] : 'NO_BREAKOUT';
  const signal = validSignal.includes(g.signal as string) ? g.signal as GLMSmartMoneyResult['signal'] : 'WAIT';

  const rawLabels = (g.labels || {}) as Record<string, unknown>;

  return {
    price: typeof g.price === 'number' ? g.price : 0,
    structure,
    liquidity,
    breakout,
    signal,
    labels: {
      structure: typeof rawLabels.structure === 'string' ? rawLabels.structure : structure,
      liquidity: typeof rawLabels.liquidity === 'string' ? rawLabels.liquidity : liquidity,
      breakout: typeof rawLabels.breakout === 'string' ? rawLabels.breakout : breakout,
      signal: typeof rawLabels.signal === 'string' ? rawLabels.signal : signal,
    },
    structureHistory: Array.isArray(g.structureHistory) ? g.structureHistory.filter((s: unknown) => validStructures.includes(s as string)) as GLMSmartMoneyResult['structureHistory'] : [],
    liquidityHistory: Array.isArray(g.liquidityHistory) ? g.liquidityHistory.filter((l: unknown) => validLiquidity.includes(l as string)) as GLMSmartMoneyResult['liquidityHistory'] : [],
  };
}

/**
 * Normalize MTF confluence from API — ensure all required fields exist
 */
function normalizeMTFConfluence(raw: unknown): MTFConfluence | null {
  if (!raw || typeof raw !== 'object') return null;
  const c = raw as Record<string, unknown>;

  // Normalize timeframeResults — ensure all 6 timeframes exist
  const tfNames: MTFTimeframe[] = ['30s', '45s', '1m', '2m', '3m', '5m'];
  const rawResults = (c.timeframeResults || {}) as Record<string, unknown>;
  const timeframeResults: Record<MTFTimeframe, MTFAnalysis> = {} as Record<MTFTimeframe, MTFAnalysis>;
  for (const tf of tfNames) {
    const r = rawResults[tf] as Record<string, unknown> | undefined;
    timeframeResults[tf] = r && typeof r === 'object' ? {
      timeframe: tf,
      trend: r.trend === 'bullish' || r.trend === 'bearish' ? r.trend as 'bullish' | 'bearish' : 'neutral',
      trendStrength: typeof r.trendStrength === 'number' ? r.trendStrength : 0,
      rsi: typeof r.rsi === 'number' ? r.rsi : 50,
      stochK: typeof r.stochK === 'number' ? r.stochK : 50,
      stochD: typeof r.stochD === 'number' ? r.stochD : 50,
      adx: typeof r.adx === 'number' ? r.adx : 20,
      bosConfirmed: !!r.bosConfirmed,
      chochConfirmed: !!r.chochConfirmed,
      fvgActive: !!r.fvgActive,
      liquiditySweep: !!r.liquiditySweep,
      emaShort: typeof r.emaShort === 'number' ? r.emaShort : 0,
      emaLong: typeof r.emaLong === 'number' ? r.emaLong : 0,
      bbWidth: typeof r.bbWidth === 'number' ? r.bbWidth : 0.02,
      volumeSpike: !!r.volumeSpike,
    } : {
      timeframe: tf, trend: 'neutral', trendStrength: 0, rsi: 50, stochK: 50, stochD: 50,
      adx: 20, bosConfirmed: false, chochConfirmed: false, fvgActive: false,
      liquiditySweep: false, emaShort: 0, emaLong: 0, bbWidth: 0.02, volumeSpike: false,
    };
  }

  // Normalize checklist — ensure all 8 keys exist
  const rawChecklist = (c.checklist || {}) as Record<string, unknown>;
  const checklist = {
    higher_tf_trend_alignment: !!rawChecklist.higher_tf_trend_alignment,
    structure_break_confirmed: !!rawChecklist.structure_break_confirmed,
    momentum_convergence: !!rawChecklist.momentum_convergence,
    volume_confirmation: !!rawChecklist.volume_confirmation,
    rsi_divergence_check: !!rawChecklist.rsi_divergence_check,
    ema_stack_alignment: !!rawChecklist.ema_stack_alignment,
    volatility_filter: !!rawChecklist.volatility_filter,
    liquidity_pool_proximity: !!rawChecklist.liquidity_pool_proximity,
  };

  return {
    aligned: !!c.aligned,
    alignmentScore: typeof c.alignmentScore === 'number' ? c.alignmentScore : 0,
    dominantTrend: c.dominantTrend === 'bullish' || c.dominantTrend === 'bearish' ? c.dominantTrend as 'bullish' | 'bearish' : 'neutral',
    bullishCount: typeof c.bullishCount === 'number' ? c.bullishCount : 0,
    bearishCount: typeof c.bearishCount === 'number' ? c.bearishCount : 0,
    neutralCount: typeof c.neutralCount === 'number' ? c.neutralCount : 0,
    timeframeResults,
    checklist,
    checklistScore: typeof c.checklistScore === 'number' ? c.checklistScore : 0,
  };
}

/**
 * Normalize S/R level from API — ensure all required fields exist
 */
function normalizeSRLevel(raw: unknown): SRLevel | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const price = typeof r.price === 'number' ? r.price : NaN;
  if (isNaN(price)) return null;
  return {
    price,
    strength: typeof r.strength === 'number' ? r.strength : 0,
    type: r.type === 'support' || r.type === 'resistance' ? r.type as 'support' | 'resistance' : 'support',
    zoneWidth: typeof r.zoneWidth === 'number' ? r.zoneWidth : 0.002,
    timeframe: typeof r.timeframe === 'string' ? r.timeframe : 'merged',
    score: typeof r.score === 'number' ? r.score : 0,
    isMajor: !!r.isMajor,
    lastTest: typeof r.lastTest === 'string' ? r.lastTest : new Date().toISOString(),
    breakout: !!r.breakout,
  };
}

/**
 * Normalize S/D zone from API — ensure all required fields exist
 */
function normalizeSDZone(raw: unknown): SupplyDemandZone | null {
  if (!raw || typeof raw !== 'object') return null;
  const z = raw as Record<string, unknown>;
  return {
    id: typeof z.id === 'string' ? z.id : `ZONE-${Date.now()}`,
    type: z.type as string ?? 'volume_profile',
    direction: z.direction === 'bullish' || z.direction === 'bearish' ? z.direction : 'bullish',
    high: typeof z.high === 'number' ? z.high : 0,
    low: typeof z.low === 'number' ? z.low : 0,
    midpoint: typeof z.midpoint === 'number' ? z.midpoint : 0,
    width: typeof z.width === 'number' ? z.width : 0,
    strength: z.strength as string ?? 'moderate',
    beliefScore: typeof z.beliefScore === 'number' ? z.beliefScore : 50,
    creationIndex: typeof z.creationIndex === 'number' ? z.creationIndex : 0,
    touches: typeof z.touches === 'number' ? z.touches : 0,
    lastTouchIndex: typeof z.lastTouchIndex === 'number' ? z.lastTouchIndex : 0,
    active: !!z.active,
    tested: !!z.tested,
    broken: !!z.broken,
    volumeAtCreation: typeof z.volumeAtCreation === 'number' ? z.volumeAtCreation : 0,
    atrAtCreation: typeof z.atrAtCreation === 'number' ? z.atrAtCreation : 0,
    age: typeof z.age === 'number' ? z.age : 0,
    performance: z.performance && typeof z.performance === 'object'
      ? {
          timesTested: typeof (z.performance as Record<string, unknown>).timesTested === 'number' ? (z.performance as Record<string, unknown>).timesTested as number : 0,
          timesHeld: typeof (z.performance as Record<string, unknown>).timesHeld === 'number' ? (z.performance as Record<string, unknown>).timesHeld as number : 0,
          timesBroken: typeof (z.performance as Record<string, unknown>).timesBroken === 'number' ? (z.performance as Record<string, unknown>).timesBroken as number : 0,
          holdRate: typeof (z.performance as Record<string, unknown>).holdRate === 'number' ? (z.performance as Record<string, unknown>).holdRate as number : 0,
        }
      : { timesTested: 0, timesHeld: 0, timesBroken: 0, holdRate: 0 },
  };
}

/**
 * Normalize zone interaction from API — ensure all required fields exist
 */
function normalizeZoneInteraction(raw: unknown): ZoneInteraction | null {
  if (!raw || typeof raw !== 'object') return null;
  const z = raw as Record<string, unknown>;
  // The 'zone' property is required by ZoneInteraction type but is only used for reference
  // We normalize it to prevent rendering issues
  const zone = normalizeSDZone(z.zone);
  if (!zone) return null;
  return {
    zone,
    interactionType: (z.interactionType as string) ?? 'approach',
    signal: z.signal === 'BUY' || z.signal === 'SELL' ? z.signal : null,
    confidence: typeof z.confidence === 'number' ? z.confidence : 0,
    entryPrice: typeof z.entryPrice === 'number' ? z.entryPrice : 0,
    stopLoss: typeof z.stopLoss === 'number' ? z.stopLoss : 0,
    takeProfit: typeof z.takeProfit === 'number' ? z.takeProfit : 0,
    riskReward: typeof z.riskReward === 'number' ? z.riskReward : 0,
  };
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
