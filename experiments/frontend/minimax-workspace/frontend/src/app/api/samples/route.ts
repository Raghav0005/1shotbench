import { NextRequest, NextResponse } from "next/server";
import { loadDevQueries } from "@/lib/queries";

export const dynamic = "force-dynamic";

function sampleWithoutReplacement<T>(arr: T[], n: number): T[] {
  const copy = arr.slice();
  const out: T[] = [];
  const count = Math.min(n, copy.length);
  for (let i = 0; i < count; i++) {
    const idx = Math.floor(Math.random() * (copy.length - i));
    out.push(copy[idx]);
    // Swap chosen element to the end so we don't pick it again.
    const last = copy.length - i - 1;
    [copy[idx], copy[last]] = [copy[last], copy[idx]];
  }
  return out;
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const countParam = url.searchParams.get("count");
  let count = Number.parseInt(countParam ?? "5", 10);
  if (!Number.isFinite(count) || count < 1) count = 5;
  if (count > 50) count = 50;

  try {
    const queries = await loadDevQueries();
    if (queries.length === 0) {
      return NextResponse.json(
        { error: "Dev queries file is empty or missing." },
        { status: 500 },
      );
    }
    const samples = sampleWithoutReplacement(queries, count);
    return NextResponse.json({ samples });
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to load dev queries: " + (err as Error).message },
      { status: 500 },
    );
  }
}
