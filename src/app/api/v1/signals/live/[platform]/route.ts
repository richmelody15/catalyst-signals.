// GET /api/v1/signals/live/[platform] - Get live signals for platform
import { NextResponse } from 'next/server';
import { signalGenerator, ensureInitialized } from '@/lib/trading/engine-singleton';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ platform: string }> }
) {
  try {
    ensureInitialized();

    const { platform } = await params;

    if (!['iq-option', 'pocket-option'].includes(platform)) {
      return NextResponse.json(
        { error: 'Invalid platform. Use "iq-option" or "pocket-option"', signals: [] },
        { status: 400 }
      );
    }

    const signals = signalGenerator.getRecentSignals(20);

    // Safely serialize — replace NaN/Infinity, convert Date to ISO string
    const safeSignals = signals.map((s) => {
      try {
        const raw = JSON.parse(JSON.stringify(s, (key, value) => {
          if (typeof value === 'number' && (!isFinite(value) || isNaN(value))) return null;
          return value;
        }));
        raw.entryTime = s.entryTime instanceof Date
          ? s.entryTime.toISOString()
          : new Date(s.entryTime || Date.now()).toISOString();
        return raw;
      } catch {
        return null;
      }
    }).filter(Boolean);

    return NextResponse.json({
      platform,
      signals: safeSignals,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Get live signals error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch signals', signals: [] },
      { status: 500 }
    );
  }
}
