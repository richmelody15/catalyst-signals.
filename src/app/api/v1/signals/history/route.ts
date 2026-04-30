// GET /api/v1/signals/history - Get signal history
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '100');

    const signals = await db.signal.findMany({
      take: limit,
      orderBy: { createdAt: 'desc' },
    });

    return NextResponse.json({
      signals: signals.map((s) => ({
        ...s,
        entryTime: s.entryTime.toISOString(),
        createdAt: s.createdAt.toISOString(),
        updatedAt: s.updatedAt.toISOString(),
      })),
      total: signals.length,
    });
  } catch (error) {
    console.error('Get signal history error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch signal history' },
      { status: 500 }
    );
  }
}
