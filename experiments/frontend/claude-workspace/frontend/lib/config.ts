import path from "node:path";

// Server-side configuration. Everything is overridable via env vars; we never
// pause the app to ask for ports — defaults match the PRD.
export const config = {
  anseriniBaseUrl: (process.env.ANSERINI_BASE_URL ?? "http://localhost:8080").replace(/\/$/, ""),
  anseriniIndex: process.env.ANSERINI_INDEX ?? "msmarco-v1-passage",
  sampleQueriesPath:
    process.env.SAMPLE_QUERIES_PATH ??
    path.join(process.cwd(), "data", "msmarco-passage-dev-queries.json"),
  sampleQueriesCount: Number.parseInt(process.env.SAMPLE_QUERIES_COUNT ?? "6", 10) || 6,
  defaultHits: Number.parseInt(process.env.SEARCH_HITS ?? "10", 10) || 10,
};
