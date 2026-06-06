export const INDEX_NAME = process.env.ANSERINI_INDEX || 'msmarco-v1-passage';

export function getBackendBaseUrl() {
  if (process.env.ANSERINI_BACKEND_URL) {
    return process.env.ANSERINI_BACKEND_URL.replace(/\/$/, '');
  }

  const port = process.env.ANSERINI_BACKEND_PORT || '8080';
  return `http://localhost:${port}`;
}

export function normalizeCandidate(candidate, fallbackRank) {
  const rank = Number(candidate.rank ?? fallbackRank);
  const score = Number(candidate.score ?? 0);
  const rawDoc = String(candidate.doc ?? '');

  return {
    docid: String(candidate.docid ?? ''),
    rank: Number.isFinite(rank) ? rank : fallbackRank,
    score: Number.isFinite(score) ? score : 0,
    passage: extractPassage(rawDoc),
    raw: rawDoc,
  };
}

export function extractPassage(rawDoc) {
  if (!rawDoc) return '';

  const trimmed = rawDoc.trim();
  try {
    const parsed = JSON.parse(trimmed);
    const value = parsed.contents ?? parsed.content ?? parsed.text ?? parsed.body ?? parsed.raw;
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  } catch {
    // Anserini indexes do not all store raw documents as JSON.
  }

  return trimmed
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}
