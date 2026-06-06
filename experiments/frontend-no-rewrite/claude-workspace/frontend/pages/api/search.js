import { ANSERINI_BASE_URL, ANSERINI_INDEX, DEFAULT_HITS } from '../../lib/config';

// Proxy to the Anserini REST API:
//   GET /v1/{index}/search?query=...&hits=N
// Response shape (see anserini-cli skill):
//   { api, index, query: { text }, candidates: [ { docid, score, rank, doc } ] }
export default async function handler(req, res) {
  const rawQuery = (req.query.q || '').toString().trim();
  const hits = parseInt(req.query.hits || `${DEFAULT_HITS}`, 10) || DEFAULT_HITS;

  if (!rawQuery) {
    return res.status(400).json({ error: 'Empty query.' });
  }

  const url =
    `${ANSERINI_BASE_URL}/v1/${encodeURIComponent(ANSERINI_INDEX)}/search` +
    `?query=${encodeURIComponent(rawQuery)}&hits=${hits}`;

  try {
    const upstream = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });

    if (!upstream.ok) {
      const text = await upstream.text().catch(() => '');
      return res.status(502).json({
        error: `Anserini backend returned ${upstream.status} ${upstream.statusText}`,
        detail: text.slice(0, 500),
      });
    }

    const data = await upstream.json();
    return res.status(200).json({
      index: data.index || ANSERINI_INDEX,
      query: rawQuery,
      hits,
      candidates: Array.isArray(data.candidates) ? data.candidates : [],
    });
  } catch (err) {
    return res.status(502).json({
      error: 'Could not reach Anserini backend.',
      detail: String(err && err.message ? err.message : err),
      backend: ANSERINI_BASE_URL,
    });
  }
}
