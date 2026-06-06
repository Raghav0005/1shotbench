import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.API_URL || "http://localhost:8080";
const INDEX_NAME = "msmarco-v1-passage";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query");
  const hits = searchParams.get("hits") || "10";

  if (!query || !query.trim()) {
    return NextResponse.json(
      { error: "Query parameter is required" },
      { status: 400 }
    );
  }

  const backendUrl = `${BACKEND_URL}/v1/${INDEX_NAME}/search?query=${encodeURIComponent(
    query.trim()
  )}&hits=${encodeURIComponent(hits)}`;

  try {
    const res = await fetch(backendUrl);
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data.message || "Backend error" },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to connect to search backend" },
      { status: 502 }
    );
  }
}
