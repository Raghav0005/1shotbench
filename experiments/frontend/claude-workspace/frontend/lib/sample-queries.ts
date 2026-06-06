import { promises as fs } from "node:fs";
import { config } from "./config";

export type SampleQuery = { id: string; text: string };

let cache: SampleQuery[] | null = null;

async function loadAll(): Promise<SampleQuery[]> {
  if (cache) return cache;
  const raw = await fs.readFile(config.sampleQueriesPath, "utf8");
  const parsed = JSON.parse(raw) as SampleQuery[];
  cache = parsed.filter((q) => q && typeof q.text === "string" && q.text.trim().length > 0);
  return cache;
}

export async function pickRandomSampleQueries(count: number): Promise<SampleQuery[]> {
  const all = await loadAll();
  if (all.length === 0) return [];
  const n = Math.min(count, all.length);
  // Reservoir/Fisher-Yates partial shuffle over a copy of indices.
  const idx = Array.from({ length: all.length }, (_, i) => i);
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(Math.random() * (all.length - i));
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx.slice(0, n).map((i) => all[i]);
}
