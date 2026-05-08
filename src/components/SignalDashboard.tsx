'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ExternalLink,
  RefreshCw,
  Radio,
  Wifi,
  WifiOff,
  Zap,
  Shield,
  Clock,
  ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

// Dashboard URL - configurable via environment variable
const DASHBOARD_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_URL ||
  'https://catalyst-signals.up.railway.app';

// Local fallback URL - served by Next.js API route
const LOCAL_DASHBOARD_URL = '/dashboard';

export default function SignalDashboard() {
  const [iframeUrl, setIframeUrl] = useState(DASHBOARD_URL);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [useLocal, setUseLocal] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(true);
  const [retryCount, setRetryCount] = useState(0);

  // Try to detect if Railway is reachable
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(DASHBOARD_URL, {
          method: 'HEAD',
          mode: 'no-cors',
          signal: controller.signal,
        });
        clearTimeout(timeout);
        // If we get here, the server responded (even with opaque response)
        setIframeUrl(DASHBOARD_URL);
        setUseLocal(false);
      } catch {
        // Railway not reachable, try local
        try {
          const controller2 = new AbortController();
          const timeout2 = setTimeout(() => controller2.abort(), 3000);
          const localRes = await fetch(LOCAL_DASHBOARD_URL, {
            method: 'HEAD',
            signal: controller2.signal,
          });
          clearTimeout(timeout2);
          if (localRes.ok) {
            setIframeUrl(LOCAL_DASHBOARD_URL);
            setUseLocal(true);
          }
        } catch {
          // Neither available
          setIframeUrl(DASHBOARD_URL);
        }
      }
    };

    checkConnection();
  }, [retryCount]);

  const handleIframeLoad = useCallback(() => {
    setIsLoading(false);
    setHasError(false);
  }, []);

  const handleIframeError = useCallback(() => {
    setIsLoading(false);
    setHasError(true);
  }, []);

  const handleRetry = useCallback(() => {
    setIsLoading(true);
    setHasError(false);
    setRetryCount((prev) => prev + 1);
    // Force iframe reload
    const iframe = document.querySelector(
      'iframe'
    ) as HTMLIFrameElement | null;
    if (iframe) {
      iframe.src = iframe.src;
    }
  }, []);

  const handleSwitchSource = useCallback(() => {
    if (useLocal) {
      setIframeUrl(DASHBOARD_URL);
      setUseLocal(false);
    } else {
      setIframeUrl(LOCAL_DASHBOARD_URL);
      setUseLocal(true);
    }
    setIsLoading(true);
    setHasError(false);
  }, [useLocal]);

  const handleOpenExternal = useCallback(() => {
    window.open(iframeUrl, '_blank');
  }, [iframeUrl]);

  return (
    <div className="flex flex-col h-screen bg-[#050510]">
      {/* Top Bar */}
      <header className="flex-shrink-0 border-b border-zinc-800/60 bg-[#0a0a2e]/80 backdrop-blur-xl">
        <div className="flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 bg-emerald-400 rounded-full animate-pulse" />
              <span className="text-sm font-bold tracking-wide text-white">
                CATALYST<span className="text-emerald-400">FINAL</span>
              </span>
              <span className="text-[10px] text-zinc-500 font-mono">
                v3.3
              </span>
            </div>
            <Badge
              variant="outline"
              className={`text-[9px] h-5 ${
                useLocal
                  ? 'bg-cyan-400/10 text-cyan-400 border-cyan-400/20'
                  : 'bg-emerald-400/10 text-emerald-400 border-emerald-400/20'
              }`}
            >
              {useLocal ? (
                <>
                  <Wifi className="h-2.5 w-2.5 mr-1" />
                  Local
                </>
              ) : (
                <>
                  <Radio className="h-2.5 w-2.5 mr-1" />
                  Railway Live
                </>
              )}
            </Badge>
            {isLoading && (
              <Badge
                variant="outline"
                className="text-[9px] h-5 bg-yellow-400/10 text-yellow-400 border-yellow-400/20"
              >
                <RefreshCw className="h-2.5 w-2.5 mr-1 animate-spin" />
                Connecting...
              </Badge>
            )}
            {!isLoading && !hasError && (
              <Badge
                variant="outline"
                className="text-[9px] h-5 bg-emerald-400/10 text-emerald-400 border-emerald-400/20"
              >
                <Shield className="h-2.5 w-2.5 mr-1" />
                Connected
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-[10px] text-zinc-400 hover:text-white hover:bg-zinc-800"
              onClick={handleSwitchSource}
            >
              {useLocal ? (
                <>
                  <Radio className="h-3 w-3 mr-1" />
                  Switch to Railway
                </>
              ) : (
                <>
                  <Wifi className="h-3 w-3 mr-1" />
                  Switch to Local
                </>
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-[10px] text-zinc-400 hover:text-white hover:bg-zinc-800"
              onClick={handleOpenExternal}
            >
              <ExternalLink className="h-3 w-3 mr-1" />
              Open in Tab
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-[10px] text-zinc-400 hover:text-white hover:bg-zinc-800"
              onClick={handleRetry}
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </header>

      {/* Iframe Container */}
      <div className="flex-1 relative">
        {/* Loading Overlay */}
        {isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#050510]">
            <div className="text-center space-y-4">
              <div className="relative inline-block">
                <div className="w-16 h-16 rounded-full bg-zinc-900/60 border border-zinc-800 flex items-center justify-center">
                  <Activity className="h-7 w-7 text-emerald-400 animate-pulse" />
                </div>
                <div className="absolute -top-1 -right-1 h-3 w-3 bg-emerald-400/50 rounded-full animate-ping" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-medium text-zinc-300">
                  Connecting to CATALYST AI
                </h3>
                <p className="text-[10px] text-zinc-600">
                  {useLocal
                    ? 'Loading from local server...'
                    : 'Loading from Railway deployment...'}
                </p>
              </div>
              <div className="flex items-center justify-center gap-1">
                <div
                  className="h-1 w-1 bg-emerald-400 rounded-full animate-bounce"
                  style={{ animationDelay: '0ms' }}
                />
                <div
                  className="h-1 w-1 bg-emerald-400 rounded-full animate-bounce"
                  style={{ animationDelay: '150ms' }}
                />
                <div
                  className="h-1 w-1 bg-emerald-400 rounded-full animate-bounce"
                  style={{ animationDelay: '300ms' }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Error Overlay */}
        {hasError && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#050510]">
            <div className="text-center space-y-4 max-w-md px-6">
              <div className="w-16 h-16 rounded-full bg-red-900/20 border border-red-800/40 flex items-center justify-center mx-auto">
                <WifiOff className="h-7 w-7 text-red-400" />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-zinc-300">
                  Dashboard Unavailable
                </h3>
                <p className="text-xs text-zinc-500">
                  The CATALYST AI dashboard is not reachable. Make sure the
                  server is deployed to Railway or running locally.
                </p>
              </div>
              <div className="space-y-2">
                <Button
                  size="sm"
                  className="generate-gradient text-black font-bold rounded-full px-6"
                  onClick={handleRetry}
                >
                  <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                  Retry Connection
                </Button>
                <div className="flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-[10px] border-zinc-700 text-zinc-400"
                    onClick={handleSwitchSource}
                  >
                    {useLocal
                      ? 'Try Railway Instead'
                      : 'Try Local Server'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-[10px] border-zinc-700 text-zinc-400"
                    onClick={handleOpenExternal}
                  >
                    <ExternalLink className="h-3 w-3 mr-1" />
                    Open Direct
                  </Button>
                </div>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-3 text-left">
                <p className="text-[10px] text-zinc-500 font-mono mb-1">
                  Deployment URL:
                </p>
                <p className="text-[10px] text-cyan-400 font-mono break-all">
                  {DASHBOARD_URL}
                </p>
                <p className="text-[10px] text-zinc-500 font-mono mt-1 mb-1">
                  Local Fallback:
                </p>
                <p className="text-[10px] text-cyan-400 font-mono break-all">
                  {LOCAL_DASHBOARD_URL}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* The actual iframe */}
        <iframe
          src={iframeUrl}
          onLoad={handleIframeLoad}
          onError={handleIframeError}
          className="w-full h-full border-0"
          title="CATALYST AI Signals"
          allow="clipboard-write"
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-downloads allow-modals"
        />
      </div>

      {/* Footer */}
      <footer className="flex-shrink-0 border-t border-zinc-800/40 bg-[#0a0a2e]/60">
        <div className="flex items-center justify-between px-4 py-1.5">
          <div className="flex items-center gap-2">
            <div className="h-1 w-1 bg-emerald-400 rounded-full animate-pulse" />
            <span className="text-[9px] text-zinc-600">
              CATALYST AI v3.3 - Smart Money - AI-Powered
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[9px] text-zinc-600">
              8 pairs &middot; 6 timeframes &middot; 94.3% Filter
            </span>
            <span className="text-[9px] text-zinc-700 font-mono">
              <Clock className="h-2.5 w-2.5 inline mr-0.5" />
              {new Date().toLocaleTimeString('en-GB', {
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'Africa/Lagos',
              })}{' '}
              WAT
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
