import fs from 'fs';
import path from 'path';

let cachedQueries = null;

function loadQueries() {
  if (cachedQueries) return cachedQueries;
  const file = path.join(process.cwd(), 'data', 'msmarco-dev-queries.json');
  const raw = fs.readFileSync(file, 'utf8');
  cachedQueries = JSON.parse(raw);
  return cachedQueries;
}

export default function handler(req, res) {
  const n = Math.max(
    1,
    Math.min(20, parseInt(req.query.n || '6', 10) || 6)
  );
  try {
    const all = loadQueries();
    const picks = new Set();
    while (picks.size < Math.min(n, all.length)) {
      picks.add(Math.floor(Math.random() * all.length));
    }
    const samples = Array.from(picks).map((i) => all[i]);
    res.status(200).json({ total: all.length, samples });
  } catch (err) {
    res.status(500).json({
      error: 'Failed to load MS MARCO dev queries.',
      detail: String(err && err.message ? err.message : err),
    });
  }
}
