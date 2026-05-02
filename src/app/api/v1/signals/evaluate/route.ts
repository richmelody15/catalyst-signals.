// POST /api/v1/signals/evaluate - Submit signal outcome for learning
// Tries Python backend first, falls back to local engine
import { NextResponse } from 'next/server';
import { learningEngine } from '@/lib/trading/engine-singleton';

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || 'http://127.0.0.1:8000';

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

    // Try to record in Python backend
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      await fetch(`${PYTHON_BACKEND_URL}/api/v1/signals/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signalId, outcome }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
    } catch {
      // Python backend unavailable, still record locally
    }

    // Also record in local learning engine
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
