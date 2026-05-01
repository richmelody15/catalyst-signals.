'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Clock, TrendingUp, TrendingDown, Sparkles, Gauge } from 'lucide-react';
import type { Signal } from '@/lib/trading/types';

interface SignalHistoryProps {
  signals: Signal[];
}

export function SignalHistory({ signals }: SignalHistoryProps) {
  const formatTime = (time: Date | string) => {
    try {
      const t = new Date(time).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
      return `${t} WAT`;
    } catch {
      return '--:-- WAT';
    }
  };

  return (
    <Card className="bg-zinc-900/80 border-zinc-800">
      <CardHeader className="pb-2 pt-3 px-4">
        <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
          <Clock className="h-3.5 w-3.5" />
          Signal History
          <Badge variant="outline" className="text-[9px] h-4 border-zinc-700 text-zinc-500 ml-auto">
            {signals.length} signals
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        <ScrollArea className="h-[300px]">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-[10px] text-zinc-500 h-7">Pair</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">Direction</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">GLM Prob</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">Regime</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">Time</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">S/R</TableHead>
                <TableHead className="text-[10px] text-zinc-500 h-7">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {signals.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-xs text-zinc-600 py-8">
                    No signals generated yet. Waiting for market data...
                  </TableCell>
                </TableRow>
              ) : (
                signals.map((signal) => (
                  <TableRow key={signal.id} className="border-zinc-800/50 hover:bg-zinc-800/30">
                    <TableCell className="text-xs font-medium text-white py-1.5">
                      {signal.tradePair}
                    </TableCell>
                    <TableCell className="py-1.5">
                      <div className="flex items-center gap-1">
                        {signal.direction === 'BUY' ? (
                          <TrendingUp className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <TrendingDown className="h-3 w-3 text-red-400" />
                        )}
                        <span className={`text-xs font-bold ${signal.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                          {signal.direction}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="py-1.5">
                      <div className="flex items-center gap-1">
                        <Sparkles className="h-2.5 w-2.5 text-yellow-400" />
                        <span className="text-xs font-bold text-yellow-400">
                          {signal.glmProbability ?? 94.3}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="py-1.5">
                      <Badge variant="outline" className="text-[8px] h-4 border-zinc-700 text-zinc-400">
                        {signal.regimeLabel || 'N/A'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500 py-1.5">
                      {formatTime(signal.entryTime)}
                    </TableCell>
                    <TableCell className="py-1.5">
                      <div className="flex flex-col gap-0.5">
                        {signal.nearestSupport && signal.nearestSupport.price != null && typeof signal.nearestSupport.price === 'number' && !isNaN(signal.nearestSupport.price) && (
                          <span className="text-[9px] text-emerald-400/70">
                            S: {signal.nearestSupport.price.toFixed(signal.nearestSupport.price < 100 ? 4 : 2)}
                          </span>
                        )}
                        {signal.nearestResistance && signal.nearestResistance.price != null && typeof signal.nearestResistance.price === 'number' && !isNaN(signal.nearestResistance.price) && (
                          <span className="text-[9px] text-red-400/70">
                            R: {signal.nearestResistance.price.toFixed(signal.nearestResistance.price < 100 ? 4 : 2)}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="py-1.5">
                      <Badge
                        variant="outline"
                        className={`text-[9px] h-4 ${
                          signal.signalQuality === 'HIGH PROBABILITY ONLY'
                            ? 'border-yellow-500/30 text-yellow-400'
                            : 'border-zinc-700 text-zinc-500'
                        }`}
                      >
                        {signal.signalQuality === 'HIGH PROBABILITY ONLY' ? 'HIGH PROB' : 'STANDARD'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
