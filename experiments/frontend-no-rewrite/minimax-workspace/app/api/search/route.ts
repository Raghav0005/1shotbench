import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/queries";

export const dynamic = "force-dynamic";

const DEFAULT_INDEX = "msmarco-v1-passage";
const DEFAULT_HITS = 10;
const MAX_HITS = 100;

/**
 * GET /api/search?query=...&hits=N[&index=msmarco-v1-passage]
 *
 * Proxies the request to the Anserini REST server (e.g.
 * `GET /v1/{index}/search?query=...&hits=N`) and returns its JSON response.
 *
 * The shape returned by Anserini is documented in $anserini-cli and looks like:
 *   { api, index, query: { text }, candidates: [{ docid, score, rank, doc }] }
 * On error Anserini returns `{ "error": "..." }`; we surface that to the client.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = (searchParams.get("query") ?? "").trim();
  const index = (searchParams.get("index") ?? DEFAULT_INDEX).trim() || DEFAULT_INDEX;

  if (!query) {
    return NextResponse.json(
      { error: "Query is required. Type a query or pick a sample." },
      { status: 400 },
    );
  }

  const rawHits = searchParams.get("hits");
  let hits = DEFAULT_HITS;
  if (rawHits !== null) {
    const parsed = Number.parseInt(rawHits, 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      hits = Math.min(parsed, MAX_HITS);
    }
  }

  const base = getBackendBaseUrl();
  const upstream = new URL(`${base}/v1/${encodeURIComponent(index)}/search`);
  upstream.searchParams.set("query", query);
  upstream.searchParams.set("hits", String(hits));

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream.toString(), {
      method: "GET",
      // Don't keep the Anserini index resident longer than the request.
      cache: "no-store",
    });
  } catch (err) {
    const message =
      err instanceof Error
        ? `Could not reach Anserini backend at ${base}: ${err.message}`
        : `Could not reach Anserini backend at ${base}.`;
    return NextResponse.json({ error: message }, { status: 502 });
  }

  // Pass through Anserini's JSON body verbatim so the client can render
  // `candidates` directly. Translate non-OK upstream statuses into 502/504.
  const body = await upstreamRes.text();
  let parsed: unknown = null;
  try {
    parsed = body ? JSON.parse(body) : null;
  } catch {
    parsed = { error: `Anserini backend returned a non-JSON response (status ${upstreamRes.status}).` };
  }

  if (!upstreamRes.ok) {
    const status = upstreamRes.status === 404 ? 404 : 502;
    return NextResponse.json(parsed ?? { error: "Anserini backend error" }, { status });
  }

  return NextResponse.json(parsed);
}
