// GET /api/v1/pairs/available - Get available trading pairs and timeframes
import { NextResponse } from 'next/server';
import { TRADING_PAIRS, TIMEFRAMES } from '@/lib/trading/types';

export async function GET() {
  return NextResponse.json({
    pairs: TRADING_PAIRS,
    timeframes: TIMEFRAMES,
    totalPairs: TRADING_PAIRS.length,
    totalTimeframes: TIMEFRAMES.length,
  });
}
