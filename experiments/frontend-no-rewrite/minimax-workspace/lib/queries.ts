import { promises as fs } from "node:fs";
import path from "node:path";

export type DevQuery = {
  id: string;
  text: string;
};

// The Anserini TopicsRegistry emits a JSON object of the form
// { "<qid>": { "title": "<query text>", ... }, ... } for msmarco-v1-passage.dev.
// See $anserini-cli for the registry/CLI examples and $install-anserini-fatjar
// for the TopicsRegistry data we exported during setup.
type DevQueryFile = Record<string, { title?: string } & Record<string, unknown>>;

let cached: DevQuery[] | null = null;

/**
 * Load every MS MARCO V1 passage dev query from the JSON file produced by
 * `io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev`.
 */
export async function loadAllDevQueries(): Promise<DevQuery[]> {
  if (cached) return cached;

  const filePath = path.join(process.cwd(), "data", "msmarco-v1-passage.dev.json");
  const raw = await fs.readFile(filePath, "utf8");
  const parsed = JSON.parse(raw) as DevQueryFile;

  const all: DevQuery[] = [];
  for (const [id, value] of Object.entries(parsed)) {
    if (!value || typeof value.title !== "string") continue;
    const text = value.title.trim();
    if (!text) continue;
    all.push({ id, text });
  }

  if (all.length === 0) {
    throw new Error(
      `No dev queries found in ${filePath}. ` +
        "Re-export the topics via `java -cp $ANSERINI_JAR io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev > data/msmarco-v1-passage.dev.json`.",
    );
  }

  cached = all;
  return all;
}

/**
 * Return `count` unique dev queries drawn uniformly at random, with a stable
 * seed so the server picks one set per request without bias.
 */
export async function pickRandomDevQueries(count: number, seed?: number): Promise<DevQuery[]> {
  const all = await loadAllDevQueries();
  const n = Math.max(0, Math.min(count, all.length));
  if (n === 0) return [];

  // Mulberry32: tiny, deterministic PRNG. Seedable when needed for reproducible tests.
  const makeRng = (s: number) => {
    let a = s >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  const rng = makeRng(seed ?? Math.floor(Math.random() * 2 ** 31));

  // Fisher-Yates partial shuffle for a uniform sample without replacement.
  const indices = all.map((_, i) => i);
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(rng() * (indices.length - i));
    const tmp = indices[i];
    indices[i] = indices[j];
    indices[j] = tmp;
  }
  return indices.slice(0, n).map((i) => all[i]);
}

/**
 * Build the base URL used by the Next.js API routes to reach the Anserini
 * REST server. Defaults to http://localhost:8080, matching the PRD.
 */
export function getBackendBaseUrl(): string {
  const host = process.env.BACKEND_HOST || "localhost";
  const port = process.env.BACKEND_PORT || "8080";
  return `http://${host}:${port}`;
}
