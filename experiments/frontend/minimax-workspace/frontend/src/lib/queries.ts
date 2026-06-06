import { promises as fs } from "node:fs";
import path from "node:path";

export type DevQuery = {
  id: string;
  text: string;
};

let cachedQueries: DevQuery[] | null = null;

function findQueriesFile(): string {
  // The queries TSV is co-located with the Next.js app (frontend/msmarco-v1-passage.dev.queries.tsv).
  // We look first in CWD, then in the directory above process.cwd() so the app works
  // when started from inside the frontend directory or from the project root.
  const candidates = [
    path.join(process.cwd(), "msmarco-v1-passage.dev.queries.tsv"),
    path.join(process.cwd(), "..", "msmarco-v1-passage.dev.queries.tsv"),
  ];
  for (const candidate of candidates) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      require("node:fs").accessSync(candidate);
      return candidate;
    } catch {
      // try next
    }
  }
  return candidates[0];
}

export async function loadDevQueries(): Promise<DevQuery[]> {
  if (cachedQueries) {
    return cachedQueries;
  }
  const file = findQueriesFile();
  const raw = await fs.readFile(file, "utf8");
  const queries: DevQuery[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!line) continue;
    const tab = line.indexOf("\t");
    if (tab < 0) continue;
    const id = line.slice(0, tab).trim();
    const text = line.slice(tab + 1).trim();
    if (!id || !text) continue;
    queries.push({ id, text });
  }
  cachedQueries = queries;
  return queries;
}
