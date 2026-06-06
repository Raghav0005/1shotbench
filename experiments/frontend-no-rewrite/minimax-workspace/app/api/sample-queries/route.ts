import { NextResponse } from "next/server";
import { pickRandomDevQueries } from "@/lib/queries";

export const dynamic = "force-dynamic";

const DEFAULT_COUNT = 5;
const MAX_COUNT = 20;

/**
 * GET /api/sample-queries?count=N[&seed=S]
 *
 * Returns up to N (default 5, max 20) MS MARCO V1 passage dev queries chosen
 * uniformly at random. `seed` is optional and is mostly useful for tests.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rawCount = searchParams.get("count");
  const rawSeed = searchParams.get("seed");

  let count = DEFAULT_COUNT;
  if (rawCount !== null) {
    const parsed = Number.parseInt(rawCount, 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      count = Math.min(parsed, MAX_COUNT);
    }
  }

  let seed: number | undefined;
  if (rawSeed !== null) {
    const parsed = Number.parseInt(rawSeed, 10);
    if (Number.isFinite(parsed)) seed = parsed;
  }

  try {
    const queries = await pickRandomDevQueries(count, seed);
    return NextResponse.json({ queries });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to load sample queries.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
