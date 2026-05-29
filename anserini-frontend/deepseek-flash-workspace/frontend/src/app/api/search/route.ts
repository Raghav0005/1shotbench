import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.ANSERINI_API_URL ?? "http://localhost:8080";
const INDEX_NAME = "msmarco-v1-passage";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("query");
  const hits = request.nextUrl.searchParams.get("hits") ?? "10";

  if (!query || !query.trim()) {
    return NextResponse.json({ error: "query parameter is required" }, { status: 400 });
  }

  const backendUrl = `${API_BASE}/v1/${INDEX_NAME}/search?query=${encodeURIComponent(query.trim())}&hits=${hits}`;

  try {
    const res = await fetch(backendUrl);

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `Backend returned ${res.status}`, details: body },
        { status: res.status },
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to reach backend";
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
