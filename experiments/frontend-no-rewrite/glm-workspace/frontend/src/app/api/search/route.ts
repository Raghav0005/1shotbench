import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.ANSERINI_BACKEND_URL || "http://localhost:8080";
const INDEX_NAME = "msmarco-v1-passage";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query");
  const hits = searchParams.get("hits") || "10";

  if (!query || query.trim() === "") {
    return NextResponse.json(
      { error: "Query parameter is required and cannot be empty." },
      { status: 400 }
    );
  }

  try {
    const url = `${BACKEND_URL}/v1/${INDEX_NAME}/search?query=${encodeURIComponent(query)}&hits=${hits}`;
    const response = await fetch(url, {
      signal: AbortSignal.timeout(30_000),
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${text}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : "Unknown error occurred";
    return NextResponse.json(
      { error: `Failed to connect to search backend: ${message}` },
      { status: 502 }
    );
  }
}
