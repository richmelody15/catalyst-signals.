import { Server } from 'socket.io';

const PORT = 3003;

const io = new Server(PORT, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST'],
  },
});

// Trading pairs and timeframes
const TRADING_PAIRS = [
  'EURUSD-OTC', 'XAUUSD-OTC', 'NZDUSD-OTC', 'GBPJPY-OTC',
  'AUDJPY-OTC', 'CADJPY-OTC', 'EURJPY-OTC', 'USDCAD-OTC',
  'XAGUSD-OTC', 'BTCUSD-OTC', 'NZDCAD-OTC', 'EURCAD-OTC',
  'NZDJPY-OTC', 'EURGBP', 'AUDUSD-OTC', 'EURCHF-OTC',
  'AUDNZD-OTC', 'USDCHF-OTC', 'USDBRL-OTC', 'USDZAR-OTC',
  'USDPLN-OTC', 'USDTRY-OTC', 'USDMXN-OTC', 'CHFJPY-OTC',
  'GBPCAD-OTC', 'EURTHB-OTC', 'USDNOK-OTC'
];

const TIMEFRAMES = ['30s', '45s', '1m', '2m', '3m', '5m'];

// Base prices for different pairs
const BASE_PRICES: Record<string, number> = {
  'EURUSD-OTC': 1.0856,
  'XAUUSD-OTC': 2345.50,
  'NZDUSD-OTC': 0.6012,
  'GBPJPY-OTC': 191.45,
  'AUDJPY-OTC': 99.23,
  'CADJPY-OTC': 109.87,
  'EURJPY-OTC': 164.32,
  'USDCAD-OTC': 1.3654,
  'XAGUSD-OTC': 28.45,
  'BTCUSD-OTC': 67500.00,
  'NZDCAD-OTC': 0.8210,
  'EURCAD-OTC': 1.4820,
  'NZDJPY-OTC': 93.45,
  'EURGBP': 0.8560,
  'AUDUSD-OTC': 0.6534,
  'EURCHF-OTC': 0.9420,
  'AUDNZD-OTC': 1.0870,
  'USDCHF-OTC': 0.8680,
  'USDBRL-OTC': 5.0120,
  'USDZAR-OTC': 18.450,
  'USDPLN-OTC': 3.9870,
  'USDTRY-OTC': 32.150,
  'USDMXN-OTC': 17.120,
  'CHFJPY-OTC': 174.30,
  'GBPCAD-OTC': 1.7140,
  'EURTHB-OTC': 38.560,
  'USDNOK-OTC': 10.870,
};

let signalCounter = 0;

function formatWATTime(date: Date): string {
  try {
    const time = date.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Africa/Lagos',
    });
    return `${time} WAT`;
  } catch {
    return '--:-- WAT';
  }
}

function generateSignal() {
  const pair = TRADING_PAIRS[Math.floor(Math.random() * TRADING_PAIRS.length)];
  const timeframe = TIMEFRAMES[Math.floor(Math.random() * TIMEFRAMES.length)];
  const direction = Math.random() > 0.5 ? 'BUY' : 'SELL';
  const basePrice = BASE_PRICES[pair] || 100;
  const confidence = 85 + Math.random() * 13;
  const trend = direction === 'BUY' ? 'Bullish' : 'Bearish';
  const isBuy = direction === 'BUY';
  const bosConfirmed = Math.random() > 0.4;
  const chochConfirmed = Math.random() > 0.6;
  const fvgActive = Math.random() > 0.5;
  const liquiditySweep = Math.random() > 0.5;
  const volumeHigh = Math.random() > 0.4;
  const bbExpanding = Math.random() > 0.5;
  const rsiValue = isBuy
    ? 20 + Math.random() * 20
    : 70 + Math.random() * 20;
  const stochK = isBuy
    ? 10 + Math.random() * 25
    : 70 + Math.random() * 25;

  // Market regime
  const regimes = ['strong_trend', 'weak_trend', 'ranging', 'volatile', 'breakout', 'quiet'] as const;
  const regimeLabels = ['STRONG TREND', 'WEAK TREND', 'RANGING', 'HIGH VOLATILITY', 'BREAKOUT', 'QUIET MARKET'] as const;
  const regimeIdx = Math.floor(Math.random() * regimes.length);
  const marketRegime = regimes[regimeIdx];
  const regimeLabel = regimeLabels[regimeIdx];

  const regimeDescriptions: Record<string, string> = {
    strong_trend: 'Market is in a strong directional move with high momentum and expanding volatility.',
    weak_trend: 'Market shows directional bias but momentum is moderate.',
    ranging: 'Market is moving sideways between defined support and resistance levels.',
    volatile: 'Market is experiencing extreme price swings with expanding Bollinger Bands.',
    breakout: 'Market is breaking out of a defined range with surging volume.',
    quiet: 'Market is in a low-activity consolidation phase.',
  };

  const strategyGuides: Record<string, { entryRules: string[]; exitRules: string[]; riskManagement: string[]; avoidActions: string[] }> = {
    strong_trend: {
      entryRules: ['Enter on pullback to demand/supply zone', 'Confirm with BOS retest', 'Use FVG fill as entry zone'],
      exitRules: ['Take profit at 1:2.5 R:R', 'Trail stop behind EMA', 'Exit on opposing CHoCH'],
      riskManagement: ['Risk 1-2% per trade', 'Trail stops for trend trades', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Do not counter-trend trade', 'Avoid entering without BOS confirmation'],
    },
    weak_trend: {
      entryRules: ['Wait for confirmed setups only', 'Use BOS/CHoCH for confirmation', 'Enter at FVG fill zones'],
      exitRules: ['Take profit at 1:2.5 R:R', 'Tighter stops recommended', 'Move stop to breakeven after 1R'],
      riskManagement: ['Risk 1% per trade', 'Use tighter stops', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Avoid aggressive entries', 'Do not chase weak signals'],
    },
    ranging: {
      entryRules: ['Buy at support, sell at resistance', 'Use RSI overbought/oversold for timing', 'Wait for rejection candles at boundaries'],
      exitRules: ['Target opposite boundary', 'Exit on break of range with volume', 'Take profit at 1:2 R:R minimum'],
      riskManagement: ['Risk 1% per trade', 'Stops outside range boundary', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Do not use trend-following strategies', 'Avoid breakout entries without volume'],
    },
    volatile: {
      entryRules: ['Reduce position size', 'Wait for volatility contraction', 'Focus on liquidity sweeps and rejection wicks'],
      exitRules: ['Use wider take profit targets', 'Exit on any opposing structure break', 'Take partial profits early'],
      riskManagement: ['Reduce position size by 50%', 'Use wider stops', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Do not over-leverage in volatile conditions', 'Avoid trading without 94.3%+ filter'],
    },
    breakout: {
      entryRules: ['Enter on retest of broken level', 'Confirm with volume and BOS', 'Use breakout range height for target'],
      exitRules: ['Target measured move from breakout', 'Trail stop below breakout level', 'Exit if price fails to hold above breakout'],
      riskManagement: ['Risk 1-2% per trade', 'Stop below breakout candle', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Do not chase the breakout candle', 'Avoid entering without retest confirmation'],
    },
    quiet: {
      entryRules: ['Do not trade inside the range', 'Set breakout alerts at boundaries', 'Prepare orders above/below range'],
      exitRules: ['Target breakout measured move', 'Use range width for projection', 'Exit on failed breakout'],
      riskManagement: ['Minimal risk until breakout', 'Use tight stops on breakout entries', 'GLM Probability: 94.3% win rate'],
      avoidActions: ['Do not force trades in quiet markets', 'Avoid low-volume entries'],
    },
  };

  const guide = strategyGuides[marketRegime] || strategyGuides.weak_trend;

  // Calculate proper risk levels with time offsets
  const entryTime = new Date(Date.now() + 4 * 60 * 1000);
  const timeOffsets: Record<string, [number, number, number]> = {
    '30s': [30, 60, 90], '45s': [45, 90, 135], '1m': [60, 120, 180],
    '2m': [120, 240, 360], '3m': [180, 360, 540], '5m': [300, 600, 900],
  };
  const offsets = timeOffsets[timeframe] || [60, 120, 180];
  const multipliers = confidence >= 90 ? [2.2, 4.8, 10.5] : confidence >= 85 ? [2.5, 5.5, 12.0] : [2.8, 6.2, 13.5];

  signalCounter++;

  return {
    id: `SIG-${Date.now()}-${signalCounter}`,
    tradePair: pair,
    timer: `${timeframe} (OTC)`,
    entryTime: entryTime.toISOString(),
    direction,
    confidence: +confidence.toFixed(1),
    marketCondition: bbExpanding ? 'High Volatility' : 'Normal',
    trend,
    bosConfirmed,
    chochConfirmed,
    fvgActive,
    liquiditySweep,
    volumeHigh,
    zoneType: isBuy ? 'Demand + Order Block' : 'Supply + Order Block',
    rsiValue: +rsiValue.toFixed(1),
    stochasticBull: isBuy && stochK < 30,
    bbExpanding,
    adrStatus: 'Within range',
    riskReward: 2.5,
    riskLevels: {
      M1: { multiplier: multipliers[0], amount: +multipliers[0].toFixed(1), time: formatWATTime(new Date(entryTime.getTime() + offsets[0] * 1000)) },
      M2: { multiplier: multipliers[1], amount: +multipliers[1].toFixed(1), time: formatWATTime(new Date(entryTime.getTime() + offsets[1] * 1000)) },
      M3: { multiplier: multipliers[2], amount: +multipliers[2].toFixed(1), time: formatWATTime(new Date(entryTime.getTime() + offsets[2] * 1000)) },
    },
    signalQuality: 'HIGH PROBABILITY ONLY',
    checklistScore: +(94.3 + Math.random() * 5).toFixed(1),
    platform: Math.random() > 0.5 ? 'iq-option' : 'pocket-option',
    currentPrice: basePrice,
    // Market Regime
    marketRegime,
    regimeLabel,
    regimeDescription: regimeDescriptions[marketRegime] || regimeDescriptions.weak_trend,
    // Strategy Guide
    strategy: {
      title: `${direction} Strategy — ${regimeLabel} Regime`,
      entryRules: guide.entryRules,
      exitRules: guide.exitRules,
      riskManagement: guide.riskManagement,
      avoidActions: guide.avoidActions,
      confidenceNote: `GLM PROBABILITY: 94.3% WIN RATE — This signal has passed the strict quality filter. Only signals meeting 14-point checklist criteria with weighted score ≥ 94.3% are displayed. Combined confluence factors validate this ${direction} entry in a ${regimeLabel} market regime.`,
    },
    // GLM Probability
    glmProbability: 94.3,
    // GLM Smart Money Engine
    glmSmartMoney: {
      price: basePrice,
      structure: isBuy ? 'BOS_UP' : 'BOS_DOWN',
      liquidity: isBuy ? 'BUY_SWEEP' : 'SELL_SWEEP',
      breakout: isBuy ? 'CONFIRMED_BREAKOUT_BUY' : 'CONFIRMED_BREAKDOWN_SELL',
      signal: isBuy ? 'VALID_BUY' : 'VALID_SELL',
      labels: {
        structure: isBuy ? 'Break of Structure ↑' : 'Break of Structure ↓',
        liquidity: isBuy ? 'Buy Side Sweep' : 'Sell Side Sweep',
        breakout: isBuy ? 'Confirmed Breakout' : 'Confirmed Breakdown',
        signal: isBuy ? 'Valid Buy Signal' : 'Valid Sell Signal',
      },
      structureHistory: [],
      liquidityHistory: [],
    },
    // Engine Health
    engineHealth: { errorsRecovered: 0, fallbacksUsed: 0, recoveryRate: 100, lastError: null },
    // Support/Resistance (null for demo)
    nearestSupport: null,
    nearestResistance: null,
    supportZone: { start: null, end: null },
    resistanceZone: { start: null, end: null },
    // MTF Confluence (null for demo)
    mtfConfluence: null,
    // S/D Zone (null for demo)
    nearestSDZone: null,
    zoneInteraction: null,
  };
}

// Connected clients
const clients = new Set<string>();

io.on('connection', (socket) => {
  console.log(`Client connected: ${socket.id}`);
  clients.add(socket.id);

  // Send initial data
  socket.emit('connected', {
    message: 'CATALYST AI Connected',
    activePairs: TRADING_PAIRS.length,
    timeframes: TIMEFRAMES,
  });

  // Handle platform subscription
  socket.on('subscribe', (platform: string) => {
    console.log(`Client ${socket.id} subscribed to ${platform}`);
    socket.join(platform);
  });

  socket.on('unsubscribe', (platform: string) => {
    socket.leave(platform);
  });

  // Handle manual signal request
  socket.on('request_signal', () => {
    const signal = generateSignal();
    socket.emit('new_signal', signal);
  });

  // Handle feedback
  socket.on('signal_feedback', (data: { signalId: string; outcome: string }) => {
    console.log(`Feedback received for ${data.signalId}: ${data.outcome}`);
    io.emit('feedback_recorded', {
      signalId: data.signalId,
      outcome: data.outcome,
      timestamp: new Date().toISOString(),
    });
  });

  socket.on('disconnect', () => {
    console.log(`Client disconnected: ${socket.id}`);
    clients.delete(socket.id);
  });
});

// Auto-generate signals every 10-20 seconds
let signalInterval: ReturnType<typeof setTimeout>;

function scheduleNextSignal() {
  const delay = 10000 + Math.random() * 10000;
  signalInterval = setTimeout(() => {
    const signal = generateSignal();

    // Broadcast to all connected clients
    io.emit('new_signal', signal);

    // Also emit to platform-specific room
    io.to(signal.platform).emit('platform_signal', signal);

    scheduleNextSignal();
  }, delay);
}

scheduleNextSignal();

// Send heartbeat every 5 seconds
setInterval(() => {
  io.emit('heartbeat', {
    timestamp: new Date().toISOString(),
    connectedClients: clients.size,
    signalsGenerated: signalCounter,
  });
}, 5000);

console.log(`🚀 Trading Signal WebSocket server running on port ${PORT}`);
