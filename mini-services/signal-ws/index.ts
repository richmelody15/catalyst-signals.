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

function generateSignal() {
  const pair = TRADING_PAIRS[Math.floor(Math.random() * TRADING_PAIRS.length)];
  const timeframe = TIMEFRAMES[Math.floor(Math.random() * TIMEFRAMES.length)];
  const direction = Math.random() > 0.5 ? 'BUY' : 'SELL';
  const basePrice = BASE_PRICES[pair] || 100;
  const confidence = 85 + Math.random() * 13;
  const trend = direction === 'BUY' ? 'Bullish' : 'Bearish';
  const bosConfirmed = Math.random() > 0.4;
  const chochConfirmed = Math.random() > 0.6;
  const fvgActive = Math.random() > 0.5;
  const liquiditySweep = Math.random() > 0.5;
  const volumeHigh = Math.random() > 0.4;
  const bbExpanding = Math.random() > 0.5;
  const rsiValue = direction === 'BUY'
    ? 20 + Math.random() * 20
    : 70 + Math.random() * 20;
  const stochK = direction === 'BUY'
    ? 10 + Math.random() * 25
    : 70 + Math.random() * 25;

  signalCounter++;

  return {
    id: `SIG-${Date.now()}-${signalCounter}`,
    tradePair: pair,
    timer: `${timeframe} (OTC)`,
    entryTime: new Date(Date.now() + 4 * 60 * 1000).toISOString(),
    direction,
    confidence: +confidence.toFixed(1),
    marketCondition: bbExpanding ? 'High Volatility' : 'Normal',
    trend,
    bosConfirmed,
    chochConfirmed,
    fvgActive,
    liquiditySweep,
    volumeHigh,
    zoneType: direction === 'BUY' ? 'Demand + Order Block' : 'Supply + Order Block',
    rsiValue: +rsiValue.toFixed(1),
    stochasticBull: direction === 'BUY' && stochK < 30,
    bbExpanding,
    adrStatus: 'Within range',
    riskReward: 2.5,
    riskLevels: {
      M1: +(2.2 * (1 + Math.random() * 0.3)).toFixed(1),
      M2: +(4.8 * (1 + Math.random() * 0.3)).toFixed(1),
      M3: +(10.5 * (1 + Math.random() * 0.3)).toFixed(1),
    },
    signalQuality: 'HIGH PROBABILITY ONLY',
    checklistScore: +(94.3 + Math.random() * 5).toFixed(1),
    platform: Math.random() > 0.5 ? 'iq-option' : 'pocket-option',
    currentPrice: basePrice,
  };
}

// Connected clients
const clients = new Set<string>();

io.on('connection', (socket) => {
  console.log(`Client connected: ${socket.id}`);
  clients.add(socket.id);

  // Send initial data
  socket.emit('connected', {
    message: 'Trading Signal System Connected',
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

// Auto-generate signals every 8-15 seconds
let signalInterval: ReturnType<typeof setTimeout>;

function scheduleNextSignal() {
  const delay = 8000 + Math.random() * 7000;
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
