// Trading Signal System - Type Definitions

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
  MIN_CONFIDENCE_SCORE: 0.85,
  QUALITY_CHECKLIST_THRESHOLD: 0.943,
  RSI_PERIOD: 14,
  RSI_OVERSOLD: 30,
  RSI_OVERBOUGHT: 70,
  STOCHASTIC_K: 14,
  STOCHASTIC_D: 3,
  EMA_SHORT: 50,
  EMA_LONG: 200,
  ADX_PERIOD: 14,
  ADX_THRESHOLD: 25,
  BB_PERIOD: 20,
  BB_STD: 2.0,
};
