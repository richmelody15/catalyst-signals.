// CATALYST AI - Type Definitions

import type { MarketRegime } from './market-regime';
import type { SRLevel } from './support-resistance';

// ─── Bug Fixer Types ──────────────────────────────────────────────
export interface BugFixerConfig {
  fallbackValue: unknown;
  retryCount: number;
  retryDelay: number;
  module: string;
  function: string;
}

export interface ErrorRecord {
  id: string;
  error: string;
  module: string;
  function: string;
  timestamp: string;
  retryCount: number;
  recovered: boolean;
  fallbackUsed: boolean;
}

export interface BugFixerStats {
  totalErrors: number;
  recoveredErrors: number;
  fallbackUsed: number;
  unrecoveredErrors: number;
  recoveryRate: number;
  errorsByModule: Record<string, number>;
  recentErrors: ErrorRecord[];
}

// ─── Multi-Timeframe Types ────────────────────────────────────────
export type MTFTimeframe = '30s' | '45s' | '1m' | '2m' | '3m' | '5m';

export interface MTFAnalysis {
  timeframe: MTFTimeframe;
  trend: 'bullish' | 'bearish' | 'neutral';
  trendStrength: number; // 0-100
  rsi: number;
  stochK: number;
  stochD: number;
  adx: number;
  bosConfirmed: boolean;
  chochConfirmed: boolean;
  fvgActive: boolean;
  liquiditySweep: boolean;
  emaShort: number;
  emaLong: number;
  bbWidth: number;
  volumeSpike: boolean;
}

export interface MTFConfluence {
  aligned: boolean;
  alignmentScore: number; // 0-100
  dominantTrend: 'bullish' | 'bearish' | 'neutral';
  bullishCount: number;
  bearishCount: number;
  neutralCount: number;
  timeframeResults: Record<MTFTimeframe, MTFAnalysis>;
  // 8-point advanced checklist
  checklist: {
    higher_tf_trend_alignment: boolean;
    structure_break_confirmed: boolean;
    momentum_convergence: boolean;
    volume_confirmation: boolean;
    rsi_divergence_check: boolean;
    ema_stack_alignment: boolean;
    volatility_filter: boolean;
    liquidity_pool_proximity: boolean;
  };
  checklistScore: number; // 0-100
}

// ─── Supply/Demand Zone Types ─────────────────────────────────────
export type ZoneType = 'RBR' | 'DBR' | 'RBD' | 'DBD' | 'flip' | 'failed_breakout' | 'volume_profile';
export type ZoneStrength = 'weak' | 'moderate' | 'strong' | 'extreme';

export interface SupplyDemandZone {
  id: string;
  type: ZoneType;
  direction: 'bullish' | 'bearish';
  high: number;
  low: number;
  midpoint: number;
  width: number;
  strength: ZoneStrength;
  beliefScore: number; // 0-100
  creationIndex: number;
  touches: number;
  lastTouchIndex: number;
  active: boolean;
  tested: boolean;
  broken: boolean;
  volumeAtCreation: number;
  atrAtCreation: number;
  age: number; // bars since creation
  // Performance tracking
  performance: {
    timesTested: number;
    timesHeld: number;
    timesBroken: number;
    holdRate: number; // 0-100
  };
}

export interface ZoneInteraction {
  zone: SupplyDemandZone;
  interactionType: 'approach' | 'test' | 'bounce' | 'break' | 'flip';
  signal: 'BUY' | 'SELL' | null;
  confidence: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  riskReward: number;
}

export interface ZoneTrackerStats {
  totalZones: number;
  activeZones: number;
  brokenZones: number;
  averageHoldRate: number;
  zonesByType: Record<ZoneType, number>;
  bestPerformingType: ZoneType;
  worstPerformingType: ZoneType;
}

// ─── Signal Formatter Types ───────────────────────────────────────
export interface FormattedSignal {
  plain: string;
  emoji: string;
  compact: string;
  detailed: string;
}

// ─── Main Signal Type ─────────────────────────────────────────────
export interface Signal {
  id: string;
  tradePair: string;
  timer: string;
  entryTime: Date;
  direction: 'BUY' | 'SELL';
  confidence: number;
  marketCondition: string;
  trend: string;
  bosConfirmed: boolean;
  chochConfirmed: boolean;
  fvgActive: boolean;
  liquiditySweep: boolean;
  volumeHigh: boolean;
  zoneType: string;
  rsiValue: number;
  stochasticBull: boolean;
  bbExpanding: boolean;
  adrStatus: string;
  riskReward: number;
  riskLevels: Record<string, number>;
  signalQuality: string;
  checklistScore: number;
  platform: string;
  // Market Regime Detection
  marketRegime: MarketRegime;
  regimeLabel: string;
  regimeDescription: string;
  // Strategy Guide
  strategy: {
    title: string;
    entryRules: string[];
    exitRules: string[];
    riskManagement: string[];
    avoidActions: string[];
    confidenceNote: string;
  };
  // GLM Probability
  glmProbability: number;
  // Support & Resistance
  nearestSupport: SRLevel | null;
  nearestResistance: SRLevel | null;
  supportZone: { start: number | null; end: number | null };
  resistanceZone: { start: number | null; end: number | null };
  // Multi-Timeframe Analysis
  mtfConfluence: MTFConfluence | null;
  // Supply/Demand Zone
  nearestSDZone: SupplyDemandZone | null;
  zoneInteraction: ZoneInteraction | null;
  // Bug Fixer Status
  engineHealth: {
    errorsRecovered: number;
    fallbacksUsed: number;
    recoveryRate: number;
    lastError: string | null;
  };
  // Formatted Signal
  formatted: FormattedSignal | null;
}

export interface MarketData {
  pair: string;
  timeframe: string;
  closePrices: number[];
  highPrices: number[];
  lowPrices: number[];
  openPrices: number[];
  volumes: number[];
}

export interface QualityChecklist {
  conditions: Record<string, boolean>;
  score: number;
  passed: boolean;
}

export interface StructureResult {
  bos: boolean;
  choch: boolean;
  swingHighs: Array<{ price: number; index: number }>;
  swingLows: Array<{ price: number; index: number }>;
}

export interface LiquidityResult {
  sweepDetected: boolean;
  sweepType: 'buy_side' | 'sell_side' | null;
  recentHigh: number;
  recentLow: number;
}

export interface FVG {
  type: 'bullish' | 'bearish';
  index: number;
  gapTop: number;
  gapBottom: number;
}

export interface BBResult {
  sma: number;
  upperBand: number;
  lowerBand: number;
  bbWidth: number;
}

export interface StochasticResult {
  k: number;
  d: number;
}

export interface PerformanceData {
  winRate: number;
  totalTrades: number;
  wins: number;
  losses: number;
  bestPair: string;
  dailyPnl: number;
  confidenceAccuracy: {
    accuracy: number;
    total: number;
    wins: number;
    losses: number;
  };
}

export const TRADING_PAIRS = [
  'EURUSD-OTC', 'XAUUSD-OTC', 'NZDUSD-OTC', 'GBPJPY-OTC',
  'AUDJPY-OTC', 'CADJPY-OTC', 'EURJPY-OTC', 'USDCAD-OTC',
  'XAGUSD-OTC', 'BTCUSD-OTC', 'NZDCAD-OTC', 'EURCAD-OTC',
  'NZDJPY-OTC', 'EURGBP', 'AUDUSD-OTC', 'EURCHF-OTC',
  'AUDNZD-OTC', 'USDCHF-OTC', 'USDBRL-OTC', 'USDZAR-OTC',
  'USDPLN-OTC', 'USDTRY-OTC', 'USDMXN-OTC', 'CHFJPY-OTC',
  'GBPCAD-OTC', 'EURTHB-OTC', 'USDNOK-OTC'
];

export const TIMEFRAMES = ['30s', '45s', '1m', '2m', '3m', '5m'];

export const TRADING_CONFIG = {
  MIN_CONFIDENCE_SCORE: 0.55,
  QUALITY_CHECKLIST_THRESHOLD: 0.943,
  RSI_PERIOD: 14,
  RSI_OVERSOLD: 30,
  RSI_OVERBOUGHT: 70,
  STOCHASTIC_K: 14,
  STOCHASTIC_D: 3,
  EMA_SHORT: 50,
  EMA_LONG: 200,
  ADX_PERIOD: 14,
  ADX_THRESHOLD: 20,
  BB_PERIOD: 20,
  BB_STD: 2.0,
};
