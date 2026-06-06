import { NextResponse } from 'next/server';
import { getBackendBaseUrl, INDEX_NAME, normalizeCandidate } from '../../../lib/anserini.js';

export const dynamic = 'force-dynamic';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const query = (searchParams.get('q') || searchParams.get('query') || '').trim();
  const hitsParam = Number(searchParams.get('hits') || '10');
  const hits = Number.isFinite(hitsParam) ? Math.min(Math.max(Math.floor(hitsParam), 1), 50) : 10;

  if (!query) {
    return NextResponse.json(
      { error: 'Enter a search query before searching.', results: [] },
      { status: 400 },
    );
  }

  const backendUrl = `${getBackendBaseUrl()}/v1/${encodeURIComponent(INDEX_NAME)}/search?query=${encodeURIComponent(query)}&hits=${hits}`;

  try {
    const response = await fetch(backendUrl, { cache: 'no-store' });
    const text = await response.text();

    if (!response.ok) {
      return NextResponse.json(
        {
          error: `Anserini backend returned HTTP ${response.status}.`,
          detail: text.slice(0, 1000),
          results: [],
        },
        { status: 502 },
      );
    }

    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      return NextResponse.json(
        { error: 'Anserini backend returned a non-JSON response.', detail: text.slice(0, 1000), results: [] },
        { status: 502 },
      );
    }

    const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
    const results = candidates.map((candidate, index) => normalizeCandidate(candidate, index + 1));

    return NextResponse.json({
      query,
      index: payload.index || INDEX_NAME,
      results,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: 'Could not reach the Anserini REST API backend.',
        detail: error instanceof Error ? error.message : String(error),
        hint: `Start it with: ANSERINI_BACKEND_PORT=${process.env.ANSERINI_BACKEND_PORT || '8080'} npm run backend`,
        results: [],
      },
      { status: 502 },
    );
  }
}
