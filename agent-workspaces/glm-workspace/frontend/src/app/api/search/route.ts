import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.ANSERINI_BACKEND_URL || "http://localhost:8080";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query");
  const hits = searchParams.get("hits") || "10";

  if (!query || query.trim() === "") {
    return NextResponse.json(
      { error: "Query parameter is required and must not be empty." },
      { status: 400 }
    );
  }

  const url = `${BACKEND_URL}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query)}&hits=${hits}`;

  try {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        {
          error: `Backend returned ${res.status}: ${text}`,
        },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : "Unknown backend error";
    return NextResponse.json(
      { error: `Failed to connect to Anserini backend: ${message}` },
      { status: 502 }
    );
  }
}
