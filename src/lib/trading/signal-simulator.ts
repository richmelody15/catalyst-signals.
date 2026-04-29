// Market Data Simulator - Generates realistic market data for demo
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

export class MarketSimulator {
  private priceHistory: Record<string, number[]> = {};
  private initialized = false;

  initialize(): void {
    if (this.initialized) return;

    for (const pair of TRADING_PAIRS) {
      const basePrice = BASE_PRICES[pair] || 100;
      this.priceHistory[pair] = [];

      // Generate 200 candles of historical data
      let price = basePrice;
      for (let i = 0; i < 200; i++) {
        const volatility = basePrice * 0.001;
        const change = (Math.random() - 0.5) * 2 * volatility;
        price = Math.max(price + change, basePrice * 0.95);
        price = Math.min(price, basePrice * 1.05);
        this.priceHistory[pair].push(price);
      }
    }

    this.initialized = true;
  }

  tick(): void {
    for (const pair of TRADING_PAIRS) {
      const history = this.priceHistory[pair];
      if (!history || history.length === 0) continue;

      const lastPrice = history[history.length - 1];
      const basePrice = BASE_PRICES[pair] || 100;
      const volatility = basePrice * 0.0008;

      // Random walk with mean reversion
      const meanReversionForce = (basePrice - lastPrice) * 0.01;
      const randomChange = (Math.random() - 0.5) * 2 * volatility;
      const trendForce = (Math.random() > 0.5 ? 1 : -1) * volatility * 0.3;

      let newPrice = lastPrice + randomChange + meanReversionForce + trendForce;
      newPrice = Math.max(newPrice, basePrice * 0.92);
      newPrice = Math.min(newPrice, basePrice * 1.08);

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
    const volatility = basePrice * 0.0005;

    const closePrices = [...history];
    const highPrices = closePrices.map((p) => p + Math.random() * volatility * 2);
    const lowPrices = closePrices.map((p) => p - Math.random() * volatility * 2);
    const openPrices = closePrices.map((p, i) =>
      i === 0 ? p : closePrices[i - 1] + (Math.random() - 0.5) * volatility
    );
    const volumes = closePrices.map(() =>
      1000 + Math.random() * 5000 + (Math.random() > 0.9 ? 5000 : 0)
    );

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
