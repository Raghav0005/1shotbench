import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { pickRandomSampleQueries } from "@/lib/sample-queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const countParam = url.searchParams.get("count");
  const count =
    countParam && Number.isFinite(Number(countParam)) && Number(countParam) > 0
      ? Math.min(50, Math.floor(Number(countParam)))
      : config.sampleQueriesCount;

  try {
    const samples = await pickRandomSampleQueries(count);
    return NextResponse.json(
      { samples },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      {
        error: `Failed to load sample queries: ${message}`,
        hint:
          "Generate the dev-queries file with frontend/scripts/fetch-dev-queries.sh, " +
          "or set SAMPLE_QUERIES_PATH to a JSON array of {id, text} objects.",
      },
      { status: 500 },
    );
  }
}
