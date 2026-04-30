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
        { error: 'Invalid platform. Use "iq-option" or "pocket-option"' },
        { status: 400 }
      );
    }

    const signals = signalGenerator.getRecentSignals(20);

    return NextResponse.json({
      platform,
      signals: signals.map((s) => ({
        ...s,
        entryTime: s.entryTime.toISOString(),
      })),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Get live signals error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch signals' },
      { status: 500 }
    );
  }
}
