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

  setSignals: (signals) => set({ signals }),
  addSignal: (signal) =>
    set((state) => ({
      signals: [signal, ...state.signals].slice(0, 50),
    })),
  setConnected: (connected) => set({ isConnected: connected }),
  setPlatform: (platform) => set({ platform }),
  setPerformance: (performance) => set({ performance }),
  setLoading: (loading) => set({ isLoading: loading }),
  clearSignals: () => set({ signals: [] }),
}));
