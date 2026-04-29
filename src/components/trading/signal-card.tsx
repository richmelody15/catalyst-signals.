'use client';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
  Copy,
  Share2,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  Activity,
  BarChart3,
  Zap,
  Droplets,
  Volume2,
  Target,
} from 'lucide-react';
import type { Signal } from '@/lib/trading/types';
import { toast } from 'sonner';

function CheckItem({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {value ? (
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
      ) : (
        <XCircle className="h-3.5 w-3.5 text-zinc-600" />
      )}
      <span className={value ? 'text-zinc-300' : 'text-zinc-600'}>{label}</span>
    </div>
  );
}

function formatEntryTime(entryTime: Date | string) {
  const date = new Date(entryTime);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface SignalCardProps {
  signal: Signal;
  onFeedback?: (signalId: string, outcome: 'win' | 'loss') => void;
}

export function SignalCard({ signal, onFeedback }: SignalCardProps) {
  const isBuy = signal.direction === 'BUY';
  const directionColor = isBuy ? 'text-emerald-400' : 'text-red-400';
  const borderColor = isBuy ? 'border-l-emerald-400' : 'border-l-red-400';
  const bgGlow = isBuy ? 'bg-emerald-400/5' : 'bg-red-400/5';

  const copySignal = () => {
    const text = [
      `🔔 NEW SIGNAL!`,
      ``,
      `🎫 Trade: ${signal.tradePair}`,
      `⏳ Timer: ${signal.timer}`,
      `➡️ Entry: ${formatEntryTime(signal.entryTime)}`,
      `📈 Direction: ${signal.direction}`,
      `🎯 AI Confidence: ${signal.confidence}%`,
      `📊 Market: ${signal.marketCondition}`,
      ``,
      `🧠 Trend: ${signal.trend}`,
      `📉 BOS: ${signal.bosConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `🔄 CHoCH: ${signal.chochConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `📦 FVG: ${signal.fvgActive ? 'Active' : 'Not Active'}`,
      `💧 Liquidity: ${signal.liquiditySweep ? 'Sweep Detected' : 'None'}`,
      `📦 Volume: ${signal.volumeHigh ? 'High' : 'Normal'}`,
      `🏗️ Zone: ${signal.zoneType}`,
      `📉 RSI: ${signal.rsiValue}`,
      `📊 Stochastic: ${signal.stochasticBull ? 'Bullish Crossover' : 'Neutral'}`,
      `📊 BB Width: ${signal.bbExpanding ? 'Expanding' : 'Contracting'}`,
      `⚖️ RR: 1:${signal.riskReward}`,
      ``,
      `↪️ Risk Levels:`,
      ...Object.entries(signal.riskLevels).map(([key, value]) => `  ${key} → ${value}x`),
      ``,
      `🎯 SIGNAL STATUS: ${signal.signalQuality}`,
    ].join('\n');

    navigator.clipboard.writeText(text).then(() => {
      toast.success('Signal copied to clipboard!');
    });
  };

  return (
    <Card className={`border-l-4 ${borderColor} ${bgGlow} bg-zinc-900/80 backdrop-blur-sm hover:bg-zinc-900 transition-all duration-300 group`}>
      <CardHeader className="pb-3 pt-4 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`p-1.5 rounded-lg ${isBuy ? 'bg-emerald-400/10' : 'bg-red-400/10'}`}>
              {isBuy ? (
                <TrendingUp className={`h-4 w-4 ${directionColor}`} />
              ) : (
                <TrendingDown className={`h-4 w-4 ${directionColor}`} />
              )}
            </div>
            <div>
              <h3 className="font-bold text-white text-sm">{signal.tradePair}</h3>
              <p className="text-[10px] text-zinc-500">{formatEntryTime(signal.entryTime)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400 h-5">
              {signal.timer}
            </Badge>
            <Badge
              className={`text-xs font-bold ${
                isBuy
                  ? 'bg-emerald-400/20 text-emerald-400 hover:bg-emerald-400/30 border-0'
                  : 'bg-red-400/20 text-red-400 hover:bg-red-400/30 border-0'
              }`}
            >
              {signal.direction}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-3">
        {/* Confidence Bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">AI Confidence</span>
            <span className={`text-xs font-bold ${signal.confidence > 90 ? 'text-emerald-400' : signal.confidence > 85 ? 'text-yellow-400' : 'text-red-400'}`}>
              {signal.confidence}%
            </span>
          </div>
          <Progress
            value={signal.confidence}
            className="h-2 bg-zinc-800"
          />
          <p className="text-[10px] text-zinc-600">
            {signal.signalQuality} • Score: {signal.checklistScore}%
          </p>
        </div>

        <Separator className="bg-zinc-800" />

        {/* Technical Indicators Grid */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          <CheckItem label="BOS" value={signal.bosConfirmed} />
          <CheckItem label="CHoCH" value={signal.chochConfirmed} />
          <CheckItem label="FVG" value={signal.fvgActive} />
          <CheckItem label="Liquidity" value={signal.liquiditySweep} />
          <CheckItem label="Volume" value={signal.volumeHigh} />
          <CheckItem label="BB Expand" value={signal.bbExpanding} />
        </div>

        <Separator className="bg-zinc-800" />

        {/* Market Details */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <Activity className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">RSI</p>
            <p className="text-xs font-bold text-white">{signal.rsiValue}</p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <BarChart3 className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">Trend</p>
            <p className={`text-xs font-bold ${isBuy ? 'text-emerald-400' : 'text-red-400'}`}>
              {signal.trend}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <Target className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">R:R</p>
            <p className="text-xs font-bold text-white">1:{signal.riskReward}</p>
          </div>
        </div>

        {/* Risk Levels */}
        <div className="flex items-center gap-1">
          <Zap className="h-3 w-3 text-yellow-500" />
          <span className="text-[10px] text-zinc-500 mr-1">Risk:</span>
          {Object.entries(signal.riskLevels).map(([key, value]) => (
            <Badge key={key} variant="outline" className="text-[9px] h-4 border-zinc-700 text-zinc-400 px-1.5">
              {key}: {value}x
            </Badge>
          ))}
        </div>

        {/* Zone & Market Condition */}
        <div className="flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1">
            <Droplets className="h-3 w-3 text-blue-400" />
            <span className="text-zinc-400">{signal.zoneType}</span>
          </div>
          <div className="flex items-center gap-1">
            <Volume2 className="h-3 w-3 text-zinc-500" />
            <span className="text-zinc-500">{signal.marketCondition}</span>
          </div>
        </div>

        <Separator className="bg-zinc-800" />

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 h-7 text-xs border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            onClick={copySignal}
          >
            <Copy className="h-3 w-3 mr-1" />
            Copy Signal
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            onClick={() => {
              toast.info('Share feature coming soon!');
            }}
          >
            <Share2 className="h-3 w-3" />
          </Button>
        </div>

        {/* Feedback */}
        {onFeedback && (
          <div className="flex gap-2">
            <Button
              size="sm"
              className="flex-1 h-6 text-[10px] bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border-0"
              onClick={() => onFeedback(signal.id, 'win')}
            >
              <CheckCircle2 className="h-3 w-3 mr-1" /> Win
            </Button>
            <Button
              size="sm"
              className="flex-1 h-6 text-[10px] bg-red-500/20 text-red-400 hover:bg-red-500/30 border-0"
              onClick={() => onFeedback(signal.id, 'loss')}
            >
              <XCircle className="h-3 w-3 mr-1" /> Loss
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
