import { NextRequest, NextResponse } from "next/server";

const ANSERINI_BASE_URL =
  process.env.ANSERINI_URL || "http://localhost:8080";
const DEFAULT_HITS = parseInt(process.env.SEARCH_HITS || "10", 10);

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const query = searchParams.get("query")?.trim();
  const hits = parseInt(searchParams.get("hits") || String(DEFAULT_HITS), 10);

  if (!query) {
    return NextResponse.json(
      { error: "Query parameter is required" },
      { status: 400 }
    );
  }

  try {
    const url = `${ANSERINI_BASE_URL}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query)}&hits=${hits}`;
    const res = await fetch(url, { cache: "no-store" });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Anserini returned status ${res.status}` },
        { status: 502 }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error("Anserini proxy error:", err);
    return NextResponse.json(
      { error: "Failed to reach Anserini backend. Is the REST server running?" },
      { status: 502 }
    );
  }
}
