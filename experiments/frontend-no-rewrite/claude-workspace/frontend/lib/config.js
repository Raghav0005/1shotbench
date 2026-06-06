// Server-side configuration. Values come from environment variables with
// sensible defaults that match the PRD (backend on :8080, MS MARCO passage).
export const ANSERINI_BASE_URL =
  process.env.ANSERINI_BASE_URL || 'http://localhost:8080';
export const ANSERINI_INDEX =
  process.env.ANSERINI_INDEX || 'msmarco-v1-passage';
export const DEFAULT_HITS = parseInt(process.env.ANSERINI_HITS || '10', 10);
