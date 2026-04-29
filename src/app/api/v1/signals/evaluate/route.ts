// POST /api/v1/signals/evaluate - Submit signal outcome for learning
import { NextResponse } from 'next/server';
import { learningEngine } from '@/lib/trading/engine-singleton';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { signalId, outcome, direction, confidence, pair } = body;

    if (!signalId || !outcome) {
      return NextResponse.json(
        { error: 'Missing signalId or outcome' },
        { status: 400 }
      );
    }

    if (!['win', 'loss'].includes(outcome)) {
      return NextResponse.json(
        { error: 'Invalid outcome. Use "win" or "loss"' },
        { status: 400 }
      );
    }

    await learningEngine.processOutcome(
      signalId,
      outcome,
      direction || 'BUY',
      confidence || 85,
      pair || 'EURUSD-OTC'
    );

    return NextResponse.json({
      status: 'success',
      message: 'Feedback recorded',
      accuracy: learningEngine.getConfidenceAccuracy(),
    });
  } catch (error) {
    console.error('Evaluate signal error:', error);
    return NextResponse.json(
      { error: 'Failed to evaluate signal' },
      { status: 500 }
    );
  }
}
