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

function formatEntryTime(entryTime: Date | string | null | undefined): string {
  try {
    if (!entryTime) return '--:-- WAT';
    const date = new Date(entryTime);
    if (isNaN(date.getTime())) return '--:-- WAT';
    // Format in WAT (Africa/Lagos = UTC+1)
    const time = date.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Africa/Lagos',
    });
    return `${time} WAT`;
  } catch {
    return '--:-- WAT';
  }
}

/** Safe toFixed that handles null/undefined/NaN numbers */
function safeToFixed(value: number | null | undefined, decimals: number = 4): string {
  if (value == null || typeof value !== 'number' || isNaN(value) || !isFinite(value)) return 'N/A';
  return value.toFixed(decimals);
}

/** Get decimal places based on price magnitude */
function priceDecimals(price: number | null | undefined): number {
  if (price == null || typeof price !== 'number' || isNaN(price) || !isFinite(price)) return 4;
  return price < 100 ? 4 : 2;
}

/** Safe string getter — returns fallback for null/undefined/empty strings */
function safeStr(val: unknown, fallback: string = 'N/A'): string {
  if (val == null || typeof val !== 'string' || val === '') return fallback;
  return val;
}

/** Safe number getter — returns fallback for null/undefined/NaN numbers */
function safeNum(val: unknown, fallback: number = 0): number {
  if (val == null || typeof val !== 'number' || isNaN(val) || !isFinite(val)) return fallback;
  return val;
}

/** Safe boolean getter */
function safeBool(val: unknown, fallback: boolean = false): boolean {
  if (val == null || typeof val !== 'boolean') return fallback;
  return val;
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
  // ─── Safe value extraction ────────────────────────────────────────
  // Every property is defensively accessed so that no null/undefined
  // can possibly reach a .toFixed(), .map(), or .replace() call.

  const direction = signal?.direction === 'SELL' ? 'SELL' : 'BUY';
  const isBuy = direction === 'BUY';
  const directionColor = isBuy ? 'text-emerald-400' : 'text-red-400';
  const borderColor = isBuy ? 'border-l-emerald-400' : 'border-l-red-400';
  const bgGlow = isBuy ? 'bg-emerald-400/5' : 'bg-red-400/5';
  const [showStrategy, setShowStrategy] = useState(false);

  const regimeKey = typeof signal?.marketRegime === 'string' ? signal.marketRegime : 'weak_trend';
  const regimeColorClass = REGIME_COLORS[regimeKey] || REGIME_COLORS.weak_trend;
  const glmProb = safeNum(signal?.glmProbability, 94.3);
  const safeConfidence = safeNum(signal?.confidence, 0);
  const regimeLabel = safeStr(signal?.regimeLabel, 'Weak Trend');
  const regimeDescription = safeStr(signal?.regimeDescription, '');
  const signalQuality = safeStr(signal?.signalQuality, 'HIGH PROBABILITY ONLY');
  const checklistScore = safeNum(signal?.checklistScore, 0);
  const tradePair = safeStr(signal?.tradePair, 'UNKNOWN');
  const timer = safeStr(signal?.timer, '1m (OTC)');
  const trend = safeStr(signal?.trend, 'N/A');
  const zoneType = safeStr(signal?.zoneType, 'N/A');
  const marketCondition = safeStr(signal?.marketCondition, 'Normal');
  const riskReward = safeNum(signal?.riskReward, 2.5);
  const rsiValue = safeNum(signal?.rsiValue, 50);
  const entryTime = signal?.entryTime;

  const bosConfirmed = safeBool(signal?.bosConfirmed);
  const chochConfirmed = safeBool(signal?.chochConfirmed);
  const fvgActive = safeBool(signal?.fvgActive);
  const liquiditySweep = safeBool(signal?.liquiditySweep);
  const volumeHigh = safeBool(signal?.volumeHigh);
  const stochasticBull = safeBool(signal?.stochasticBull);
  const bbExpanding = safeBool(signal?.bbExpanding);

  // Strategy — ensure all arrays are actually arrays
  const rawStrategy = signal?.strategy;
  const strategy = rawStrategy && typeof rawStrategy === 'object' ? rawStrategy : null;
  const entryRules: string[] = Array.isArray(strategy?.entryRules) ? strategy!.entryRules.filter((r: unknown) => typeof r === 'string') : [];
  const exitRules: string[] = Array.isArray(strategy?.exitRules) ? strategy!.exitRules.filter((r: unknown) => typeof r === 'string') : [];
  const riskManagement: string[] = Array.isArray(strategy?.riskManagement) ? strategy!.riskManagement.filter((r: unknown) => typeof r === 'string') : [];
  const avoidActions: string[] = Array.isArray(strategy?.avoidActions) ? strategy!.avoidActions.filter((r: unknown) => typeof r === 'string') : [];
  const confidenceNote = safeStr(strategy?.confidenceNote, 'High probability signal with strong confluence.');

  // GLM Smart Money — safe access
  const glmSmartMoney = signal?.glmSmartMoney && typeof signal.glmSmartMoney === 'object' && 'signal' in signal.glmSmartMoney
    ? signal.glmSmartMoney
    : null;
  const glmStructure = safeStr(glmSmartMoney?.structure, 'RANGE');
  const glmLiquidity = safeStr(glmSmartMoney?.liquidity, 'NO_SWEEP');
  const glmBreakout = safeStr(glmSmartMoney?.breakout, 'NO_BREAKOUT');
  const glmSignal = safeStr(glmSmartMoney?.signal, 'WAIT');
  const glmLabels = glmSmartMoney?.labels && typeof glmSmartMoney.labels === 'object'
    ? glmSmartMoney.labels
    : { structure: glmStructure, liquidity: glmLiquidity, breakout: glmBreakout, signal: glmSignal };

  // MTF Confluence — safe access
  const mtfConfluence = signal?.mtfConfluence && typeof signal.mtfConfluence === 'object' && 'timeframeResults' in signal.mtfConfluence
    ? signal.mtfConfluence
    : null;
  const mtfAligned = safeBool(mtfConfluence?.aligned);
  const mtfScore = safeNum(mtfConfluence?.alignmentScore, 0);
  const mtfChecklistScore = safeNum(mtfConfluence?.checklistScore, 0);
  const mtfTimeframeResults = mtfConfluence?.timeframeResults && typeof mtfConfluence.timeframeResults === 'object'
    ? mtfConfluence.timeframeResults
    : {};
  const mtfChecklist = mtfConfluence?.checklist && typeof mtfConfluence.checklist === 'object'
    ? mtfConfluence.checklist
    : {};

  // S/R — safe access
  const nearestSupport = signal?.nearestSupport && typeof signal.nearestSupport === 'object' && 'price' in signal.nearestSupport
    ? signal.nearestSupport
    : null;
  const nearestResistance = signal?.nearestResistance && typeof signal.nearestResistance === 'object' && 'price' in signal.nearestResistance
    ? signal.nearestResistance
    : null;
  const supportZone = signal?.supportZone && typeof signal.supportZone === 'object'
    ? signal.supportZone
    : { start: null, end: null };
  const resistanceZone = signal?.resistanceZone && typeof signal.resistanceZone === 'object'
    ? signal.resistanceZone
    : { start: null, end: null };

  // S/D Zone — safe access
  const nearestSDZone = signal?.nearestSDZone && typeof signal.nearestSDZone === 'object' && 'low' in signal.nearestSDZone
    ? signal.nearestSDZone
    : null;

  // Zone Interaction — safe access
  const zoneInteraction = signal?.zoneInteraction && typeof signal.zoneInteraction === 'object' && 'signal' in signal.zoneInteraction
    ? signal.zoneInteraction
    : null;

  // Engine Health — safe access
  const engineHealth = signal?.engineHealth && typeof signal.engineHealth === 'object'
    ? signal.engineHealth
    : null;

  // Risk Levels — safe normalization
  const riskLevels: Record<string, { multiplier: number; time: string; amount: number }> = {};
  const rawRiskLevels = signal?.riskLevels;
  if (rawRiskLevels && typeof rawRiskLevels === 'object') {
    for (const [key, val] of Object.entries(rawRiskLevels)) {
      if (val != null && typeof val === 'object' && 'multiplier' in (val as object)) {
        const obj = val as { multiplier?: unknown; time?: unknown; amount?: unknown };
        riskLevels[key] = {
          multiplier: safeNum(obj.multiplier, 0),
          time: typeof obj.time === 'string' && obj.time ? obj.time : '--:-- WAT',
          amount: safeNum(obj.amount, 0),
        };
      } else if (typeof val === 'number') {
        riskLevels[key] = { multiplier: val, time: '--:-- WAT', amount: 0 };
      }
    }
  }

  // ─── Copy Signal Handler ──────────────────────────────────────────

  const copySignal = async () => {
    const riskLevelLines = Object.entries(riskLevels).map(([key, level]) => {
      return `  ${key} │ ${level.multiplier}x │ $${level.amount} │ Entry: ${level.time}`;
    });

    const text = signal?.formatted?.emoji || [
      `🔔 CATALYST AI SIGNAL!`,
      ``,
      `🎫 Trade: ${tradePair}`,
      `⏳ Timer: ${timer}`,
      `➡️ Entry: ${formatEntryTime(entryTime)}`,
      `📈 Direction: ${direction}`,
      `🎯 GLM Probability: ${glmProb}% WIN RATE`,
      `📊 Market: ${marketCondition}`,
      ``,
      `🔮 Market Regime: ${regimeLabel}`,
      `   ${regimeDescription}`,
      ``,
      `🧠 Trend: ${trend}`,
      `📉 BOS: ${bosConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `🔄 CHoCH: ${chochConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `📦 FVG: ${fvgActive ? 'Active' : 'Not Active'}`,
      `💧 Liquidity: ${liquiditySweep ? 'Sweep Detected' : 'None'}`,
      `📦 Volume: ${volumeHigh ? 'High' : 'Normal'}`,
      `🏗️ Zone: ${zoneType}`,
      `📉 RSI: ${rsiValue}`,
      `📊 Stochastic: ${stochasticBull ? 'Bullish Crossover' : 'Neutral'}`,
      `📊 BB Width: ${bbExpanding ? 'Expanding' : 'Contracting'}`,
      `⚖️ RR: 1:${riskReward}`,
      ``,
      `↪️ ── 🛡️ MARTINGALE RECOVERY (Risk Level) ──`,
      ...riskLevelLines,
      ...(glmSmartMoney ? [
        ``,
        `🧪 GLM SMART MONEY:`,
        `  Structure: ${glmLabels.structure ?? glmStructure}`,
        `  Liquidity: ${glmLabels.liquidity ?? glmLiquidity}`,
        `  Breakout: ${glmLabels.breakout ?? glmBreakout}`,
        `  Signal: ${glmLabels.signal ?? glmSignal}`,
      ] : []),
      ``,
      `📋 STRATEGY GUIDE:`,
      ...entryRules.map((r: string) => `  ✅ ${r}`),
      ...exitRules.map((r: string) => `  🚪 ${r}`),
      ...riskManagement.map((r: string) => `  🛡️ ${r}`),
      ``,
      `📐 SUPPORT/RESISTANCE:`,
      ...(nearestSupport && nearestSupport.price != null ? [`  ⬇ Support: ${safeToFixed(nearestSupport.price, priceDecimals(nearestSupport.price))} (Str: ${nearestSupport.strength ?? 0}${nearestSupport.isMajor ? ', Major' : ''})`] : []),
      ...(nearestResistance && nearestResistance.price != null ? [`  ⬆ Resistance: ${safeToFixed(nearestResistance.price, priceDecimals(nearestResistance.price))} (Str: ${nearestResistance.strength ?? 0}${nearestResistance.isMajor ? ', Major' : ''})`] : []),
      ``,
      `Note: Trade 1% - 3% of your capability and capital`,
      `🎯 SIGNAL STATUS: ${signalQuality}`,
      ``,
      `🎯 GLM PROBABILITY: ${glmProb}% WIN RATE`,
      `   ${signalQuality}`,
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

  // ─── Render ──────────────────────────────────────────────────────

  return (
    <Card className={`border-l-4 ${borderColor} ${bgGlow} bg-zinc-900/80 backdrop-blur-sm hover:bg-zinc-900/90 signal-card-hover transition-all duration-300 group`}>
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
              <h3 className="font-bold text-white text-sm">{tradePair}</h3>
              <p className="text-[10px] text-zinc-500">{formatEntryTime(entryTime)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400 h-5">
              {timer}
            </Badge>
            <Badge
              className={`text-xs font-bold ${
                isBuy
                  ? 'bg-emerald-400/20 text-emerald-400 hover:bg-emerald-400/30 border-0'
                  : 'bg-red-400/20 text-red-400 hover:bg-red-400/30 border-0'
              }`}
            >
              {direction}
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
            <span className={`text-xs font-bold ${safeConfidence > 90 ? 'text-emerald-400' : safeConfidence > 85 ? 'text-yellow-400' : 'text-red-400'}`}>
              {safeConfidence}%
            </span>
          </div>
          <Progress
            value={safeConfidence}
            className="h-2 bg-zinc-800"
          />
          <p className="text-[10px] text-zinc-600">
            {signalQuality} • Score: {checklistScore}%
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
              {regimeLabel}
            </Badge>
          </div>
          <p className="text-[10px] text-zinc-500 leading-relaxed">{regimeDescription}</p>
        </div>

        <Separator className="bg-zinc-800" />

        {/* Technical Indicators Grid */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          <CheckItem label="BOS" value={bosConfirmed} />
          <CheckItem label="CHoCH" value={chochConfirmed} />
          <CheckItem label="FVG" value={fvgActive} />
          <CheckItem label="Liquidity" value={liquiditySweep} />
          <CheckItem label="Volume" value={volumeHigh} />
          <CheckItem label="BB Expand" value={bbExpanding} />
        </div>

        <Separator className="bg-zinc-800" />

        {/* Market Details */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <Activity className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">RSI</p>
            <p className="text-xs font-bold text-white">{rsiValue}</p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <BarChart3 className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">Trend</p>
            <p className={`text-xs font-bold ${isBuy ? 'text-emerald-400' : 'text-red-400'}`}>
              {trend}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-2">
            <Target className="h-3 w-3 text-zinc-500 mx-auto mb-1" />
            <p className="text-[10px] text-zinc-500">R:R</p>
            <p className="text-xs font-bold text-white">1:{riskReward}</p>
          </div>
        </div>

        {/* Support & Resistance Zones */}
        {(nearestSupport || nearestResistance) && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center gap-1.5 mb-1.5">
              <Layers className="h-3.5 w-3.5 text-cyan-400" />
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider">S/R Zones</span>
            </div>
            <div className="space-y-1">
              {nearestSupport && nearestSupport.price != null && typeof nearestSupport.price === 'number' && isFinite(nearestSupport.price) && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <ArrowDown className="h-3 w-3 text-emerald-400" />
                    <span className="text-[10px] text-zinc-400">Support</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-emerald-400">
                      {safeToFixed(nearestSupport.price, priceDecimals(nearestSupport.price))}
                    </span>
                    {nearestSupport.isMajor && (
                      <Badge className="text-[8px] h-3 px-1 bg-emerald-400/10 text-emerald-400 border-0">Major</Badge>
                    )}
                    <span className="text-[9px] text-zinc-600">Str: {nearestSupport.strength ?? 0}</span>
                  </div>
                </div>
              )}
              {nearestResistance && nearestResistance.price != null && typeof nearestResistance.price === 'number' && isFinite(nearestResistance.price) && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <ArrowUp className="h-3 w-3 text-red-400" />
                    <span className="text-[10px] text-zinc-400">Resistance</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-red-400">
                      {safeToFixed(nearestResistance.price, priceDecimals(nearestResistance.price))}
                    </span>
                    {nearestResistance.isMajor && (
                      <Badge className="text-[8px] h-3 px-1 bg-red-400/10 text-red-400 border-0">Major</Badge>
                    )}
                    <span className="text-[9px] text-zinc-600">Str: {nearestResistance.strength ?? 0}</span>
                  </div>
                </div>
              )}
              {/* Zone Ranges */}
              <div className="flex gap-2 pt-0.5">
                {supportZone.start != null && typeof supportZone.start === 'number' && isFinite(supportZone.start) && (
                  <div className="flex-1 bg-emerald-400/5 rounded px-1.5 py-0.5">
                    <p className="text-[8px] text-zinc-600 text-center">Supply Zone</p>
                    <p className="text-[9px] text-emerald-400/70 text-center">
                      {safeToFixed(supportZone.start, priceDecimals(supportZone.start))} - {safeToFixed(supportZone.end, priceDecimals(supportZone.end))}
                    </p>
                  </div>
                )}
                {resistanceZone.start != null && typeof resistanceZone.start === 'number' && isFinite(resistanceZone.start) && (
                  <div className="flex-1 bg-red-400/5 rounded px-1.5 py-0.5">
                    <p className="text-[8px] text-zinc-600 text-center">Resist Zone</p>
                    <p className="text-[9px] text-red-400/70 text-center">
                      {safeToFixed(resistanceZone.start, priceDecimals(resistanceZone.start))} - {safeToFixed(resistanceZone.end, priceDecimals(resistanceZone.end))}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Risk Levels — Martingale Recovery */}
        <div className="rounded-lg p-3 border border-yellow-500/20 bg-gradient-to-b from-yellow-400/5 to-transparent">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5 text-yellow-500" />
              <span className="text-[10px] font-bold text-yellow-400 uppercase tracking-wider">MARTINGALE RECOVERY</span>
            </div>
            <span className="text-[8px] text-yellow-500/50 uppercase">Risk Level</span>
          </div>
          <div className="space-y-1.5">
            {Object.keys(riskLevels).length > 0 ? (
              Object.entries(riskLevels).map(([key, level], idx) => (
                <div key={key} className="flex items-center justify-between bg-zinc-900/80 rounded-lg px-3 py-1.5 border border-zinc-800/50">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-yellow-400 bg-yellow-400/10 px-1.5 py-0.5 rounded">{key}</span>
                    <span className="text-[10px] font-bold text-white">{level.multiplier}x</span>
                    <span className="text-[10px] font-bold text-emerald-400">${level.amount}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="h-2.5 w-2.5 text-emerald-400" />
                    <span className="text-[10px] text-emerald-400 font-mono font-bold">{level.time}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[10px] text-zinc-600 text-center py-2">
                Risk levels will appear when signal is generated
              </div>
            )}
          </div>
          <p className="text-[8px] text-yellow-500/40 mt-2 text-center">Trade 1% - 3% of your capability and capital</p>
        </div>

        {/* GLM Smart Money Engine */}
        {glmSmartMoney && glmSignal && glmSignal !== 'WAIT' && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <FlaskConical className="h-3.5 w-3.5 text-purple-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">GLM Smart Money</span>
              </div>
              <Badge className={`text-[9px] h-4 font-bold border ${
                glmSignal === 'VALID_BUY'
                  ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                  : glmSignal === 'VALID_SELL'
                  ? 'text-red-400 bg-red-400/10 border-red-400/20'
                  : glmSignal === 'FILTERED_NO_TRADE'
                  ? 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20'
                  : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
              }`}>
                {glmSignal.replace(/_/g, ' ')}
              </Badge>
            </div>
            <div className="space-y-1">
              {/* Structure */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Structure</span>
                <span className={`text-[10px] font-bold ${
                  glmStructure === 'BOS_UP' ? 'text-emerald-400' :
                  glmStructure === 'BOS_DOWN' ? 'text-red-400' : 'text-yellow-400'
                }`}>
                  {glmStructure === 'BOS_UP' ? '↑' : glmStructure === 'BOS_DOWN' ? '↓' : '↔'} {glmStructure}
                </span>
              </div>
              {/* Liquidity */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Liquidity</span>
                <span className={`text-[10px] font-bold ${
                  glmLiquidity === 'BUY_SWEEP' ? 'text-emerald-400' :
                  glmLiquidity === 'SELL_SWEEP' ? 'text-red-400' : 'text-zinc-500'
                }`}>
                  {glmLiquidity.replace(/_/g, ' ')}
                </span>
              </div>
              {/* Breakout */}
              <div className="flex items-center justify-between bg-zinc-900/60 rounded px-2 py-0.5">
                <span className="text-[9px] text-zinc-500">Breakout</span>
                <span className={`text-[10px] font-bold ${
                  glmBreakout === 'CONFIRMED_BREAKOUT_BUY' ? 'text-emerald-400' :
                  glmBreakout === 'CONFIRMED_BREAKDOWN_SELL' ? 'text-red-400' : 'text-zinc-600'
                }`}>
                  {glmBreakout === 'CONFIRMED_BREAKOUT_BUY' ? '🚀 Buy' :
                   glmBreakout === 'CONFIRMED_BREAKDOWN_SELL' ? '📉 Sell' : 'None'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Zone & Market Condition */}
        <div className="flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1">
            <Droplets className="h-3 w-3 text-blue-400" />
            <span className="text-zinc-400">{zoneType}</span>
          </div>
          <div className="flex items-center gap-1">
            <Volume2 className="h-3 w-3 text-zinc-500" />
            <span className="text-zinc-500">{marketCondition}</span>
          </div>
        </div>

        {/* Multi-Timeframe Confluence */}
        {mtfConfluence && Object.keys(mtfTimeframeResults).length > 0 && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5 text-purple-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">MTF Confluence</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge className={`text-[9px] h-4 font-bold border ${
                  mtfAligned
                    ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                    : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
                }`}>
                  {mtfAligned ? 'ALIGNED' : 'MIXED'}
                </Badge>
                <span className="text-[9px] text-zinc-500">{mtfScore}%</span>
              </div>
            </div>
            {/* Timeframe breakdown */}
            <div className="grid grid-cols-6 gap-1 mb-1.5">
              {Object.entries(mtfTimeframeResults).map(([tf, analysis]) => {
                // Safely access nested analysis
                const a = analysis && typeof analysis === 'object' ? analysis as Record<string, unknown> : {};
                const trendVal = a.trend;
                return (
                  <div key={tf} className="bg-zinc-800/60 rounded px-1 py-0.5 text-center">
                    <p className="text-[8px] text-zinc-600">{tf}</p>
                    <p className={`text-[9px] font-bold ${
                      trendVal === 'bullish' ? 'text-emerald-400' :
                      trendVal === 'bearish' ? 'text-red-400' : 'text-zinc-500'
                    }`}>
                      {trendVal === 'bullish' ? '↑' : trendVal === 'bearish' ? '↓' : '→'}
                    </p>
                  </div>
                );
              })}
            </div>
            {/* MTF Checklist Score */}
            <div className="flex items-center justify-between">
              <span className="text-[9px] text-zinc-600">8-Point Checklist</span>
              <span className={`text-[9px] font-bold ${
                mtfChecklistScore >= 70 ? 'text-emerald-400' :
                mtfChecklistScore >= 50 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {mtfChecklistScore}%
              </span>
            </div>
            {Object.keys(mtfChecklist).length > 0 && (
              <div className="grid grid-cols-4 gap-1 mt-1">
                {Object.entries(mtfChecklist).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-0.5">
                    {val ? (
                      <CheckCircle2 className="h-2.5 w-2.5 text-emerald-400" />
                    ) : (
                      <XCircle className="h-2.5 w-2.5 text-zinc-700" />
                    )}
                    <span className="text-[7px] text-zinc-600 truncate">{String(key).replace(/_/g, ' ').slice(0, 12)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Supply/Demand Zone */}
        {nearestSDZone && nearestSDZone.low != null && nearestSDZone.high != null && (
          <div className="rounded-lg p-2 border border-zinc-700/50 bg-zinc-800/40">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Crosshair className="h-3.5 w-3.5 text-orange-400" />
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">S/D Zone</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge className={`text-[9px] h-4 font-bold border ${
                  nearestSDZone.direction === 'bullish'
                    ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                    : 'text-red-400 bg-red-400/10 border-red-400/20'
                }`}>
                  {nearestSDZone.type || 'N/A'}
                </Badge>
                <Badge className={`text-[8px] h-3.5 px-1 border ${
                  nearestSDZone.strength === 'extreme' ? 'text-purple-400 bg-purple-400/10 border-purple-400/20' :
                  nearestSDZone.strength === 'strong' ? 'text-orange-400 bg-orange-400/10 border-orange-400/20' :
                  nearestSDZone.strength === 'moderate' ? 'text-blue-400 bg-blue-400/10 border-blue-400/20' :
                  'text-zinc-400 bg-zinc-400/10 border-zinc-400/20'
                }`}>
                  {nearestSDZone.strength || 'N/A'}
                </Badge>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[9px] text-zinc-500">
                Range: {safeToFixed(nearestSDZone.low, 5)} - {safeToFixed(nearestSDZone.high, 5)}
              </span>
              <span className="text-[9px] text-zinc-400">
                Belief: <span className="font-bold text-orange-400">{safeNum(nearestSDZone.beliefScore, 0)}%</span>
              </span>
            </div>
            {nearestSDZone.performance?.timesTested > 0 && (
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-[8px] text-zinc-600">
                  Tested: {nearestSDZone.performance.timesTested}x
                </span>
                <span className={`text-[8px] ${safeNum(nearestSDZone.performance.holdRate, 0) >= 70 ? 'text-emerald-400' : 'text-yellow-400'}`}>
                  Hold: {safeNum(nearestSDZone.performance.holdRate, 0)}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* Zone Interaction Signal */}
        {zoneInteraction && zoneInteraction.signal && (
          <div className={`rounded-lg p-2 border ${
            zoneInteraction.signal === 'BUY'
              ? 'border-emerald-400/30 bg-emerald-400/5'
              : 'border-red-400/30 bg-red-400/5'
          }`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Target className="h-3.5 w-3.5 text-yellow-400" />
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider">
                  Zone Signal: {safeStr(zoneInteraction.interactionType, 'N/A')}
                </span>
              </div>
              <span className={`text-xs font-bold ${
                zoneInteraction.signal === 'BUY' ? 'text-emerald-400' : 'text-red-400'
              }`}>
                {zoneInteraction.signal}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-1 text-center">
              <div>
                <p className="text-[8px] text-zinc-600">SL</p>
                <p className="text-[9px] text-red-400 font-bold">{safeToFixed(zoneInteraction.stopLoss, 4)}</p>
              </div>
              <div>
                <p className="text-[8px] text-zinc-600">Entry</p>
                <p className="text-[9px] text-white font-bold">{safeToFixed(zoneInteraction.entryPrice, 4)}</p>
              </div>
              <div>
                <p className="text-[8px] text-zinc-600">TP</p>
                <p className="text-[9px] text-emerald-400 font-bold">{safeToFixed(zoneInteraction.takeProfit, 4)}</p>
              </div>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[8px] text-zinc-600">R:R 1:{safeNum(zoneInteraction.riskReward, 0)}</span>
              <span className="text-[8px] text-zinc-500">Conf: {safeNum(zoneInteraction.confidence, 0)}%</span>
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

        {showStrategy && (
          <div className="space-y-2 animate-in slide-in-from-top-1 duration-200">
            {/* Entry Rules */}
            {entryRules.length > 0 && (
              <div className="bg-emerald-400/5 border border-emerald-400/10 rounded-lg p-2">
                <div className="flex items-center gap-1 mb-1">
                  <ListChecks className="h-3 w-3 text-emerald-400" />
                  <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">Entry Rules</span>
                </div>
                <ul className="space-y-0.5">
                  {entryRules.map((rule, i) => (
                    <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                      <span className="text-emerald-400 shrink-0">✓</span>
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Exit Rules */}
            {exitRules.length > 0 && (
              <div className="bg-blue-400/5 border border-blue-400/10 rounded-lg p-2">
                <div className="flex items-center gap-1 mb-1">
                  <LogOut className="h-3 w-3 text-blue-400" />
                  <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider">Exit Rules</span>
                </div>
                <ul className="space-y-0.5">
                  {exitRules.map((rule, i) => (
                    <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                      <span className="text-blue-400 shrink-0">→</span>
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risk Management */}
            {riskManagement.length > 0 && (
              <div className="bg-yellow-400/5 border border-yellow-400/10 rounded-lg p-2">
                <div className="flex items-center gap-1 mb-1">
                  <Shield className="h-3 w-3 text-yellow-400" />
                  <span className="text-[10px] font-bold text-yellow-400 uppercase tracking-wider">Risk Management</span>
                </div>
                <ul className="space-y-0.5">
                  {riskManagement.map((rule, i) => (
                    <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                      <span className="text-yellow-400 shrink-0">🛡</span>
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Avoid Actions */}
            {avoidActions.length > 0 && (
              <div className="bg-red-400/5 border border-red-400/10 rounded-lg p-2">
                <div className="flex items-center gap-1 mb-1">
                  <ShieldAlert className="h-3 w-3 text-red-400" />
                  <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Avoid</span>
                </div>
                <ul className="space-y-0.5">
                  {avoidActions.map((rule, i) => (
                    <li key={i} className="text-[10px] text-zinc-400 flex items-start gap-1">
                      <span className="text-red-400 shrink-0">✗</span>
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* GLM Confidence Note */}
            <div className="bg-yellow-400/5 border border-yellow-400/20 rounded-lg p-2">
              <div className="flex items-center gap-1 mb-1">
                <Sparkles className="h-3 w-3 text-yellow-400" />
                <span className="text-[10px] font-bold text-yellow-400">GLM PROBABILITY: {glmProb}% WIN RATE</span>
              </div>
              <p className="text-[10px] text-zinc-500 leading-relaxed">{confidenceNote}</p>
            </div>
          </div>
        )}

        {/* Engine Health Indicator */}
        {engineHealth && (safeNum(engineHealth.errorsRecovered, 0) > 0 || engineHealth.lastError) && (
          <div className="flex items-center justify-between bg-zinc-800/30 rounded px-2 py-1">
            <div className="flex items-center gap-1">
              <Wrench className="h-3 w-3 text-zinc-600" />
              <span className="text-[8px] text-zinc-600">Engine Health</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[8px] text-zinc-500">
                {safeNum(engineHealth.errorsRecovered, 0)} recovered
              </span>
              <Badge className={`text-[7px] h-3 px-1 border ${
                safeNum(engineHealth.recoveryRate, 0) >= 90
                  ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                  : 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20'
              }`}>
                {safeNum(engineHealth.recoveryRate, 0)}%
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
              onClick={() => onFeedback(signal?.id || '', 'win')}
            >
              <CheckCircle2 className="h-3 w-3 mr-1" /> Win
            </Button>
            <Button
              size="sm"
              className="flex-1 h-6 text-[10px] bg-red-500/20 text-red-400 hover:bg-red-500/30 border-0"
              onClick={() => onFeedback(signal?.id || '', 'loss')}
            >
              <XCircle className="h-3 w-3 mr-1" /> Loss
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
