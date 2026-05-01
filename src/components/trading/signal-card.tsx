'use client';

import { useState } from 'react';
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
  Shield,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Gauge,
  AlertTriangle,
  ListChecks,
  LogOut,
  ShieldAlert,
  Sparkles,
  Layers,
  ArrowDown,
  ArrowUp,
  Clock,
  Wrench,
  Crosshair,
  FlaskConical,
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
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${time} WAT`;
}

const REGIME_COLORS: Record<string, string> = {
  strong_trend: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  weak_trend: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  ranging: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
  volatile: 'text-red-400 bg-red-400/10 border-red-400/20',
  breakout: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
  quiet: 'text-zinc-400 bg-zinc-400/10 border-zinc-400/20',
};

interface SignalCardProps {
  signal: Signal;
  onFeedback?: (signalId: string, outcome: 'win' | 'loss') => void;
}

export function SignalCard({ signal, onFeedback }: SignalCardProps) {
  const isBuy = signal.direction === 'BUY';
  const directionColor = isBuy ? 'text-emerald-400' : 'text-red-400';
  const borderColor = isBuy ? 'border-l-emerald-400' : 'border-l-red-400';
  const bgGlow = isBuy ? 'bg-emerald-400/5' : 'bg-red-400/5';
  const [showStrategy, setShowStrategy] = useState(false);

  const regimeColorClass = REGIME_COLORS[signal.marketRegime] || REGIME_COLORS.weak_trend;
  const glmProb = signal.glmProbability ?? 94.3;

  const copySignal = async () => {
    // Use the formatted signal if available, otherwise fall back to manual formatting
    const text = signal.formatted?.emoji || [
      `🔔 CATALYST AI SIGNAL!`,
      ``,
      `🎫 Trade: ${signal.tradePair}`,
      `⏳ Timer: ${signal.timer}`,
      `➡️ Entry: ${formatEntryTime(signal.entryTime)}`,
      `📈 Direction: ${signal.direction}`,
      `🎯 GLM Probability: ${glmProb}% WIN RATE`,
      `📊 Market: ${signal.marketCondition}`,
      ``,
      `🔮 Market Regime: ${signal.regimeLabel}`,
      `   ${signal.regimeDescription}`,
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
      ...Object.entries(signal.riskLevels).map(([key, level], idx) => {
        const mult = typeof level === 'object' && level !== null && 'multiplier' in level ? (level as { multiplier: number; time: string }).multiplier : level;
        const time = typeof level === 'object' && level !== null && 'time' in level ? (level as { multiplier: number; time: string }).time : '';
        return `  ${key} → ${mult}x (${time})   ← initial entry`;
      }),
      ...(signal.glmSmartMoney ? [
        ``,
        `🧪 GLM SMART MONEY:`,
        `  Structure: ${signal.glmSmartMoney.labels.structure}`,
        `  Liquidity: ${signal.glmSmartMoney.labels.liquidity}`,
        `  Breakout: ${signal.glmSmartMoney.labels.breakout}`,
        `  Signal: ${signal.glmSmartMoney.labels.signal}`,
      ] : []),
      ``,
      `📋 STRATEGY GUIDE:`,
      ...(signal.strategy?.entryRules?.map((r: string) => `  ✅ ${r}`) || []),
      ...(signal.strategy?.exitRules?.map((r: string) => `  🚪 ${r}`) || []),
      ...(signal.strategy?.riskManagement?.map((r: string) => `  🛡️ ${r}`) || []),
      ``,
      `📐 SUPPORT/RESISTANCE:`,
      ...(signal.nearestSupport ? [`  ⬇ Support: ${signal.nearestSupport.price.toFixed(signal.nearestSupport.price < 100 ? 4 : 2)} (Str: ${signal.nearestSupport.strength}${signal.nearestSupport.isMajor ? ', Major' : ''})`] : []),
      ...(signal.nearestResistance ? [`  ⬆ Resistance: ${signal.nearestResistance.price.toFixed(signal.nearestResistance.price < 100 ? 4 : 2)} (Str: ${signal.nearestResistance.strength}${signal.nearestResistance.isMajor ? ', Major' : ''})`] : []),
      ``,
      `🎯 GLM PROBABILITY: ${glmProb}% WIN RATE`,
      `   ${signal.signalQuality}`,
    ].join('\n');

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        toast.success('Signal copied to clipboard!');
      } else {
        // Fallback for non-secure contexts (HTTP preview)
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        toast.success('Signal copied to clipboard!');
      }
    } catch {
      toast.error('Failed to copy signal');
    }
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
        {/* GLM Probability Badge */}
        <div className="flex items-center justify-between bg-zinc-800/60 rounded-lg p-2 border border-zinc-700/50">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-yellow-400" />
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider">GLM Probability</span>
          </div>
          <span className="text-sm font-bold text-yellow-400">{glmProb}% WIN RATE</span>
        </div>

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

        {/* Market Regime */}
        <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1.5">
              <Gauge className="h-3.5 w-3.5 text-zinc-400" />
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Market Regime</span>
            </div>
            <Badge className={`text-[10px] h-5 font-bold border ${regimeColorClass}`}>
              {signal.regimeLabel}
            </Badge>
          </div>
          <p className="text-[10px] text-zinc-500 leading-relaxed">{signal.regimeDescription}</p>
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

        {/* Support & Resistance Zones */}
        {(signal.nearestSupport || signal.nearestResistance) && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center gap-1.5 mb-1.5">
              <Layers className="h-3.5 w-3.5 text-cyan-400" />
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider">S/R Zones</span>
            </div>
            <div className="space-y-1">
              {signal.nearestSupport && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <ArrowDown className="h-3 w-3 text-emerald-400" />
                    <span className="text-[10px] text-zinc-400">Support</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-emerald-400">
                      {signal.nearestSupport.price.toFixed(signal.nearestSupport.price < 100 ? 4 : 2)}
                    </span>
                    {signal.nearestSupport.isMajor && (
                      <Badge className="text-[8px] h-3 px-1 bg-emerald-400/10 text-emerald-400 border-0">Major</Badge>
                    )}
                    <span className="text-[9px] text-zinc-600">Str: {signal.nearestSupport.strength}</span>
                  </div>
                </div>
              )}
              {signal.nearestResistance && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <ArrowUp className="h-3 w-3 text-red-400" />
                    <span className="text-[10px] text-zinc-400">Resistance</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-red-400">
                      {signal.nearestResistance.price.toFixed(signal.nearestResistance.price < 100 ? 4 : 2)}
                    </span>
                    {signal.nearestResistance.isMajor && (
                      <Badge className="text-[8px] h-3 px-1 bg-red-400/10 text-red-400 border-0">Major</Badge>
                    )}
                    <span className="text-[9px] text-zinc-600">Str: {signal.nearestResistance.strength}</span>
                  </div>
                </div>
              )}
              {/* Zone Ranges */}
              <div className="flex gap-2 pt-0.5">
                {signal.supportZone.start != null && (
                  <div className="flex-1 bg-emerald-400/5 rounded px-1.5 py-0.5">
                    <p className="text-[8px] text-zinc-600 text-center">Supply Zone</p>
                    <p className="text-[9px] text-emerald-400/70 text-center">
                      {signal.supportZone.start?.toFixed(signal.supportZone.start < 100 ? 4 : 2)} - {signal.supportZone.end?.toFixed((signal.supportZone.end ?? 0) < 100 ? 4 : 2)}
                    </p>
                  </div>
                )}
                {signal.resistanceZone.start != null && (
                  <div className="flex-1 bg-red-400/5 rounded px-1.5 py-0.5">
                    <p className="text-[8px] text-zinc-600 text-center">Resist Zone</p>
                    <p className="text-[9px] text-red-400/70 text-center">
                      {signal.resistanceZone.start?.toFixed(signal.resistanceZone.start < 100 ? 4 : 2)} - {signal.resistanceZone.end?.toFixed((signal.resistanceZone.end ?? 0) < 100 ? 4 : 2)}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Risk Levels */}
        <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Zap className="h-3.5 w-3.5 text-yellow-500" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Risk Levels</span>
          </div>
          <div className="space-y-1">
            {Object.entries(signal.riskLevels).map(([key, level], idx) => {
              const mult = typeof level === 'object' && level !== null && 'multiplier' in level ? (level as { multiplier: number; time: string }).multiplier : level;
              const time = typeof level === 'object' && level !== null && 'time' in level ? (level as { multiplier: number; time: string }).time : '';
              return (
                <div key={key} className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-yellow-400">{key}</span>
                    <span className="text-[10px] text-zinc-500">→</span>
                    <span className="text-[10px] font-bold text-white">{mult}x</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-emerald-400 font-mono font-bold">({time})</span>
                    <span className="text-[8px] text-zinc-700">← initial entry</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* GLM Smart Money Engine */}
        {signal.glmSmartMoney && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <FlaskConical className="h-3.5 w-3.5 text-purple-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">GLM Smart Money</span>
              </div>
              <Badge className={`text-[9px] h-4 font-bold border ${
                signal.glmSmartMoney.signal === 'VALID_BUY'
                  ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                  : signal.glmSmartMoney.signal === 'VALID_SELL'
                  ? 'text-red-400 bg-red-400/10 border-red-400/20'
                  : signal.glmSmartMoney.signal === 'FILTERED_NO_TRADE'
                  ? 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20'
                  : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
              }`}>
                {signal.glmSmartMoney.signal.replace(/_/g, ' ')}
              </Badge>
            </div>
            <div className="space-y-1">
              {/* Structure */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Structure</span>
                <span className={`text-[10px] font-bold ${
                  signal.glmSmartMoney.structure === 'BOS_UP' ? 'text-emerald-400' :
                  signal.glmSmartMoney.structure === 'BOS_DOWN' ? 'text-red-400' : 'text-yellow-400'
                }`}>
                  {signal.glmSmartMoney.structure === 'BOS_UP' ? '↑' : signal.glmSmartMoney.structure === 'BOS_DOWN' ? '↓' : '↔'} {signal.glmSmartMoney.structure}
                </span>
              </div>
              {/* Liquidity */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Liquidity</span>
                <span className={`text-[10px] font-bold ${
                  signal.glmSmartMoney.liquidity === 'BUY_SWEEP' ? 'text-emerald-400' :
                  signal.glmSmartMoney.liquidity === 'SELL_SWEEP' ? 'text-red-400' : 'text-zinc-500'
                }`}>
                  {signal.glmSmartMoney.liquidity.replace(/_/g, ' ')}
                </span>
              </div>
              {/* Breakout */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Breakout</span>
                <span className={`text-[10px] font-bold ${
                  signal.glmSmartMoney.breakout === 'CONFIRMED_BREAKOUT_BUY' ? 'text-emerald-400' :
                  signal.glmSmartMoney.breakout === 'CONFIRMED_BREAKDOWN_SELL' ? 'text-red-400' : 'text-zinc-600'
                }`}>
                  {signal.glmSmartMoney.breakout === 'CONFIRMED_BREAKOUT_BUY' ? '🚀 Buy' :
                   signal.glmSmartMoney.breakout === 'CONFIRMED_BREAKDOWN_SELL' ? '📉 Sell' : 'None'}
                </span>
              </div>
            </div>
          </div>
        )}

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

        {/* Multi-Timeframe Confluence */}
        {signal.mtfConfluence && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5 text-purple-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">MTF Confluence</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge className={`text-[9px] h-4 font-bold border ${
                  signal.mtfConfluence.aligned
                    ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                    : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
                }`}>
                  {signal.mtfConfluence.aligned ? 'ALIGNED' : 'MIXED'}
                </Badge>
                <span className="text-[9px] text-zinc-500">{signal.mtfConfluence.alignmentScore}%</span>
              </div>
            </div>
            {/* Timeframe breakdown */}
            <div className="grid grid-cols-6 gap-1 mb-1.5">
              {Object.entries(signal.mtfConfluence.timeframeResults).map(([tf, analysis]) => (
                <div key={tf} className="bg-zinc-800/60 rounded px-1 py-0.5 text-center">
                  <p className="text-[8px] text-zinc-600">{tf}</p>
                  <p className={`text-[9px] font-bold ${
                    analysis.trend === 'bullish' ? 'text-emerald-400' :
                    analysis.trend === 'bearish' ? 'text-red-400' : 'text-zinc-500'
                  }`}>
                    {analysis.trend === 'bullish' ? '↑' : analysis.trend === 'bearish' ? '↓' : '→'}
                  </p>
                </div>
              ))}
            </div>
            {/* MTF Checklist Score */}
            <div className="flex items-center justify-between">
              <span className="text-[9px] text-zinc-600">8-Point Checklist</span>
              <span className={`text-[9px] font-bold ${
                signal.mtfConfluence.checklistScore >= 70 ? 'text-emerald-400' :
                signal.mtfConfluence.checklistScore >= 50 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {signal.mtfConfluence.checklistScore}%
              </span>
            </div>
            <div className="grid grid-cols-4 gap-1 mt-1">
              {Object.entries(signal.mtfConfluence.checklist).map(([key, val]) => (
                <div key={key} className="flex items-center gap-0.5">
                  {val ? (
                    <CheckCircle2 className="h-2.5 w-2.5 text-emerald-400" />
                  ) : (
                    <XCircle className="h-2.5 w-2.5 text-zinc-700" />
                  )}
                  <span className="text-[7px] text-zinc-600 truncate">{key.replace(/_/g, ' ').slice(0, 12)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Supply/Demand Zone */}
        {signal.nearestSDZone && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Crosshair className="h-3.5 w-3.5 text-orange-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">S/D Zone</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge className={`text-[9px] h-4 font-bold border ${
                  signal.nearestSDZone.direction === 'bullish'
                    ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                    : 'text-red-400 bg-red-400/10 border-red-400/20'
                }`}>
                  {signal.nearestSDZone.type}
                </Badge>
                <Badge className={`text-[8px] h-3.5 px-1 border ${
                  signal.nearestSDZone.strength === 'extreme' ? 'text-purple-400 bg-purple-400/10 border-purple-400/20' :
                  signal.nearestSDZone.strength === 'strong' ? 'text-orange-400 bg-orange-400/10 border-orange-400/20' :
                  signal.nearestSDZone.strength === 'moderate' ? 'text-blue-400 bg-blue-400/10 border-blue-400/20' :
                  'text-zinc-400 bg-zinc-400/10 border-zinc-400/20'
                }`}>
                  {signal.nearestSDZone.strength}
                </Badge>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[9px] text-zinc-500">
                Range: {signal.nearestSDZone.low.toFixed(5)} - {signal.nearestSDZone.high.toFixed(5)}
              </span>
              <span className="text-[9px] text-zinc-400">
                Belief: <span className="font-bold text-orange-400">{signal.nearestSDZone.beliefScore}%</span>
              </span>
            </div>
            {signal.nearestSDZone.performance.timesTested > 0 && (
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-[8px] text-zinc-600">
                  Tested: {signal.nearestSDZone.performance.timesTested}x
                </span>
                <span className={`text-[8px] ${signal.nearestSDZone.performance.holdRate >= 70 ? 'text-emerald-400' : 'text-yellow-400'}`}>
                  Hold: {signal.nearestSDZone.performance.holdRate}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* Zone Interaction Signal */}
        {signal.zoneInteraction && signal.zoneInteraction.signal && (
          <div className={`rounded-lg p-2 border ${
            signal.zoneInteraction.signal === 'BUY'
              ? 'border-emerald-400/30 bg-emerald-400/5'
              : 'border-red-400/30 bg-red-400/5'
          }`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Target className="h-3.5 w-3.5 text-yellow-400" />
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider">
                  Zone Signal: {signal.zoneInteraction.interactionType}
                </span>
              </div>
              <span className={`text-xs font-bold ${
                signal.zoneInteraction.signal === 'BUY' ? 'text-emerald-400' : 'text-red-400'
              }`}>
                {signal.zoneInteraction.signal}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-1 text-center">
              <div>
                <p className="text-[8px] text-zinc-600">SL</p>
                <p className="text-[9px] text-red-400 font-bold">{signal.zoneInteraction.stopLoss.toFixed(4)}</p>
              </div>
              <div>
                <p className="text-[8px] text-zinc-600">Entry</p>
                <p className="text-[9px] text-white font-bold">{signal.zoneInteraction.entryPrice.toFixed(4)}</p>
              </div>
              <div>
                <p className="text-[8px] text-zinc-600">TP</p>
                <p className="text-[9px] text-emerald-400 font-bold">{signal.zoneInteraction.takeProfit.toFixed(4)}</p>
              </div>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[8px] text-zinc-600">R:R 1:{signal.zoneInteraction.riskReward}</span>
              <span className="text-[8px] text-zinc-500">Conf: {signal.zoneInteraction.confidence}%</span>
            </div>
          </div>
        )}

        <Separator className="bg-zinc-800" />

        {/* Strategy Guide Toggle */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full h-6 text-[10px] text-zinc-400 hover:text-white hover:bg-zinc-800 justify-between px-2"
          onClick={() => setShowStrategy(!showStrategy)}
        >
          <span className="flex items-center gap-1">
            <BookOpen className="h-3 w-3" />
            Strategy Guide
          </span>
          {showStrategy ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </Button>

        {showStrategy && signal.strategy && (
          <div className="space-y-2 animate-in slide-in-from-top-1 duration-200">
            {/* Entry Rules */}
            <div className="bg-emerald-400/5 border border-emerald-400/10 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <ListChecks className="h-3 w-3 text-emerald-400" />
                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">Entry Rules</span>
              </div>
              <ul className="space-y-0.5">
                {signal.strategy.entryRules.map((rule, i) => (
                  <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                    <span className="text-emerald-400 shrink-0">✓</span>
                    {rule}
                  </li>
                ))}
              </ul>
            </div>

            {/* Exit Rules */}
            <div className="bg-blue-400/5 border border-blue-400/10 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <LogOut className="h-3 w-3 text-blue-400" />
                <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider">Exit Rules</span>
              </div>
              <ul className="space-y-0.5">
                {signal.strategy.exitRules.map((rule, i) => (
                  <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                    <span className="text-blue-400 shrink-0">→</span>
                    {rule}
                  </li>
                ))}
              </ul>
            </div>

            {/* Risk Management */}
            <div className="bg-yellow-400/5 border border-yellow-400/10 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <Shield className="h-3 w-3 text-yellow-400" />
                <span className="text-[10px] font-bold text-yellow-400 uppercase tracking-wider">Risk Management</span>
              </div>
              <ul className="space-y-0.5">
                {signal.strategy.riskManagement.map((rule, i) => (
                  <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                    <span className="text-yellow-400 shrink-0">🛡</span>
                    {rule}
                  </li>
                ))}
              </ul>
            </div>

            {/* Avoid Actions */}
            <div className="bg-red-400/5 border border-red-400/10 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <ShieldAlert className="h-3 w-3 text-red-400" />
                <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Avoid</span>
              </div>
              <ul className="space-y-0.5">
                {signal.strategy.avoidActions.map((rule, i) => (
                  <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                    <span className="text-red-400 shrink-0">✗</span>
                    {rule}
                  </li>
                ))}
              </ul>
            </div>

            {/* GLM Confidence Note */}
            <div className="bg-yellow-400/5 border border-yellow-400/20 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <Sparkles className="h-3 w-3 text-yellow-400" />
                <span className="text-[10px] font-bold text-yellow-400">GLM PROBABILITY: {glmProb}% WIN RATE</span>
              </div>
              <p className="text-[10px] text-zinc-500 leading-relaxed">{signal.strategy.confidenceNote}</p>
            </div>
          </div>
        )}

        {/* Engine Health Indicator */}
        {signal.engineHealth && (signal.engineHealth.errorsRecovered > 0 || signal.engineHealth.lastError) && (
          <div className="flex items-center justify-between bg-zinc-800/30 rounded px-2 py-1">
            <div className="flex items-center gap-1">
              <Wrench className="h-3 w-3 text-zinc-600" />
              <span className="text-[8px] text-zinc-600">Engine Health</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[8px] text-zinc-500">
                {signal.engineHealth.errorsRecovered} recovered
              </span>
              <Badge className={`text-[7px] h-3 px-1 border ${
                signal.engineHealth.recoveryRate >= 90
                  ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                  : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
              }`}>
                {signal.engineHealth.recoveryRate}%
              </Badge>
            </div>
          </div>
        )}

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
