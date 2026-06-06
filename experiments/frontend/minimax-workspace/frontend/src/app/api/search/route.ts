import { NextRequest, NextResponse } from "next/server";
import { getAnseriniConfig } from "@/lib/anserini";

export const dynamic = "force-dynamic";

type AnseriniSearchResponse = {
  api?: string;
  index?: string;
  query?: { text?: string };
  candidates?: Array<{
    docid: string;
    score: number;
    rank: number;
    doc: string;
  }>;
  error?: string;
};

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const query = (url.searchParams.get("query") ?? "").trim();
  const hitsParam = url.searchParams.get("hits");
  let hits = Number.parseInt(hitsParam ?? "10", 10);
  if (!Number.isFinite(hits) || hits < 1) hits = 10;
  if (hits > 100) hits = 100;

  if (!query) {
    return NextResponse.json(
      { error: "Query is required." },
      { status: 400 },
    );
  }

  const { baseUrl, index } = getAnseriniConfig();
  const upstream = new URL(`${baseUrl}/v1/${index}/search`);
  upstream.searchParams.set("query", query);
  upstream.searchParams.set("hits", String(hits));

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      // The Anserini REST server does not currently support caching of search
      // results, so revalidate on every call.
      cache: "no-store",
    });
  } catch (err) {
    return NextResponse.json(
      {
        error:
          "Could not reach the Anserini REST backend at " +
          baseUrl +
          ". Is the server running? (" +
          (err as Error).message +
          ")",
      },
      { status: 502 },
    );
  }

  const text = await upstreamRes.text();
  let parsed: AnseriniSearchResponse = {};
  try {
    parsed = text.length > 0 ? (JSON.parse(text) as AnseriniSearchResponse) : {};
  } catch {
    return NextResponse.json(
      {
        error:
          "Anserini returned a non-JSON response (HTTP " +
          upstreamRes.status +
          ").",
      },
      { status: 502 },
    );
  }

  if (!upstreamRes.ok) {
    return NextResponse.json(
      {
        error: parsed.error ?? `Anserini returned HTTP ${upstreamRes.status}.`,
      },
      { status: upstreamRes.status },
    );
  }

  return NextResponse.json({
    query,
    index,
    backend: baseUrl,
    candidates: parsed.candidates ?? [],
  });
}
