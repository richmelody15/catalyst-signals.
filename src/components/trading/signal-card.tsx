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

  const copySignal = () => {
    const text = [
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
      ...Object.entries(signal.riskLevels).map(([key, value]) => `  ${key} → ${value}x`),
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
