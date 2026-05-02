'use client';

import React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  SignalCard,
} from '@/components/trading/signal-card';
import { AnalyticsPanel } from '@/components/trading/analytics-panel';
import { SignalHistory } from '@/components/trading/signal-history';
import { PlatformHeader } from '@/components/trading/platform-header';
import { useTradingStore } from '@/lib/trading/signal-store';
import { useSignalWebSocket } from '@/lib/trading/use-signal-websocket';
import type { Signal, PerformanceData } from '@/lib/trading/types';
import {
  LayoutDashboard,
  BarChart3,
  Clock,
  Zap,
  Activity,
} from 'lucide-react';

// ─── Per-Card Error Boundary ──────────────────────────────────────
// React render errors can ONLY be caught by class-based Error Boundaries.
// try/catch around JSX does NOT work — the error propagates through the
// React reconciler and crashes the entire page.

interface CardErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class CardErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  CardErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode; fallback?: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): CardErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[CardErrorBoundary] Signal card render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="border border-red-400/30 bg-red-400/5 rounded-lg p-4 text-center">
          <p className="text-xs text-red-400">Signal render error — data may be incomplete</p>
          <button
            className="text-[10px] text-zinc-500 hover:text-white mt-1 underline"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Home() {
  // Client-side hydration guard — prevents SSR/client mismatch
  const [isClient, setIsClient] = useState(false);

  const {
    signals,
    isConnected,
    platform,
    performance,
    setPlatform,
    setPerformance,
    addSignal,
  } = useTradingStore();

  const { requestSignal, submitFeedback, backendAvailable } = useSignalWebSocket();
  const [activeTab, setActiveTab] = useState('signals');
  const [isGenerating, setIsGenerating] = useState(false);

  // Mark as client-rendered after mount
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Fetch initial signals
  useEffect(() => {
    if (!isClient) return;
    fetchSignals();
  }, [platform, isClient]);

  // Auto-refresh analytics
  useEffect(() => {
    if (!isClient) return;
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, 15000);
    return () => clearInterval(interval);
  }, [isClient]);

  const fetchSignals = useCallback(async () => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const res = await fetch(`/api/v1/signals/live/${platform}?XTransformPort=3000`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) {
        const data = await res.json();
        if (data.signals && data.signals.length > 0) {
          // Don't overwrite real-time signals if we already have them
        }
      }
    } catch {
      // Silently fail — network/proxy errors are non-fatal
    }
  }, [platform]);

  const fetchAnalytics = useCallback(async () => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const res = await fetch('/api/v1/analytics/performance?XTransformPort=3000', {
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) {
        const data = await res.json();
        setPerformance({
          winRate: data.winRate ?? 0,
          totalTrades: data.totalTrades ?? 0,
          wins: data.wins ?? 0,
          losses: data.losses ?? 0,
          bestPair: data.bestPair ?? 'EURUSD-OTC',
          dailyPnl: data.dailyPnl ?? 0,
          confidenceAccuracy: data.confidenceAccuracy ?? { accuracy: 0, total: 0, wins: 0, losses: 0 },
        });
      }
    } catch {
      // Silently fail — network/proxy errors are non-fatal
    }
  }, [setPerformance]);

  const generateSignals = useCallback(async () => {
    setIsGenerating(true);
    try {
      // Try Python backend first
      const PYTHON_BACKEND_HTTP = process.env.NEXT_PUBLIC_PYTHON_BACKEND_HTTP || 'http://localhost:8000';
      let signalsFromBackend = false;

      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(`${PYTHON_BACKEND_HTTP}/api/signals/${platform}`, {
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (res.ok) {
          const data = await res.json();
          if (data.signals && Array.isArray(data.signals) && data.signals.length > 0) {
            for (const signal of data.signals) {
              try {
                addSignal(signal);
              } catch (e) {
                console.error('[Home] Failed to add backend signal:', e);
              }
            }
            signalsFromBackend = true;
          }
        }
      } catch {
        // Python backend not available — fall through to internal generation
      }

      // Fallback: Use internal Next.js signal generator
      if (!signalsFromBackend) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        const res = await fetch('/api/v1/signals/generate?XTransformPort=3000', {
          method: 'POST',
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (res.ok) {
          const data = await res.json();
          if (data.signals && Array.isArray(data.signals)) {
            for (const signal of data.signals) {
              try {
                addSignal(signal);
              } catch (e) {
                console.error('[Home] Failed to add signal:', e);
              }
            }
          }
        }
      }
    } catch {
      // Silently fail — network/proxy errors are non-fatal
    } finally {
      setIsGenerating(false);
    }
  }, [addSignal, platform]);

  const handleFeedback = useCallback(
    async (signalId: string, outcome: 'win' | 'loss') => {
      submitFeedback(signalId, outcome);
      try {
        await fetch('/api/v1/signals/evaluate?XTransformPort=3000', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ signalId, outcome }),
        });
      } catch {
        // Silently fail
      }
    },
    [submitFeedback]
  );

  const handlePlatformChange = useCallback(
    (newPlatform: 'iq-option' | 'pocket-option') => {
      setPlatform(newPlatform);
    },
    [setPlatform]
  );

  const handleRefresh = useCallback(() => {
    if (!isClient) return;
    fetchSignals();
    fetchAnalytics();
    requestSignal();
  }, [fetchSignals, fetchAnalytics, requestSignal, isClient]);

  // SSR: render a lightweight placeholder to avoid hydration mismatch
  // Client: render the full interactive dashboard
  if (!isClient) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="relative inline-block">
            <Activity className="h-10 w-10 text-zinc-700 animate-pulse" />
          </div>
          <p className="text-xs text-zinc-600">Loading CATALYST AI...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-zinc-800/50 bg-zinc-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <PlatformHeader
            platform={platform}
            isConnected={isConnected}
            signalCount={signals.length}
            onPlatformChange={handlePlatformChange}
            onRefresh={handleRefresh}
          />
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Navigation Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="bg-zinc-900/60 border border-zinc-800">
            <TabsTrigger
              value="signals"
              className="text-xs data-[state=active]:bg-emerald-400/10 data-[state=active]:text-emerald-400"
            >
              <LayoutDashboard className="h-3.5 w-3.5 mr-1.5" />
              Live Signals
            </TabsTrigger>
            <TabsTrigger
              value="analytics"
              className="text-xs data-[state=active]:bg-emerald-400/10 data-[state=active]:text-emerald-400"
            >
              <BarChart3 className="h-3.5 w-3.5 mr-1.5" />
              Analytics
            </TabsTrigger>
            <TabsTrigger
              value="history"
              className="text-xs data-[state=active]:bg-emerald-400/10 data-[state=active]:text-emerald-400"
            >
              <Clock className="h-3.5 w-3.5 mr-1.5" />
              History
            </TabsTrigger>
          </TabsList>

          {/* Live Signals Tab */}
          <TabsContent value="signals" className="space-y-4">
            {/* Quick Stats Bar */}
            <div className="flex items-center gap-3 overflow-x-auto pb-1">
              <div className="flex items-center gap-2 bg-zinc-900/60 rounded-lg px-3 py-1.5 border border-zinc-800">
                <Activity className="h-3 w-3 text-emerald-400" />
                <span className="text-[10px] text-zinc-500">Active</span>
                <span className="text-xs font-bold text-emerald-400">{signals.length}</span>
              </div>
              <div className="flex items-center gap-2 bg-zinc-900/60 rounded-lg px-3 py-1.5 border border-zinc-800">
                <Zap className="h-3 w-3 text-yellow-400" />
                <span className="text-[10px] text-zinc-500">Platform</span>
                <span className="text-xs font-bold text-white">
                  {platform === 'iq-option' ? 'IQ Option' : 'Pocket Option'}
                </span>
              </div>
              <Button
                size="sm"
                className="h-7 text-xs bg-emerald-400/10 text-emerald-400 hover:bg-emerald-400/20 border border-emerald-400/20"
                onClick={generateSignals}
                disabled={isGenerating}
              >
                <Zap className="h-3 w-3 mr-1" />
                {isGenerating ? 'Generating...' : 'Generate Signal'}
              </Button>
            </div>

            {/* Signal Grid */}
            {signals.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 space-y-4">
                <div className="relative">
                  <Activity className="h-12 w-12 text-zinc-700" />
                  <div className="absolute -top-1 -right-1 h-3 w-3 bg-emerald-400/50 rounded-full animate-pulse" />
                </div>
                <div className="text-center space-y-1">
                  <h3 className="text-sm font-medium text-zinc-400">Waiting for Signals</h3>
                  <p className="text-xs text-zinc-600 max-w-sm">
                    The AI engine is analyzing market data across 27 trading pairs.
                    Signals meeting the 94.3% quality threshold will appear here in real-time.
                  </p>
                </div>
                <Button
                  size="sm"
                  className="bg-emerald-400/10 text-emerald-400 hover:bg-emerald-400/20 border border-emerald-400/20"
                  onClick={generateSignals}
                  disabled={isGenerating}
                >
                  <Zap className="h-3.5 w-3.5 mr-1.5" />
                  Generate Demo Signal
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {signals.map((signal, index) => (
                  <div key={signal.id || `sig-${index}`} className="signal-enter" style={{ animationDelay: `${index * 50}ms` }}>
                    <CardErrorBoundary
                      fallback={
                        <div className="border border-yellow-500/30 bg-zinc-900/80 rounded-lg p-4">
                          <p className="text-xs text-yellow-400">Signal data incomplete — refreshing...</p>
                          <p className="text-[10px] text-zinc-600 mt-1">{signal.tradePair || 'Unknown'} • {signal.direction || 'N/A'}</p>
                        </div>
                      }
                    >
                      <SignalCard signal={signal} onFeedback={handleFeedback} />
                    </CardErrorBoundary>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Analytics Tab */}
          <TabsContent value="analytics" className="space-y-4">
            <AnalyticsPanel performance={performance} signalCount={signals.length} />
          </TabsContent>

          {/* History Tab */}
          <TabsContent value="history" className="space-y-4">
            <SignalHistory signals={signals} />
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800/50 bg-zinc-950/50 mt-8">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 bg-emerald-400 rounded-full pulse-glow" />
              <span className="text-[10px] text-zinc-600">
                CATALYST AI v1.0 • Smart Money • AI-Powered
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-zinc-600">
                {TRADING_PAIRS_COUNT} pairs • {TIMEFRAMES_COUNT} timeframes
              </span>
              <Badge variant="outline" className="text-[9px] h-4 border-zinc-800 text-zinc-600">
                94.3% Filter Active
              </Badge>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

const TRADING_PAIRS_COUNT = 27;
const TIMEFRAMES_COUNT = 6;
