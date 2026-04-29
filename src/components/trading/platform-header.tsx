'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Wifi,
  WifiOff,
  RefreshCw,
  Bell,
  Signal,
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
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Signal className="h-7 w-7 text-emerald-400" />
            <div className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 bg-emerald-400 rounded-full animate-pulse" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              CATALYST AI
            </h1>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest">
              Smart Money • AI-Powered • 94.3% Filter
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Connection Status */}
        <div className="flex items-center gap-1.5">
          {isConnected ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-red-400" />
          )}
          <span className={`text-[10px] ${isConnected ? 'text-emerald-400' : 'text-red-400'}`}>
            {isConnected ? 'Live' : 'Offline'}
          </span>
        </div>

        {/* Signal Count */}
        <Badge variant="outline" className="text-[10px] h-5 border-zinc-700 text-zinc-400">
          <Bell className="h-2.5 w-2.5 mr-1" />
          {signalCount}
        </Badge>

        {/* Platform Tabs */}
        <Tabs value={platform} onValueChange={(v) => onPlatformChange(v as 'iq-option' | 'pocket-option')}>
          <TabsList className="h-7 bg-zinc-800/80 border border-zinc-700">
            <TabsTrigger
              value="iq-option"
              className="text-[10px] h-5 px-2 data-[state=active]:bg-emerald-400/20 data-[state=active]:text-emerald-400"
            >
              IQ Option
            </TabsTrigger>
            <TabsTrigger
              value="pocket-option"
              className="text-[10px] h-5 px-2 data-[state=active]:bg-emerald-400/20 data-[state=active]:text-emerald-400"
            >
              Pocket Option
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Refresh Button */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-[10px] border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-white"
          onClick={onRefresh}
        >
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>
    </div>
  );
}
