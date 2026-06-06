import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL || "http://localhost:8080";

interface AnseriniCandidate {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface AnseriniResponse {
  api: string;
  index: string;
  query: { text: string };
  candidates: AnseriniCandidate[];
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query");
  const hits = searchParams.get("hits") || "10";

  if (!query || query.trim().length === 0) {
    return NextResponse.json(
      { error: "Query must not be empty." },
      { status: 400 }
    );
  }

  const backendUrl = `${BACKEND_URL}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query.trim())}&hits=${encodeURIComponent(hits)}`;

  try {
    const res = await fetch(backendUrl, { signal: AbortSignal.timeout(30000) });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `Backend returned ${res.status}: ${text}` },
        { status: 502 }
      );
    }

    const data: AnseriniResponse = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : "Unknown error connecting to backend";
    return NextResponse.json(
      { error: `Could not connect to Anserini backend. ${message}` },
      { status: 503 }
    );
  }
}
