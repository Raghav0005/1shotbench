// Local web app for browsing Anserini's prebuilt Lucene inverted indexes
// and running reproducible retrieval evaluations. The catalog is
// discovered by calling Anserini's `PrebuiltIndexRegistry` and
// `TopicsRegistry` CLIs, the qrels set is read straight out of
// `io.anserini.eval.Qrels` via `javap`, and the run/evaluate flow
// invokes Anserini's `SearchCollection` and `TrecEval` mains underneath.

const path = require('path');
const fs = require('fs');
const express = require('express');

const {
  listInvertedIndexes,
  listTopics,
  jarPath,
  runJava,
} = require('./lib/registry');
const { listKnownQrels } = require('./lib/qrels');
const {
  KNOWN_PAIRINGS,
  reconcileWithRegistries,
  findPairing,
} = require('./lib/datasets');
const { METRICS, DEFAULT_METRICS, metricHelp, metricFlag } = require('./lib/metrics');
const { runEvaluation } = require('./lib/runner');

const PORT = Number(process.env.PORT || 8080);
const HOST = process.env.HOST || '127.0.0.1';
const RUNS_DIR = path.join(__dirname, 'data', 'runs');
const EVALS_DIR = path.join(__dirname, 'data', 'evals');
fs.mkdirSync(RUNS_DIR, { recursive: true });
fs.mkdirSync(EVALS_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Cache the Anserini registry data for the life of the process. The
// registries don't change while the server is running, so re-querying
// on every request would be wasteful (each call spawns a JVM).
let catalogCache = null;
let catalogCacheError = null;

async function loadCatalog() {
  if (catalogCache) return catalogCache;
  if (catalogCacheError) throw catalogCacheError;
  try {
    const [indexes, topics, qrels] = await Promise.all([
      listInvertedIndexes(),
      listTopics(),
      Promise.resolve(listKnownQrels()),
    ]);
    const pairings = reconcileWithRegistries(
      KNOWN_PAIRINGS,
      topics,
      qrels,
      indexes.map((i) => i.name)
    );
    catalogCache = { indexes, topics, qrels: Array.from(qrels), pairings };
    return catalogCache;
  } catch (err) {
    catalogCacheError = err;
    throw err;
  }
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    anseriniJar: jarPath(),
    runsDir: RUNS_DIR,
    evalsDir: EVALS_DIR,
  });
});

app.get('/api/catalog', async (_req, res) => {
  try {
    const catalog = await loadCatalog();
    res.json({
      indexes: catalog.indexes.map((idx) => ({
        name: idx.name,
        type: idx.type,
        description: idx.description || '',
        filename: idx.filename || '',
        corpusIndex: idx.corpus_index || null,
        evaluable: findPairing(idx.name) !== null,
      })),
      topics: catalog.topics,
      qrels: catalog.qrels,
      pairings: catalog.pairings,
      metrics: Object.entries(METRICS).map(([key, v]) => ({
        label: v.label,
        key,
        flag: v.flag,
        help: v.help,
      })),
      defaults: {
        index: 'cacm',
        topic: 'cacm',
        metric: 'nDCG@10',
      },
    });
  } catch (err) {
    res.status(500).json({
      error: 'Failed to load Anserini catalog',
      detail: err.message,
    });
  }
});

app.get('/api/dataset/:index', async (req, res) => {
  try {
    const catalog = await loadCatalog();
    const pairing = catalog.pairings.find((p) => p.index === req.params.index);
    if (!pairing) {
      res.status(404).json({
        error: `No evaluable pairing for index "${req.params.index}"`,
      });
      return;
    }
    res.json({
      ...pairing,
      metrics: pairing.metrics.map((label) => ({
        label,
        key: label,
        flag: metricFlag(label),
        help: metricHelp(label),
      })),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/run', async (req, res) => {
  const { index, topics, metric } = req.body || {};
  if (!index || !topics || !metric) {
    res.status(400).json({
      error: 'Missing required fields: index, topics, metric',
    });
    return;
  }
  let catalog;
  try {
    catalog = await loadCatalog();
  } catch (err) {
    res.status(500).json({ error: 'Failed to load catalog', detail: err.message });
    return;
  }
  const pairing = catalog.pairings.find((p) => p.index === index);
  if (!pairing) {
    res.status(400).json({
      error: `Index "${index}" is not in the known evaluable pairings list.`,
    });
    return;
  }
  if (!pairing.topics.includes(topics)) {
    res.status(400).json({
      error: `Topics "${topics}" are not in the supported topic set for index "${index}".`,
      supportedTopics: pairing.topics,
    });
    return;
  }
  if (!pairing.metrics.includes(metric)) {
    res.status(400).json({
      error: `Metric "${metric}" is not in the supported metric set for index "${index}".`,
      supportedMetrics: pairing.metrics,
    });
    return;
  }
  try {
    const startedAt = Date.now();
    const result = await runEvaluation({
      index,
      topics,
      qrels: pairing.qrels,
      metric,
      runsDir: RUNS_DIR,
      evalsDir: EVALS_DIR,
    });
    res.json({
      ok: true,
      index,
      topics,
      qrels: pairing.qrels,
      metric,
      score: result.score,
      scoreMeasure: result.scoreMeasure,
      runFile: result.runFile,
      runFileBytes: result.runFileBytes,
      runPreview: result.runPreview,
      evalFile: result.evalFile,
      evalOutput: result.evalOutput,
      metrics: result.metrics,
      commands: result.commands,
      durationMs: Date.now() - startedAt,
    });
  } catch (err) {
    const phase = err.phase || 'evaluation';
    res.status(500).json({
      ok: false,
      phase,
      error: err.message,
      stdout: err.stdout || null,
      stderr: err.stderr || null,
    });
  }
});

// Convenience for the E2E test: spawn a tiny SearchCollection run in
// advance so the test doesn't have to time the CACM download on its
// own. Returns 200 once the run finishes, or 500 with the failure.
app.get('/api/prewarm', async (req, res) => {
  const index = req.query.index || 'cacm';
  const topics = req.query.topics || 'cacm';
  try {
    // The CACM prebuilt index lives in the user's local cache. Running
    // SearchCollection once downloads it on first use; subsequent calls
    // are essentially free.
    const { code, stdout, stderr } = await runJava([
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', index,
      '-topics', topics,
      '-output', path.join(RUNS_DIR, `prewarm.${index}.${topics}.txt`),
      '-hits', '100',
      '-bm25',
    ]);
    res.json({ ok: code === 0, code, stdout, stderr });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get('/api/run-file', (req, res) => {
  const p = req.query.path;
  if (!p || !p.startsWith(RUNS_DIR)) {
    res.status(400).json({ error: 'Invalid run file path' });
    return;
  }
  if (!fs.existsSync(p)) {
    res.status(404).json({ error: 'Run file not found', path: p });
    return;
  }
  res.set('Content-Type', 'text/plain');
  res.send(fs.readFileSync(p, 'utf8'));
});

app.listen(PORT, HOST, () => {
  // eslint-disable-next-line no-console
  console.log(`Anserini Prebuilt Index Evaluator listening on http://${HOST}:${PORT}`);
  // eslint-disable-next-line no-console
  console.log(`  ANSERINI_JAR=${jarPath()}`);
  // eslint-disable-next-line no-console
  console.log(`  runs dir: ${RUNS_DIR}`);
  // eslint-disable-next-line no-console
  console.log(`  evals dir: ${EVALS_DIR}`);
});
