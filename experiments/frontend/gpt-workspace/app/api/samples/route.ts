import { NextResponse } from 'next/server';
import queries from '@/src/data/msmarco-passage-dev-queries.json';

type DevQuery = {
  id: string;
  query: string;
};

export const dynamic = 'force-dynamic';

function randomSamples<T>(items: T[], count: number): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, count);
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const requestedCount = Number(searchParams.get('count') ?? '6');
  const count = Number.isFinite(requestedCount)
    ? Math.min(Math.max(Math.trunc(requestedCount), 1), 12)
    : 6;

  return NextResponse.json(
    { samples: randomSamples(queries as DevQuery[], count) },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
