// Market Data Simulator - Generates realistic market data for demo
// Improved: Stronger trend cycles, wider H/L spreads, volume spikes
import { TRADING_PAIRS, TIMEFRAMES, type MarketData } from './types';

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

// Each pair has its own trend state for realistic trending behavior
interface PairTrendState {
  direction: 1 | -1;       // Current trend direction
  strength: number;         // 0.3–1.0
  duration: number;         // How many bars left in this trend phase
}

export class MarketSimulator {
  private priceHistory: Record<string, number[]> = {};
  private trendStates: Record<string, PairTrendState> = {};
  private initialized = false;

  initialize(): void {
    if (this.initialized) return;

    for (const pair of TRADING_PAIRS) {
      const basePrice = BASE_PRICES[pair] || 100;
      this.priceHistory[pair] = [];

      // Initialize trend state for each pair
      this.trendStates[pair] = {
        direction: Math.random() > 0.5 ? 1 : -1,
        strength: 0.3 + Math.random() * 0.7,
        duration: Math.floor(20 + Math.random() * 60), // 20–80 bars per trend phase
      };

      // Generate 200 candles of historical data with realistic trend cycles
      let price = basePrice;
      for (let i = 0; i < 200; i++) {
        this.updateTrendState(pair);
        const state = this.trendStates[pair];

        const volatility = basePrice * 0.002; // 0.2% per candle
        const trendComponent = state.direction * state.strength * volatility * 0.8;
        const randomComponent = (Math.random() - 0.5) * 2 * volatility * 0.6;
        const meanReversion = (basePrice - price) * 0.003; // Gentle mean reversion

        price = price + trendComponent + randomComponent + meanReversion;
        price = Math.max(price, basePrice * 0.90);
        price = Math.min(price, basePrice * 1.10);

        this.priceHistory[pair].push(price);
      }
    }

    this.initialized = true;
  }

  private updateTrendState(pair: string): void {
    const state = this.trendStates[pair];
    if (!state) return;

    state.duration--;

    // When trend phase expires, pick a new direction and strength
    if (state.duration <= 0) {
      state.direction = Math.random() > 0.5 ? 1 : -1;
      state.strength = 0.3 + Math.random() * 0.7;
      state.duration = Math.floor(15 + Math.random() * 50);
    }
  }

  tick(): void {
    for (const pair of TRADING_PAIRS) {
      const history = this.priceHistory[pair];
      if (!history || history.length === 0) continue;

      this.updateTrendState(pair);
      const state = this.trendStates[pair];
      const lastPrice = history[history.length - 1];
      const basePrice = BASE_PRICES[pair] || 100;

      const volatility = basePrice * 0.002;
      const trendComponent = state.direction * state.strength * volatility * 0.8;
      const randomComponent = (Math.random() - 0.5) * 2 * volatility * 0.5;
      const meanReversion = (basePrice - lastPrice) * 0.003;

      let newPrice = lastPrice + trendComponent + randomComponent + meanReversion;
      newPrice = Math.max(newPrice, basePrice * 0.88);
      newPrice = Math.min(newPrice, basePrice * 1.12);

      history.push(newPrice);

      // Keep last 300 candles
      if (history.length > 300) {
        history.shift();
      }
    }
  }

  generateMarketData(pair: string, timeframe: string): MarketData | null {
    const history = this.priceHistory[pair];
    if (!history || history.length < 50) return null;

    const basePrice = BASE_PRICES[pair] || 100;
    const volatility = basePrice * 0.0015; // 0.15% — wider H/L spreads for realistic indicators

    const closePrices = [...history];
    const highPrices = closePrices.map((p) => p + Math.random() * volatility * 3);
    const lowPrices = closePrices.map((p) => p - Math.random() * volatility * 3);
    const openPrices = closePrices.map((p, i) =>
      i === 0 ? p : closePrices[i - 1] + (Math.random() - 0.5) * volatility * 2
    );

    // Generate volume with occasional spikes (1 in 8 chance)
    const volumes = closePrices.map(() => {
      const base = 1000 + Math.random() * 4000;
      const spike = Math.random() > 0.875 ? 8000 + Math.random() * 7000 : 0;
      return base + spike;
    });

    return {
      pair,
      timeframe,
      closePrices,
      highPrices,
      lowPrices,
      openPrices,
      volumes,
    };
  }

  getRandomPairAndTimeframe(): { pair: string; timeframe: string } {
    const pair = TRADING_PAIRS[Math.floor(Math.random() * TRADING_PAIRS.length)];
    const timeframe = TIMEFRAMES[Math.floor(Math.random() * TIMEFRAMES.length)];
    return { pair, timeframe };
  }
}
