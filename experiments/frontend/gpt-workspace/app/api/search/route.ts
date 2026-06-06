import { NextResponse } from 'next/server';

type AnseriniCandidate = {
  docid?: string;
  score?: number;
  rank?: number;
  doc?: string;
  [key: string]: unknown;
};

type AnseriniSearchResponse = {
  candidates?: AnseriniCandidate[];
  [key: string]: unknown;
};

export const dynamic = 'force-dynamic';

function getBackendBaseUrl() {
  if (process.env.ANSERINI_API_BASE_URL) {
    return process.env.ANSERINI_API_BASE_URL.replace(/\/$/, '');
  }

  const backendPort = process.env.BACKEND_PORT ?? process.env.ANSERINI_PORT ?? '8080';
  return `http://localhost:${backendPort}`;
}

function getHits(value: string | null) {
  const parsed = Number(value ?? process.env.DEFAULT_HITS ?? '10');
  if (!Number.isFinite(parsed)) return 10;
  return Math.min(Math.max(Math.trunc(parsed), 1), 50);
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = (searchParams.get('q') ?? '').trim();

  if (!query) {
    return NextResponse.json({ error: 'Enter a query before searching.' }, { status: 400 });
  }

  const hits = getHits(searchParams.get('hits'));
  const index = process.env.ANSERINI_INDEX ?? 'msmarco-v1-passage';
  const url = new URL(`/v1/${encodeURIComponent(index)}/search`, getBackendBaseUrl());
  url.searchParams.set('query', query);
  url.searchParams.set('hits', String(hits));

  try {
    const response = await fetch(url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(60_000),
    });

    const text = await response.text();
    let payload: AnseriniSearchResponse | { error: string };
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { error: text || 'The Anserini backend returned a non-JSON response.' };
    }

    if (!response.ok) {
      return NextResponse.json(
        {
          error: 'The Anserini backend could not complete the search.',
          details: payload,
        },
        { status: 502 },
      );
    }

    const candidates = Array.isArray((payload as AnseriniSearchResponse).candidates)
      ? (payload as AnseriniSearchResponse).candidates
      : [];

    return NextResponse.json({ query, index, hits, candidates }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown backend error';
    return NextResponse.json(
      {
        error: 'Unable to reach the Anserini REST API backend.',
        details: message,
        backend: getBackendBaseUrl(),
      },
      { status: 502 },
    );
  }
}
