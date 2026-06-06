import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { AnseriniError, searchAnserini } from "@/lib/anserini";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const query = (url.searchParams.get("q") ?? "").trim();
  const hitsParam = url.searchParams.get("hits");
  const hits =
    hitsParam && Number.isFinite(Number(hitsParam)) && Number(hitsParam) > 0
      ? Math.min(100, Math.floor(Number(hitsParam)))
      : config.defaultHits;

  if (!query) {
    return NextResponse.json(
      { error: "Query must not be empty." },
      { status: 400 },
    );
  }

  try {
    const data = await searchAnserini(query, hits);
    return NextResponse.json(
      {
        index: data.index,
        query: data.query.text,
        results: data.candidates.map((c) => ({
          rank: c.rank,
          docid: c.docid,
          score: c.score,
          text: c.doc,
        })),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    if (err instanceof AnseriniError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Unexpected error: ${message}` }, { status: 500 });
  }
}
