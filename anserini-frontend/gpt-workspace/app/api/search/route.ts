import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

type AnseriniCandidate = {
  docid?: string;
  score?: number;
  rank?: number;
  doc?: string;
};

type AnseriniSearchResponse = {
  api?: string;
  index?: string;
  query?: { text?: string };
  candidates?: AnseriniCandidate[];
};

function getBackendBaseUrl() {
  if (process.env.ANSERINI_API_URL) {
    return process.env.ANSERINI_API_URL.replace(/\/$/, '');
  }

  const host = process.env.ANSERINI_HOST || 'localhost';
  const port = process.env.ANSERINI_PORT || '8080';
  return `http://${host}:${port}`;
}

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get('q')?.trim() || '';
  const hitsParam = Number(request.nextUrl.searchParams.get('hits') || '10');
  const hits = Number.isFinite(hitsParam) ? Math.min(Math.max(Math.trunc(hitsParam), 1), 50) : 10;
  const index = process.env.ANSERINI_INDEX || 'msmarco-v1-passage';

  if (!query) {
    return NextResponse.json({ error: 'Enter a query to search MS MARCO passages.' }, { status: 400 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  const url = `${getBackendBaseUrl()}/v1/${encodeURIComponent(index)}/search?query=${encodeURIComponent(query)}&hits=${hits}`;

  try {
    const response = await fetch(url, { signal: controller.signal, cache: 'no-store' });
    const bodyText = await response.text();

    if (!response.ok) {
      return NextResponse.json(
        {
          error: `Anserini backend returned HTTP ${response.status}.`,
          detail: bodyText.slice(0, 1000),
        },
        { status: 502 },
      );
    }

    let data: AnseriniSearchResponse;
    try {
      data = JSON.parse(bodyText) as AnseriniSearchResponse;
    } catch {
      return NextResponse.json(
        { error: 'Anserini backend returned a non-JSON response.', detail: bodyText.slice(0, 1000) },
        { status: 502 },
      );
    }

    return NextResponse.json({
      index: data.index || index,
      query: data.query?.text || query,
      candidates: Array.isArray(data.candidates) ? data.candidates : [],
    });
  } catch (error) {
    const message = error instanceof Error && error.name === 'AbortError'
      ? 'Timed out waiting for the Anserini backend.'
      : 'Could not reach the Anserini backend.';

    return NextResponse.json(
      {
        error: message,
        detail: `Expected Anserini REST at ${getBackendBaseUrl()}. Start it with npm run backend.`,
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
