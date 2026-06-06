import { NextRequest, NextResponse } from 'next/server';

const ANSERINI_PORT = process.env.ANSERINI_PORT || '8080';
const ANSERINI_BASE_URL = `http://localhost:${ANSERINI_PORT}`;

interface AnseriniCandidate {
  docid: string;
  score: number;
  doc: string;
}

interface AnseriniResponse {
  query: {
    text: string;
  };
  candidates: AnseriniCandidate[];
}

interface SearchResult {
  docid: string;
  score: number;
  doc: string;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('query');
  const hits = searchParams.get('hits') || '10';

  if (!query) {
    return NextResponse.json(
      { error: 'Query parameter is required' },
      { status: 400 }
    );
  }

  try {
    const encodedQuery = encodeURIComponent(query);
    const response = await fetch(
      `${ANSERINI_BASE_URL}/v1/msmarco-v1-passage/search?query=${encodedQuery}&hits=${hits}`
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Anserini server error: ${errorText}` },
        { status: response.status }
      );
    }

    const data: AnseriniResponse = await response.json();

    const results: SearchResult[] = data.candidates.map((candidate) => ({
      docid: candidate.docid,
      score: candidate.score,
      doc: candidate.doc,
    }));

    return NextResponse.json({ query: data.query.text, results });
  } catch (error) {
    console.error('Search error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to Anserini server. Please ensure the backend is running.' },
      { status: 503 }
    );
  }
}
