'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Wifi,
  WifiOff,
  RefreshCw,
  Rocket,
  Activity,
} from 'lucide-react';

interface PlatformHeaderProps {
  platform: 'iq-option' | 'pocket-option';
  isConnected: boolean;
  signalCount: number;
  onPlatformChange: (platform: 'iq-option' | 'pocket-option') => void;
  onRefresh: () => void;
}

export function PlatformHeader({
  platform,
  isConnected,
  signalCount,
  onPlatformChange,
  onRefresh,
}: PlatformHeaderProps) {
  return (
    <div className="flex flex-col gap-4">
      {/* Top Row: Logo + Status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Logo Icon */}
          <div className="relative">
            <div className="generate-gradient rounded-xl p-2">
              <Rocket className="h-5 w-5 text-black" />
            </div>
            {isConnected && (
              <div className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 bg-emerald-400 rounded-full animate-pulse" />
            )}
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              CATALYST<span className="text-emerald-400">AI</span>
            </h1>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest">
              Smart Money &middot; AI-Powered &middot; 94.3% Filter
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Signal Count */}
          <div className="flex items-center gap-1.5 bg-zinc-900/60 rounded-lg px-3 py-1.5 border border-zinc-800">
            <Activity className="h-3 w-3 text-emerald-400" />
            <span className="text-[10px] text-zinc-500">Active</span>
            <span className="text-xs font-bold text-emerald-400">{signalCount}</span>
          </div>

          {/* Connection Status Badge */}
          {isConnected ? (
            <div className="status-online rounded-full px-3 py-1 flex items-center gap-1.5">
              <Wifi className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-[10px] font-medium text-emerald-400">Online</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 bg-red-400/5 border border-red-400/20 rounded-full px-3 py-1">
              <WifiOff className="h-3.5 w-3.5 text-red-400" />
              <span className="text-[10px] font-medium text-red-400">Offline</span>
            </div>
          )}
        </div>
      </div>

      {/* Platform Selector Row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {/* IQ Option Button */}
          <button
            onClick={() => onPlatformChange('iq-option')}
            className={`px-5 py-2 rounded-full text-sm font-semibold transition-all duration-300 border ${
              platform === 'iq-option'
                ? 'platform-active border-emerald-400/50'
                : 'bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:bg-zinc-800/60 hover:text-zinc-300'
            }`}
          >
            🎯 IQ Option
          </button>

          {/* Pocket Option Button */}
          <button
            onClick={() => onPlatformChange('pocket-option')}
            className={`px-5 py-2 rounded-full text-sm font-semibold transition-all duration-300 border ${
              platform === 'pocket-option'
                ? 'platform-active border-emerald-400/50'
                : 'bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:bg-zinc-800/60 hover:text-zinc-300'
            }`}
          >
            💼 Pocket Option
          </button>

          {/* Platform Label */}
          <div className="ml-2 flex items-center gap-1.5">
            <span className="text-[10px] text-zinc-600">Platform:</span>
            <span className="text-xs font-bold text-emerald-400">
              {platform === 'iq-option' ? 'IQ Option' : 'Pocket Option'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh Button */}
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-white rounded-full px-4"
            onClick={onRefresh}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Refresh
          </Button>
        </div>
      </div>
    </div>
  );
}
