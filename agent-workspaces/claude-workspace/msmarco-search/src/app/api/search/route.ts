import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.ANSERINI_BACKEND_URL ??
  `http://localhost:${process.env.ANSERINI_BACKEND_PORT ?? "8080"}`;

const INDEX = "msmarco-v1-passage";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query")?.trim() ?? "";
  const hits = parseInt(searchParams.get("hits") ?? "10", 10);

  if (!query) {
    return NextResponse.json(
      { error: "Query parameter is required." },
      { status: 400 }
    );
  }

  const backendUrl = `${BACKEND_URL}/v1/${INDEX}/search?query=${encodeURIComponent(
    query
  )}&hits=${hits}`;

  try {
    const res = await fetch(backendUrl, {
      signal: AbortSignal.timeout(30_000),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        {
          error: `Backend returned HTTP ${res.status}.`,
          detail: text,
        },
        { status: 502 }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : "Unknown error contacting backend.";
    return NextResponse.json(
      {
        error: "Could not reach the Anserini backend.",
        detail: message,
        backendUrl,
      },
      { status: 503 }
    );
  }
}
